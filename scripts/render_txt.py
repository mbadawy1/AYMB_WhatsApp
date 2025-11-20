#!/usr/bin/env python
"""CLI to render chat_with_audio.txt from messages.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render chat_with_audio.txt from messages.jsonl")
    parser.add_argument("--messages", required=True, help="Path to messages.jsonl")
    parser.add_argument("--out", required=True, help="Output path for chat_with_audio.txt")
    parser.add_argument("--hide-system", action="store_true", help="Hide system messages")
    parser.add_argument("--show-status", action="store_true", help="Append status suffix")
    parser.add_argument("--flatten-multiline", action="store_true", help="Flatten multiline bodies")
    return parser.parse_args()


def load_messages(path: Path):
    from src.schema.message import Message

    msgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        msgs.append(Message(**data))
    return msgs


def main() -> int:
    _bootstrap_paths()
    from src.writers.text_renderer import TextRenderOptions, render_messages_to_txt

    args = parse_args()
    messages_path = Path(args.messages)
    out_path = Path(args.out)

    messages = load_messages(messages_path)
    options = TextRenderOptions(
        hide_system=args.hide_system,
        show_status=args.show_status,
        flatten_multiline=args.flatten_multiline,
    )
    summary = render_messages_to_txt(messages, out_path, options)
    print(
        f"Rendered {summary['total']} messages (text={summary['text']}, voice={summary['voice']}, "
        f"media={summary['media']}, system={summary['system']}) to {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
