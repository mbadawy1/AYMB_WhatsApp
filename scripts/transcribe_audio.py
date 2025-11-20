#!/usr/bin/env python
"""CLI to parse, resolve, and transcribe WhatsApp chats (smoke)."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


def _bootstrap_paths() -> None:
    """Ensure repository root is on sys.path for src imports."""
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe WhatsApp voice messages.")
    parser.add_argument("--root", required=True, help="Path to chat folder or _chat.txt")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable cache writes (use a temp cache directory for this run).",
    )
    return parser.parse_args()


def main() -> int:
    _bootstrap_paths()

    from src.parser_agent import ParserAgent
    from src.media_resolver import MediaResolver
    from src.audio_transcriber import AudioTranscriber, AudioConfig

    args = parse_args()
    root_path = Path(args.root)

    parser = ParserAgent(str(root_path))
    messages = parser.parse()

    resolver = MediaResolver(root_path)
    resolver.map_media(messages)

    cfg = AudioConfig()
    if args.no_cache:
        cfg.cache_dir = Path(tempfile.mkdtemp(prefix="audio_cache_"))

    transcriber = AudioTranscriber(cfg)
    for msg in messages:
        if msg.kind != "voice":
            continue
        transcriber.transcribe(msg)

    summary = {"ok": 0, "partial": 0, "failed": 0, "skipped": 0}
    for msg in messages:
        if msg.kind != "voice":
            continue
        summary[msg.status] = summary.get(msg.status, 0) + 1

    print(
        "Audio transcription summary: "
        f"ok={summary['ok']}, partial={summary['partial']}, "
        f"failed={summary['failed']}, skipped={summary['skipped']}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
