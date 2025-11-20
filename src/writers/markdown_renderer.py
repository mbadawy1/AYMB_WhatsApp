"""Markdown renderer for chat_with_audio.md (M5.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from src.schema.message import Message
from src.writers.text_renderer import RtlMode, wrap_rtl_segments


@dataclass
class MarkdownOptions:
    hide_system: bool = False
    rtl_mode: RtlMode = "none"


def _ts_parts(ts: str) -> tuple[str, str]:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if "Z" in ts else datetime.fromisoformat(ts)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")


def _voice_badge(msg: Message) -> Optional[str]:
    if msg.status != "ok":
        reason = getattr(msg.status_reason, "code", None)
        if reason:
            return f"⚠️ status={msg.status} (reason={reason})"
        return f"⚠️ status={msg.status}"
    return None


def _placeholder_for_kind(msg: Message) -> str:
    if msg.kind == "voice":
        if msg.status == "failed":
            return "[AUDIO TRANSCRIPTION FAILED]"
        return "[UNTRANSCRIBED VOICE NOTE]"
    if msg.kind == "image":
        return f"[IMAGE: {msg.media_hint or 'unknown'}]"
    if msg.kind == "video":
        return f"[VIDEO: {msg.media_hint or 'unknown'}]"
    if msg.kind == "document":
        return f"[DOCUMENT: {msg.media_hint or 'unknown'}]"
    if msg.kind == "sticker":
        return "[STICKER]"
    if msg.kind == "unknown":
        return "[UNKNOWN MESSAGE]"
    if msg.status == "skipped":
        reason = getattr(msg.status_reason, "code", None) or "reason_unknown"
        return f"[SKIPPED: {reason}]"
    return ""


def _body_text(msg: Message) -> str:
    if msg.content_text:
        return msg.content_text
    if msg.caption:
        return msg.caption
    return _placeholder_for_kind(msg)


def render_messages_to_markdown(
    messages: Iterable[Message],
    out_path: Path,
    options: Optional[MarkdownOptions] = None,
) -> dict:
    opts = options or MarkdownOptions()
    msgs = sorted(list(messages), key=lambda m: m.idx)
    summary = {"total": 0, "voice": 0, "media": 0, "text": 0, "system": 0, "dates": 0}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        current_date = None
        for msg in msgs:
            msg_date, msg_time = _ts_parts(msg.ts)

            if msg.kind == "system" and opts.hide_system:
                continue

            if msg_date != current_date:
                if current_date is not None:
                    f.write("\n")
                f.write(f"## {msg_date}\n")
                current_date = msg_date
                summary["dates"] += 1

            if msg.kind == "system":
                body = msg.content_text or msg.raw_block or "[SYSTEM MESSAGE]"
                # Apply RTL wrapping to system messages
                body = wrap_rtl_segments(body, opts.rtl_mode)
                f.write(f"- {msg_time} **SYSTEM:** {body}\n")
                summary["system"] += 1
                summary["total"] += 1
                continue

            if msg.kind == "voice":
                body = _body_text(msg)
                # Apply RTL wrapping to voice transcript
                body = wrap_rtl_segments(body, opts.rtl_mode)
                f.write(f"- {msg_time} **{msg.sender} (voice):**\n")
                badge = _voice_badge(msg)
                if badge:
                    f.write(f"  > {badge}\n")
                lines = body.splitlines() or [""]
                for line in lines:
                    f.write(f"  > {line}\n")
                summary["voice"] += 1
            else:
                if msg.kind in {"image", "video", "document"}:
                    body_main = _placeholder_for_kind(msg)
                else:
                    body_main = _body_text(msg)

                first_line, *rest = body_main.splitlines() or [""]
                prefix = f"- {msg_time} **{msg.sender}:**"
                f.write(f"{prefix} {first_line}\n")
                if msg.caption and msg.kind in {"image", "video", "document"}:
                    f.write(f"  > {msg.caption}\n")
                for line in rest:
                    f.write(f"  > {line}\n")
                if msg.kind in {"image", "video", "document"}:
                    summary["media"] += 1
                else:
                    summary["text"] += 1

            summary["total"] += 1

    return summary
