"""Pipeline coordinator - owns the safety state machine.

Flow:
  client request -> [Zone A] intake (sanitize + extract, no tools)
                 -> handoff (structured ClientIntake only)
                 -> [Zone B] work agent proposes actions
                 -> deterministic validator (allow-list, schemas, patterns)
                 -> risk gate: LOW/MEDIUM execute (audited), HIGH waits for approval
                 -> audit trail records everything
Extra hardening: if the intake carried injection flags, even MEDIUM actions
are escalated to human review (_effective_risk).
"""
from __future__ import annotations

import config
from agents.intake_agent import IntakeAgent
from agents.work_agent import WorkAgent
from core.llm import get_llm
from core.safety.audit import AuditLog
from core.safety.gates import ActionValidator
from core.schemas import ActionRequest, ClientIntake, ExecutedAction, RiskTier
from integrations.crm import CRM
from integrations.email import EmailService
from knowledge.vector_store import VectorStore


class Orchestrator:
    def __init__(self, llm=None, approval_mode: str | None = None, audit: AuditLog | None = None) -> None:
        self.llm = llm or get_llm()
        self.audit = audit or AuditLog(echo=False)
        self.kb = VectorStore()
        self.crm = CRM()
        self.email = EmailService()
        self.validator = ActionValidator()
        self.intake_agent = IntakeAgent(self.llm, self.audit)
        self.work_agent = WorkAgent(self.llm, self.audit, self.validator)
        self.approval_mode = approval_mode or config.APPROVAL_MODE
        self.pending: list[dict] = []

    def process_client_request(
        self, client_id: str, message: str, attachment_paths: list[str] | None = None
    ) -> dict:
        intake = self.intake_agent.process(client_id, message, attachment_paths)
        proposals = self.work_agent.propose(intake)
        executed: list[ExecutedAction] = []

        for action, verdict in proposals:
            if not verdict.ok:
                executed.append(ExecutedAction(
                    action_id=action.action_id, tool=action.tool,
                    risk=verdict.base_risk, status="rejected",
                    detail="; ".join(verdict.reasons),
                ))
                self.audit.log("action.rejected", "orchestrator",
                               action_id=action.action_id, tool=action.tool,
                               reasons=verdict.reasons)
                continue

            risk = self._effective_risk(verdict.base_risk, intake)
            if risk is RiskTier.HIGH:
                item = self._queue_for_approval(action, intake, risk)
                executed.append(item["executed"])
                continue

            result = self._execute(action)
            executed.append(ExecutedAction(
                action_id=action.action_id, tool=action.tool,
                risk=risk, status="executed", result=result,
            ))

        self.audit.log("request.completed", "orchestrator",
                       request_id=intake.request_id, actions=len(executed),
                       pending_approvals=len(self.pending))
        return {"intake": intake, "actions": executed}

    # ------------------------------------------------------------------ gates
    def _effective_risk(self, base: RiskTier, intake: ClientIntake) -> RiskTier:
        """Defense in depth: flagged requests escalate anything non-read-only."""
        if intake.risk_flags and base is not RiskTier.LOW:
            return RiskTier.HIGH
        return base

    def _queue_for_approval(self, action: ActionRequest, intake: ClientIntake, risk: RiskTier) -> dict:
        item = {
            "action_id": action.action_id,
            "tool": action.tool,
            "params": action.params,
            "rationale": action.rationale,
            "risk": risk.value,
            "client_id": intake.client_id,
            "request_id": intake.request_id,
        }
        self.pending.append(item)
        self.audit.log("action.pending_approval", "orchestrator",
                       action_id=action.action_id, tool=action.tool)
        return {"executed": ExecutedAction(
            action_id=action.action_id, tool=action.tool, risk=risk,
            status="pending_approval", detail=item["rationale"],
        )}

    def decide_pending(self, action_id: str, approved: bool, approver: str = "human") -> str:
        item = next((p for p in self.pending if p["action_id"] == action_id), None)
        if item is None:
            return "not_found"
        self.pending.remove(item)
        self.audit.log("approval.decided", approver,
                       action_id=action_id, approved=approved)
        if not approved:
            return "denied"
        action = ActionRequest(
            action_id=item["action_id"], request_id=item["request_id"],
            client_id=item["client_id"], tool=item["tool"],
            params=item["params"], rationale=item["rationale"],
        )
        result = self._execute(action)
        return f"executed: {result}"

    # -------------------------------------------------------------- executor
    def _execute(self, action: ActionRequest) -> dict:
        self.audit.log("action.executed", "orchestrator",
                       action_id=action.action_id, tool=action.tool)
        tool, params = action.tool, action.params
        if tool == "kb_search":
            return {"results": self.kb.search(params["query"], action.client_id)}
        if tool == "crm_lookup":
            return {"results": self.crm.lookup(params["query"])}
        if tool == "crm_upsert_contact":
            return {"contact": self.crm.upsert_contact(**params)}
        if tool == "log_interaction":
            return self.crm.log_interaction(**params)
        if tool == "draft_followup_email":
            return {"draft": self.email.draft(**params)}
        if tool == "send_email":
            # Only reachable post-approval. Create + approve + send atomically.
            draft = self.email.draft(**params)
            self.email.approve_draft(draft["id"], approver="human_via_gate")
            return self.email.send_approved(draft["id"])
        raise ValueError(f"executor has no implementation for tool '{tool}'")