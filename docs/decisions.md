# Decisions

**Branch decision logs** (kept as separate files):
- [feat/feeds](decisions/feeds.md): KEV fetcher, lifecycle.csv sourcing
- [feat/eval](decisions/feat-eval.md): baseline, metrics, report, Sheet template
- [feat/agents](decisions/feat-agents.md): subagent prompts, schemas, runner, Agent Designer port

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

### 2026-11-11 · Shared file contracts
- **Choice:** `docs/contracts.md` v1. Raw KEV is stored byte-for-byte, with sha256 in `kev_meta.json`.
  The lifecycle `model_pattern` is a case-insensitive glob. Predictions `evidence` is `;`-separated
  CVE/lifecycle ids, so it can be scored automatically. The lane tie-break is unknown > retire > patch > fine.
- **Alternatives:** regex for `model_pattern` (more powerful, but harder for humans to label); free-text
  evidence (not scorable); a normalized KEV copy (loses reproducibility).
- **Source:** https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
  (fetched 2026-11-11: catalogVersion 2026.11.09, count 1773; entry fields include the new `forensicTriage`).
- **Not verified:** the tie-break order is my proposal and still needs the team's sign-off.

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

### 2026-11-11 · jsonschema
- **Choice:** `jsonschema` unpinned (like the other entries); installed 4.26.0, `Requires-Python >=3.10`, so fine on 3.11.7. `pip check` reports no conflicts with the current requirements. Verified from the installed package metadata.
- **Source:** https://pypi.org/project/jsonschema/

### 2026-11-11 · openpyxl
- **Choice:** `openpyxl` unpinned (like the other entries), needed by `scripts/make_sheet_template.py` (feat/eval) to write the .xlsx Sheet template. Installed 3.1.5; `Requires-Python >=3.8`. Verified from the installed package metadata.
- **Alternatives:** `xlsxwriter` (write-only, can't read back for tests); pandas `to_excel` (still needs an engine).
- **Source:** https://pypi.org/project/openpyxl/

### 2026-11-11 · Contracts v1.1
- **Choice:** `model_pattern` globs the device's model (hardware rows) or version/firmware (software rows), most specific matching row wins; booleans read case-insensitively; `critical` counts as urgent; optional trailing `fixed_version` column in `lifecycle.csv` (blank for now); `data/ground_truth_meta.json` with `as_of_date` 2026-11-12, used by the eval and Checker instead of the wall clock.
- **Why:** feat/feeds found the v1 `model_pattern` rule could never match KEV family names (see [decisions/feeds.md](decisions/feeds.md)); Sheets exports `TRUE`/`FALSE`; `LC-030` flips to retire on 2026-12-09, so a wall-clock date would change the ground truth.
- **Alternatives:** a separate `version_pattern` column (cleaner, more churn two days before the deadline).
- **Not verified:** the Sheets `TRUE`/`FALSE` export behaviour is taken from the user's instruction, not tested here.

### 2026-11-11 · Firmware version comparison and pattern matching
- **Choice:** own strict parser in `sim/guards.py`: optional `v`/`V`, then dot-separated ASCII
  integers (`[0-9]`, not `\d`, which matches non-ASCII digits), compared as integer tuples with
  trailing zeros dropped (`1.5.1` == `1.5.1.0`, `1.0.03.26` == `1.0.3.26`). Anything else
  (`7.0.12 build 523`, `11.1.4-h13`, `22.7R2.6`, `7.0.1-5161`) does not parse, and the guard
  forces `unknown`. Glob matching uses `fnmatch.fnmatchcase` on lowercased strings.
- **Why:** checked locally with packaging 26.3 on Python 3.11: `packaging.version.Version` rejects
  `7.0.12 build 523` but *accepts* `7.0.1-5161` as `7.0.1.post5161` (PEP 440 post-release), so a
  SonicWall build number would be silently reinterpreted. `v1.4.2.22` parses fine in both.
  `fnmatch.fnmatch` applies `os.path.normcase`, so it is case-insensitive on Windows only;
  `fnmatchcase` + explicit lowercasing is the same on every OS.
- **Alternatives:** `packaging.version` (PEP 440 semantics don't fit vendor firmware);
  `looseversion`/`distutils.LooseVersion` (compares mixed int/str parts, order is surprising
  and distutils is removed in 3.12); regex-extract the first dotted number (guesses).
- **Source:** https://docs.python.org/3/library/fnmatch.html ·
  https://packaging.pypa.io/en/stable/version.html · https://peps.python.org/pep-0440/#post-releases
- **Limits:** strict parsing sends every vendor-specific suffix (hotfix `-h13`, `R` trains, build
  numbers) to `unknown`; `fixed_version` is blank in every `data/lifecycle.csv` row today, so
  every KEV-listed device with a lifecycle row currently goes to `unknown` ("fixed version not
  documented") until humans fill that column.
