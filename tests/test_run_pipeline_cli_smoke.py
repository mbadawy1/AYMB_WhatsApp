import sys
from pathlib import Path

import scripts.run_pipeline as run_pipeline_script


def test_run_pipeline_cli_smoke(tmp_path, pipeline_sample_root, stub_transcriber, monkeypatch):
    run_dir = tmp_path / "cli-run"
    args = [
        "run_pipeline.py",
        "--root",
        str(pipeline_sample_root),
        "--run-dir",
        str(run_dir),
        "--run-id",
        "cli-test",
        "--max-workers-audio",
        "2",
        "--no-resume",
    ]
    monkeypatch.setattr(sys, "argv", args)
    exit_code = run_pipeline_script.main()
    assert exit_code == 0
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "metrics.json").exists()
