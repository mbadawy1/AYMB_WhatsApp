import json
from pathlib import Path

from src.pipeline.manifest import build_manifest, write_manifest
from src.pipeline.metrics import compute_metrics, write_metrics
from src.pipeline.materialize import materialize_run
from src.pipeline.validation import validate_jsonl, SchemaValidationError
from src.schema.message import Message


def _make_msg(idx: int, kind: str, status: str = "ok") -> Message:
    return Message(
        idx=idx,
        ts="2025-01-01T00:00:00",
        sender="Alice",
        kind=kind,
        content_text="",
        raw_line="",
        raw_block="",
        media_hint=None,
        media_filename=None,
        caption=None,
        status=status,
    )


def test_manifest_and_metrics_roundtrip(tmp_path):
    m1 = [_make_msg(0, "text"), _make_msg(1, "voice")]
    m2 = m1
    m3 = [_make_msg(0, "text"), _make_msg(1, "voice", status="partial")]

    inputs = {"messages_m1": "m1.jsonl", "messages_m2": "m2.jsonl", "messages_m3": "m3.jsonl"}
    outputs = {"chat_with_audio": "chat.txt", "preview_transcripts": None, "manifest": "manifest.json", "metrics": "metrics.json"}

    manifest = build_manifest("run-1", m1, m2, m3, inputs=inputs, outputs=outputs)
    manifest_path = tmp_path / "run_manifest.json"
    write_manifest(manifest, manifest_path)
    loaded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded_manifest["summary"]["messages_total"] == 2
    assert loaded_manifest["summary"]["voice_total"] == 1

    metrics = compute_metrics(m3)
    metrics_path = tmp_path / "metrics.json"
    write_metrics(metrics, metrics_path)
    loaded_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert loaded_metrics["messages_total"] == 2
    assert loaded_metrics["voice_total"] == 1


def test_materialize_run_writes_outputs(tmp_path):
    msgs = [
        _make_msg(0, "text"),
        _make_msg(1, "voice"),
    ]
    run_dir = tmp_path / "run"
    summary = materialize_run("run-2", run_dir, msgs, msgs, msgs)
    assert (run_dir / "messages.M1.jsonl").exists()
    assert (run_dir / "messages.M2.jsonl").exists()
    assert (run_dir / "messages.M3.jsonl").exists()
    assert (run_dir / "chat_with_audio.txt").exists()
    assert (run_dir / "preview_transcripts.txt").exists()
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "metrics.json").exists()
    assert summary["preview_count"] >= 0

    validate_jsonl(run_dir / "messages.M1.jsonl")
    validate_jsonl(run_dir / "messages.M2.jsonl")
    validate_jsonl(run_dir / "messages.M3.jsonl")
