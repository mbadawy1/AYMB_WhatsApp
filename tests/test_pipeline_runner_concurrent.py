from pathlib import Path

from src.pipeline.config import PipelineConfig
from src.pipeline.runner import run_pipeline


def test_pipeline_runner_concurrent_matches_sequential(tmp_path, pipeline_sample_root, stub_transcriber):
    run_seq = tmp_path / "run_seq"
    cfg_seq = PipelineConfig(root=pipeline_sample_root, run_dir=run_seq, max_workers_audio=1, resume=False)
    result_seq = run_pipeline(cfg_seq)
    m3_seq = Path(result_seq["outputs"]["messages_m3"]).read_text(encoding="utf-8")

    run_conc = tmp_path / "run_conc"
    cfg_conc = PipelineConfig(root=pipeline_sample_root, run_dir=run_conc, max_workers_audio=4, resume=False)
    result_conc = run_pipeline(cfg_conc)
    m3_conc = Path(result_conc["outputs"]["messages_m3"]).read_text(encoding="utf-8")

    assert m3_seq == m3_conc
    assert Path(result_conc["outputs"]["chat_with_audio"]).read_text(encoding="utf-8") == Path(
        result_seq["outputs"]["chat_with_audio"]
    ).read_text(encoding="utf-8")
