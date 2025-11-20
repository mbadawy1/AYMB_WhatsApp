"""Tests for resolver scoring helpers."""

from src.resolvers.scoring import _score_ext, _score_mtime, _score_seq


def test_ext_priority_ordering_default():
    """Default ext priority should order voice > image > video > document > other."""
    scores = {
        "voice": _score_ext("voice"),
        "image": _score_ext("image"),
        "video": _score_ext("video"),
        "document": _score_ext("document"),
        "other": _score_ext("other"),
    }
    assert scores["voice"] > scores["image"] > scores["video"] > scores["document"] > scores["other"]


def test_ext_priority_custom():
    """Custom ext priority should reflect provided ordering."""
    custom = ("image", "video", "voice")
    scores = {t: _score_ext(t, custom) for t in custom}
    assert scores["image"] > scores["video"] > scores["voice"]
    assert _score_ext("document", custom) == 0.0


def test_score_seq_prefers_closest():
    """Sequence scoring should reward proximity."""
    assert _score_seq(10, 10) == 1.0
    assert _score_seq(10, 11) > _score_seq(10, 20)
    assert _score_seq(None, 5) == 0.1
    assert _score_seq(5, None) == 0.0


def test_score_mtime_prefers_closest():
    """Mtime scoring should decay with distance."""
    assert _score_mtime(0) == 1.0
    assert _score_mtime(10) > _score_mtime(100)
    assert _score_mtime(-5) == _score_mtime(5)
