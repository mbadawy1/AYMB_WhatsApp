"""Core Message schema for WhatsApp chat processing.

Canonical message representation with status tracking, media handling,
and deterministic field semantics as defined in AGENTS.md M1.0.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class StatusReason(BaseModel):
    """Structured reason for non-ok status states.

    Attributes:
        code: Machine-readable error/status code (e.g., "PARSE_FAILED", "MEDIA_NOT_FOUND")
        message: Human-readable description
        context: Optional additional context (line numbers, file paths, etc.)
    """

    code: str
    message: str
    context: Optional[dict[str, Any]] = None


class Message(BaseModel):
    """Canonical WhatsApp message representation.

    All fields follow the contract defined in AGENTS.md M1.0.
    Status discipline: ok | partial | failed | skipped

    Required fields:
        idx: Sequential message index (0-based)
        ts: ISO 8601 timestamp string
        sender: Display name of sender
        kind: Message classification

    Optional content fields:
        content_text: Extracted text content (may be empty for media-only messages)
        raw_line: First line from the source file
        raw_block: Complete multi-line block from source

    Media fields:
        media_hint: Text placeholder like "<Media omitted>" or "Voice message (0:36)"
        media_filename: Resolved actual filename (e.g., "PTT-20250708-WA0028.opus")
        caption: Attached caption for media messages

    Status tracking:
        derived: Arbitrary metadata added by pipeline stages (ASR transcript, file hash, etc.)
        status: Current processing state
        partial: Quick boolean flag for partial status
        status_reason: Structured reason for non-ok states
        errors: Accumulated error messages during processing
    """

    # Required fields
    idx: int = Field(..., ge=0, description="Sequential message index (0-based)")
    ts: str = Field(..., description="ISO 8601 timestamp")
    sender: str = Field(..., min_length=1, description="Sender display name")
    kind: Literal["text", "voice", "image", "video", "document", "sticker", "system", "unknown"] = (
        Field(..., description="Message type classification")
    )

    # Content fields
    content_text: str = Field(default="", description="Extracted text content")
    raw_line: str = Field(default="", description="First line from source file")
    raw_block: str = Field(default="", description="Complete multi-line source block")

    # Media fields
    media_hint: Optional[str] = Field(
        default=None, description="Media placeholder text from source"
    )
    media_filename: Optional[str] = Field(
        default=None, description="Resolved actual media filename"
    )
    caption: Optional[str] = Field(default=None, description="Media caption")

    # Status tracking
    derived: dict[str, Any] = Field(default_factory=dict, description="Stage-specific metadata")
    status: Literal["ok", "partial", "failed", "skipped"] = Field(
        default="ok", description="Processing status"
    )
    partial: bool = Field(default=False, description="Quick flag for partial status")
    status_reason: Optional[StatusReason] = Field(
        default=None, description="Structured reason for non-ok status"
    )
    errors: list[str] = Field(default_factory=list, description="Accumulated error messages")

    model_config = ConfigDict(
        extra="forbid",  # Forbid extra fields
        validate_assignment=True,  # Validate on assignment
        use_enum_values=True,  # Use enum values
    )

    def mark_partial(
        self, code: str, message: str, context: Optional[dict[str, Any]] = None
    ) -> None:
        """Mark message as partial with a reason.

        Args:
            code: Machine-readable status code
            message: Human-readable description
            context: Optional additional context
        """
        self.status = "partial"
        self.partial = True
        self.status_reason = StatusReason(code=code, message=message, context=context)

    def mark_failed(
        self, code: str, message: str, context: Optional[dict[str, Any]] = None
    ) -> None:
        """Mark message as failed with a reason.

        Args:
            code: Machine-readable status code
            message: Human-readable description
            context: Optional additional context
        """
        self.status = "failed"
        self.status_reason = StatusReason(code=code, message=message, context=context)

    def mark_skipped(
        self, code: str, message: str, context: Optional[dict[str, Any]] = None
    ) -> None:
        """Mark message as skipped with a reason.

        Args:
            code: Machine-readable status code
            message: Human-readable description
            context: Optional additional context
        """
        self.status = "skipped"
        self.status_reason = StatusReason(code=code, message=message, context=context)

    def add_error(self, error: str) -> None:
        """Append an error message to the errors list.

        Args:
            error: Error message to append
        """
        self.errors.append(error)
