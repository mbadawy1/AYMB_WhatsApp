"""Media resolver skeleton for M2.

Provides class surface and configuration placeholders; scoring/resolution
logic is implemented in later milestones.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from src.indexer.media_index import FileInfo, _parse_seq_num, _scan_media
from src.resolvers.scoring import _score_ext, _score_mtime, _score_seq
from src.schema.message import Message, StatusReason
from src.utils.hashing import sha256_file
from src.utils.dates import parse_ts
from src.writers.exceptions_csv import write_exceptions


@dataclass
class ResolverConfig:
    """Configuration knobs for media resolution."""

    ext_priority: tuple[str, ...] = ("voice", "image", "video", "document", "other")
    hint_window: int = 2
    ladder_weights: tuple[float, float, float, float] = (3.0, 2.0, 1.0, 1.0)
    decisive_tau: float = 0.75
    tie_margin: float = 0.02
    clock_drift_hours: float = 4.0
    allowed_extensions: Optional[Iterable[str]] = None
    unresolved_policy: str = "keep"  # placeholder for future use


class MediaResolver:
    """Resolve media placeholders to actual files."""

    def __init__(
        self,
        root: Path,
        ext_priority: tuple[str, ...] = ("voice", "image", "video", "document", "other"),
        cfg: Optional[ResolverConfig] = None,
    ) -> None:
        self.root = Path(root)
        self.ext_priority = ext_priority
        self.cfg = cfg or self._load_config()
        if self.cfg.ext_priority != ext_priority:
            self.cfg.ext_priority = ext_priority
        self._exceptions: list[dict] = []

    def map_media(self, msgs: list[Message]) -> None:
        """Map media to filenames using scoring ladder."""
        index = _scan_media(self.root)

        for i, msg in enumerate(msgs):
            # Filename fast path: exact filename in media_hint
            fastpath = self._fastpath_filename(msg)
            if fastpath:
                msg.media_filename = str(fastpath)
                msg.status_reason = None
                msg.derived["media_sha256"] = sha256_file(fastpath)
                continue

            media_type = self._kind_to_type(msg.kind)
            ts_dt = datetime.fromisoformat(msg.ts)
            drift_seconds = self.cfg.clock_drift_hours * 3600
            # Collect candidates within drift window on mtime
            candidates = [
                fi
                for (date_key, typ), infos in index.items()
                if typ == media_type
                for fi in infos
                if abs(fi.mtime - ts_dt.timestamp()) <= drift_seconds
            ]

            if not candidates:
                msg.status_reason = StatusReason.from_code("unresolved_media")
                self._log_exception(msg, "unresolved_media", [])
                continue

            hints = self._extract_hints(msgs, i)
            target_seq = self._extract_seq_target(msg, hints)
            ranked = self._rank_candidates(msg, candidates, hints, target_seq)

            if not ranked:
                msg.status_reason = StatusReason.from_code("unresolved_media")
                self._log_exception(msg, "unresolved_media", [])
                continue

            top_score = ranked[0][1]
            second_score = ranked[1][1] if len(ranked) > 1 else None

            if second_score is not None and (top_score - second_score) < self.cfg.decisive_tau:
                msg.status_reason = StatusReason.from_code("ambiguous_media")
                msg.derived["disambiguation"] = {
                    "candidates": [
                        {
                            "path": str(p),
                            "score": s,
                            "sha256": meta.get("sha256"),
                            "seq_num": meta.get("seq_num"),
                        }
                        for p, s, meta in ranked[:2]
                    ],
                    "top_score": top_score,
                    "tie_margin": top_score - second_score,
                }
                self._log_exception(msg, "ambiguous_media", ranked[:2])
                continue

            msg.media_filename = str(ranked[0][0])
            msg.status_reason = None
            msg.derived["media_sha256"] = ranked[0][2].get("sha256")

        write_exceptions(self._exceptions)

    def _rank_candidates(
        self, msg: Message, day_files: list[FileInfo], hints: set[str], target_seq: Optional[int]
    ) -> list[tuple[Path, float, dict]]:
        """Rank candidate media files for a message."""
        weights = self.cfg.ladder_weights  # hint, ext, seq, mtime
        ts = datetime.fromisoformat(msg.ts)
        ranked: list[tuple[Path, float, dict]] = []

        for info in day_files:
            hint_score = 1.0 if hints and hints.intersection(info.name_tokens) else 0.0
            ext_score = _score_ext(self._kind_to_type(msg.kind), self.cfg.ext_priority)
            seq_score = _score_seq(target_seq, info.seq_num)
            mtime_score = _score_mtime(abs(info.mtime - ts.timestamp()))
            if target_seq is not None and info.seq_num == target_seq:
                seq_score += self.cfg.tie_margin  # small bump to break ties toward exact seq

            total = (
                weights[0] * hint_score
                + weights[1] * ext_score
                + weights[2] * seq_score
                + weights[3] * mtime_score
            )
            ranked.append(
                (
                    info.path,
                    total,
                    {
                        "hint": hint_score,
                        "ext": ext_score,
                        "seq": seq_score,
                        "mtime": mtime_score,
                        "total": total,
                        "sha256": info.sha256,
                        "seq_num": info.seq_num,
                    },
                )
            )

        ranked.sort(key=lambda item: (-item[1], Path(item[0]).stat().st_size, str(item[0])))
        return ranked

    def _extract_hints(self, msgs: list[Message], i: int) -> set[str]:
        """Extract filename-ish hints from ±hint_window surrounding messages.

        Prefers hints from the same sender; falls back to any surrounding messages.
        """
        window = self.cfg.hint_window
        target_sender = msgs[i].sender

        def tokenize(text: str) -> set[str]:
            import re

            lower = text.lower()
            tokens: set[str] = set()
            # WhatsApp filename patterns IMG/VID/PTT/AUD/DOC-YYYYMMDD-WA####
            for match in re.findall(r"(?:img|vid|ptt|aud|doc)-\d{8}-wa\d+", lower):
                tokens.add(match)
            for match in re.findall(r"(?:wa[-_]?\d+)", lower):
                tokens.add(match)
            for match in re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)+", lower):
                tokens.add(match)
            return tokens

        same_sender_tokens: set[str] = set()
        global_tokens: set[str] = set()

        # Include target message tokens as highest-priority hints
        for candidate in (msgs[i].content_text, msgs[i].caption or ""):
            if candidate:
                same_sender_tokens.update(tokenize(candidate))

        start = max(0, i - window)
        end = min(len(msgs), i + window + 1)
        for idx in range(start, end):
            if idx == i:
                continue
            msg = msgs[idx]
            for candidate in (msg.content_text, msg.caption or ""):
                if not candidate:
                    continue
                tokens = tokenize(candidate)
                if msg.sender == target_sender:
                    same_sender_tokens.update(tokens)
                global_tokens.update(tokens)

        return same_sender_tokens if same_sender_tokens else global_tokens

    def _kind_to_type(self, kind: str) -> str:
        """Map message kind to media type buckets."""
        if kind in {"voice"}:
            return "voice"
        if kind in {"image"}:
            return "image"
        if kind in {"video"}:
            return "video"
        if kind in {"document"}:
            return "document"
        return "other"

    def _fastpath_filename(self, msg: Message) -> Optional[Path]:
        """If media_hint is exact filename, resolve directly."""
        if not msg.media_hint:
            return None
        possible = list(self.root.rglob(msg.media_hint))
        if possible:
            return possible[0]
        return None

    def _extract_seq_target(self, msg: Message, hints: set[str]) -> Optional[int]:
        """Derive target sequence number from media_hint or hints."""
        if msg.media_hint:
            seq = _parse_seq_num(msg.media_hint)
            if seq is not None:
                return seq
        for token in hints:
            seq = _parse_seq_num(token)
            if seq is not None:
                return seq
        return None

    def _log_exception(self, msg: Message, reason: str, candidates: list[tuple[Path, float, dict]]) -> None:
        """Record an exception entry for unresolved/ambiguous media."""
        row = {
            "idx": msg.idx,
            "ts": msg.ts,
            "sender": msg.sender,
            "kind": msg.kind,
            "media_hint": msg.media_hint or "",
            "reason": reason,
            "top1_path": candidates[0][0] if candidates else "",
            "top1_score": candidates[0][1] if candidates else "",
            "top2_path": candidates[1][0] if len(candidates) > 1 else "",
            "top2_score": candidates[1][1] if len(candidates) > 1 else "",
        }
        self._exceptions.append(row)

    def _load_config(self) -> ResolverConfig:
        """Load resolver defaults from config/media.yaml if present."""
        default_cfg = ResolverConfig()
        cfg_path = Path(__file__).resolve().parents[1] / "config" / "media.yaml"
        if not cfg_path.exists():
            return default_cfg
        with cfg_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        resolver_cfg = data.get("resolver", {})
        weights = resolver_cfg.get("weights", {})
        ladder_weights = (
            float(weights.get("hint", default_cfg.ladder_weights[0])),
            float(weights.get("ext", default_cfg.ladder_weights[1])),
            float(weights.get("seq", default_cfg.ladder_weights[2])),
            float(weights.get("mtime", default_cfg.ladder_weights[3])),
        )
        return ResolverConfig(
            ext_priority=tuple(resolver_cfg.get("ext_priority", default_cfg.ext_priority)),
            hint_window=int(resolver_cfg.get("hint_window", default_cfg.hint_window)),
            ladder_weights=ladder_weights,
            decisive_tau=float(resolver_cfg.get("tau", default_cfg.decisive_tau)),
            tie_margin=float(resolver_cfg.get("tie_margin", default_cfg.tie_margin)),
            clock_drift_hours=float(resolver_cfg.get("clock_drift_hours", default_cfg.clock_drift_hours)),
            allowed_extensions=resolver_cfg.get("allowed_extensions", default_cfg.allowed_extensions),
            unresolved_policy=resolver_cfg.get("unresolved_policy", default_cfg.unresolved_policy),
        )
