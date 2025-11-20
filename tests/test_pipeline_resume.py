import json
from pathlib import Path

from src.pipeline.config import PipelineConfig
from src.pipeline.runner import run_pipeline


def test_pipeline_resume_skips_completed_steps(tmp_path, pipeline_sample_root, stub_transcriber):
    run_dir = tmp_path / "run"
    cfg = PipelineConfig(root=pipeline_sample_root, run_dir=run_dir, max_workers_audio=1, resume=True)

    first_result = run_pipeline(cfg)
    manifest_path = Path(first_result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["steps"]["M3_audio"]["status"] == "ok"
    first_calls = len(stub_transcriber)

    # Re-run with resume; should skip all work (no additional transcriber calls)
    second_result = run_pipeline(cfg)
    assert len(stub_transcriber) == first_calls
    manifest2 = json.loads(Path(second_result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest2["summary"]["messages_total"] == manifest["summary"]["messages_total"]
