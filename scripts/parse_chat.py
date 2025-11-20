"""CLI to parse WhatsApp chat export to JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser_agent import ParserAgent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse WhatsApp _chat.txt into JSONL")
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Path to export root or _chat.txt file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    agent = ParserAgent(root=str(args.root))
    messages = agent.parse()

    for msg in messages:
        payload = msg.model_dump() if hasattr(msg, "model_dump") else msg.dict()  # type: ignore[attr-defined]
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
