"""Minimal CRM stand-in persisted to JSON. In production this would be the
vendor CRM's API client (HubSpot / Salesforce / Pipedrive ...)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import config


class CRM:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or (config.DATA_DIR / "crm.json"))
        self.contacts: dict = {}
        if self.path.exists():
            try:
                self.contacts = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.contacts = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.contacts, indent=2), encoding="utf-8")

    def lookup(self, query: str) -> list[dict]:
        q = query.lower().strip()
        hits = []
        for contact in self.contacts.values():
            blob = f"{contact['name']} {contact['email']} {contact['company']}".lower()
            if q and q in blob:
                hits.append(contact)
        return hits

    def upsert_contact(self, name: str, email: str, notes: str = "", company: str = "") -> dict:
        email = email.strip().lower()
        existing = next(
            (c for c in self.contacts.values() if c["email"] == email), None
        )
        if existing:
            if notes:
                existing["notes"] = f"{existing['notes']}\n{notes}".strip()
            existing["updated_at"] = time.time()
            self._save()
            return existing
        contact_id = f"c_{len(self.contacts) + 1:04d}"
        record = {
            "id": contact_id,
            "name": name,
            "email": email,
            "company": company,
            "notes": notes,
            "created_at": time.time(),
        }
        self.contacts[contact_id] = record
        self._save()
        return record

    def log_interaction(self, email: str, summary: str) -> dict:
        entry = {"ts": time.time(), "summary": summary}
        existing = next(
            (c for c in self.contacts.values() if c["email"] == email.strip().lower()),
            None,
        )
        if existing is None:
            return {"status": "logged_unmatched", "note": f"no contact with email {email}"}
        existing.setdefault("interactions", []).append(entry)
        self._save()
        return {"status": "logged", "contact_id": existing["id"]}