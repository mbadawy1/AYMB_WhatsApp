#!/usr/bin/env python
"""CLI to generate preview_transcripts.txt from messages.jsonl."""

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
    parser = argparse.ArgumentParser(description="Render preview_transcripts.txt for voice messages.")
    parser.add_argument("--messages", required=True, help="Path to messages.jsonl")
    parser.add_argument("--out", required=True, help="Path to preview_transcripts.txt")
    parser.add_argument("--max-chars", type=int, default=120, help="Max characters per preview text")
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
    from src.writers.text_renderer import write_transcript_preview

    args = parse_args()
    messages = load_messages(Path(args.messages))
    count = write_transcript_preview(messages, Path(args.out), max_chars=args.max_chars)
    print(f"Wrote transcript preview for {count} voice messages to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
