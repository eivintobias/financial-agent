"""Email service with a hard draft/send separation. Drafts are created freely;
sending is an explicitly approved, separately invoked step. The orchestrator
is the ONLY caller of ``send_approved``, and only after a recorded approval."""
from __future__ import annotations

import itertools
import time

_counter = itertools.count(1)


class EmailService:
    def __init__(self) -> None:
        self.drafts: dict[str, dict] = {}

    def draft(self, to: str, subject: str, body: str) -> dict:
        draft_id = f"draft_{next(_counter):03d}"
        record = {
            "id": draft_id,
            "to": to,
            "subject": subject,
            "body": body,
            "status": "draft",
            "created_at": time.time(),
        }
        self.drafts[draft_id] = record
        return record

    def approve_draft(self, draft_id: str, approver: str = "human") -> dict:
        self.drafts[draft_id]["status"] = "approved"
        self.drafts[draft_id]["approved_by"] = approver
        return self.drafts[draft_id]

    def send_approved(self, draft_id: str) -> dict:
        """Called ONLY by the orchestrator after a recorded human approval."""
        draft = self.drafts[draft_id]
        if draft["status"] != "approved":
            raise PermissionError(f"draft {draft_id} is not approved for sending")
        draft["status"] = "sent"
        draft["sent_at"] = time.time()
        # Real implementation: SMTP / SendGrid / SES call goes here.
        return {"status": "sent", "id": draft_id, "to": draft["to"]}

    def pending_drafts(self) -> list[dict]:
        return [d for d in self.drafts.values() if d["status"] == "draft"]