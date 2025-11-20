"""Hashing utilities for media files."""

from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK_SIZE = 8 * 1024 * 1024  # 8MB


def sha256_file(path: Path, extra: str | None = None) -> str:
    """Compute SHA256 hash of a file using streamed reads."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    if extra:
        h.update(extra.encode("utf-8"))
    return h.hexdigest()
