import json
from pathlib import Path

from src.schema.message import Message
from src.writers.markdown_renderer import MarkdownOptions, render_messages_to_markdown


def _load_messages(path: Path) -> list[Message]:
    msgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msgs.append(Message(**json.loads(line)))
    return msgs


def test_markdown_renderer_basic_golden(tmp_path):
    fixture_dir = Path("tests/fixtures/chat_with_audio_md")
    msgs = _load_messages(fixture_dir / "messages.jsonl")
    out = tmp_path / "chat_with_audio.md"
    summary = render_messages_to_markdown(msgs, out)
    assert out.read_text(encoding="utf-8") == (fixture_dir / "expected.md").read_text(encoding="utf-8")
    assert summary["dates"] == 2
    assert summary["voice"] == 2
    assert summary["media"] == 1


def test_markdown_renderer_hide_system(tmp_path):
    fixture_dir = Path("tests/fixtures/chat_with_audio_md")
    msgs = _load_messages(fixture_dir / "messages.jsonl")
    out = tmp_path / "chat_with_audio.md"
    render_messages_to_markdown(msgs, out, MarkdownOptions(hide_system=True))
    text = out.read_text(encoding="utf-8")
    assert "SYSTEM" not in text
