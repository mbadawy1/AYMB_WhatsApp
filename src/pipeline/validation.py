"""Schema/enum validation helpers for contract pre-flight checks."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from src.pipeline.outputs import load_messages
from src.schema.message import Message


class SchemaValidationError(Exception):
    """Raised when a message file violates schema invariants."""


def _validate_messages(messages: Iterable[Message]) -> None:
    last_idx = -1
    for msg in messages:
        if msg.idx != last_idx + 1:
            raise SchemaValidationError(f"idx sequence break at {msg.idx} (expected {last_idx + 1})")
        last_idx = msg.idx


def validate_jsonl(path: Path) -> List[Message]:
    """Load and validate a JSONL file; returns the Message list."""
    messages = load_messages(path)
    _validate_messages(messages)
    return messages
