"""Sanitizes untrusted client content before it ever reaches an LLM prompt.

Design rule: content coming from clients is DATA, never INSTRUCTIONS. The
sanitizer (a) strips invisible trickery such as zero-width characters,
(b) detects classic prompt-injection phrasing and FLAGS it (evidence kept for
the audit trail), and (c) provides ``render_as_data`` so the rest of the
pipeline can only embed it inside explicit untrusted-content tags.
"""
from __future__ import annotations

import re

import config

from core.schemas import SanitizedContent, TrustLevel

# Case-insensitive patterns indicating an injection attempt. Flagging does not
# silently drop content; downstream gates treat flagged requests strictly:
# the orchestrator escalates ANY non-read-only action to human approval.
INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above|earlier)",
    r"disregard\s+(?:all\s+)?(?:previous|prior|above|earlier)",
    r"forget\s+(?:all\s+)?(?:previous|prior|earlier)\s+(?:instructions|prompts?)?",
    r"(?:system|developer|admin)\s+(?:prompt|message|instructions)",
    r"you\s+are\s+now\b",
    r"act\s+as\s+(?:a|an|the|if)",
    r"pretend\s+(?:to\s+be|you\s+are)",
    r"(?:reveal|print|show)\s+(?:me\s+)?(?:your|the)\s+(?:prompt|instructions|rules|system)",
    r"</?\s*(?:system|\|im_start\|)\s*>",
    r"\bexecute\b.{0,20}\bcommand\b",
    r"\bsend\b.{0,30}\b(?:all\s+)?(?:client|customer|user)s?\b.{0,30}\b(?:data|database|records|list)\b",
]

_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")


def sanitize_untrusted(text: str, source: str = "") -> SanitizedContent:
    flags: list[str] = []
    cleaned = _ZERO_WIDTH.sub("", text or "")
    if cleaned != (text or ""):
        flags.append("zero_width_chars_removed")

    lowered = cleaned.lower()
    for pat in INJECTION_PATTERNS:
        if re.search(pat, lowered):
            flags.append(f"injection_pattern::{pat}")

    limit = config.MAX_UNTRUSTED_CHARS
    if len(cleaned) > limit:
        cleaned = cleaned[:limit]
        flags.append(f"truncated_to_{limit}_chars")

    return SanitizedContent(
        text=cleaned.strip(), trust=TrustLevel.SANITIZED, source=source, flags=flags
    )


def render_as_data(content: SanitizedContent) -> str:
    """Render untrusted content for embedding in a prompt. The surrounding tags
    tell the model this is data; inline flags warn it about detected tampering.
    Fake closing tags inside the content are neutralized first."""
    warning = f" [SECURITY FLAGS: {', '.join(content.flags)}]" if content.flags else ""
    safe_text = content.text.replace("<untrusted_client_content>", "[removed fake tag]")
    return (
        f'<untrusted_client_content source="{content.source}"{warning}>\n'
        f"{safe_text}\n"
        f"</untrusted_client_content>"
    )