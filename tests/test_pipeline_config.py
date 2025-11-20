from argparse import Namespace

import pytest

from src.pipeline.config import PipelineConfig


def test_pipeline_config_root_paths(tmp_path):
    root = tmp_path / "Export Chat"
    root.mkdir()
    chat = root / "_chat.txt"
    chat.write_text("7/8/25, 14:23 - Alice: hi\n", encoding="utf-8")

    cfg = PipelineConfig(root=root)
    cfg.validate()

    assert cfg.run_id == "export-chat"
    assert cfg.run_dir == (root / "runs" / "export-chat").resolve()
    assert cfg.chat_file == chat.resolve()
    assert cfg.messages_path("M1").name == "messages.M1.jsonl"
    assert cfg.chat_output_path.name == "chat_with_audio.txt"


def test_pipeline_config_from_args_allows_overrides(tmp_path):
    root = tmp_path / "chat"
    root.mkdir()
    chat = root / "custom.txt"
    chat.write_text("7/8/25, 14:23 - Alice: hi\n", encoding="utf-8")

    ns = Namespace(
        root=str(root),
        chat_file=str(chat),
        run_id="My Run",
        run_dir=str(tmp_path / "run-dir"),
        max_workers_audio=4,
        asr_provider="whisper",
        asr_model="tiny",
        asr_language="en",
        sample_limit=5,
        sample_every=2,
        no_resume=True,
    )
    cfg = PipelineConfig.from_args(ns)
    cfg.validate()

    assert cfg.run_id == "my-run"
    assert cfg.run_dir == (tmp_path / "run-dir").resolve()
    assert cfg.chat_file == chat.resolve()
    assert cfg.max_workers_audio == 4
    assert cfg.sample_limit == 5
    assert cfg.sample_every == 2
    assert cfg.resume is False


def test_pipeline_config_rejects_invalid_sampling(tmp_path):
    root = tmp_path / "chat"
    root.mkdir()
    (root / "_chat.txt").write_text("7/8/25, 14:23 - Alice: hi\n", encoding="utf-8")
    with pytest.raises(ValueError):
        PipelineConfig(root=root, sample_every=0)
    with pytest.raises(ValueError):
        PipelineConfig(root=root, sample_limit=0)
