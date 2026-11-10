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

### 2026-11-11 · Model for the evaluation (supersedes the default above)
- **Choice:** `gemini-3.5-flash-lite` for the evaluation and the prototype pipeline.
- **Why:** it's badged *Stable* on Google's models page, while `gemini-3.8-flash` is badged *New*.
  The live smoke test (`eval/smoke_test.py`, 2026-11-11, google-genai 3.0.0, temperature 0, JSON schema):
  - `gemini-3.5-flash-lite`: 3/3 OK, outputs byte-identical, latency 4.3 to 7.9 s (avg 6.2 s).
  - `gemini-3.8-flash`: 0/3. All three returned `503 UNAVAILABLE` "This model is currently experiencing high
    demand...". The new model wasn't clearly better; it didn't answer at all.
- **Alternatives:** `gemini-3.8-flash` (retest later; it may be a temporary capacity spike);
  `gemini-3.6-flash` (Stable, "previous-generation"; not tested).
- **Source:** https://aistudio.google.com/docs/models
- **Not verified:**
  - The 3.8 calls took 3.6 s, 17.8 s and 40.1 s before failing, which looks like the SDK's built-in
    retry/backoff, but I haven't confirmed it.
  - One structured-extraction prompt says nothing about accuracy on our task.
  - `models.list()` still lists `gemini-2.5-flash`/`-pro`/`-flash-lite` for this key. We don't use
    them (deprecated per the docs).

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

### 2026-11-11 · Git hook for manual commits
- **Choice:** the scanner moved to `scripts/block_secrets.py` (tracked), with `--claude-hook` and
  `--git-hook` modes. Git runs it through `scripts/githooks/pre-commit` and `pre-merge-commit`.
  Install with `git config core.hooksPath <absolute path>/scripts/githooks`.
- **Why `pre-merge-commit` too:** a merge commit doesn't run `pre-commit`.
- **Why an absolute hooksPath:** `core.hooksPath` lives in the shared `.git/config`, so every
  worktree sees it. A *relative* path would resolve inside each worktree's own checkout, so a
  worktree on a branch without `scripts/` would silently have no hook. The absolute path makes all
  worktrees use the main checkout's script. Tested in a real worktree: it blocked a staged `.env`
  and a fake key, and `git -C <worktree> config core.hooksPath` showed the shared value.
  *Not verified from docs:* how a relative hooksPath resolves (that statement is from memory).
  The shared-config point is tested, and the docs only imply it.
- **Alternatives:** copy into `.git/hooks` (shared by worktrees, but not versioned and must be
  re-copied after edits); the `pre-commit` framework + gitleaks (stronger, but adds a dependency).
- **Source:** https://git-scm.com/docs/githooks · https://git-scm.com/docs/git-config#Documentation/git-config.txt-corehooksPath
- **Limits:** this is a client-side hook, so `--no-verify` skips it and each clone must run the
  install line. A fast-forward merge or a push creates no commit, so neither runs it (commits
  pushed from elsewhere aren't scanned; a `pre-push` hook or GitHub secret scanning would cover
  that). The commit *message* isn't scanned in git mode (that would need a `commit-msg` hook).
  It fails closed if no Python is on PATH.

### 2026-11-11 · Python environment
- **Choice:** plain `python -m venv .venv` on conda base 3.11.7, activated with `.venv\Scripts\Activate.ps1`.
- **Alternatives:** a conda env, or uv. Not used, per the user's instruction (and `conda deactivate` switches to 3.14).
