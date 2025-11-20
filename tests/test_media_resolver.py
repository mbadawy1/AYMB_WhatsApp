"""Smoke tests for MediaResolver skeleton."""

from pathlib import Path

from src.media_resolver import MediaResolver, ResolverConfig
from src.indexer.media_index import FileInfo
from src.writers.exceptions_csv import write_exceptions
from src.schema.message import Message


def test_media_resolver_instantiates(tmp_path):
    """Ensure MediaResolver can be constructed."""
    resolver = MediaResolver(root=tmp_path)
    assert resolver.root == Path(tmp_path)
    assert isinstance(resolver.cfg, ResolverConfig)


def test_rank_candidates_stub(tmp_path):
    """_rank_candidates returns empty list for now."""
    resolver = MediaResolver(root=tmp_path)
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Test", kind="text")
    ranked = resolver._rank_candidates(msg, [], set(), None)
    assert ranked == []


def test_map_media_noop(tmp_path):
    """map_media stub should not mutate messages."""
    resolver = MediaResolver(root=tmp_path)
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Test", kind="text")
    msgs = [msg]
    resolver.map_media(msgs)
    assert msgs[0].media_filename is None
    assert msgs[0].status == "ok"


def test_hints_prefer_same_sender(tmp_path):
    resolver = MediaResolver(root=tmp_path)
    msgs = [
        Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="text", content_text="See photo WA-0012"),
        Message(idx=1, ts="2025-01-01T00:01:00", sender="Alice", kind="text", content_text="IMG-20250101-WA0099.jpg attached"),
        Message(idx=2, ts="2025-01-01T00:02:00", sender="Bob", kind="text", content_text="Check VID-20250101-WA7777.mp4"),
    ]
    hints = resolver._extract_hints(msgs, 1)
    assert any("img" in h or "wa" in h for h in hints)
    # Should prefer same sender tokens (includes IMG token)
    assert any("img-20250101-wa0099" in h for h in hints)


def test_hints_from_captions_and_global(tmp_path):
    resolver = MediaResolver(root=tmp_path)
    msgs = [
        Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="image", content_text="", caption="See doc DOC-20250101-WA0001.pdf"),
        Message(idx=1, ts="2025-01-01T00:01:00", sender="Bob", kind="text", content_text="Nearby hint WA-0420"),
        Message(idx=2, ts="2025-01-01T00:02:00", sender="Carol", kind="text", content_text="Unrelated"),
    ]
    hints = resolver._extract_hints(msgs, 2)
    assert "wa-0420" in hints or any("wa" in h for h in hints)


def test_rank_candidates_prefers_hint_and_mtime(tmp_path, monkeypatch):
    resolver = MediaResolver(root=tmp_path)
    msgs = [
        Message(idx=0, ts="2025-01-01T00:00:10", sender="Alice", kind="image", content_text="See IMG-20250101-WA0001.jpg"),
    ]

    # Create two candidates
    f1 = tmp_path / "IMG-20250101-WA0001.jpg"
    f1.write_bytes(b"a")
    f2 = tmp_path / "IMG-20250101-WA0002.jpg"
    f2.write_bytes(b"a")

    # Adjust mtimes: f1 closer to message ts
    import time, os
    base = time.time()
    os.utime(f1, (base + 1, base + 1))
    os.utime(f2, (base + 100, base + 100))

    index = {
        ("2025-01-01", "image"): [
            FileInfo(path=f1, size=f1.stat().st_size, mtime=f1.stat().st_mtime, name_tokens=["img", "20250101", "wa0001"], seq_num=1),
            FileInfo(path=f2, size=f2.stat().st_size, mtime=f2.stat().st_mtime, name_tokens=["img", "20250101", "wa0002"], seq_num=2),
        ]
    }

    hints = resolver._extract_hints(msgs, 0)
    ranked = resolver._rank_candidates(msgs[0], index[("2025-01-01", "image")], hints, resolver._extract_seq_target(msgs[0], hints))
    assert ranked[0][0].name == f1.name


def test_filename_fastpath(tmp_path):
    resolver = MediaResolver(root=tmp_path)
    f = tmp_path / "IMG-20250101-WA0001.jpg"
    f.write_bytes(b"a")
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="image", media_hint=f.name, content_text="")
    resolver.map_media([msg])
    assert msg.media_filename.endswith(f.name)
    assert msg.status_reason is None


def test_unresolved_sets_status_reason(tmp_path):
    resolver = MediaResolver(root=tmp_path)
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="image", content_text="")
    resolver.map_media([msg])
    assert msg.media_filename is None
    assert msg.status_reason is not None
    assert msg.status_reason.code == "unresolved_media"


def test_ambiguous_logs_exceptions_csv(tmp_path, monkeypatch):
    resolver = MediaResolver(root=tmp_path, cfg=ResolverConfig(decisive_tau=1.0))
    # Two identical candidates to force ambiguity
    f1 = tmp_path / "IMG-20250101-WA0001.jpg"
    f2 = tmp_path / "IMG-20250101-WA0002.jpg"
    f1.write_bytes(b"a")
    f2.write_bytes(b"a")
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="image", content_text="")

    # Monkeypatch indexer to return our files with matching mtime
    base_ts = 1735689600.0  # 2025-01-01T00:00:00 epoch

    def fake_scan_media(root):
        return {
            ("2025-01-01", "image"): [
                FileInfo(path=f1, size=1, mtime=base_ts, name_tokens=["img", "20250101"], seq_num=None, sha256=None),
                FileInfo(path=f2, size=1, mtime=base_ts, name_tokens=["img", "20250101"], seq_num=None, sha256=None),
            ]
        }

    monkeypatch.setattr("src.media_resolver._scan_media", fake_scan_media)

    resolver.map_media([msg])
    exceptions_path = Path("exceptions.csv")
    assert exceptions_path.exists()
    content = exceptions_path.read_text(encoding="utf-8")
    assert "ambiguous_media" in content
    assert msg.status_reason is not None
    assert msg.status_reason.code == "ambiguous_media"
    assert "disambiguation" in msg.derived
