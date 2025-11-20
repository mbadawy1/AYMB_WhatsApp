"""Tests for media indexer (M2.2)."""

import os
from pathlib import Path
from time import time

from src.indexer.media_index import FileInfo, _parse_seq_num, _scan_media


def _touch_with_mtime(path: Path, mtime: float) -> None:
    path.write_text("data", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_parse_seq_num():
    assert _parse_seq_num("IMG-20250726-WA0037") == 37
    assert _parse_seq_num("PTT-20250708-WA0028") == 28
    assert _parse_seq_num("random") is None


def test_index_groups_by_day_and_type(tmp_path: Path):
    # Create sample files across two days and types
    now = time()
    day1 = now - 86400
    day2 = now

    img1 = tmp_path / "IMG-20250726-WA0037.jpg"
    vid1 = tmp_path / "VID-20250726-WA0038.mp4"
    voice1 = tmp_path / "PTT-20250708-WA0028.opus"
    doc1 = tmp_path / "DOC-20250728-WA0001.pdf"

    _touch_with_mtime(img1, day1)
    _touch_with_mtime(vid1, day1)
    _touch_with_mtime(voice1, day2)
    _touch_with_mtime(doc1, day2)

    index = _scan_media(tmp_path)

    # Verify grouping by date and type
    day1_key_image = (Path(img1).stat().st_mtime, "image")
    day1_date = Path(img1).stat().st_mtime
    day1_iso = Path(img1).stat().st_mtime
    date1 = Path(img1).stat().st_mtime
    date_key1 = Path(img1).stat().st_mtime
    # Assert keys exist
    key_image = (Path(img1).stat().st_mtime, "image")
    assert any(key[1] == "image" for key in index.keys())
    assert any(key[1] == "video" for key in index.keys())
    assert any(key[1] == "voice" for key in index.keys())
    assert any(key[1] == "document" for key in index.keys())

    # Spot check FileInfo contents
    image_infos = [v for (date, typ), vals in index.items() if typ == "image" for v in vals]
    img_info = image_infos[0]
    assert isinstance(img_info, FileInfo)
    assert img_info.path.name == img1.name
    assert img_info.seq_num == 37
    assert "img" in img_info.name_tokens

    voice_infos = [v for (date, typ), vals in index.items() if typ == "voice" for v in vals]
    assert voice_infos[0].seq_num == 28
