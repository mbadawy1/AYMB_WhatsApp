import shutil
from pathlib import Path
from typing import List

import pytest


@pytest.fixture
def pipeline_sample_root(tmp_path: Path) -> Path:
    """Copy the pipeline_small_chat fixture into a temp directory for mutation."""
    src = Path("tests/fixtures/pipeline_small_chat")
    dst = tmp_path / "chat"
    shutil.copytree(src, dst)
    return dst


@pytest.fixture
def stub_transcriber(monkeypatch) -> List[int]:
    """Patch AudioTranscriber with a deterministic stub and record calls."""
    calls: List[int] = []

    class StubTranscriber:
        pipeline_version = "stub-m3"

        def __init__(self, cfg=None) -> None:
            self.cfg = cfg

        def transcribe(self, msg):
            if msg.kind != "voice":
                return
            calls.append(msg.idx)
            msg.content_text = f"voice-{msg.idx}"
            msg.status = "ok"
            msg.partial = False
            msg.status_reason = None
            msg.derived["asr"] = {
                "pipeline_version": self.pipeline_version,
                "provider": getattr(self.cfg, "asr_provider", "stub"),
                "model": getattr(self.cfg, "asr_model", None),
                "total_duration_seconds": 1.0,
                "cost": 0.001,
            }

    monkeypatch.setattr("src.pipeline.runner.AudioTranscriber", StubTranscriber)
    return calls
