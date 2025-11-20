"""Tests for clock drift handling in media resolver."""

import os
import time
from pathlib import Path

from src.media_resolver import MediaResolver
from src.schema.message import Message


def _touch(path: Path, when: float) -> None:
    path.write_bytes(b"a")
    os.utime(path, (when, when))


def test_clock_drift_window_allows_late_file(tmp_path):
    resolver = MediaResolver(root=tmp_path)
    msg_time = time.time()
    late_time = msg_time + 2 * 3600  # +2 hours

    f = tmp_path / "IMG-20250101-WA0001.jpg"
    _touch(f, late_time)

    msg = Message(idx=0, ts=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(msg_time)), sender="Alice", kind="image", content_text="IMG-20250101-WA0001.jpg")

    resolver.map_media([msg])
    assert msg.media_filename is not None


def test_day_boundary_midnight(tmp_path):
    resolver = MediaResolver(root=tmp_path)
    # 23:58 vs 00:03 (5 minutes apart, across midnight)
    msg_time = time.mktime((2025, 1, 1, 23, 58, 0, 0, 1, -1))
    file_time = msg_time + 5 * 60  # 00:03 next day

    f = tmp_path / "IMG-20250101-WA0002.jpg"
    _touch(f, file_time)

    msg = Message(idx=0, ts="2025-01-01T23:58:00", sender="Alice", kind="image", content_text="IMG-20250101-WA0002.jpg")

    resolver.map_media([msg])
    assert msg.media_filename is not None
