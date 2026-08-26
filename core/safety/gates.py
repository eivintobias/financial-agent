"""Deterministic gate between the LLM's *plans* and actual tool execution.

The work agent (an LLM) can only PROPOSE actions. Nothing runs until it passes
through this module: allow-listed tool, exact parameter schema, sane values,
blocked-pattern scan on outbound text. This is the heart of the client/internal
safety split: a prompt, however manipulated, cannot invent capabilities that
are not on the allow-list.
"""
from __future__ import annotations

import re

from core.schemas import ActionRequest, RiskTier, ValidationResult

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")

TOOL_REGISTRY: dict = {
    "kb_search": {
        "risk": RiskTier.LOW,
        "description": "Search the internal knowledge base scoped to one client.",
        "params": {"query": str},
        "max_lens": {"query": 500},
    },
    "crm_lookup": {
        "risk": RiskTier.LOW,
        "description": "Look up a contact in the CRM.",
        "params": {"query": str},
        "max_lens": {"query": 300},
    },
    "crm_upsert_contact": {
        "risk": RiskTier.MEDIUM,
        "description": "Create or update a CRM contact (reversible internal write).",
        "params": {"name": str, "email": str, "notes": str, "company": str},
        "max_lens": {"name": 200, "notes": 2000, "company": 200},
    },
    "log_interaction": {
        "risk": RiskTier.MEDIUM,
        "description": "Append an interaction note for a contact.",
        "params": {"email": str, "summary": str},
        "max_lens": {"summary": 2000},
    },
    "draft_followup_email": {
        "risk": RiskTier.MEDIUM,
        "description": "Create an email DRAFT (never sent automatically).",
        "params": {"to": str, "subject": str, "body": str},
        "max_lens": {"subject": 300, "body": 8000},
    },
    "send_email": {
        "risk": RiskTier.HIGH,
        "description": "Send an email externally. Requires recorded human approval.",
        "params": {"to": str, "subject": str, "body": str},
        "max_lens": {"subject": 300, "body": 8000},
    },
}

# Strings that must never appear in OUTBOUND-bound text (defense in depth: even
# if a jailbreak slipped past the intake stage, outbound content is re-checked).
OUTBOUND_BLOCK_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)",
    r"(internal|confidential).{0,40}(do not|don.t) (tell|disclose|share)",
    r"<untrusted_client_content>",
]


class ActionValidator:
    def validate(self, action: ActionRequest) -> ValidationResult:
        reasons: list[str] = []
        spec = TOOL_REGISTRY.get(action.tool)
        if spec is None:
            return ValidationResult(ok=False, reasons=[f"unknown tool '{action.tool}'"])
        risk = spec["risk"]

        expected = set(spec["params"].keys())
        got = set(action.params.keys())
        missing, extra = expected - got, got - expected
        if missing:
            reasons.append(f"missing params: {sorted(missing)}")
        if extra:
            reasons.append(f"unexpected params: {sorted(extra)}")

        for name, typ in spec["params"].items():
            value = action.params.get(name)
            if value is None:
                continue
            if typ is str and not isinstance(value, str):
                reasons.append(f"param '{name}' must be a string")
                continue
            if isinstance(value, str):
                limit = spec.get("max_lens", {}).get(name)
                if limit and len(value) > limit:
                    reasons.append(f"param '{name}' exceeds max length {limit}")
                # Address-shaped params must hold a syntactically valid email.
                if (
                    ("email" in name or name in ("to", "cc", "bcc"))
                    and value
                    and not EMAIL_RE.match(value.strip())
                ):
                    reasons.append(f"param '{name}' is not a valid email address")

        # Outbound-content scan applies to anything carrying email/body text.
        if "email" in action.params or "body" in action.params:
            blob = " ".join(str(v) for v in action.params.values()).lower()
            for pat in OUTBOUND_BLOCK_PATTERNS:
                if re.search(pat, blob):
                    reasons.append(f"outbound content matched blocked pattern: {pat}")

        if not action.rationale.strip():
            reasons.append("missing rationale")

        return ValidationResult(ok=not reasons, reasons=reasons, base_risk=risk)