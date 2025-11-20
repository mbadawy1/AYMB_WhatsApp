"""Tests for filename pattern parsing variants."""

from src.indexer.filename_patterns import normalize_stem, parse_filename


def test_parse_whatsapp_standard():
    parsed = parse_filename("IMG-20250101-WA0001.jpg")
    assert parsed.prefix == "IMG"
    assert parsed.seq_num == 1
    assert parsed.kind == "image"


def test_parse_copy_suffix():
    parsed = parse_filename("VID-20250102-WA0002 (1).mp4")
    assert parsed.seq_num == 2
    assert parsed.kind == "video"
    assert parsed.stem == "VID-20250102-WA0002".lower()


def test_normalize_copy_suffix():
    assert normalize_stem("IMG-2025 (2)") == "IMG-2025"


def test_parse_unknown_returns_none():
    parsed = parse_filename("randomfile.txt")
    assert parsed.seq_num is None
    assert parsed.kind is None
