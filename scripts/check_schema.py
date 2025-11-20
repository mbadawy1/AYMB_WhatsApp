#!/usr/bin/env python
"""Schema/enum validation for message JSONL files (M6C.2)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Message JSONL files against schema invariants.")
    parser.add_argument("files", nargs="+", help="Paths to messages JSONL files")
    return parser.parse_args()


def main() -> int:
    _bootstrap_paths()
    from src.pipeline.validation import validate_jsonl, SchemaValidationError

    args = parse_args()
    ok = True
    for file in args.files:
        path = Path(file)
        try:
            validate_jsonl(path)
            print(f"[OK] {path}")
        except SchemaValidationError as exc:
            ok = False
            print(f"[FAIL] {path}: {exc}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
