"""Tests for media resolver configuration defaults."""

from src.media_resolver import MediaResolver


def test_loads_defaults_from_config():
    resolver = MediaResolver(root=".")
    cfg = resolver.cfg
    assert cfg.ladder_weights == (3.0, 2.0, 1.0, 1.0)
    assert cfg.decisive_tau == 0.75
    assert cfg.tie_margin == 0.02
    assert cfg.ext_priority == ("voice", "image", "video", "document", "other")
