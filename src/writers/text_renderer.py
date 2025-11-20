"""Text renderer for chat_with_audio.txt (M5.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Optional
from datetime import datetime

from src.schema.message import Message

# RTL mode type
RtlMode = Literal["none", "bidi_marks"]

# Bidi control characters
RLE = "\u202B"  # Right-to-Left Embedding
PDF = "\u202C"  # Pop Directional Formatting


@dataclass
class TextRenderOptions:
    hide_system: bool = False
    show_status: bool = False
    flatten_multiline: bool = False
    rtl_mode: RtlMode = "none"


def _has_arabic(text: str) -> bool:
    """Check if text contains Arabic characters (U+0600 to U+06FF)."""
    return bool(re.search(r'[\u0600-\u06FF]', text))


def wrap_rtl_segments(text: str, rtl_mode: RtlMode) -> str:
    """Wrap text with bidi marks if it contains Arabic and rtl_mode is enabled.

    Args:
        text: The text to potentially wrap
        rtl_mode: The RTL mode setting

    Returns:
        Original text if rtl_mode="none" or no Arabic found,
        otherwise text wrapped with RLE...PDF marks
    """
    if rtl_mode == "none":
        return text

    if rtl_mode == "bidi_marks" and _has_arabic(text):
        return f"{RLE}{text}{PDF}"

    return text


def _ts_human(ts_iso: str) -> str:
    """Format ISO timestamp as YYYY-MM-DD HH:MM:SS."""
    dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00")) if "Z" in ts_iso else datetime.fromisoformat(ts_iso)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _status_suffix(msg: Message, options: TextRenderOptions) -> str:
    if not options.show_status:
        return ""
    reason = msg.status_reason.code if getattr(msg.status_reason, "code", None) else None
    if reason:
        return f"[status={msg.status}, reason={reason}]"
    return f"[status={msg.status}]"


def _select_body(msg: Message) -> str:
    if msg.kind == "system":
        if msg.content_text:
            return msg.content_text
        if msg.raw_block:
            return msg.raw_block
        return "[SYSTEM MESSAGE]"

    if msg.status == "skipped" and getattr(msg.status_reason, "code", None) == "merged_into_previous_media":
        return ""  # caller should skip

    if msg.content_text:
        return msg.content_text
    if msg.caption:
        return msg.caption

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

    return msg.content_text or ""


def render_messages_to_txt(
    messages: Iterable[Message],
    out_path: Path,
    options: Optional[TextRenderOptions] = None,
) -> dict:
    opts = options or TextRenderOptions()
    msgs = sorted(list(messages), key=lambda m: m.idx)
    summary = {"total": 0, "text": 0, "voice": 0, "media": 0, "system": 0}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for msg in msgs:
            if msg.kind == "system":
                if opts.hide_system:
                    continue
                body = _select_body(msg)
                # Apply RTL wrapping to system messages too
                body = wrap_rtl_segments(body, opts.rtl_mode)
                ts = _ts_human(msg.ts)
                suffix = _status_suffix(msg, opts)
                f.write(f"{ts} - SYSTEM: {body}{suffix}\n")
                summary["system"] += 1
                summary["total"] += 1
                continue

            if msg.status == "skipped" and getattr(msg.status_reason, "code", None) == "merged_into_previous_media":
                continue

            body = _select_body(msg)
            # Apply RTL wrapping to the entire body
            body = wrap_rtl_segments(body, opts.rtl_mode)
            lines = body.splitlines() or [""]
            ts = _ts_human(msg.ts)
            suffix = _status_suffix(msg, opts)

            first_line = lines[0].strip() if opts.flatten_multiline else lines[0]
            f.write(f"{ts} - {msg.sender}: {first_line}{suffix}\n")
            if not opts.flatten_multiline:
                for cont in lines[1:]:
                    f.write(f"    {cont}\n")

            # summary counts
            summary["total"] += 1
            if msg.kind == "voice":
                summary["voice"] += 1
            elif msg.kind in {"image", "video", "document"}:
                summary["media"] += 1
            else:
                summary["text"] += 1

    return summary


def format_preview_line(msg: Message, max_chars: int = 120) -> str:
    """Return single-line preview for a voice message."""
    if msg.kind != "voice":
        raise ValueError("format_preview_line only supports voice messages")

    ts = _ts_human(msg.ts)
    status_reason = getattr(msg.status_reason, "code", None)
    status_part = f"{msg.status}/{status_reason}" if status_reason else msg.status
    provider = msg.derived.get("asr", {}).get("provider", "-")

    # Base text selection mirrors voice fallback logic
    if msg.content_text:
        text = msg.content_text
    elif msg.status == "failed":
        text = "[AUDIO TRANSCRIPTION FAILED]"
    else:
        text = "[UNTRANSCRIBED VOICE NOTE]"

    # Normalize: replace newlines, collapse spaces
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    text = text.replace('"', r"\"")

    sender = msg.sender.replace("|", " ")
    return f'{ts} | idx={msg.idx} | sender={sender} | status={status_part} | provider={provider} | text="{text}"'


def write_transcript_preview(messages: Iterable[Message], out_path: Path, max_chars: int = 120) -> int:
    """Write preview_transcripts.txt with one line per voice message (sorted by idx)."""
    voice_msgs = sorted([m for m in messages if m.kind == "voice"], key=lambda m: m.idx)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for msg in voice_msgs:
            f.write(format_preview_line(msg, max_chars=max_chars) + "\n")
    return len(voice_msgs)
