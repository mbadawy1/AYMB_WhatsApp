"""Utilities for reading/writing Message JSONL files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from src.schema.message import Message


def load_messages(path: Path) -> List[Message]:
    """Load Message[] from a JSONL file."""
    msgs: List[Message] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        msgs.append(Message(**data))
    return msgs


def write_messages_jsonl(messages: Iterable[Message], path: Path) -> None:
    """Write Message[] to JSONL deterministically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for msg in messages:
            if hasattr(msg, "model_dump"):
                data = msg.model_dump()
            else:
                data = msg.dict()
            fh.write(json.dumps(data, ensure_ascii=False))
            fh.write("\n")
