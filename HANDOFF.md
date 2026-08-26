# HANDOFF.md

Handoff notes for the next AI/human picking up this project.
Last updated: 2026-08-26.

## What was done

Full first build of the safety-first financial AI agent (training scaffold):

- Two-zone architecture: client-facing **IntakeAgent** (Zone A, zero tools)
  and internal **WorkAgent** (Zone B, propose-only) joined by a Pydantic
  `ClientIntake` contract (`core/schemas.py`).
- Sanitizer (`core/safety/sanitizer.py`): regex injection-pattern flagging,
  zero-width character stripping, `<untrusted_client_content>` delimiting,
  truncation cap.
- Deterministic gate (`core/safety/gates.py`): 6-tool allow-list registry with
  risk tiers (LOW/MEDIUM/HIGH), exact parameter schemas, length caps, email
  syntax checks on address params, blocked-pattern scan of outbound text.
- Orchestrator (`agents/orchestrator.py`): validate -> risk-gate -> execute;
  HIGH-risk actions queue for human approval (`decide_pending`); any request
  carrying injection flags escalates ALL non-read-only actions to approval.
- Tenant-isolated RAG (`knowledge/vector_store.py`, ChromaDB persistent).
  Forced `$or[client_id, __global__]` metadata filter on every query.
- Mock integrations: JSON-file CRM, draft/send-separated EmailService.
- Pluggable LLM (`core/llm.py`): OpenAI chat client + deterministic MockLLM
  routed by `TASK:` markers in system prompts (offline mode = default).
- Demo (`main.py`): invoice happy path, inbound lead (exercises approval
  gate), prompt-injection attack scenario.
- Test suite (`tests/test_safety.py`): 7 offline safety regression tests.
- Python venv at `.venv`; deps pinned loosely in `requirements.txt`.

## What worked

- End-to-end offline run of all three demo scenarios (see Captains log).
- Attack containment verified live: 5 injection patterns flagged on the attack
  message; only read-only `kb_search` executed; zero outward actions; 0 emails
  sent in the whole session even with a pending HIGH-risk send.
- All 7 pytest tests green after fixes below.
- ChromaDB default embedding (all-MiniLM-L6-v2 ONNX, ~79 MB) downloaded fine
  on first use; `_KeywordEmbedding` fallback exists for offline machines.

## What did NOT work (and fixes applied)

1. **ChromaDB >= 1.x rejects short collection names** (`"kb"` failed with
   `InvalidArgumentError ... Expected 3-512 characters`). Fixed by renaming the
   collection to `financial_kb`. If you add collections, keep names >= 3 chars.
2. **Validator email check missed `to=` params** - it only checked param names
   containing the substring "email", so `send_email(to=...)` skipped the check.
   Caught by `test_validator_rejects_schema_violation`. Fixed: `to`, `cc`,
   `bcc` (or names containing "email") are now validated as addresses.
3. **Loose email regex** accepted trailing dots (`bob@x.com.`); tightened to
   `^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$` and the mock extractor now rstrips ".".
4. First pytest run: 2 failed / 2 errors from issues 1-2 above; final state
   7 passed.

## Environment notes

- Windows, PowerShell 7, Python 3.12.10. Global pip already had openai /
  pydantic / dotenv / pytest; chromadb + pypdf installed into `.venv` only.
- `config.py` resolves paths at import time -> anything that needs an isolated
  DATA_DIR (like the tests) must set the env var BEFORE importing the package.
- Audit log + crm.json + chroma dir all live under `data/` (gitignored).
- `main.py` reads stdin at the approval gate when APPROVAL_MODE=manual; pipe
  `"n","n" | python main.py` for non-interactive runs.

## Known limitations / sharp edges

- MockLLM echoes raw (wrapped) client text into `intake.summary`; cosmetic,
  but a real LLM prompt should explicitly ask for a clean summary.
- Outbound blocked-pattern scan also applies to drafts/log summaries -
  quoting a client who wrote "ignore previous..." would reject that draft.
  Deliberate defense-in-depth tradeoff; relax per-tool if needed.
- Single-pass planning: kb_search results are not fed back into planning yet.
  See ROADMAP phase 2 for the iterative loop.
- No auth, no rate limiting, no concurrency control - single-process demo.

## Suggested next steps

Start at ROADMAP.md phase 1. Run `pytest -q` after every change; the safety
suite is the regression net for exactly the properties this project exists to
protect.