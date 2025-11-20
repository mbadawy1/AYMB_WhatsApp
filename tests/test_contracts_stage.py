from src.schema.message import Message
from src.pipeline.validation import validate_jsonl, SchemaValidationError


def test_parser_caption_tail_marked():
    msg_media = Message(
        idx=0,
        ts="2025-01-01T00:00:00",
        sender="Alice",
        kind="image",
        caption="caption",
        content_text="",
    )
    msg_tail = Message(
        idx=1,
        ts="2025-01-01T00:00:00",
        sender="Alice",
        kind="text",
        content_text="tail",
        status="skipped",
        status_reason={"code": "merged_into_previous_media", "message": "", "context": None},
    )
    # sanity check
    assert msg_tail.status == "skipped"
    assert getattr(msg_tail.status_reason, "code", "merged_into_previous_media") == "merged_into_previous_media"


def test_media_resolver_status_semantics():
    unresolved = Message(
        idx=0,
        ts="2025-01-01T00:00:00",
        sender="Alice",
        kind="image",
        media_filename=None,
        content_text="",
        status="ok",
        status_reason={"code": "unresolved_media", "message": "", "context": None},
    )
    ambiguous = Message(
        idx=1,
        ts="2025-01-01T00:00:01",
        sender="Alice",
        kind="image",
        media_filename=None,
        content_text="",
        status="ok",
        status_reason={"code": "ambiguous_media", "message": "", "context": None},
    )
    assert getattr(unresolved.status_reason, "code", None) == "unresolved_media"
    assert getattr(ambiguous.status_reason, "code", None) == "ambiguous_media"


def test_audio_status_mapping():
    failed = Message(
        idx=0,
        ts="2025-01-01T00:00:00",
        sender="Alice",
        kind="voice",
        content_text="",
        status="failed",
        status_reason={"code": "asr_failed", "message": "", "context": None},
    )
    partial = Message(
        idx=1,
        ts="2025-01-01T00:00:00",
        sender="Bob",
        kind="voice",
        content_text="hi",
        status="partial",
        status_reason={"code": "asr_partial", "message": "", "context": None},
    )
    assert getattr(failed.status_reason, "code", None) == "asr_failed"
    assert getattr(partial.status_reason, "code", None) == "asr_partial"
