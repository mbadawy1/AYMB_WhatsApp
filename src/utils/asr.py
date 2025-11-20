"""ASR client abstraction used by the audio pipeline."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Protocol

import yaml

from src.schema.message import StatusReason

logger = logging.getLogger(__name__)


# Error classification for ASR operations
AsrErrorKind = Literal["timeout", "auth", "quota", "client", "server", "unknown"]


def map_asr_error_to_status_reason(kind: AsrErrorKind) -> StatusReason:
    """
    Map ASR error kinds to StatusReason codes.

    Args:
        kind: The type of ASR error encountered.

    Returns:
        Appropriate StatusReason for the error type.
    """
    if kind == "timeout":
        return StatusReason.from_code("timeout_asr")
    # All other errors map to asr_failed
    return StatusReason.from_code("asr_failed")


def classify_asr_error(exception: Exception) -> AsrErrorKind:
    """
    Classify an exception into an AsrErrorKind.

    Args:
        exception: The exception to classify.

    Returns:
        The classified error kind.
    """
    error_str = str(exception).lower()
    error_type = type(exception).__name__.lower()

    # Timeout detection
    if "timeout" in error_str or "timeout" in error_type:
        return "timeout"

    # Authentication errors
    if any(word in error_str for word in ["auth", "unauthorized", "401", "api key", "invalid_api_key"]):
        return "auth"

    # Quota/rate limit errors
    if any(word in error_str for word in ["quota", "rate limit", "429", "exceeded"]):
        return "quota"

    # Client errors (4xx)
    if any(word in error_str for word in ["400", "bad request", "invalid"]):
        return "client"

    # Server errors (5xx)
    if any(word in error_str for word in ["500", "502", "503", "504", "server error", "internal"]):
        return "server"

    return "unknown"


@dataclass
class AsrChunkResult:
    status: str  # "ok" | "error"
    text: str
    start_sec: float
    end_sec: float
    duration_sec: float
    language: Optional[str] = None
    error: Optional[str] = None
    error_kind: Optional[AsrErrorKind] = None
    provider_meta: Optional[Dict] = None


@dataclass(frozen=True)
class AsrProviderConfig:
    """Resolved ASR provider configuration."""

    name: str
    backend: str
    model: str
    timeout_seconds: int
    max_retries: int
    billing: str
    language: str
    api_version: Optional[str]


class AsrConfigError(RuntimeError):
    """Raised when ASR provider configuration is invalid."""


class AsrProvider(Protocol):
    """Interface implemented by ASR backends."""

    def transcribe_chunk(self, wav_path: Path, start_sec: float, end_sec: float) -> AsrChunkResult:
        ...


ASR_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "asr.yaml"


def _default_asr_config() -> dict[str, Any]:
    return {
        "default_provider": "whisper_openai",
        "providers": {
            "whisper_openai": {
                "backend": "whisper_stub",
                "model": "whisper-1",
                "available_models": ["whisper-1", "whisper-large-v3"],
                "timeout_seconds": 30,
                "max_retries": 2,
                "billing": "openai_whisper_v1",
                "default_language": "auto",
                "languages": [
                    {"code": "auto", "label": "Auto detect"},
                    {"code": "en", "label": "English"},
                    {"code": "ar", "label": "Arabic"},
                    {"code": "es", "label": "Spanish"},
                ],
                "api_versions": [],
                "require_env": False,
            }
        },
    }


@lru_cache()
def _load_asr_config() -> dict[str, Any]:
    if ASR_CONFIG_PATH.exists():
        with ASR_CONFIG_PATH.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or _default_asr_config()
    return _default_asr_config()


def _select_backend(provider_name: str, env_key: Optional[str]) -> str:
    """Auto-select real backend if API key available, else stub.

    Args:
        provider_name: The provider config name (e.g., 'whisper_openai')
        env_key: Environment variable name for API key

    Returns:
        Backend identifier to use
    """
    # Map providers to their real and stub backends
    real_backends = {
        "whisper_openai": "whisper_openai_real",
        "google_stt": "google_stt_real",
    }
    stub_backends = {
        "whisper_openai": "whisper_stub",
        "whisper_local": "whisper_stub",
        "google_stt": "google_stub",
    }

    # Check if API key exists
    has_key = bool(env_key and os.getenv(env_key))

    # Select backend based on key availability
    if has_key and provider_name in real_backends:
        backend = real_backends[provider_name]
        logger.info(f"ASR: Using real backend '{backend}' for '{provider_name}' (API key found)")
    elif provider_name in stub_backends:
        backend = stub_backends[provider_name]
        if provider_name in real_backends:
            logger.info(f"ASR: Using stub backend '{backend}' for '{provider_name}' (no API key)")
        else:
            logger.info(f"ASR: Using backend '{backend}' for '{provider_name}'")
    else:
        # Fallback to provider name as backend
        backend = provider_name
        logger.info(f"ASR: Using default backend '{backend}'")

    return backend


def resolve_asr_provider_config(
    provider_name: Optional[str],
    *,
    model_override: Optional[str] = None,
    language_override: Optional[str] = None,
    api_version_override: Optional[str] = None,
) -> AsrProviderConfig:
    """Resolve provider configuration from config/asr.yaml and overrides."""

    config = _load_asr_config()
    providers = config.get("providers") or {}
    name = provider_name or config.get("default_provider")
    if not name or name not in providers:
        raise AsrConfigError(f"Unknown ASR provider '{provider_name}'")

    provider_cfg = providers[name] or {}
    backend = provider_cfg.get("backend") or name

    model = model_override or provider_cfg.get("model")
    if not model:
        raise AsrConfigError(f"Provider '{name}' is missing a default model")

    language = language_override or provider_cfg.get("default_language") or "auto"
    env_key = provider_cfg.get("env_key")
    require_env = bool(provider_cfg.get("require_env"))
    if require_env and env_key and not os.getenv(env_key):
        raise AsrConfigError("Provider '{name}' requires environment variable '{env_key}'")

    api_versions = provider_cfg.get("api_versions") or []
    default_api_version = provider_cfg.get("default_api_version") or (api_versions[0] if api_versions else None)
    api_version = api_version_override or default_api_version

    return AsrProviderConfig(
        name=name,
        backend=backend,
        model=model,
        timeout_seconds=int(provider_cfg.get("timeout_seconds", 30)),
        max_retries=int(provider_cfg.get("max_retries", 1)),
        billing=provider_cfg.get("billing", "per_minute"),
        language=language,
        api_version=api_version,
    )

def get_asr_provider_options() -> Dict[str, Dict[str, Any]]:
    """Return provider metadata (models, languages, api versions) for UI usage."""

    config = _load_asr_config()
    providers: Dict[str, Dict[str, Any]] = {}
    for name, data in (config.get("providers") or {}).items():
        display_name = data.get("display_name") or name.replace("_", " " ).title()
        providers[name] = {
            "name": display_name,
            "models": data.get("available_models") or ([data.get("model")] if data.get("model") else []),
            "default_model": data.get("model"),
            "languages": data.get("languages") or [{"code": data.get("default_language", "auto"), "label": data.get("default_language", "auto")}],
            "default_language": data.get("default_language", "auto"),
            "api_versions": data.get("api_versions") or [],
            "default_api_version": data.get("default_api_version"),
        }
    return providers



def get_default_provider_name() -> Optional[str]:
    """Return the default provider name from configuration."""
    config = _load_asr_config()
    return config.get("default_provider")


class WhisperStubProvider:
    """Deterministic stub backend simulating Whisper/OpenAI responses."""

    def __init__(self, config: AsrProviderConfig) -> None:
        self.config = config

    def transcribe_chunk(self, wav_path: Path, start_sec: float, end_sec: float) -> AsrChunkResult:
        duration = max(0.0, end_sec - start_sec)
        if "fail" in wav_path.name:
            return AsrChunkResult(
                status="error",
                text="",
                start_sec=start_sec,
                end_sec=end_sec,
                duration_sec=duration,
                language=self.config.language,
                error="simulated_failure",
                error_kind="unknown",
                provider_meta={"provider": self.config.name, "model": self.config.model},
            )
        text = f"{self.config.model}-chunk-{start_sec:.2f}-{end_sec:.2f}"
        return AsrChunkResult(
            status="ok",
            text=text,
            start_sec=start_sec,
            end_sec=end_sec,
            duration_sec=duration,
            language=self.config.language,
            provider_meta={"provider": self.config.name, "model": self.config.model},
        )


class GoogleStubProvider(WhisperStubProvider):
    """Google STT stub backend (inherits deterministic behavior)."""

    def transcribe_chunk(self, wav_path: Path, start_sec: float, end_sec: float) -> AsrChunkResult:
        result = super().transcribe_chunk(wav_path, start_sec, end_sec)
        if result.status == "ok":
            result.text = f"{self.config.model}-google-{start_sec:.2f}-{end_sec:.2f}"
        return result


class WhisperOpenAIBackend:
    """Real Whisper backend using OpenAI API.

    Based on official OpenAI Python documentation:
    https://github.com/openai/openai-python
    """

    def __init__(self, config: AsrProviderConfig) -> None:
        self.config = config
        self._client = None

    def _get_client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI()
            except ImportError:
                raise AsrConfigError("openai package not installed. Run: pip install openai")
        return self._client

    def transcribe_chunk(self, wav_path: Path, start_sec: float, end_sec: float) -> AsrChunkResult:
        duration = max(0.0, end_sec - start_sec)
        meta = {"provider": self.config.name, "model": self.config.model}

        for attempt in range(self.config.max_retries):
            try:
                client = self._get_client()

                with open(wav_path, "rb") as audio_file:
                    # Use verbose_json to get language detection info
                    # Language parameter uses ISO-639-1 codes (e.g., "en", "ar", "es")
                    if self.config.language and self.config.language != "auto":
                        response = client.audio.transcriptions.create(
                            model=self.config.model,
                            file=audio_file,
                            response_format="verbose_json",
                            language=self.config.language,
                            timeout=self.config.timeout_seconds,
                        )
                    else:
                        # Let Whisper auto-detect language
                        response = client.audio.transcriptions.create(
                            model=self.config.model,
                            file=audio_file,
                            response_format="verbose_json",
                            timeout=self.config.timeout_seconds,
                        )

                # Extract detected language from verbose response
                detected_lang = getattr(response, 'language', None) or self.config.language

                return AsrChunkResult(
                    status="ok",
                    text=response.text,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    duration_sec=duration,
                    language=detected_lang,
                    provider_meta={
                        **meta,
                        "detected_language": detected_lang,
                        "audio_duration": getattr(response, 'duration', None),
                    },
                )

            except Exception as e:
                error_kind = classify_asr_error(e)
                if attempt == self.config.max_retries - 1:
                    return AsrChunkResult(
                        status="error",
                        text="",
                        start_sec=start_sec,
                        end_sec=end_sec,
                        duration_sec=duration,
                        language=self.config.language,
                        error=str(e)[:500],
                        error_kind=error_kind,
                        provider_meta=meta,
                    )
                # Retry on certain errors
                if error_kind in ("server", "timeout"):
                    continue
                # Don't retry auth/quota/client errors
                return AsrChunkResult(
                    status="error",
                    text="",
                    start_sec=start_sec,
                    end_sec=end_sec,
                    duration_sec=duration,
                    language=self.config.language,
                    error=str(e)[:500],
                    error_kind=error_kind,
                    provider_meta=meta,
                )

        # Should not reach here
        return AsrChunkResult(
            status="error",
            text="",
            start_sec=start_sec,
            end_sec=end_sec,
            duration_sec=duration,
            language=self.config.language,
            error="max retries exceeded",
            error_kind="unknown",
            provider_meta=meta,
        )


class GoogleSttBackend:
    """Real Google Speech-to-Text backend.

    Based on official Google Cloud Speech-to-Text documentation:
    https://cloud.google.com/speech-to-text/docs/sync-recognize

    Note: Requires GOOGLE_APPLICATION_CREDENTIALS env var pointing to
    a service account JSON file.
    """

    # Map ISO-639-1 codes to BCP-47 language codes for Google STT
    LANGUAGE_CODE_MAP = {
        "en": "en-US",
        "ar": "ar-SA",  # Arabic (Saudi Arabia)
        "es": "es-ES",
        "fr": "fr-FR",
        "de": "de-DE",
        "it": "it-IT",
        "pt": "pt-BR",
        "ru": "ru-RU",
        "zh": "zh-CN",
        "ja": "ja-JP",
        "ko": "ko-KR",
        "hi": "hi-IN",
        "auto": "en-US",  # Default fallback
    }

    def __init__(self, config: AsrProviderConfig) -> None:
        self.config = config
        self._client = None

    def _get_client(self):
        """Lazy-load Google Speech client."""
        if self._client is None:
            try:
                from google.cloud import speech
                self._client = speech.SpeechClient()
            except ImportError:
                raise AsrConfigError(
                    "google-cloud-speech package not installed. "
                    "Run: pip install google-cloud-speech"
                )
        return self._client

    def _get_language_code(self) -> str:
        """Convert language hint to BCP-47 format for Google STT."""
        lang = self.config.language or "auto"

        # If already in BCP-47 format (contains hyphen), use as-is
        if "-" in lang:
            return lang

        # Map ISO-639-1 to BCP-47
        return self.LANGUAGE_CODE_MAP.get(lang, f"{lang}-US" if len(lang) == 2 else "en-US")

    def transcribe_chunk(self, wav_path: Path, start_sec: float, end_sec: float) -> AsrChunkResult:
        duration = max(0.0, end_sec - start_sec)
        meta = {
            "provider": self.config.name,
            "model": self.config.model,
            "api_version": self.config.api_version or "v1",
        }

        for attempt in range(self.config.max_retries):
            try:
                from google.cloud import speech

                client = self._get_client()

                # Read audio file content
                with open(wav_path, "rb") as audio_file:
                    content = audio_file.read()

                audio = speech.RecognitionAudio(content=content)

                # Build recognition config per Google docs
                language_code = self._get_language_code()

                # Map model names to Google's model identifiers
                # For V1 API: use model parameter in RecognitionConfig
                model_map = {
                    "chirp-3": "chirp",  # Chirp is the latest in V1
                    "chirp-2": "chirp_2",
                    "chirp-1": "chirp",
                    "google-default": "default",
                }
                google_model = model_map.get(self.config.model, "default")

                config = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=16000,
                    language_code=language_code,
                    enable_automatic_punctuation=True,
                    model=google_model,
                )

                # Perform synchronous recognition
                response = client.recognize(
                    config=config,
                    audio=audio,
                    timeout=self.config.timeout_seconds,
                )

                # Extract transcript from response
                # Each result is for a consecutive portion of the audio
                transcript_parts = []
                for result in response.results:
                    if result.alternatives:
                        # The first alternative is the most likely one
                        transcript_parts.append(result.alternatives[0].transcript)

                transcript = " ".join(transcript_parts)

                return AsrChunkResult(
                    status="ok",
                    text=transcript,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    duration_sec=duration,
                    language=language_code,
                    provider_meta={
                        **meta,
                        "language_code": language_code,
                    },
                )

            except Exception as e:
                error_kind = classify_asr_error(e)
                if attempt == self.config.max_retries - 1:
                    return AsrChunkResult(
                        status="error",
                        text="",
                        start_sec=start_sec,
                        end_sec=end_sec,
                        duration_sec=duration,
                        language=self.config.language,
                        error=str(e)[:500],
                        error_kind=error_kind,
                        provider_meta=meta,
                    )
                # Retry on certain errors
                if error_kind in ("server", "timeout"):
                    continue
                # Don't retry auth/quota/client errors
                return AsrChunkResult(
                    status="error",
                    text="",
                    start_sec=start_sec,
                    end_sec=end_sec,
                    duration_sec=duration,
                    language=self.config.language,
                    error=str(e)[:500],
                    error_kind=error_kind,
                    provider_meta=meta,
                )

        # Should not reach here
        return AsrChunkResult(
            status="error",
            text="",
            start_sec=start_sec,
            end_sec=end_sec,
            duration_sec=duration,
            language=self.config.language,
            error="max retries exceeded",
            error_kind="unknown",
            provider_meta=meta,
        )


PROVIDER_BACKENDS: Dict[str, type[AsrProvider]] = {
    "whisper_stub": WhisperStubProvider,
    "whisper_openai_real": WhisperOpenAIBackend,
    "whisper_openai": WhisperStubProvider,  # Default to stub for safety
    "whisper_local": WhisperStubProvider,
    "google_stub": GoogleStubProvider,
    "google_stt_real": GoogleSttBackend,
    "google_stt": GoogleStubProvider,  # Default to stub for safety
}


class AsrClient:
    """Provider-agnostic ASR client with pluggable backends."""

    def __init__(self, cfg) -> None:
        provider_name = getattr(cfg, "asr_provider", None)
        model_override = getattr(cfg, "asr_model", None)
        language_override = getattr(cfg, "asr_language", None)
        api_version_override = getattr(cfg, "asr_api_version", None)
        self.provider_config = resolve_asr_provider_config(
            provider_name,
            model_override=model_override,
            language_override=language_override,
            api_version_override=api_version_override,
        )
        backend_cls = PROVIDER_BACKENDS.get(self.provider_config.backend)
        if backend_cls is None:
            raise AsrConfigError(f"No backend registered for '{self.provider_config.backend}'")
        self.backend: AsrProvider = backend_cls(self.provider_config)
        self.provider_name = self.provider_config.name
        self.model = self.provider_config.model
        self.api_version = self.provider_config.api_version
        self.language_hint = self.provider_config.language

    def transcribe_chunk(self, wav_path: Path | str, start_sec: float, end_sec: float) -> AsrChunkResult:
        """Transcribe a single chunk synchronously via the configured backend."""

        path = Path(wav_path)
        result = self.backend.transcribe_chunk(path, start_sec, end_sec)
        if not result.provider_meta:
            result.provider_meta = {"provider": self.provider_name, "model": self.model}
        else:
            result.provider_meta.setdefault("provider", self.provider_name)
            result.provider_meta.setdefault("model", self.model)
        if result.language is None:
            result.language = self.language_hint
        return result
