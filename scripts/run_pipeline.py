#!/usr/bin/env python
"""Run the full WhatsApp pipeline (M1→M3→M5) with manifest/metrics outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run WhatsApp pipeline and materialize run_dir outputs.")
    parser.add_argument("--root", required=True, help="Path to chat export root (folder containing _chat.txt).")
    parser.add_argument("--chat-file", help="Override chat file path (defaults to <root>/_chat.txt).")
    parser.add_argument("--run-id", help="Run identifier (defaults to slugified root folder name).")
    parser.add_argument("--run-dir", help="Output directory for run artifacts (defaults to <root>/runs/<run_id>).")
    parser.add_argument("--max-workers-audio", type=int, default=1, help="Max concurrent voice workers (default 1).")
    parser.add_argument("--asr-provider", default="whisper_openai", help="ASR provider identifier.")
    parser.add_argument("--asr-model", help="ASR model identifier.")
    parser.add_argument("--asr-language", help="Optional ASR language hint.")
    parser.add_argument("--asr-api-version", help="ASR provider API version (provider specific).")
    parser.add_argument("--sample-limit", type=int, help="Limit number of messages processed for smoke runs.")
    parser.add_argument("--sample-every", type=int, help="Process every Nth message for sampling.")
    parser.add_argument("--no-resume", action="store_true", help="Disable resume behavior and re-run all steps.")
    return parser


def parse_args() -> argparse.Namespace:
    return _build_parser().parse_args()


def main() -> int:
    _bootstrap_paths()
    from src.pipeline.config import PipelineConfig
    from src.pipeline.runner import run_pipeline

    args = parse_args()
    cfg = PipelineConfig.from_args(args)
    result = run_pipeline(cfg)
    print(
        f"run_id={result['run_id']} run_dir={result['run_dir']} "
        f"manifest={result['manifest_path']} metrics={result['metrics_path']} "
        f"preview_lines={result['preview_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
