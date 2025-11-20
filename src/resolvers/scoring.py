"""Scoring helpers for media resolution (M2 ladder components)."""

from __future__ import annotations

from typing import Iterable


def _score_ext(type_str: str, ext_priority: Iterable[str] = ("voice", "image", "video", "document", "other")) -> float:
    """Score a media type based on configured priority.

    Higher score means higher priority. Unknown types score 0.0.
    """
    priority = list(ext_priority)
    if type_str not in priority:
        return 0.0
    # Highest priority gets highest score
    return float(len(priority) - priority.index(type_str))


def _score_seq(target: int | None, cand: int | None) -> float:
    """Score proximity between target and candidate WA sequence numbers."""
    if target is None and cand is None:
        return 0.0
    if target is None:
        # Prefer having any sequence over none
        return 0.1
    if cand is None:
        return 0.0
    # Absolute distance; closer is better
    return 1.0 / (1 + abs(target - cand))


def _score_mtime(delta_seconds: float) -> float:
    """Score based on absolute mtime delta; closer to zero is better."""
    if delta_seconds < 0:
        delta_seconds = -delta_seconds
    # Avoid division by zero and cap scores at 1.0 for exact match
    return 1.0 / (1.0 + delta_seconds)
