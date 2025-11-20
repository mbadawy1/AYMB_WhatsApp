"""Exceptions CSV writer for unresolved/ambiguous media mappings."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List, Tuple


def write_exceptions(rows: Iterable[dict]) -> None:
    """Write exceptions.csv to the current working directory."""
    rows = list(rows)
    if not rows:
        return

    headers = [
        "idx",
        "ts",
        "sender",
        "kind",
        "media_hint",
        "reason",
        "top1_path",
        "top1_score",
        "top2_path",
        "top2_score",
    ]

    path = Path("exceptions.csv")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            cleaned = {
                "idx": row.get("idx"),
                "ts": row.get("ts"),
                "sender": row.get("sender"),
                "kind": row.get("kind"),
                "media_hint": row.get("media_hint"),
                "reason": row.get("reason"),
                "top1_path": str(row.get("top1_path") or ""),
                "top1_score": row.get("top1_score") or "",
                "top2_path": str(row.get("top2_path") or ""),
                "top2_score": row.get("top2_score") or "",
            }
            writer.writerow(cleaned)
