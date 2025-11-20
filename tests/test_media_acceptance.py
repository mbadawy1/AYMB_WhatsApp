"""Acceptance-style tests for media resolver easy/ambiguous fixtures."""

import os
import shutil
from pathlib import Path

import pytest

from src.media_resolver import MediaResolver
from src.parser_agent import ParserAgent
from src.schema.message import Message
from src.utils.hashing import sha256_file


def _prepare_fixture(root: Path):
    # Ensure clean exceptions.csv
    exceptions = Path("exceptions.csv")
    if exceptions.exists():
        exceptions.unlink()


def test_easy_fixture_resolution(tmp_path, monkeypatch):
    fixture_root = Path(__file__).parent / "fixtures" / "media_easy"
    # Copy fixture to tmp to avoid mutating timestamps
    run_root = tmp_path / "easy"
    shutil.copytree(fixture_root, run_root)

    agent = ParserAgent(root=str(run_root))
    msgs = agent.parse()

    resolver = MediaResolver(root=run_root)
    resolver.map_media(msgs)

    resolved = [m for m in msgs if m.media_filename]
    assert len(resolved) == 3  # all resolved
    for msg in resolved:
        assert msg.status_reason is None
        assert msg.derived.get("media_sha256") is not None


def test_ambiguous_yields_csv_and_no_assignment(tmp_path, monkeypatch):
    fixture_root = Path(__file__).parent / "fixtures" / "media_ambiguous"
    run_root = tmp_path / "ambiguous"
    shutil.copytree(fixture_root, run_root)

    agent = ParserAgent(root=str(run_root))
    msgs = agent.parse()

    resolver = MediaResolver(root=run_root, cfg=None)
    resolver.map_media(msgs)

    msg = msgs[0]
    assert msg.media_filename is None
    assert msg.status_reason is not None
    assert msg.status_reason.code in {"ambiguous_media", "unresolved_media"}
    # Exceptions CSV should exist
    assert Path("exceptions.csv").exists()
    content = Path("exceptions.csv").read_text(encoding="utf-8")
    assert msg.status_reason.code in content


def test_hashing_streaming():
    path = Path(__file__).parent / "fixtures" / "media_easy" / "IMG-20250101-WA0001.jpg"
    expected = sha256_file(path)
    assert len(expected) == 64  # hex digest length


def test_media_hash_in_outputs(tmp_path):
    fixture_root = Path(__file__).parent / "fixtures" / "media_easy"
    run_root = tmp_path / "easy2"
    shutil.copytree(fixture_root, run_root)

    agent = ParserAgent(root=str(run_root))
    msgs = agent.parse()
    resolver = MediaResolver(root=run_root)
    resolver.map_media(msgs)

    for msg in msgs:
        if msg.media_filename:
            assert msg.derived.get("media_sha256")
