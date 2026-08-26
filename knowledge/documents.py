"""Small document-parsing helper for attachments (.txt/.md/.pdf)."""
from __future__ import annotations

from pathlib import Path


def parse_file(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".txt", ".md"):
        return p.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        from pypdf import PdfReader  # lazy import: only needed for pdfs

        reader = PdfReader(str(p))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(f"Unsupported attachment type: '{suffix}' ({p.name})")