"""Run-level metrics helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    import jsonschema
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False

from src.schema.message import Message

METRICS_SCHEMA_VERSION = "1.0.0"


def _as_list(messages: Iterable[Message]) -> list[Message]:
    if isinstance(messages, list):
        return messages
    return list(messages)


@dataclass
class RunMetrics:
    """Aggregated metrics for a pipeline run."""

    schema_version: str = METRICS_SCHEMA_VERSION
    messages_total: int = 0
    voice_total: int = 0
    voice_status: Dict[str, int] = field(
        default_factory=lambda: {"ok": 0, "partial": 0, "failed": 0}
    )
    media_resolution: Dict[str, int] = field(
        default_factory=lambda: {"resolved": 0, "unresolved": 0, "ambiguous": 0}
    )
    audio_seconds_total: float = 0.0
    asr_cost_total_usd: float = 0.0
    wall_clock_seconds: float = 0.0
    asr_provider: Optional[str] = None
    asr_model: Optional[str] = None
    asr_language: Optional[str] = None

    def record_messages(self, messages: Iterable[Message]) -> None:
        msgs = _as_list(messages)
        self.messages_total = len(msgs)

    def record_media_resolution(self, messages: Iterable[Message]) -> None:
        counts = {"resolved": 0, "unresolved": 0, "ambiguous": 0}
        for msg in messages:
            code = getattr(msg.status_reason, "code", None)
            if msg.media_filename:
                counts["resolved"] += 1
            elif code == "unresolved_media":
                counts["unresolved"] += 1
            elif code == "ambiguous_media":
                counts["ambiguous"] += 1
        self.media_resolution = counts

    def record_audio(self, messages: Iterable[Message]) -> None:
        voice_counts = {"ok": 0, "partial": 0, "failed": 0}
        seconds = 0.0
        cost = 0.0
        total_voice = 0
        for msg in messages:
            if msg.kind != "voice":
                continue
            total_voice += 1
            if msg.status in voice_counts:
                voice_counts[msg.status] += 1
            asr_payload = msg.derived.get("asr") if isinstance(msg.derived, dict) else None
            if asr_payload:
                seconds += float(asr_payload.get("total_duration_seconds") or 0.0)
                cost += float(asr_payload.get("cost") or 0.0)
                if not self.asr_provider and asr_payload.get("provider"):
                    self.asr_provider = str(asr_payload.get("provider"))
                if not self.asr_model and asr_payload.get("model"):
                    self.asr_model = str(asr_payload.get("model"))
                lang_hint = (
                    asr_payload.get("language_hint")
                    or asr_payload.get("language")
                    or asr_payload.get("detected_language")
                )
                if not self.asr_language and lang_hint:
                    self.asr_language = str(lang_hint)
        self.voice_total = total_voice
        self.voice_status = voice_counts
        self.audio_seconds_total = round(seconds, 3)
        self.asr_cost_total_usd = round(cost, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "messages_total": self.messages_total,
            "voice_total": self.voice_total,
            "voice_status": self.voice_status,
            "media_resolution": self.media_resolution,
            "audio_seconds_total": self.audio_seconds_total,
            "asr_cost_total_usd": self.asr_cost_total_usd,
            "wall_clock_seconds": self.wall_clock_seconds,
            "asr_provider": self.asr_provider,
            "asr_model": self.asr_model,
            "asr_language": self.asr_language,
        }


def compute_metrics(messages: Iterable[Message]) -> Dict[str, Any]:
    """Backward-compatible helper for contract materialization."""
    metrics = RunMetrics()
    metrics.record_messages(messages)
    metrics.record_audio(messages)
    return metrics.to_dict()


def write_metrics(metrics: RunMetrics | Dict[str, Any], path: Path) -> None:
    """Persist metrics to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = metrics.to_dict() if isinstance(metrics, RunMetrics) else metrics
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_metrics_schema() -> dict[str, Any]:
    """Load the metrics JSON schema from disk."""
    schema_path = Path(__file__).resolve().parents[2] / "schema" / "metrics.schema.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Metrics schema not found at {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_metrics(data: dict[str, Any]) -> None:
    """Validate a metrics dict against the JSON schema.

    Args:
        data: Metrics dictionary to validate

    Raises:
        jsonschema.ValidationError: If validation fails
        ImportError: If jsonschema is not installed
        FileNotFoundError: If schema file is missing
    """
    if not _JSONSCHEMA_AVAILABLE:
        raise ImportError(
            "jsonschema is required for validation. "
            "Install with: pip install jsonschema"
        )

    schema = _get_metrics_schema()
    jsonschema.validate(data, schema)
