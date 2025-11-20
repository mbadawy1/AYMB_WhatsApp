"""Tests for WA sequence precedence in resolver ranking."""

import os
import time
from pathlib import Path

from src.media_resolver import MediaResolver
from src.schema.message import Message


def _touch(path: Path, when: float):
    path.write_bytes(b"a")
    os.utime(path, (when, when))


def test_seq_match_preferred_over_mtime(tmp_path):
    resolver = MediaResolver(root=tmp_path)
    msg_time = time.time()

    f_exact = tmp_path / "IMG-20250101-WA0001.jpg"
    f_other = tmp_path / "IMG-20250101-WA0002.jpg"
    _touch(f_exact, msg_time + 100)  # further in time
    _touch(f_other, msg_time)  # closer mtime but different seq

    msg = Message(
        idx=0,
        ts=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(msg_time)),
        sender="Alice",
        kind="image",
        content_text="IMG-20250101-WA0001.jpg",
        media_hint=None,
    )

    resolver.map_media([msg])
    assert msg.media_filename.endswith(f_exact.name)
