"""Central configuration. Values come from environment variables / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR") or (BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "true").lower() == "true"
APPROVAL_MODE = os.getenv("APPROVAL_MODE", "manual").lower()  # manual | auto
MAX_UNTRUSTED_CHARS = int(os.getenv("MAX_UNTRUSTED_CHARS", "20000"))

AUDIT_LOG_PATH = DATA_DIR / "audit.log.jsonl"
CHROMA_DIR = DATA_DIR / "chroma"