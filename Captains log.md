# Captain's Log

Running narrative of the build: decisions, failures, fixes. Newest at top?
No - chronological, like a proper log. Newest entries at the BOTTOM.

---

## Entry 001 - 2026-08-26 - First voyage

**Mission:** Training build of an Upwork-style brief: AI agent for financial
business automation, with a deliberate safety split between client-facing
input and internal work systems.

**Course sailed:**
1. Designed the two-zone architecture on paper first: Zone A (intake, no
   tools) -> structured ClientIntake contract -> Zone B (work agent,
   propose-only) -> deterministic validator -> risk gate -> executor.
   Key principle: an LLM may PROPOSE, only deterministic code DISPOSES.
2. Scaffolded the full project (~18 files): core schemas, sanitizer, gates,
   audit log, pluggable LLM (OpenAI + offline MockLLM), tenant-isolated
   ChromaDB store, mock CRM + email, agents, orchestrator, demo, tests.
3. Created `.venv` (per good practice - nothing global), installed chromadb,
   pypdf, pydantic, dotenv, pytest, openai inside it.

**Icebergs hit:**
- *ChromaDB 1.5.9 rejected our collection name* `"kb"` - new validation
  demands 3-512 chars. Renamed to `financial_kb`. Lesson: newer chromadb is
  stricter than most tutorials assume.
- *Test suite caught a REAL bug in my own safety gate*: the email-format check
  keyed off param NAMES containing "email", so `send_email(to=...)` slipped
  through unchecked. Exactly the kind of hole the tests exist for. Fixed by
  validating `to`/`cc`/`bcc` too - and then tightened the regex itself, which
  had been accepting trailing dots (`bob@x.com.`).

**Landfalls:**
- 7/7 safety tests green.
- Full offline demo sailed cleanly: invoice inquiry handled with tenant-scoped
  KB answers; lead qualified with CRM write + send_email HELD at the approval
  gate (denied -> 0 emails sent all session); prompt-injection attack flagged
  with FIVE distinct patterns and reduced to read-only lookups. The split
  held.

**Log closed with:** README, HANDOFF (for the next AI), ROADMAP (four phases),
this log. Repo pushed to a private GitHub repository.

Next watch: Phase 1 in ROADMAP.md - real LLM against the same scenarios, and
a meaner injection corpus for the sanitizer.