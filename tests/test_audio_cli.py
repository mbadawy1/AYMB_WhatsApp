import os
import subprocess
import sys
from pathlib import Path


def test_smoke_cli_audio_transcriber():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "transcribe_audio.py"
    fixtures = repo_root / "tests" / "fixtures" / "text_only"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)

    result = subprocess.run(
        [sys.executable, str(script), "--root", str(fixtures)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Audio transcription summary" in result.stdout
