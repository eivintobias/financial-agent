"""ZONE B - the internal work agent.

Lives entirely behind the safety boundary. It receives only the structured
ClientIntake (never raw client text) and can merely PROPOSE actions from the
allow-list. Execution is handled by the orchestrator after validation and
risk gating, so the LLM here can never grant itself new capabilities.
"""
from __future__ import annotations

import json

from core.llm import BaseLLM, parse_json
from core.safety.audit import AuditLog
from core.safety.gates import ActionValidator
from core.schemas import ActionRequest, ClientIntake, ValidationResult, new_id
from agents import prompts


class WorkAgent:
    def __init__(self, llm: BaseLLM, audit: AuditLog, validator: ActionValidator | None = None) -> None:
        self.llm = llm
        self.audit = audit
        self.validator = validator or ActionValidator()

    def propose(self, intake: ClientIntake) -> list[tuple[ActionRequest, ValidationResult]]:
        intake_json = json.dumps(
            {
                "request_id": intake.request_id,
                "client_id": intake.client_id,
                "category": intake.category,
                "extracted": intake.extracted,
                "summary": intake.summary,
                "risk_flags": intake.risk_flags,
            },
            ensure_ascii=False,
        )
        response = self.llm.complete(
            prompts.PLAN_SYSTEM, prompts.build_plan_user(intake_json)
        )
        try:
            data = parse_json(response)
        except Exception:
            self.audit.log("plan.parse_error", "work_agent", request_id=intake.request_id)
            data = {"actions": []}

        proposals: list[tuple[ActionRequest, ValidationResult]] = []
        for raw in (data.get("actions") or [])[:10]:
            if not isinstance(raw, dict):
                continue
            action = ActionRequest(
                action_id=new_id("act"),
                request_id=intake.request_id,
                client_id=intake.client_id,
                tool=str(raw.get("tool", "")),
                params=raw.get("params") or {},
                rationale=str(raw.get("rationale", "")),
            )
            verdict = self.validator.validate(action)
            self.audit.log(
                "plan.proposed",
                "work_agent",
                request_id=intake.request_id,
                tool=action.tool,
                valid=verdict.ok,
                reasons=verdict.reasons,
            )
            proposals.append((action, verdict))
        return proposals