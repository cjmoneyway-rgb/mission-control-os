"""Append-only JSONL audit storage."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ExecutionRecord


class JsonlAuditLog:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def append(self, record: ExecutionRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
