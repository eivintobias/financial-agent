# ROADMAP.md

Direction of travel. Phases are ordered by value-for-effort; safety work is
never optional within a phase.

## Phase 0 - DONE - Safety-first skeleton
- [x] Two-zone architecture with structured handoff contract
- [x] Sanitizer, validator, risk gate, human-in-the-loop approvals
- [x] Tenant-isolated vector KB, draft/send email split, JSONL audit trail
- [x] Offline MockLLM mode + demo scenarios + safety regression tests

## Phase 1 - Real LLM + hardening
- [ ] Swap in real OpenAI calls (set USE_MOCK_LLM=false) and verify the same
      three demo scenarios behave sensibly with a live model
- [ ] Add structured-output / function-calling schema enforcement instead of
      freeform JSON parsing (parse_json stays as fallback)
- [ ] Expand injection corpus: multilingual, paraphrased, base64-encoded,
      markdown-image-exfil payloads into sanitizer patterns + tests
- [ ] Per-request rate limiting and max-actions-per-plan cap (already 10)
- [ ] PII scrubbing option before content reaches the LLM provider

## Phase 2 - Agentic depth
- [ ] Iterative plan-execute-replan loop: feed kb_search/crm_lookup results
      back into a bounded planning round (max N iterations, audited)
- [ ] Agent memory: conversation history per client_id with retention policy
- [ ] Confidence/abstention behavior: agent should be able to return
      "needs human" instead of guessing
- [ ] Document ingestion pipeline: batch-index uploads with per-doc quarantine
      scan before indexing (poisoned-KB defense)

## Phase 3 - Product surface
- [ ] FastAPI service wrapper: POST /requests, GET /approvals, POST
      /approvals/{id}/decide (webhooks in, dashboard out)
- [ ] Real integrations behind the same interfaces: HubSpot/Salesforce CRM,
      SendGrid/SES email, IMAP/Graph inbound mail polling
- [ ] Persistence upgrade: SQLite/Postgres instead of JSON files; alembic-free
      simple migrations
- [ ] AuthN/AuthZ on the API + per-approver identity in the audit trail

## Phase 4 - Ops & assurance
- [ ] Red-team evaluation harness: corpus of attacks scored in CI
      (pytest marks or a small eval runner)
- [ ] Observability: structured logging, metrics (flag-rate, approval-rate,
      rejection-rate), alerting on anomaly spikes
- [ ] Deployment story: Dockerfile, docker-compose (app + postgres), secrets
      handling
- [ ] Threat-model doc kept in-repo and updated per feature (STRIDE-lite)

## Non-goals (for this training build)
- Production compliance certification (SOC2/GDPR) - architecture only
- Multi-agent frameworks (LangChain/LangGraph) - the hand-rolled loop teaches
  the fundamentals first; migrating later is straightforward because the
  safety gates are framework-agnostic