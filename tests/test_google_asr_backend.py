"""Tests for Google STT backend helpers."""

import pytest

from src.utils.asr import AsrConfigError, AsrProviderConfig, GoogleSttBackend


def make_google_cfg(api_version: str = "v1") -> AsrProviderConfig:
    return AsrProviderConfig(
        name="google_stt",
        backend="google_stub",
        model="chirp-3",
        timeout_seconds=30,
        max_retries=1,
        billing="google_stt_standard",
        language="ar-EG",
        api_version=api_version,
    )


def test_google_backend_v2_requires_project(monkeypatch, tmp_path):
    cfg = make_google_cfg(api_version="v2")
    backend = GoogleSttBackend(cfg)

    # Ensure no project envs leak in
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCLOUD_PROJECT", raising=False)

    # Provide creds file without project_id
    fake_creds = tmp_path / "creds.json"
    fake_creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(fake_creds))

    with pytest.raises(AsrConfigError):
        backend._build_model_identifier("chirp")


def test_google_backend_v2_builds_full_model_path(monkeypatch):
    cfg = make_google_cfg(api_version="v2")
    backend = GoogleSttBackend(cfg)

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sample-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    model_name = backend._build_model_identifier("chirp")
    assert model_name == "projects/sample-project/locations/us-central1/models/chirp"
