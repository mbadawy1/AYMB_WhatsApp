"""Media file indexer for M2.

Builds a day/type grouped index of media files to bound candidate sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

from src.utils.hashing import sha256_file
from src.indexer.filename_patterns import parse_filename

@dataclass
class FileInfo:
    """Metadata about a media file used for resolution scoring."""

    path: Path
    size: int
    mtime: float
    name_tokens: List[str]
    seq_num: Optional[int]
    sha256: Optional[str] = None


MEDIA_TYPES = {
    "voice": {".opus", ".ogg", ".m4a", ".amr", ".aac"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".heic"},
    "video": {".mp4", ".mov", ".avi", ".mkv"},
    "document": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"},
}


def _classify_extension(ext: str) -> str:
    for label, exts in MEDIA_TYPES.items():
        if ext.lower() in exts:
            return label
    return "other"


def _parse_seq_num(name: str) -> Optional[int]:
    """Extract WA#### sequence number using filename parser."""
    parsed = parse_filename(name)
    return parsed.seq_num


def _tokenize_name(name: str) -> List[str]:
    parsed = parse_filename(name)
    tokens = [t for t in re.split(r"[^\w]+", parsed.stem) if t]
    return tokens


def _scan_media(root: Path) -> Dict[Tuple[str, str], List[FileInfo]]:
    """Scan filesystem for media files grouped by (date, type)."""
    index: Dict[Tuple[str, str], List[FileInfo]] = {}

    for path in root.rglob("*"):
        if path.is_dir():
            continue

        ext = path.suffix.lower()
        media_type = _classify_extension(ext)
        if media_type == "other" and ext:
            # Skip non-media unless explicitly other type is allowed
            pass
        # Decide inclusion: include all files with an extension
        if not ext:
            continue

        stat = path.stat()
        mtime = stat.st_mtime
        date_key = datetime.fromtimestamp(mtime).date().isoformat()
        seq_num = _parse_seq_num(path.stem)
        name_tokens = _tokenize_name(path.stem)

        info = FileInfo(
            path=path,
            size=stat.st_size,
            mtime=mtime,
            name_tokens=name_tokens,
            seq_num=seq_num,
            sha256=sha256_file(path),
        )
        bucket = index.setdefault((date_key, media_type), [])
        bucket.append(info)

    # Ensure deterministic ordering
    for bucket in index.values():
        bucket.sort(key=lambda fi: fi.path.as_posix())

    return index
