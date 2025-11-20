from pathlib import Path

from src.pipeline.runner import run_contract_pipeline


def test_run_contract_pipeline_text_only(tmp_path):
    root = Path("tests/fixtures/text_only")
    run_dir = tmp_path / "run"
    summary = run_contract_pipeline(root, run_dir, "run-test")
    assert (run_dir / "messages.M1.jsonl").exists()
    assert (run_dir / "messages.M2.jsonl").exists()
    assert (run_dir / "messages.M3.jsonl").exists()
    assert (run_dir / "chat_with_audio.txt").exists()
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "metrics.json").exists()
    assert summary["outputs"]["manifest"].endswith("run_manifest.json")
