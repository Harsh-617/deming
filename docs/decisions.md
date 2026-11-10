# Decisions

One short entry per decision: choice, alternatives, source, and what couldn't be verified.

---

### 2026-11-11 · Gemini model
- **Choice:** `gemini-3.8-flash` as default, set in one config value (e.g. `GEMINI_MODEL` env var).
  Fallback: `gemini-3.5-flash-lite`.
- **Why:** Google's models page tells new projects to "use our latest models: 3.5 Flash-Lite or
  3.8 Flash", and the official Python SDK docs use `gemini-3.8-flash` in their structured-output
  examples.
- **Alternatives:** `gemini-3.5-flash-lite` (badged *Stable*, cheaper; 3.8 Flash is badged *New*,
  not Stable). `gemini-3.6-flash` (Stable, but called "previous-generation"). Gemini 2.5: not used.
- **Source:** https://aistudio.google.com/docs/models (`ai.google.dev/gemini-api/docs/models` now redirects there)
- **Not verified:** the docs list `gemini-2.5-flash`/`-pro` as *deprecated* (rerouted from
  1 Dec 2026), and `gemini-2.5-flash-lite` as still served, not as "shut down". We avoid 2.5
  either way. No live API call was made (no key yet), so the model ID hasn't been tested against the API.

### 2026-11-11 · Structured JSON output
- **Choice:** `client.models.generate_content(..., config=types.GenerateContentConfig(
  response_mime_type="application/json", response_schema=<Pydantic model>))`.
- **Alternatives:** `response_json_schema` (plain JSON Schema dict, which may port more easily to
  Agent Designer, worth revisiting); the newer Interactions API (`client.interactions.create`
  with `response_format`), which is what Google's structured-output guide now shows.
- **Source:** https://googleapis.github.io/python-genai/ ·
  https://aistudio.google.com/docs/structured-output
- **Note:** don't repeat the schema inside the prompt (SDK docs say quality may drop).

### 2026-11-11 · SDK package
- **Choice:** `google-genai` (latest on PyPI: 3.0.0, requires Python ≥ 3.11, which fits our 3.11.7).
- **Alternatives:** the legacy `google-generativeai` package (superseded); raw REST via `requests`.
- **Source:** https://pypi.org/project/google-genai/

### 2026-11-11 · Secret-blocking commit hook
- **Choice:** Claude Code `PreToolUse` hook on `Bash|PowerShell`, stdlib Python script, exit 2 to block.
  It scans staged, unstaged and untracked (non-ignored) changes plus the command text, because
  it runs *before* a chained `git add . && git commit`.
- **Alternatives:** git `pre-commit` hook (also covers manual commits, but `.git/hooks` isn't
  versioned); `pre-commit` framework + gitleaks (stronger, but more setup).
- **Source:** https://code.claude.com/docs/en/hooks
- **Limits:** it only guards commits made *through Claude Code*, and it fails open if `python` isn't on
  PATH for Git Bash.

### 2026-11-11 · Python environment
- **Choice:** plain `python -m venv .venv` on conda base 3.11.7, activated with `.venv\Scripts\Activate.ps1`.
- **Alternatives:** a conda env, or uv. Not used, per the user's instruction (and `conda deactivate` switches to 3.14).
