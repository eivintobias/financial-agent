"""Append-only JSONL audit trail. Every meaningful decision is recorded:
sanitization results, proposals, validations, executions, approvals."""
from __future__ import annotations

import json
import time
from pathlib import Path

import config


class AuditLog:
    def __init__(self, path: Path | None = None, echo: bool = False) -> None:
        self.path = Path(path or config.AUDIT_LOG_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.echo = echo

    def log(self, event: str, actor: str, **details) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event,
            "actor": actor,
            **details,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        if self.echo:
            extras = " ".join(f"{k}={v}" for k, v in details.items())
            print(f"  [audit] {event} ({actor}) {extras}"[:160])