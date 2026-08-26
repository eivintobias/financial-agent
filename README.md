# Financial AI Agent - Safety-First Architecture (Training Build)

A training implementation of an "AI Agent for Financial Business Automation"
brief (OpenAI API / RAG / tool calling / CRM + email automation) built around
deliberate **safety separation between the client-facing side and the internal
business systems**.

> Educational scaffold - not production code. The CRM, email service and LLM
> are swappable stand-ins behind clean interfaces.

## Architecture

```
 CLIENT (untrusted)                  SAFETY BOUNDARY                  INTERNAL SYSTEMS (trusted)
+---------------------------+       +------------------------+       +---------------------------+
| Zone A: IntakeAgent       |       | 1. Sanitizer           |       | Zone B: WorkAgent         |
| - reads raw email/docs    | ----> | 2. Structured JSON     | ----> | - proposes actions ONLY   |
| - has ZERO tools          |Client |    (ClientIntake model)| only  | - allow-list enforced     |
| - cannot act              |Intake | 3. Validator           |       +---------------------------+
|                           |object |    (schema + patterns) |       | CRM / Vector KB / Email   |
+---------------------------+       | 4. Risk gate           |       | (draft vs send split)     |
                                    |    LOW -> run          |       +---------------------------+
                                    |    MEDIUM -> audit     |       | Audit trail (JSONL)       |
                                    |    HIGH -> human OK    |       +---------------------------+
                                    +------------------------+
```

## The safety split (the important part)

| # | Mechanism | Where | What it stops |
|---|-----------|-------|---------------|
| 1 | Intake agent has **no tools at all** | `agents/intake_agent.py` | A fully hijacked intake LLM can only emit odd JSON |
| 2 | Injection-pattern sanitizer + zero-width char stripping | `core/safety/sanitizer.py` | Direct/document-borne prompt injection gets flagged, evidence kept |
| 3 | Only structured `ClientIntake` crosses zones | `core/schemas.py` | Raw client text never reaches business logic |
| 4 | Deterministic action validator (allow-list, exact param schemas, blocked outbound patterns) | `core/safety/gates.py` | An LLM cannot invent capabilities; exfil-style emails are pattern-blocked |
| 5 | Risk gate + human-in-the-loop | `agents/orchestrator.py` | `send_email` never runs without recorded approval; flagged requests escalate even medium-risk actions to review |
| 6 | Tenant-isolated retrieval | `knowledge/vector_store.py` | Cross-client data leakage is structurally impossible (no cross-tenant search API exists) |
| 7 | Draft/send separation in email | `integrations/email.py` | Nothing leaves the building without two explicit gates |
| 8 | Append-only audit trail | `core/safety/audit.py` | Every decision is reconstructible |

## Quick start

```powershell
cd financial-agent
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # defaults run fully offline via MockLLM
.venv\Scripts\python main.py  # 3-scenario demo incl. a prompt-injection attack
.venv\Scripts\python -m pytest -q
```

No API key needed while `USE_MOCK_LLM=true`. To use a real LLM:

```ini
OPENAI_API_KEY=sk-...
USE_MOCK_LLM=false
MODEL_NAME=gpt-4o-mini
```

The demo will pause at the approval gate:

```
PENDING APPROVALS (human-in-the-loop gate)
  act_xxx  tool=send_email  risk=high
  Approve? [y/N]
```

## Project layout

```
config.py                 environment-driven settings
core/schemas.py           Pydantic contracts crossing the safety boundary
core/llm.py               OpenAI client + offline MockLLM
core/safety/sanitizer.py  untrusted-content hygiene + injection detection
core/safety/gates.py      tool allow-list registry + ActionValidator + risk tiers
core/safety/audit.py      append-only JSONL audit trail
agents/intake_agent.py    ZONE A: client-facing, no tools
agents/work_agent.py      ZONE B: internal, proposes allow-listed actions only
agents/orchestrator.py    pipeline + validation + risk gating + approvals
knowledge/vector_store.py ChromaDB RAG with forced tenant filter
integrations/crm.py       JSON-backed CRM stand-in
integrations/email.py     draft/send-separated email stand-in
main.py                   end-to-end demo (invoice, lead, attack scenarios)
tests/test_safety.py      safety regression suite (offline)
```

See `ROADMAP.md` for where this goes next and `HANDOFF.md` for build notes.