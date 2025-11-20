#!/usr/bin/env python
"""Run Parser→Resolver→Audio pipeline and materialize contract outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run M1→M3 pipeline and write run_dir outputs.")
    parser.add_argument("--root", required=True, help="Path to chat export root (folder containing _chat.txt)")
    parser.add_argument("--run-id", required=True, help="Run identifier")
    parser.add_argument("--run-dir", required=True, help="Output run directory")
    return parser.parse_args()


def main() -> int:
    _bootstrap_paths()
    from src.pipeline.runner import run_contract_pipeline

    args = parse_args()
    summary = run_contract_pipeline(Path(args.root), Path(args.run_dir), args.run_id)
    print(f"Pipeline completed for run_id={args.run_id}; outputs -> {args.run_dir}; preview_lines={summary['preview_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
