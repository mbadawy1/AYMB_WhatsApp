from src.pipeline.metrics import RunMetrics, compute_metrics
from src.schema.message import Message


def _voice(idx: int, status: str = "ok") -> Message:
    msg = Message(idx=idx, ts="2025-01-01T00:00:00", sender="Bob", kind="voice")
    msg.status = status
    msg.derived["asr"] = {
        "pipeline_version": "stub",
        "provider": "whisper",
        "model": "tiny",
        "language_hint": "auto",
        "total_duration_seconds": 2.5,
        "cost": 0.01,
    }
    return msg


def test_run_metrics_aggregates_counts():
    m1 = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="text")
    m2 = _voice(1, status="partial")
    m3 = _voice(2, status="failed")

    metrics = RunMetrics()
    metrics.record_messages([m1, m2, m3])
    metrics.record_media_resolution([m1, m2, m3])
    metrics.record_audio([m1, m2, m3])
    metrics.wall_clock_seconds = 1.23

    data = metrics.to_dict()
    assert data["messages_total"] == 3
    assert data["voice_total"] == 2
    assert data["voice_status"]["partial"] == 1
    assert data["audio_seconds_total"] == 5.0
    assert data["asr_cost_total_usd"] == 0.02
    assert data["asr_provider"] == "whisper"
    assert data["asr_model"] == "tiny"
    assert data["asr_language"] == "auto"


def test_compute_metrics_backcompat():
    msg = _voice(0, status="ok")
    payload = compute_metrics([msg])
    assert payload["voice_total"] == 1
    assert payload["asr_provider"] == "whisper"
