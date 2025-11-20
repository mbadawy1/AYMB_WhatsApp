"""Parser agent for WhatsApp chat exports.

Implements header splitting, multiline aggregation, and basic kind classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from src.schema.message import Message, StatusReason
from src.utils.dates import detect_datetime_format, parse_ts


@dataclass
class ParserAgent:
    """WhatsApp chat parser.

    Currently implements header splitting; full parse pipeline is added in later tasks.
    """

    root: str
    chat_file: Optional[str] = None
    locale_format: str = "auto"

    def parse(self):
        """Parse chat export into structured Message list with stable indexing."""
        if self.chat_file:
            chat_path = Path(self.chat_file)
        else:
            root_path = Path(self.root)
            chat_path = root_path if root_path.is_file() else root_path / "_chat.txt"

        lines = chat_path.read_text(encoding="utf-8").splitlines()
        fmt = detect_datetime_format(lines)
        blocks = self._to_blocks(lines, fmt)

        messages: list[Message] = []
        for block in blocks:
            if block.get("ts") is None or block.get("sender") is None:
                # Skip malformed blocks without header information
                continue

            kind, media_hint, content_text = self._classify(block)
            ts_iso = parse_ts(block["ts"], fmt)

            msg = Message(
                idx=len(messages),
                ts=ts_iso,
                sender=block.get("sender") or "",
                kind=kind,
                content_text=content_text,
                raw_line=block.get("raw_line") or "",
                raw_block=block.get("raw_block") or "",
                media_hint=media_hint,
            )
            self._validate(msg)
            messages.append(msg)

        return self._merge_captions(messages)

    def _split_header(self, line: str, fmt: dict) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Split a single line into timestamp, sender, and body components.

        Returns (None, None, line) when the line does not start with a timestamp,
        indicating it should be treated as a continuation of the previous block.
        """
        raw_line = line.rstrip("\n")
        line_no_bom = raw_line.lstrip("\ufeff")

        regex = fmt.get("regex")
        if regex is None:
            return None, None, raw_line

        match = regex.match(line_no_bom)
        if not match or match.start() != 0:
            return None, None, raw_line

        ts = match.group(1).strip()

        remainder = line_no_bom[match.end() :]
        if remainder.startswith(" - "):
            remainder = remainder[3:]
        else:
            return None, None, raw_line

        sender = remainder
        body: Optional[str] = None
        if ": " in remainder:
            sender, body = remainder.split(": ", 1)
            body = body.strip() if body is not None else None

        sender = sender.strip() if sender is not None else None
        return ts, sender or None, body

    def _to_blocks(self, lines: list[str], fmt: dict) -> list[dict]:
        """Aggregate lines into message blocks.

        A new block starts only when a header line is detected. Continuation lines
        are appended to the current block with newline preservation.
        """
        blocks: list[dict] = []
        current_block: Optional[dict] = None

        for line in lines:
            ts, sender, body = self._split_header(line, fmt)
            clean_line = line.rstrip("\n")

            if ts is not None:
                # Start a new block for a detected header
                block = {
                    "ts": ts,
                    "sender": sender,
                    "raw_line": clean_line,
                    "raw_block": clean_line,
                    "content_text": body or "",
                }
                blocks.append(block)
                current_block = block
                continue

            # Continuation line
            if current_block is None:
                # No existing block; start a generic one
                current_block = {
                    "ts": None,
                    "sender": None,
                    "raw_line": clean_line,
                    "raw_block": clean_line,
                    "content_text": clean_line,
                }
                blocks.append(current_block)
            else:
                current_block["raw_block"] = f"{current_block['raw_block']}\n{clean_line}"
                current_block["content_text"] = f"{current_block['content_text']}\n{clean_line}"

        return blocks

    def _classify(self, block: dict) -> Tuple[str, Optional[str], str]:
        """Classify a block into kind/media_hint/content_text."""
        body = block.get("content_text", "").strip()
        media_hint: Optional[str] = None
        kind = "text"
        content_text = body

        # Fast path: explicit filename with "(file attached)"
        fname_match = re.match(
            r"(?i)^(?P<fname>(IMG|VID|PTT|AUD|DOC)-\d{8}-WA\d+\.[A-Za-z0-9]+) \(file attached\)$",
            body,
        )
        if fname_match:
            fname = fname_match.group("fname")
            media_hint = fname
            prefix = fname[:3].upper()
            if prefix in {"PTT", "AUD"}:
                kind = "voice"
            elif prefix == "IMG":
                kind = "image"
            elif prefix == "VID":
                kind = "video"
            else:
                kind = "document"
            content_text = ""
            return kind, media_hint, content_text

        lower_body = body.lower()

        # Media omitted placeholders
        placeholder_map = {
            "<image omitted>": ("image", "image_omitted"),
            "<video omitted>": ("video", "video_omitted"),
            "<document omitted>": ("document", "document_omitted"),
            "<media omitted>": ("unknown", "media_omitted"),
        }
        if lower_body in placeholder_map:
            kind, media_hint = placeholder_map[lower_body]
            content_text = ""
            return kind, media_hint, content_text

        # System line patterns (common WhatsApp notices)
        system_patterns = [
            "messages and calls are end-to-end encrypted",
            "you created group",
            "you were added",
            "added",
            "removed",
            "changed this group's icon",
            "changed the subject from",
        ]
        if any(pat in lower_body for pat in system_patterns):
            kind = "system"
            return kind, media_hint, content_text

        # Voice message textual hints
        voice_match = re.match(r"(?i)^voice message \((\d+):(\d{2})\)$", body)
        if voice_match:
            minutes, seconds = voice_match.groups()
            media_hint = f"{int(minutes):02d}:{seconds}"
            kind = "voice"
            content_text = ""
            return kind, media_hint, content_text

        if lower_body == "audio omitted":
            kind = "voice"
            media_hint = "audio_omitted"
            content_text = ""
            return kind, media_hint, content_text

        # Default fallback
        return kind, media_hint, content_text

    def _merge_captions(self, messages: list[Message]) -> list[Message]:
        """Merge caption text that follows media items by same sender and ts."""
        media_kinds = {"image", "video", "voice", "document", "sticker", "unknown"}

        for idx, msg in enumerate(messages[:-1]):
            if msg.kind not in media_kinds:
                continue

            next_msg = messages[idx + 1]
            if next_msg.kind != "text":
                continue

            if msg.sender == next_msg.sender and msg.ts == next_msg.ts:
                msg.caption = next_msg.content_text
                next_msg.status = "skipped"
                next_msg.status_reason = StatusReason(
                    code="merged_into_previous_media",
                    message="Merged caption into previous media message",
                )

        return messages

    def _validate(self, msg: Message) -> None:
        """Validate message when schema validation is enabled via env."""
        from os import getenv

        if getenv("VALIDATE_SCHEMA", "false").lower() != "true":
            return

        from src.schema.message import validate_message

        validate_message(msg)
