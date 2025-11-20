from pathlib import Path
import json

import pytest

from src.schema.message import Message
from src.writers.text_renderer import TextRenderOptions, render_messages_to_txt


def build_message(idx: int, kind: str, ts: str, sender: str, **kwargs) -> Message:
    payload = {"idx": idx, "ts": ts, "sender": sender, "kind": kind}
    payload.update(kwargs)
    return Message(**payload)


def _load_fixture_messages(path: Path) -> list[Message]:
    msgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msgs.append(Message(**json.loads(line)))
    return msgs


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_basic_render_and_sorting(tmp_path):
    msgs = [
        build_message(1, "text", "2025-01-01T00:00:01", "Bob", content_text="Hi"),
        build_message(0, "text", "2025-01-01T00:00:00", "Alice", content_text="Hello"),
    ]
    out = tmp_path / "out.txt"
    summary = render_messages_to_txt(msgs, out)
    lines = _read_lines(out)
    assert lines[0].startswith("2025-01-01 00:00:00 - Alice: Hello")
    assert lines[1].startswith("2025-01-01 00:00:01 - Bob: Hi")
    assert summary == {"total": 2, "text": 2, "voice": 0, "media": 0, "system": 0}


def test_skip_caption_tail_and_media_placeholders(tmp_path):
    msgs = [
        build_message(0, "image", "2025-01-01T00:00:00", "Alice", media_hint="IMG-1"),
        build_message(
            1,
            "text",
            "2025-01-01T00:00:00",
            "Alice",
            content_text="caption",
            status="skipped",
            status_reason={"code": "merged_into_previous_media", "message": "merged", "context": None},
        ),
    ]
    out = tmp_path / "out.txt"
    render_messages_to_txt(msgs, out)
    lines = _read_lines(out)
    assert len(lines) == 1
    assert "[IMAGE: IMG-1]" in lines[0]


def test_voice_placeholders_and_status_suffix(tmp_path):
    msgs = [
        build_message(
            0,
            "voice",
            "2025-01-01T00:00:00",
            "Alice",
            content_text="",
            status="failed",
            status_reason={"code": "asr_failed", "message": "", "context": None},
        ),
    ]
    out = tmp_path / "out.txt"
    render_messages_to_txt(msgs, out, TextRenderOptions(show_status=True))
    line = out.read_text(encoding="utf-8").strip()
    assert "[AUDIO TRANSCRIPTION FAILED]" in line
    assert "[status=failed, reason=asr_failed]" in line


def test_multiline_indent_and_flatten(tmp_path):
    msgs = [build_message(0, "text", "2025-01-01T00:00:00", "Alice", content_text="line1\nline2")]
    out = tmp_path / "out.txt"
    render_messages_to_txt(msgs, out, TextRenderOptions(flatten_multiline=False))
    lines = _read_lines(out)
    assert lines[0].endswith("line1")
    assert lines[1] == "    line2"

    out2 = tmp_path / "out_flat.txt"
    render_messages_to_txt(msgs, out2, TextRenderOptions(flatten_multiline=True))
    lines2 = _read_lines(out2)
    assert len(lines2) == 1
    assert lines2[0].endswith("line1")


def test_renderer_goldens_from_fixture(tmp_path):
    fixture_dir = Path("tests/fixtures/chat_with_audio")
    msgs = _load_fixture_messages(fixture_dir / "messages.jsonl")
    out_basic = tmp_path / "basic.txt"
    render_messages_to_txt(msgs, out_basic)
    assert _read_lines(out_basic) == _read_lines(fixture_dir / "expected_basic.txt")

    out_hide = tmp_path / "hide.txt"
    render_messages_to_txt(msgs, out_hide, TextRenderOptions(hide_system=True))
    assert _read_lines(out_hide) == _read_lines(fixture_dir / "expected_hide_system.txt")

    out_status = tmp_path / "status.txt"
    render_messages_to_txt(msgs, out_status, TextRenderOptions(show_status=True))
    assert _read_lines(out_status) == _read_lines(fixture_dir / "expected_show_status.txt")
