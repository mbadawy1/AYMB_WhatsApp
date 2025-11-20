"""Filename regex helpers for WhatsApp media variants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


COPY_SUFFIX_RE = re.compile(r"( \(\d+\)|-copy)$", re.IGNORECASE)

# IMG/VID/PTT/AUD/DOC-YYYYMMDD-WA####[.ext][ copy suffix]
WA_PATTERN = re.compile(
    r"^(?P<prefix>IMG|VID|PTT|AUD|DOC)-(?P<date>\d{8})-WA(?P<seq>\d+)",
    re.IGNORECASE,
)


@dataclass
class ParsedFilename:
    prefix: Optional[str]
    date: Optional[str]
    seq_num: Optional[int]
    kind: Optional[str]
    stem: str


def normalize_stem(stem: str) -> str:
    """Strip common copy suffixes and whitespace."""
    stem = stem.strip()
    stem = COPY_SUFFIX_RE.sub("", stem)
    return stem


def parse_filename(name: str) -> ParsedFilename:
    """Parse WhatsApp-style filenames into components."""
    stem = name.split(".")[0]
    cleaned = normalize_stem(stem)
    match = WA_PATTERN.match(cleaned)
    if not match:
        return ParsedFilename(prefix=None, date=None, seq_num=None, kind=None, stem=cleaned.lower())

    prefix = match.group("prefix").upper()
    date = match.group("date")
    seq = int(match.group("seq"))
    kind = {
        "IMG": "image",
        "VID": "video",
        "PTT": "voice",
        "AUD": "voice",
        "DOC": "document",
    }.get(prefix, "other")
    return ParsedFilename(prefix=prefix, date=date, seq_num=seq, kind=kind, stem=cleaned.lower())
