"""Tests for ASR error classification and status reason mapping."""

import pytest

from src.utils.asr import (
    AsrErrorKind,
    classify_asr_error,
    map_asr_error_to_status_reason,
)
from src.schema.message import StatusReason


class TestClassifyAsrError:
    """Tests for classify_asr_error function."""

    def test_timeout_error_from_message(self):
        """Timeout errors are classified correctly."""
        exc = Exception("Request timeout after 30 seconds")
        assert classify_asr_error(exc) == "timeout"

    def test_timeout_error_from_type(self):
        """TimeoutError type is classified correctly."""
        exc = TimeoutError("Connection timed out")
        assert classify_asr_error(exc) == "timeout"

    def test_auth_error_401(self):
        """401 errors are classified as auth."""
        exc = Exception("401 Unauthorized: Invalid API key")
        assert classify_asr_error(exc) == "auth"

    def test_auth_error_invalid_key(self):
        """Invalid API key errors are classified as auth."""
        exc = Exception("invalid_api_key: The API key provided is invalid")
        assert classify_asr_error(exc) == "auth"

    def test_quota_error_429(self):
        """429 rate limit errors are classified as quota."""
        exc = Exception("429 Too Many Requests: Rate limit exceeded")
        assert classify_asr_error(exc) == "quota"

    def test_quota_error_exceeded(self):
        """Quota exceeded errors are classified correctly."""
        exc = Exception("Quota exceeded for this billing period")
        assert classify_asr_error(exc) == "quota"

    def test_client_error_400(self):
        """400 bad request errors are classified as client."""
        exc = Exception("400 Bad Request: Invalid audio format")
        assert classify_asr_error(exc) == "client"

    def test_server_error_500(self):
        """500 errors are classified as server."""
        exc = Exception("500 Internal Server Error")
        assert classify_asr_error(exc) == "server"

    def test_server_error_503(self):
        """503 errors are classified as server."""
        exc = Exception("503 Service Unavailable")
        assert classify_asr_error(exc) == "server"

    def test_unknown_error(self):
        """Unknown errors are classified as unknown."""
        exc = Exception("Something completely unexpected happened")
        assert classify_asr_error(exc) == "unknown"


class TestMapAsrErrorToStatusReason:
    """Tests for map_asr_error_to_status_reason function."""

    def test_timeout_maps_to_timeout_asr(self):
        """Timeout errors map to timeout_asr status reason."""
        result = map_asr_error_to_status_reason("timeout")
        assert isinstance(result, StatusReason)
        assert result.code == "timeout_asr"

    def test_auth_maps_to_asr_failed(self):
        """Auth errors map to asr_failed status reason."""
        result = map_asr_error_to_status_reason("auth")
        assert isinstance(result, StatusReason)
        assert result.code == "asr_failed"

    def test_quota_maps_to_asr_failed(self):
        """Quota errors map to asr_failed status reason."""
        result = map_asr_error_to_status_reason("quota")
        assert isinstance(result, StatusReason)
        assert result.code == "asr_failed"

    def test_client_maps_to_asr_failed(self):
        """Client errors map to asr_failed status reason."""
        result = map_asr_error_to_status_reason("client")
        assert isinstance(result, StatusReason)
        assert result.code == "asr_failed"

    def test_server_maps_to_asr_failed(self):
        """Server errors map to asr_failed status reason."""
        result = map_asr_error_to_status_reason("server")
        assert isinstance(result, StatusReason)
        assert result.code == "asr_failed"

    def test_unknown_maps_to_asr_failed(self):
        """Unknown errors map to asr_failed status reason."""
        result = map_asr_error_to_status_reason("unknown")
        assert isinstance(result, StatusReason)
        assert result.code == "asr_failed"


class TestErrorMappingIntegration:
    """Integration tests for error classification and mapping."""

    @pytest.mark.parametrize("error_msg,expected_kind,expected_code", [
        ("Request timeout", "timeout", "timeout_asr"),
        ("401 Unauthorized", "auth", "asr_failed"),
        ("Rate limit exceeded", "quota", "asr_failed"),
        ("500 Internal Server Error", "server", "asr_failed"),
        ("Unknown error", "unknown", "asr_failed"),
    ])
    def test_error_flow(self, error_msg, expected_kind, expected_code):
        """Test full flow from exception to status reason."""
        exc = Exception(error_msg)
        kind = classify_asr_error(exc)
        assert kind == expected_kind

        reason = map_asr_error_to_status_reason(kind)
        assert reason.code == expected_code
