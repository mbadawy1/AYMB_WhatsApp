#!/usr/bin/env python
"""Materialize run_dir outputs (messages/chat/preview/manifest/metrics)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write standardized outputs for a run directory.")
    parser.add_argument("--run-id", required=True, help="Run identifier")
    parser.add_argument("--messages-m1", required=True, help="Path to messages.M1.jsonl")
    parser.add_argument("--messages-m2", required=True, help="Path to messages.M2.jsonl")
    parser.add_argument("--messages-m3", required=True, help="Path to messages.M3.jsonl")
    parser.add_argument("--run-dir", required=True, help="Run directory for outputs")
    parser.add_argument("--no-chat", action="store_true", help="Skip rendering chat_with_audio.txt")
    parser.add_argument("--no-preview", action="store_true", help="Skip writing preview_transcripts.txt")
    parser.add_argument("--preview-max-chars", type=int, default=120, help="Preview text truncation length")
    return parser.parse_args()


def main() -> int:
    _bootstrap_paths()
    from src.pipeline.outputs import load_messages
    from src.pipeline.materialize import materialize_run

    args = parse_args()

    m1 = load_messages(Path(args.messages_m1))
    m2 = load_messages(Path(args.messages_m2))
    m3 = load_messages(Path(args.messages_m3))

    summary = materialize_run(
        args.run_id,
        Path(args.run_dir),
        m1,
        m2,
        m3,
        render_text=not args.no_chat,
        render_preview=not args.no_preview,
        preview_max_chars=args.preview_max_chars,
    )

    preview_info = (
        f", preview_lines={summary['preview_count']}"
        if summary["outputs"].get("preview_transcripts")
        else ", preview_lines=0 (skipped)"
    )
    print(
        f"Wrote messages/chat/manifest/metrics to {args.run_dir}"
        f"{preview_info}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
