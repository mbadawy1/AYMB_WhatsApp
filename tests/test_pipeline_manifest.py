from pathlib import Path

from src.pipeline.config import PipelineConfig
from src.pipeline.manifest import (
    DEFAULT_STEPS,
    build_manifest,
    finalize_manifest,
    init_manifest,
    set_summary,
    update_step,
)


def test_manifest_initial_structure(tmp_path):
    root = tmp_path / "chat"
    root.mkdir()
    (root / "_chat.txt").write_text("7/8/25, 14:23 - Alice: hi\n", encoding="utf-8")
    cfg = PipelineConfig(root=root)
    manifest = init_manifest(cfg)

    assert manifest.schema_version == "1.0.0"
    assert manifest.summary["resume_enabled"] is True
    for step in DEFAULT_STEPS:
        assert manifest.steps[step].status == "pending"

    update_step(manifest, "M1_parse", status="running", total=3)
    set_summary(manifest, messages_total=3, voice_total=1, error=None)
    finalize_manifest(manifest)
    assert manifest.steps["M1_parse"].status == "running"
    assert manifest.summary["messages_total"] == 3
    assert manifest.end_time is not None


def test_build_manifest_for_contracts(tmp_path):
    from src.schema.message import Message

    msgs = [
        Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="text"),
        Message(idx=1, ts="2025-01-01T00:00:10", sender="Bob", kind="voice"),
    ]

    inputs = {"messages_m1": "m1.jsonl"}
    outputs = {"manifest": str(tmp_path / "run_manifest.json"), "metrics": str(tmp_path / "metrics.json")}

    manifest = build_manifest("run-1", msgs, msgs, msgs, inputs=inputs, outputs=outputs)
    assert manifest.summary["messages_total"] == 2
    assert manifest.summary["voice_total"] == 1
    assert manifest.steps["M3_audio"].status == "ok"
