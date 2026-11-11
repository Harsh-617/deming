"""Single place for runtime settings. The model name lives here and nowhere else."""
import json
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

# docs/contracts.md: lane decisions compare support dates with the ground-truth as_of_date,
# not the wall clock. `--as-of` on the CLIs overrides it.
GROUND_TRUTH_META = ROOT / "data" / "ground_truth_meta.json"


def load_as_of_date(override: str | None = None, path: Path = GROUND_TRUTH_META) -> str:
    """The as_of_date to evaluate against: `override` if given, else ground_truth_meta.json."""
    import datetime as dt
    value = override or json.loads(Path(path).read_text(encoding="utf-8"))["as_of_date"]
    return dt.date.fromisoformat(value).isoformat()  # raises on a malformed date
