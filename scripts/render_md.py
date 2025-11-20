#!/usr/bin/env python
"""CLI to render chat_with_audio.md (Markdown) from messages.jsonl."""

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
    parser = argparse.ArgumentParser(description="Render chat_with_audio.md from messages.jsonl")
    parser.add_argument("--messages", required=True, help="Path to messages.jsonl")
    parser.add_argument("--out", required=True, help="Output path for chat_with_audio.md")
    parser.add_argument("--hide-system", action="store_true", help="Hide system messages")
    return parser.parse_args()


def load_messages(path: Path):
    from src.schema.message import Message

    msgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msgs.append(Message(**json.loads(line)))
    return msgs


def main() -> int:
    _bootstrap_paths()
    from src.writers.markdown_renderer import MarkdownOptions, render_messages_to_markdown

    args = parse_args()
    messages = load_messages(Path(args.messages))
    summary = render_messages_to_markdown(
        messages,
        Path(args.out),
        MarkdownOptions(hide_system=args.hide_system),
    )
    print(
        f"Rendered {summary['total']} messages across {summary['dates']} dates "
        f"(voice={summary['voice']}, media={summary['media']}, text={summary['text']}, system={summary['system']}) "
        f"to {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
