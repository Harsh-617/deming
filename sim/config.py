"""Single place for runtime settings. The model name lives here and nowhere else."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / "agents"
SCHEMAS_DIR = ROOT / "schemas"
CACHE_DIR = Path(os.environ.get("DEMING_CACHE_DIR", ROOT / ".cache" / "gemini"))

# docs/contracts.md: all evaluation runs use gemini-3.5-flash-lite. Override with GEMINI_MODEL.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
TEMPERATURE = 0.0

# Must match the literal "0.80" written in every agents/*.md prompt (checked by a test).
CONFIDENCE_THRESHOLD = 0.80

AGENT_NAMES = ("normalizer", "checker", "planner", "verifier")

# Retry policy for 429 / 503 (own loop; SDK retry is switched off).
RETRY_STATUS_CODES = (429, 503)
MAX_RETRIES = 5
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 30.0
