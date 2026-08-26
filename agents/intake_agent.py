"""ZONE A - the client-facing intake agent.

Deliberately has NO tool access whatsoever. Its entire capability is
"text in -> structured JSON out". Even if fully hijacked by a prompt
injection, the worst it can do is emit odd JSON, which is validated by
Pydantic and inspected by downstream safety gates.
"""
from __future__ import annotations

from core.llm import BaseLLM, parse_json
from core.safety.audit import AuditLog
from core.safety.sanitizer import render_as_data, sanitize_untrusted
from core.schemas import ClientIntake, new_id
from knowledge.documents import parse_file
from agents import prompts

VALID_CATEGORIES = {"invoice", "lead", "support_question", "document_request", "other"}


class IntakeAgent:
    def __init__(self, llm: BaseLLM, audit: AuditLog) -> None:
        self.llm = llm
        self.audit = audit

    def process(
        self, client_id: str, message: str, attachment_paths: list[str] | None = None
    ) -> ClientIntake:
        request_id = new_id("req")

        # Step 1: sanitize EVERYTHING untrusted before it touches a prompt.
        msg_sc = sanitize_untrusted(message, source="client_message")
        all_flags = [f"message::{f}" for f in msg_sc.flags]
        msg_block = render_as_data(msg_sc)

        attach_blocks: list[str] = []
        for path in attachment_paths or []:
            try:
                raw = parse_file(path)
            except Exception as exc:
                all_flags.append(f"unreadable_attachment:{path}")
                self.audit.log(
                    "intake.attachment_error", "intake_agent", path=path, error=str(exc)
                )
                continue
            sanitized = sanitize_untrusted(raw, source=path)
            all_flags.extend(f"{path}::{f}" for f in sanitized.flags)
            attach_blocks.append(render_as_data(sanitized))

        self.audit.log(
            "intake.sanitized",
            "intake_agent",
            request_id=request_id,
            message_flags=msg_sc.flags,
            total_flags=len(all_flags),
        )

        # Step 2: classify/extract. The LLM sees only delimited, flagged data.
        user_prompt = prompts.build_intake_user(msg_block, attach_blocks)
        response = self.llm.complete(prompts.INTAKE_SYSTEM, user_prompt)
        try:
            data = parse_json(response)
        except Exception:
            data = {}
            self.audit.log("intake.parse_error", "intake_agent", request_id=request_id)

        # Step 3: normalize + enforce. Deterministic code has the last word.
        category = data.get("category")
        if category not in VALID_CATEGORIES:
            category = "other"
        risk_flags = sorted(set(list(data.get("risk_flags") or []) + all_flags))
        intake = ClientIntake(
            request_id=request_id,
            client_id=client_id,
            category=category,
            extracted=data.get("extracted") or {},
            summary=str(data.get("summary") or "")[:1000],
            suggested_actions=[str(a)[:120] for a in (data.get("suggested_actions") or [])][:8],
            risk_flags=risk_flags,
        )
        self.audit.log(
            "intake.completed",
            "intake_agent",
            request_id=request_id,
            category=intake.category,
            risk_flags=intake.risk_flags,
        )
        return intake