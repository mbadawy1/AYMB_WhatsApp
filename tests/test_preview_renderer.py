import json
from pathlib import Path

import pytest

from src.schema.message import Message
from src.writers.text_renderer import format_preview_line, write_transcript_preview


def build_voice(idx: int, ts: str, sender: str, **kwargs) -> Message:
    payload = {"idx": idx, "ts": ts, "sender": sender, "kind": "voice"}
    payload.update(kwargs)
    return Message(**payload)


def _load_fixture_messages(path: Path) -> list[Message]:
    msgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msgs.append(Message(**json.loads(line)))
    return msgs


def test_preview_basic_ok():
    msg = build_voice(5, "2025-11-17T21:10:02Z", "Alice", content_text="hello world", status="ok")
    line = format_preview_line(msg)
    assert "idx=5" in line
    assert "sender=Alice" in line
    assert "status=ok" in line
    assert 'text="hello world"' in line


def test_preview_with_reason_and_provider_and_truncation():
    msg = build_voice(
        1,
        "2025-11-17T21:10:02",
        "Bob",
        content_text="A" * 200,
        status="failed",
        status_reason={"code": "asr_failed", "message": "", "context": None},
    )
    msg.derived["asr"] = {"provider": "whisper_openai"}
    line = format_preview_line(msg, max_chars=10)
    assert "status=failed/asr_failed" in line
    assert "provider=whisper_openai" in line
    assert line.endswith('text="AAAAAAAAAA…"')


def test_preview_raises_for_non_voice():
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="text", content_text="hi")
    with pytest.raises(ValueError):
        format_preview_line(msg)


def test_preview_placeholder_when_empty_text():
    msg = build_voice(2, "2025-01-01T00:00:00", "Alice", content_text="", status="ok")
    line = format_preview_line(msg)
    assert "[UNTRANSCRIBED VOICE NOTE]" in line


def test_write_transcript_preview_with_fixture(tmp_path):
    fixture_dir = Path("tests/fixtures/chat_with_audio")
    msgs = _load_fixture_messages(fixture_dir / "messages.jsonl")
    out = tmp_path / "preview.txt"
    count = write_transcript_preview(msgs, out, max_chars=120)
    assert count == 2  # two voice messages in fixture
    expected = (fixture_dir / "expected_preview.txt").read_text(encoding="utf-8")
    assert out.read_text(encoding="utf-8") == expected
