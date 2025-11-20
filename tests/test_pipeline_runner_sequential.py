import json
from pathlib import Path

from src.pipeline.config import PipelineConfig
from src.pipeline.runner import run_pipeline
from src.pipeline.outputs import load_messages


def test_pipeline_runner_sequential_happy_path(tmp_path, pipeline_sample_root, stub_transcriber):
    run_dir = tmp_path / "run"
    cfg = PipelineConfig(root=pipeline_sample_root, run_dir=run_dir, max_workers_audio=1, resume=False)
    result = run_pipeline(cfg)

    manifest_path = Path(result["manifest_path"])
    metrics_path = Path(result["metrics_path"])

    assert manifest_path.exists()
    assert metrics_path.exists()
    assert (run_dir / "messages.M1.jsonl").exists()
    assert (run_dir / "messages.M2.jsonl").exists()
    assert (run_dir / "messages.M3.jsonl").exists()
    assert (run_dir / "chat_with_audio.txt").exists()
    assert (run_dir / "preview_transcripts.txt").exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert all(step["status"] == "ok" for step in manifest["steps"].values())
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["voice_total"] == 1
    assert metrics["media_resolution"]["resolved"] >= 1
    assert len(stub_transcriber) == 1

    messages_m3 = load_messages(run_dir / "messages.M3.jsonl")
    assert any(m.kind == "voice" and "voice-" in m.content_text for m in messages_m3)
