"""LLM abstraction with two implementations:

- OpenAILLM: real API calls (set OPENAI_API_KEY, USE_MOCK_LLM=false)
- MockLLM:   deterministic offline stand-in so demos/tests need no API access

All task prompts carry a machine-readable marker line ``TASK: <NAME>`` so the
mock can route to canned logic.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

import config


class BaseLLM(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str: ...


def parse_json(text: str) -> dict:
    """Parse an LLM response as JSON, tolerating markdown fences and prose."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if match:
            return json.loads(match.group(0))
        raise


class OpenAILLM(BaseLLM):
    def __init__(self) -> None:
        from openai import OpenAI  # lazy import: mock mode needs no openai pkg

        self._client = OpenAI(api_key=config.OPENAI_API_KEY)
        self._model = config.MODEL_NAME

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or "{}"


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
AMOUNT_RE = re.compile(r"\$\s?[\d][\d,]*(?:\.\d{2})?")
NAME_RE = re.compile(r"(?:i'?m|my name is|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)")


class MockLLM(BaseLLM):
    """Heuristic stand-in. Understands only the TASK markers used by the
    agents - good enough to exercise the full pipeline offline."""

    def complete(self, system: str, user: str) -> str:
        match = re.search(r"TASK:\s*(\w+)", system)
        task = match.group(1).lower() if match else "generic"
        handler = getattr(self, f"_mock_{task}", self._mock_generic)
        return handler(user)

    # ----- TASK: CLASSIFY_INTAKE -----
    def _mock_classify_intake(self, user: str) -> str:
        text = user.lower()
        emails = EMAIL_RE.findall(user)
        amounts = AMOUNT_RE.findall(user)
        name_match = NAME_RE.search(user)

        if "invoice" in text:
            category = "invoice"
        elif any(k in text for k in ("quote", "pricing", "interested in", "sign up")):
            category = "lead"
        elif any(k in text for k in ("question", "how do", "help", "?")):
            category = "support_question"
        else:
            category = "other"

        extracted: dict = {}
        if emails:
            extracted["email"] = emails[0].rstrip(".")
        if amounts:
            extracted["amount"] = amounts[0]
        if name_match:
            extracted["name"] = name_match.group(1)
        inv = re.search(r"invoice\s*#?\s*(\w+)", user, re.I)
        if inv:
            extracted["invoice_number"] = inv.group(1)

        return json.dumps({
            "category": category,
            "extracted": extracted,
            "summary": user.replace("\n", " ")[:160],
            "risk_flags": [],
            "suggested_actions": [],
        })

    # ----- TASK: PLAN_ACTIONS -----
    def _mock_plan_actions(self, user: str) -> str:
        m = re.search(r"<<<INTAKE>>>\s*(\{.*?\})\s*<<<END_INTAKE>>>", user, re.S)
        intake = json.loads(m.group(1)) if m else {}
        category = intake.get("category", "other")
        extracted = intake.get("extracted", {}) or {}
        risk_flags = intake.get("risk_flags", []) or []
        email = extracted.get("email", "")
        name = extracted.get("name", email.split("@")[0].title() if email else "there")
        actions: list = []

        if risk_flags:
            # SAFETY SPLIT: flagged requests get READ-ONLY handling only.
            actions.append({
                "tool": "kb_search",
                "params": {"query": f"{category} handling policy"},
                "rationale": "Flagged content: consult policy, no outward actions.",
            })
            return json.dumps({"actions": actions})

        actions.append({
            "tool": "kb_search",
            "params": {"query": f"{category} policy"},
            "rationale": "Ground the answer in the internal knowledge base.",
        })

        if category == "invoice":
            actions.append({
                "tool": "log_interaction",
                "params": {
                    "email": email or "unknown@example.com",
                    "summary": (
                        f"Invoice inquiry #{extracted.get('invoice_number', 'n/a')} "
                        f"for {extracted.get('amount', 'n/a')}"
                    ),
                },
                "rationale": "Record the inquiry in the CRM.",
            })
        elif category == "lead":
            actions.append({
                "tool": "crm_upsert_contact",
                "params": {
                    "name": name,
                    "email": email or "unknown@example.com",
                    "notes": (intake.get("summary", "") or "")[:500],
                    "company": "",
                },
                "rationale": "New lead: register in CRM.",
            })

        if email and category == "lead":
            # Deliberately proposes the HIGH-risk variant so the approval gate
            # is exercised end-to-end in the demo.
            actions.append({
                "tool": "send_email",
                "params": {
                    "to": email,
                    "subject": "Thanks for your interest",
                    "body": (
                        f"Hello {name},\n\nThank you for reaching out about our "
                        f"services. An advisor will contact you shortly.\n\n"
                        f"Best regards,\nThe Team"
                    ),
                },
                "rationale": "Outbound reply to a new lead (needs human approval).",
            })
        elif email and category != "other":
            subject = {
                "invoice": "Re: your invoice inquiry",
                "support_question": "Re: your question",
                "document_request": "Re: your document request",
            }.get(category, "Follow-up")
            actions.append({
                "tool": "draft_followup_email",
                "params": {
                    "to": email,
                    "subject": subject,
                    "body": (
                        f"Hello {name},\n\nThank you for reaching out. Our team "
                        f"will get back to you shortly regarding your "
                        f"{category.replace('_', ' ')}.\n\nBest regards,\nThe Team"
                    ),
                },
                "rationale": "Prepare a follow-up draft for team review.",
            })
        return json.dumps({"actions": actions})

    def _mock_generic(self, user: str) -> str:
        return "{}"


def get_llm() -> BaseLLM:
    if config.USE_MOCK_LLM or not config.OPENAI_API_KEY:
        return MockLLM()
    return OpenAILLM()