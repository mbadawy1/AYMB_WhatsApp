"""Tests for the Message and StatusReason schema.

Validates:
- Required field enforcement
- Default values
- Status transitions
- Type validation
- Helper methods
"""

import pytest
import jsonschema
from pydantic import ValidationError

from src.schema.message import Message, StatusReason, validate_message


class TestStatusReason:
    """Tests for StatusReason dataclass."""

    def test_status_reason_creation(self):
        """Test basic StatusReason instantiation."""
        reason = StatusReason(code="TEST_CODE", message="Test message")
        assert reason.code == "TEST_CODE"
        assert reason.message == "Test message"
        assert reason.context is None

    def test_status_reason_with_context(self):
        """Test StatusReason with context dictionary."""
        reason = StatusReason(
            code="PARSE_ERROR",
            message="Failed to parse line",
            context={"line_num": 42, "file": "chat.txt"},
        )
        assert reason.context == {"line_num": 42, "file": "chat.txt"}


class TestMessageSchema:
    """Tests for Message schema validation and behavior."""

    def test_minimal_message_creation(self):
        """Test creating a message with only required fields."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Alice", kind="text")
        assert msg.idx == 0
        assert msg.ts == "2025-11-17T10:30:00Z"
        assert msg.sender == "Alice"
        assert msg.kind == "text"

    def test_default_values(self):
        """Test that optional fields have correct defaults."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Bob", kind="voice")
        assert msg.content_text == ""
        assert msg.raw_line == ""
        assert msg.raw_block == ""
        assert msg.media_hint is None
        assert msg.media_filename is None
        assert msg.caption is None
        assert msg.derived == {}
        assert msg.status == "ok"
        assert msg.partial is False
        assert msg.status_reason is None
        assert msg.errors == []

    def test_all_message_kinds(self):
        """Test all valid message kind values."""
        valid_kinds = [
            "text",
            "voice",
            "image",
            "video",
            "document",
            "sticker",
            "system",
            "unknown",
        ]
        for kind in valid_kinds:
            msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Test", kind=kind)
            assert msg.kind == kind

    def test_invalid_message_kind(self):
        """Test that invalid message kinds are rejected."""
        with pytest.raises(ValidationError):
            Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Test", kind="invalid")

    def test_negative_idx_rejected(self):
        """Test that negative index values are rejected."""
        with pytest.raises(ValidationError):
            Message(idx=-1, ts="2025-11-17T10:30:00Z", sender="Test", kind="text")

    def test_empty_sender_rejected(self):
        """Test that empty sender strings are rejected."""
        with pytest.raises(ValidationError):
            Message(idx=0, ts="2025-11-17T10:30:00Z", sender="", kind="text")

    def test_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            Message(idx=0)  # Missing ts, sender, kind

    def test_content_fields(self):
        """Test setting content fields."""
        msg = Message(
            idx=0,
            ts="2025-11-17T10:30:00Z",
            sender="Charlie",
            kind="text",
            content_text="Hello world",
            raw_line="11/17/25, 10:30 AM - Charlie: Hello world",
            raw_block="11/17/25, 10:30 AM - Charlie: Hello world",
        )
        assert msg.content_text == "Hello world"
        assert "Charlie: Hello world" in msg.raw_line
        assert msg.raw_block == msg.raw_line

    def test_media_fields(self):
        """Test media-related fields."""
        msg = Message(
            idx=0,
            ts="2025-11-17T10:30:00Z",
            sender="Dave",
            kind="voice",
            media_hint="Voice message (0:36)",
            media_filename="PTT-20250708-WA0028.opus",
            caption="Important audio",
        )
        assert msg.media_hint == "Voice message (0:36)"
        assert msg.media_filename == "PTT-20250708-WA0028.opus"
        assert msg.caption == "Important audio"

    def test_derived_metadata(self):
        """Test adding derived metadata."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Eve", kind="voice")
        msg.derived["asr_transcript"] = "Hello from voice message"
        msg.derived["file_hash"] = "abc123"
        assert msg.derived["asr_transcript"] == "Hello from voice message"
        assert msg.derived["file_hash"] == "abc123"

    def test_status_values(self):
        """Test all valid status values."""
        valid_statuses = ["ok", "partial", "failed", "skipped"]
        for status in valid_statuses:
            msg = Message(
                idx=0, ts="2025-11-17T10:30:00Z", sender="Test", kind="text", status=status
            )
            assert msg.status == status

    def test_invalid_status_rejected(self):
        """Test that invalid status values are rejected."""
        with pytest.raises(ValidationError):
            Message(
                idx=0,
                ts="2025-11-17T10:30:00Z",
                sender="Test",
                kind="text",
                status="invalid",
            )

    def test_mark_partial(self):
        """Test mark_partial helper method."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Test", kind="text")
        msg.mark_partial("INCOMPLETE_PARSE", "Multi-line message truncated")

        assert msg.status == "partial"
        assert msg.partial is True
        assert msg.status_reason is not None
        assert msg.status_reason.code == "INCOMPLETE_PARSE"
        assert msg.status_reason.message == "Multi-line message truncated"

    def test_mark_failed(self):
        """Test mark_failed helper method."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Test", kind="text")
        msg.mark_failed("PARSE_ERROR", "Invalid timestamp format")

        assert msg.status == "failed"
        assert msg.status_reason is not None
        assert msg.status_reason.code == "PARSE_ERROR"
        assert msg.status_reason.message == "Invalid timestamp format"

    def test_mark_skipped(self):
        """Test mark_skipped helper method."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Test", kind="system")
        msg.mark_skipped("SYSTEM_MESSAGE", "Group metadata change")

        assert msg.status == "skipped"
        assert msg.status_reason is not None
        assert msg.status_reason.code == "SYSTEM_MESSAGE"

    def test_mark_with_context(self):
        """Test status marking with context."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Test", kind="text")
        msg.mark_partial(
            "MEDIA_AMBIGUOUS",
            "Multiple candidates found",
            context={"candidates": ["file1.jpg", "file2.jpg"], "line": 42},
        )

        assert msg.status_reason.context is not None
        assert msg.status_reason.context["candidates"] == ["file1.jpg", "file2.jpg"]
        assert msg.status_reason.context["line"] == 42

    def test_add_error(self):
        """Test add_error helper method."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Test", kind="text")
        msg.add_error("First error")
        msg.add_error("Second error")

        assert len(msg.errors) == 2
        assert msg.errors[0] == "First error"
        assert msg.errors[1] == "Second error"

    def test_error_accumulation(self):
        """Test that errors can accumulate without changing status."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Test", kind="text")
        msg.add_error("Warning: Low confidence ASR")
        msg.add_error("Warning: Background noise detected")

        assert msg.status == "ok"  # Status unchanged
        assert len(msg.errors) == 2

    def test_complete_voice_message(self):
        """Test a realistic complete voice message."""
        msg = Message(
            idx=42,
            ts="2025-07-08T14:23:15Z",
            sender="Dr. Mahmoud Mostafa",
            kind="voice",
            content_text="",
            raw_line="7/8/25, 2:23 PM - Dr. Mahmoud Mostafa: PTT-20250708-WA0028.opus (file attached)",
            raw_block="7/8/25, 2:23 PM - Dr. Mahmoud Mostafa: PTT-20250708-WA0028.opus (file attached)",
            media_hint="Voice message (0:36)",
            media_filename="PTT-20250708-WA0028.opus",
            derived={
                "file_hash": "sha256:abc123...",
                "asr_transcript": "نعم، الشحنة جاهزة للتصدير",
                "duration_sec": 36.2,
                "asr_confidence": 0.92,
            },
            status="ok",
        )

        assert msg.idx == 42
        assert msg.kind == "voice"
        assert msg.media_filename == "PTT-20250708-WA0028.opus"
        assert msg.derived["asr_confidence"] == 0.92
        assert msg.status == "ok"

    def test_schema_validation_happy_path(self):
        """Validate message against JSON schema."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Alice", kind="text")
        validate_message(msg)  # Should not raise

    def test_schema_validation_rejects_bad_kind(self):
        """Schema validation should reject invalid kind values."""
        msg = Message(idx=0, ts="2025-11-17T10:30:00Z", sender="Alice", kind="text")
        with pytest.raises(ValidationError):
            msg.kind = "invalid"  # type: ignore
