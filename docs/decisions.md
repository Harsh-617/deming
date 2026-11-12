# Decisions

**Branch decision logs** (kept as separate files):
- [feat/feeds](decisions/feeds.md): KEV fetcher, lifecycle.csv sourcing
- [feat/eval](decisions/feat-eval.md): baseline, metrics, report, Sheet template
- [feat/agents](decisions/feat-agents.md): subagent prompts, schemas, runner, Agent Designer port
- [feat/inventory](decisions/feat-inventory.md): 60-device inventory, ground truth, fixed_version sources
- [feat/loop](decisions/feat-loop.md): closed-loop simulator, approvals, idempotency, loop metrics
- [feat/review](decisions/feat-review.md): label checks, static review and blind pages, review merge
- [feat/docs](decisions/feat-docs.md): README, limits, AI and teamwork, demo script, submission checklist
- [feat/cross-check](decisions/feat-cross-check.md): agreement metrics for the blind AI cross-check, adapter, source checks
- [feat/demo-sheet](decisions/feat-demo-sheet.md): demo workbooks for Sheets import, Summary double-count fix
- [feat/owner-sim](decisions/feat-owner-sim.md): scripted owner-reply simulator, seeded runs, audit

The entries of these files are also copied in full at the end of this file (see "Branch decision logs, copied into this file").

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

### 2026-11-11 · fixed_version per release train (contracts v1.2)
- **Choice:** `fixed_version` may list one fix per train (`7.24.3;7.23.6`). The version guard
  (`sim/guards.py::select_train_fixes`) compares the firmware only with the entry sharing the
  longest leading numeric prefix with it, at least major.minor, compared as numbers (`7.2` is
  not on train `7.23`). No entry on the train, unparseable firmware, or firmware between two tied
  entries → `unknown`. A single value is compared as before. Same rule in `tests/test_inventory.py`
  (its old fallback compared against all entries across trains).
- **Why:** vendor advisories list fixes per train (MikroTik stable/long-term, Cisco ASA
  9.20/9.22/9.23, PAN-OS 11.1.x hotfix lines). The lowest fix on another train makes a vulnerable
  device look fixed (RouterOS 7.24.1 > 7.23.6, but its own fix is 7.24.3).
- **Alternatives:** compare against the minimum (cross-train, wrong); against the maximum (marks
  fixed long-term devices as patch); one lifecycle row per train (more rows, same result; possible later).
- **Source:** https://mikrotik.com/supportsec/september-2026-vulnerability ·
  https://sec.cloudapps.cisco.com/security/center/resources/asa_ftd_continued_attacks (row source_urls).
  No new research; rule set by the user.
- **Limits:** PAN-OS hotfix strings (`11.1.4-h13`) are outside the strict version grammar, so every
  PAN-OS device with a KEV match still goes to `unknown`. Single-value rows are not train-checked
  (LC-029 WatchGuard `12.11.4` vs model-specific 12.5.x builds).

### 2026-11-11 · PAN-OS hotfix suffixes parse (reverses part of "Firmware version comparison")
- **Choice:** `sim/guards.parse_version` now also accepts exactly `major.minor.patch-h<digits>`
  (lowercase `h`, ASCII digits, nothing after), compared as `(major, minor, patch, hotfix)` with
  hotfix 0 when absent (`11.1.4` == `11.1.4-h0` < `11.1.4-h1`). Train selection is unchanged and
  uses the numbers before `-h`. Every other suffix still does not parse → `unknown`:
  SonicWall build numbers `7.0.1-5161`, `build 523`, Ivanti `22.7R2.6`, NetScaler `14.1-43.50`,
  and near-misses `-H7`, `11.1-h3`, `11.1.4-hotfix7`. `tests/test_inventory.py` now imports this
  parser and `select_train_fixes` instead of its own digit-grab `_vkey`.
- **Why reversed:** the earlier rule sent every PAN-OS device with a KEV match to `unknown`
  (7 real devices: DEV-033/047/048 patch, DEV-006/008/035/038 fine), although Palo Alto's own
  advisories state fixes as `-h<n>` hotfixes on a release line, which is an unambiguous total order.
  The `-h` form can't be confused with a build number, unlike `7.0.1-5161`, which stays out.
- **Side effect found:** with one shared parser, 4 `clear_patch` labels can't be compared by the
  guard (DEV-009/034 Ivanti `22.7R2.x`, DEV-021/050 NetScaler `14.1-NN.NN`). They were already
  predicted `unknown`; the old lenient test parser hid that. Pinned as an explicit list in the test.
- **Alternatives:** keep PAN-OS unknown (safe but 7 avoidable unknowns); a per-vendor parser table
  (more surface, not needed for one vendor); generic `-<suffix>` (would let `7.0.1-5161` in).
- **Source:** https://security.paloaltonetworks.com/CVE-2025-0108 (LC-021 `source_url`; fixed
  versions written `11.1.2-h18`, `11.1.4-h13`, `11.1.6-h1`). Rule set by the user; no new research.
- **Limits:** a 4-part dotted version `11.1.4.7` compares equal to `11.1.4-h7`; no PAN-OS release
  uses 4 dotted parts, and trains are chosen per lifecycle row, so the two never meet in practice.

### 2026-11-11 · Overdue KEV due date → deadline = as_of_date + 14 days
- **Choice:** if the Checker's KEV `due_date` is before `as_of_date`, the Planner's deadline is
  `as_of_date + kev_overdue_grace_days` (new Settings key, default 14) and the owner message says
  the CISA date has passed. Patch lane only: for retire the Checker's `due_date` is the support end
  date (checker.md rule 6), not a CISA date. Prompt rule 8 says so; `guards.guard_planner` enforces
  it, and the sentence is rebuilt from trusted fields (never copied from model text, which can
  carry injected words).
- **Open issue (not changed):** planner rule 8 for retire takes `today + days_until_escalation`
  unless the due date is earlier, and a retire `due_date` (support end) is always in the past, so
  retire deadlines come out in the past. Needs a rule decision.
- **Why:** most KEV due dates are years old (federal BOD 22-01 deadlines), so a deadline in the
  past is meaningless to an owner and breaks reminders and calendar windows.
- **Alternatives:** keep the past date (useless); today + escalation days (mixes two settings).
- **Source:** https://www.cisa.gov/known-exploited-vulnerabilities-catalog (dueDate is the BOD
  22-01 remediation date). Rule and default set by the user.

### 2026-11-11 · Verifier: removal closes any ticket type; merge of feat/loop
- **Choice:** `guards.guard_verifier` allows `close` on `device_removed` for patch, retire and
  identify tickets, matching `sim/loop.decide_verification`; with `record_present=True` (passed
  by `sim/pipeline.verify_ticket`) a model claiming removal while the row exists is escalated.
  On merge, `decide_verification` was switched to `select_train_fixes`: feat/loop compared the new
  version with the whole `;`-joined `fixed_version`, which can't parse after contracts v1.2.
- **Why:** a removed device leaves nothing to track; the loop already closed such tickets, so the
  LLM guard and the loop disagreed.
- **Source:** internal consistency; no external research.

### 2026-11-11 · Live smoke test concurrency (Gemini free tier)
- **Choice:** concurrency 1 (strictly sequential calls) for live runs, relying on the runner's own
  429/503 backoff (5 retries, 1 s base, 30 s cap, jitter). Harness: `eval/live_fixture_run.py`.
- **Why:** the official rate-limits page no longer lists free-tier RPM/TPM/RPD per model; it says
  limits apply **per project** (not per key), RPD resets at midnight Pacific, and the active
  limits are shown in AI Studio. Without a verified RPM, sequential is the only safe choice.
  Observed: even sequential, 17 of 69 live calls hit 429 or 503 once or more (all recovered),
  so parallel calls would hit the limit harder.
- **Alternatives:** 2-4 worker threads (faster, but unverified limits and more 429s); the Batch
  API (the page lists Gemini 3.5 Flash-Lite batch quotas only for Tier 1-3, not free tier).
- **Source:** https://ai.google.dev/gemini-api/docs/rate-limits (301 → https://aistudio.google.com/docs/rate-limits), read 2026-11-11.
- **Not verified:** the actual free-tier RPM/RPD for `gemini-3.5-flash-lite`; check AI Studio's
  rate-limit page for this project before the 60 x 3 run.
- **Result (fixture, 8 devices):** 0 schema-validation failures, 0 HTTP 400s, so no schema
  changes were needed. Lanes 5/8 correct; lane agreement over 3 repeats 8/8. The 3 misses
  (DEV-001/002/007, truth patch → unknown) follow checker.md rule 4.5: the fixture has no
  lifecycle row (so no `fixed_version`) for Fortinet or Ivanti.

### 2026-11-11 · Ivanti and NetScaler version forms (contracts v1.4)
- **Choice:** `sim/guards.parse_version` accepts two more exact forms, each its own family:
  Ivanti Connect Secure `<major>.<minor>R<release>.<build>` (`22.7R2.6`) ordered
  `(major, minor, release, build)`, and Citrix NetScaler `<major>.<minor>-<build>.<sub>`
  (`14.1-47.46`) ordered `(major, minor, build, sub)`. No `v` prefix, capital `R`, ASCII digits,
  nothing before or after. `compare_versions` returns None across families (so `22.7.2.6` vs
  `22.7R2.6` → `unknown`); the guard and the loop's Verifier rule treat that as not comparable.
  Still unparseable: `22.7r2.6`, `22.3R1` (no build), `v22.7R2.6`, `13.1-37.236-FIPS`, `14.1-47`,
  `14.1-47.46a`, `7.0.1-5161`. `tests/test_inventory.py` keeps using the same parser; its
  "unparseable clear_patch" allowance (DEV-009/021/034/050) is gone: all four now compare and
  reach `patch` through the guard (`eval/test_vendor_versions.py`, real `data/` rows).
- **How the vendors order releases (read 2026-11-11):** Ivanti's page says "Ivanti Connect Secure
  (version 22.7R2.5 and earlier)" is affected and the issue "was fully patched in Ivanti Connect
  Secure 22.7R2.6"; it gives no ordering rule beyond "and earlier" / "up to". Citrix CTX694788
  lists affected "14.1 BEFORE 14.1-47.46" and "13.1 BEFORE 13.1-59.19", fixed "14.1-47.46 and
  later releases" (per release line, "later releases of 13.1"); FIPS/NDcPP builds carry a suffix
  (`13.1-37.236-FIPS`). Neither page defines the parts, so the numeric left-to-right order is an
  inference from "earlier/BEFORE/later" and is stated as such.
- **Alternatives:** generic `<dotted><sep><dotted>` (would admit SonicWall `7.0.1-5161` build
  numbers); `packaging.version` (PEP 440 misreads both forms); keep them unknown (4 avoidable misses).
- **Source:** https://www.ivanti.com/blog/security-update-pulse-connect-secure-ivanti-connect-secure-policy-secure-and-neurons-for-zta-gateways ·
  https://support.citrix.com/external/article/CTX694788/netscaler-adc-and-netscaler-gateway-secu.html
  (the LC-022 / LC-023 `source_url`s).
- **Not verified:** that Ivanti never ships a release whose build part is compared other than
  numerically (e.g. `22.7R2.10` vs `22.7R2.9`); that NetScaler `sub` is always numeric outside
  FIPS builds.

### 2026-11-11 · Retire deadline = as_of_date + retire_days (closes the open issue above)
- **Choice:** retire deadline = `as_of_date` + Settings `retire_days` (default 30). The Checker's
  retire `due_date` (the support end date) stays as evidence: the message says "Vendor support
  ended on X." Interim isolation advice within Settings `retire_isolation_days` (default 7) days,
  except for do_not_touch devices (escalated, no isolation wording). Enforced in
  `guards.guard_planner` (sentence rebuilt from trusted fields when a fact is missing), the mock,
  the loop's body rebuild (`guards.deadline_sentence`) and planner.md rule 8.
- **Why:** the support end date is always in the past for retire, so the old rule
  (`today + days_until_escalation` unless the due date is earlier) produced past deadlines.
- **Source:** rule and defaults set by the user; no external research.

### 2026-11-11 · Recipient and ticket issue taken out of the model's hands; evidence filled in code
- **Choice:** `schemas/planner.json` / `sim/models.Message` have no `to`; `guards.recipient` sets
  it (owner_email, or approver_email for `unknown`), as the loop already did. Proposals write
  `drafted_to` blank, so `owner_routing_accuracy` is null on new state and `routing_after_guard`
  is the routing metric. `ticket.issue` is the enum `patch|retire|identify`, and the guard sets
  it from the lane. `guards.fill_evidence` sets `evidence_lifecycle_id` (governing candidate row)
  for patch/retire/fine and fills `evidence_cve` for patch/retire from the KEV candidates of the
  same vendor/product when the model gave none; model ids are kept only if they are candidates.
  `fine` carries no CVEs (a CVE on a fine device reads as "affected"). An id outside the
  candidates still forces `unknown` (unchanged anti-hallucination rule).
- **Also changed (consistency):** the version guard now applies checker.md rule 4.5 when no
  lifecycle row matches at all: a KEV match with no documented fixed version is `unknown`, never
  patch/fine. Before, a model `patch` on such a device passed, and the evidence fill would have
  given it CVE evidence. One old test pinned the gap (`test_no_matching_lifecycle_row_is_not_touched`)
  and was rewritten.
- **Why:** a model-chosen recipient is an injection target; a free-text issue breaks dedupe keys;
  empty evidence on a patch/retire decision breaks "evidence on every decision".
- **Source:** rules set by the user; internal consistency, no external research.

### 2026-11-11 · Fixture truth DEV-001/002/007 → unknown
- **Choice:** relabelled the three `eval/fixtures/ground_truth.csv` rows from patch to unknown
  (evidence cleared, notes say why), rather than adding fixture lifecycle rows.
- **Why:** the labels predate "KEV match with blank fixed_version → unknown". Adding rows would
  not have fixed DEV-002: its firmware `22.3R1` has no build number, so it is not the exact Ivanti
  form and stays `unknown` anyway. The hand-made fixture runs were left unchanged (they were
  predictions against the old labels); `eval/test_metrics.py` and `test_eval_pipeline.py`
  expectations were recomputed and commented.

### 2026-11-11 · Stability: structured fields vs free text
- **Choice:** `eval/metrics.stability` reports agreement per structured field (lane, vendor,
  product, version, evidence ids as a set) and all together; free text isn't in the predictions
  CSV, so the eval report says so. `eval/live_fixture_run.py` reports three groups: contract
  structured fields, Planner structured fields (action, priority, deadline, escalate, ticket
  issue/create, recipient), and free text (reasons, subject, body), all exact-match.
- **Why:** with temperature 0 a reworded reason made "full output agreement" look unstable
  when every decision was the same.

### 2026-11-11 · Live fixture run after the rule fixes (gemini-3.5-flash-lite, real API)
- **Setup:** `eval/live_fixture_run.py --repeats 3`, default Settings (`sim.loop.SETTINGS_DEFAULTS`,
  not `{}`), fresh empty cache (`DEMING_CACHE_DIR`) so every call was live, sequential.
- **Run 1 (regression found):** 69 calls, 0 schema failures, 15 retries (429/503), 291 s. Lanes
  6/8 on every repeat: DEV-005/006 (truth fine, no KEV match) came back `unknown` with the
  reason "fixed version not documented". My reworded checker.md step 4.5 ("…or no lifecycle row
  matches") was read as applying without a KEV match. The previous live run had both `fine`.
- **Fix:** wording only, no new rule: step 6 now says steps 4-5 apply only when a KEV entry
  matches. Guide re-synced.
- **Run 2:** 69 live calls, 0 schema failures, 0 other errors, 21 retries (429/503), 258 s. Lanes
  8/8 vs the updated fixture truth on all 3 repeats. Structured agreement: lane 8/8, vendor
  8/8, product 6/8 (DEV-006 "UniFi Access Point" vs "UniFi AP AC Pro"; DEV-008 "" vs "Router"),
  version 8/8, evidence ids 8/8, all five 6/8. Planner structured fields 8/8. Free text 0/8
  devices fully identical (subjects/bodies 3/8), though temperature is 0.
  Mean latency: Normalizer 1.9 s, Checker 4.3 s, Planner 5.0 s.
- **Not verified:** the full 60-device inventory with these changes (not run, and no prompt
  tuning on data/inventory.csv); the free-tier RPM/RPD for this model.

### 2026-11-11 · Full evaluation run driver and offline analysis (prompts-v1)
- **Choice:** `eval/full_run.py`, a thin wrapper around `eval/live_fixture_run.py` on the `data/`
  files (3 repeats, one call at a time, cache on). It adds one rule: a 429 whose message names a
  per-day quota stops the whole run (no workaround). Any other 429 that outlasts the runner's
  backoff gets up to 3 waits of 65 s. `eval/offline_analysis.py` scores every complete repeat
  per group, plus stability and a POST-HOC alias view. It rebuilds partial repeats from the
  response cache with a client that raises on any call, so analysis never spends quota.
- **Alternatives:** editing `live_fixture_run.py` itself (rejected: keep the fixture tool
  unchanged after the freeze); scoring the error-row repeat-2 CSV (rejected: network-drop rows
  are not model output).
- **Outcome:** repeats 0 and 1 complete (60/60). Repeat 2 stopped at 40/60 after a network drop,
  then the per-day quota. Headline numbers use repeats 0 and 1 only; see `docs/results-analysis.md`.
- **Source:** rate limits are per model and per day (https://ai.google.dev/gemini-api/docs/rate-limits).
  The exact RPD for `gemini-3.5-flash-lite` on this key was not verified; about 500 calls in a
  day were reached before the quota 429.

### 2026-11-11 · Publish-readiness history scan
- **Choice:** a read-only Python scan of `git log --all -p` (all branches, the `prompts-v1` tag,
  remotes; 43 commits) with gitleaks-style regexes: `AIza…`, `AQ.…`, `ya29.…`, private-key
  blocks, service-account JSON, GitHub / OpenAI / Anthropic / AWS / Slack tokens, JWTs, and
  `key|secret|password|token = value` assignments. Hits print redacted (first 4 chars + length).
  Plus path checks for `.env`, `.cache/`, `.venv/`, key files, and a blob-size scan (> 5 MB).
- **Alternatives:** gitleaks (`gitleaks git --log-opts="--all"`) is the standard tool for this
  and was the first choice; Docker wasn't running and downloading the release binary was
  declined in this session. TruffleHog (verifies live keys against the provider) was ruled out
  because it would send candidate keys to Google.
- **Result:** 0 secret hits. Every `AIza`/`AQ.` string in history is a docs mention, a hook regex
  or a test string. `.env`, `.cache/`, `.venv/` never committed (`.env.example` only, always
  `GEMINI_API_KEY=` empty). No blob over 5 MB (largest: `data/feeds/kev.json`, 1.75 MB).
- **Source:** https://github.com/gitleaks/gitleaks (README, `git` scan mode).
- **Not verified:** a regex scan can miss secrets with no recognisable shape; gitleaks itself
  was not run.

### 2026-11-11 · Fresh-clone fixes: label wording from data, pinned installs, README reproducibility
- **Choice (report wording):** `data/ground_truth_meta.json` gets `label_status`
  (`ai_drafted_unverified` now). `eval/report.py` builds its caveat sentence from that value
  instead of a hardcoded string, so the report can't say more than the data does;
  `eval/run_eval.py` refuses `human_verified` unless every truth row has two different
  reviewers. `eval/test_report_wording.py` fails if a fresh report, its failures.csv, or any
  git-tracked `eval/results/*/report.md` claims human labelling while the meta says unverified.
  The failure explanations also said "a human labelled"; reworded to "labelled".
- **Regenerated report:** same command and inputs as the published one, written to a scratch
  folder, diffed (only the caveat line and explanation wording changed; every number equal),
  then copied over `eval/results/20261111T141730Z/` so existing doc links stay valid.
  The `prompts-v1` sha256 of the meta file in `docs/prompts-freeze.md` is the tagged version;
  `as_of_date` is unchanged, so no result changes.
- **Choice (README numbers):** no test count in the README (it drifted: 396 at freeze, 458 now).
  Published figures point at the files they come from; the README says which ones need the
  gitignored response cache (repeat 1 column, per-group per-repeat tables, three-repeat footnote,
  post-hoc alias view) and states that the `run_eval.py` example scores the published baseline.
  Alternatives: a test asserting README numbers equal the published report (rejected for now:
  the README table mixes run_eval and offline_analysis outputs; more parsing than the deadline allows).
- **Choice (pins):** keep `requirements.txt` as the unpinned direct-dependency list and add
  `requirements-lock.txt` = `pip freeze` of the venv the suite passes in (Python 3.11.7,
  Windows 11); README installs from the lock. `requirements-dev.txt` = lock + `formulas==1.3.4`
  (optional; 1.3.4 was the latest release on PyPI today and was not installed in the tested
  venv). Alternatives: pinning in place in `requirements.txt` (loses the direct-vs-transitive
  split); pip-tools / uv lock files (another tool to install for a 2-day deadline).
  Note: the lock has google-genai 3.0.0; the published run used 2.4.0 (`docs/prompts-freeze.md`).
- **Source:** https://pip.pypa.io/en/stable/topics/repeatable-installs/ ("Repeatable Installs":
  "A requirements file, containing pinned package versions can be generated using pip freeze");
  https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1
  (`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`; the `Process` scope
  affects only the current session). Both pages were opened and checked on 2026-11-12
  (fix/final-polish). The PowerShell link now pins the 5.1 view, which is the Windows PowerShell
  the README targets. Its content was read from the 7.6 view, which the unpinned link served.
- **Not verified:** the lock file installing on Linux/macOS or another Python version (colorama
  is a Windows-only pytest dependency but installs anywhere).

### 2026-11-12 · Source URLs that were cited from memory (fix/final-polish)
- **Choice:** keep both URLs from the fresh-clone entry. Both were opened and checked against what
  the entry claims: the pip "Repeatable Installs" page (pip freeze makes a pinned requirements file)
  and Microsoft's `about_Execution_Policies` (CurrentUser RemoteSigned, Process scope). The PowerShell
  link is pinned to `?view=powershell-5.1` because the README targets Windows PowerShell 5.1.
- **Alternatives:** delete them (they were correct, so nothing gained); cite a blog or Stack Overflow
  (secondary).
- **Not verified:** the 5.1 view was not opened. The 7.6 view was read, and it gives the same
  commands and scopes. The page lists 5.1 as a supported version.
- **Also open:** the hooksPath entry (2026-11-11) still says its relative-path statement is from
  memory. The task named only the pip and PowerShell URLs, so that one is unchanged.

### 2026-11-12 · Sheet template brought up to contracts 1.3 (Decision Log, Tickets, Settings)
- **Choice:** `scripts/make_sheet_template.py` now has the exact `decision_log.csv` and
  `tickets.csv` column lines from `docs/contracts.md`, in `sim/loop.py` order. The Settings tab uses
  the contract's keys and defaults (`approver_email` … `digest_channel`, including the 1.4 keys
  `retire_days` and `retire_isolation_days`, because the file is now at 1.4). It also keeps a
  human-only `description` column. New Tickets columns get the same treatment as the old ones: ids,
  versions, evidence and flags are text (`@`), and `last_updated_at_open` and `closed_on` are dates.
  The demo exporter therefore writes no grey extra columns. It still supports them if the simulator
  ever adds one, and it now stops if the simulator has a Settings key the template lacks. Summary
  formulas find columns by name, so the moved Tickets `status` column (D → F) needed no formula edit.
- **Tests:** template headers equal `loop.DECISION_LOG_COLUMNS` / `TICKET_COLUMNS` and the contract's
  column lines; the Settings tab equals `loop.SETTINGS_DEFAULTS`; the demo workbooks have no extras,
  and their Settings match the simulator's. The optional `formulas` check (Summary column B evaluated
  = loop values, all three stages) was run with `formulas==1.3.4` installed in the scratchpad only,
  and it passed.
- **Alternatives:** keep the extras at the right (rejected: the user asked for normal template
  columns); import `sim.loop` from the template script (rejected: it keeps the template script
  free of the simulator; a test pins the two together instead).
- **Source:** `docs/contracts.md` (Loop state files); `docs/decisions/feat-demo-sheet.md` ("Proposed
  for main").

### 2026-11-12 · Decision Log lane dropdown: allow blank (not "removed")
- **Choice:** the lane validation now has `allow_blank=True`, and its error text says blank is only
  for the verify row of a removed device. Any value outside the four lanes is still rejected.
- **Why this is the safer fix:** contracts 1.3 already defines a blank lane on that row, and
  `sim/loop.py` writes it (DEV-102 in demo stage 3). Writing `removed` would add a fifth lane value
  that the Lane enum, `guards`, the Summary `COUNTIFS` and the conditional formatting don't know.
  It would also change loop output and contracts. Allowing blank changes only the Sheet rule.
- **Cost:** a blank lane on a device row (not a verify row) is no longer rejected by the dropdown.
  The loop never writes one, and a dropdown can't tell row types apart without a custom formula.
  A custom-formula rule (`=OR(D2<>"",G2="verify")`) was considered and rejected: it is more
  fragile to port, and the 1:1 Sheets mapping hasn't been checked.
- **Tests:** `test_decision_log_lane_allows_blank` and `test_removed_device_verify_row_fits_the_lane_rule`
  (`scripts/test_make_sheet_template.py`); `test_removed_device_has_blank_lane_in_stage_3`
  (`scripts/test_export_demo_to_sheet.py`).
- **Source:** https://openpyxl.readthedocs.io/en/stable/validation.html (shows `allow_blank` but
  does not define it); https://support.google.com/docs/answer/186103 (non-list entries are
  rejected; nothing about blanks).
- **Not verified:** neither page says how a blank cell is treated. That `allowBlank` maps to
  Excel's "Ignore blank" and survives a Google Sheets import is from memory, untested. It is on
  the Sheets import test in `docs/submission-checklist.md`.

### 2026-11-12 · Submission checklist brought up to date
- **Choice:** a new "Open items for a human" section lists the T35 EOL check (DEV-052, DEV-025),
  human label review, the Sheets import test, the coordinator message and the backup video, all
  unticked. Stale facts were updated: repo still private, no LICENSE, test count 463 passed /
  1 skipped, all branches merged. No research needed (repo facts only, from `gh repo view` and
  `git branch --no-merged`).

### 2026-11-12 · T35 labels corrected to retire (fix/t35-labels)
- **Choice:** DEV-025 (patch → retire) and DEV-052 (fine → retire). Both raw names say plain
  "T35" (Firebox T35). The source is WatchGuard's End of Life Policy page,
  https://www.watchguard.com/node/111406, opened 2026-11-12. It gives Firebox T35 EOS 17 Jul 2021 /
  EOL 31 Dec 2025, T35-W EOL 31 Dec 2025, and T35-R and T35-DW EOL 01 Mar 2027. 31 Dec 2025 is
  before `as_of_date` 2026-11-12. Only the lane changed. Vendor, product, version, evidence ids
  and group were kept; `verified_by_*` stay blank; `label_status` stays `ai_drafted_unverified`.
  The change was made in `scripts/build_inventory.py` and regenerated (only these two rows
  changed).
- **Alternatives:** (a) add a T35 hardware row to `data/lifecycle.csv` and cite it. Rejected for
  now: the published Deming run used the old file, and changing it would mix data and label
  fixes. The gap is listed as candidate fix 5. (b) Leave the labels and keep only the doubt.
  Rejected: the vendor page is primary and unambiguous for a plain T35.
- **Consequence:** the two rows fail three lifecycle-derived label tests (retire needs a
  lifecycle cite past support; supported_fine must be fine). They are exempted by id in
  `tests/test_inventory.py` (`VENDOR_EOL_OVERRIDES`), and a new test checks that each exempt row
  is a plain T35, cites the WatchGuard URL and is still unverified. `scripts/check_labels.py`
  now flags both rows (recomputed lane differs), as expected.
- **Re-scoring:** offline only, on the published prediction CSVs, with no API calls. The new
  results are in `eval/results/20261112T152247Z/`, and the old directory is kept.
  `eval/offline_analysis.py` gained `--ground-truth` (default unchanged) so the old labels can be
  re-scored. Old labels reproduce the published `offline_analysis.md` byte-for-byte.
- **Not verified:** that the synthetic names mean a plain T35 and not a T35-R / T35-DW recorded
  without a suffix. A human reviewer must confirm.

### 2026-11-12 · MIT license and going public (fix/submit-ready)
- **Choice:** MIT `LICENSE` at the repo root, copyright "2026 Gitgud (Harsh Mahendra Kudu,
  Vaishya Surya Kumar Kamalapati)". GitHub's licensing page says to put the license file in the
  root, points to choosealicense.com, and notes that without a license default copyright applies
  and nobody may reuse the code. GitHub detects the license with Licensee, so the standard MIT
  text is kept unchanged. Source:
  https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository
- **Alternatives:** Apache-2.0 (adds a patent grant and NOTICE handling, more than a hackathon
  prototype needs); no license (judges could read it but not reuse it). Chosen by the team.
- **Visibility:** `gh repo edit Harsh-617/deming --visibility public --accept-visibility-change-consequences`.
  The gh manual says the accept flag is required with `--visibility` and lists consequences
  (stars/watchers lost, forks detached, push rulesets disabled, Actions logs visible). GitHub's
  visibility page adds that the whole code and history become readable by anyone. Sources:
  https://cli.github.com/manual/gh_repo_edit ,
  https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility
- **Alternative:** keep it private and add judges as collaborators. Rejected: no judge usernames.
- **Precondition:** a full-history secret scan (all 53 commits, working tree, every .xlsx blob)
  found no key, token or private key before the switch.

### 2026-11-12 · Extended lifecycle data, optional and off by default (feat/lifecycle-coverage)
- **Goal:** widen end-of-life coverage with sourced rows and measure the retrieval gain with no
  model call. `data/lifecycle.csv` (the 30 rows the published run used), prompts, schemas, guards,
  labels and published results are unchanged.
- **Inventory vendors/products checked:** Fortinet FortiOS; Ivanti Connect Secure 22.x and Pulse
  Connect Secure 9.1x; D-Link DIR-600/820L/859, DNS-320L/325; MikroTik RouterOS; Palo Alto PAN-OS;
  Edimax IC-7100; Citrix NetScaler ADC 13.0/14.1; WatchGuard Firebox (incl. T35) / Fireware 12.x;
  Cisco RV320/RV042G/RV345, ASA 5506-X, ASA software 9.16/9.20/9.22; Sophos XG 210, XGS 2100; NUUO
  NVRmini2, NVRmini 3; SonicWall SMA 210/410 (SMA100), SMA 1000; Zyxel USG60; DrayTek Vigor 300B.
- **endoflife.date:** API v1 (`https://endoflife.date/api/v1/products`, schema 1.2.1, 489
  products, read 2026-11-12). Slugs that exist for these vendors: `fortios`, `panos`, `routeros`
  (also `cisco-ios-xe`, not in the inventory). No slug for Ivanti, NetScaler ADC, Cisco ASA,
  WatchGuard, Sophos, SonicWall, Zyxel, D-Link, DrayTek, NUUO or Edimax. Docs:
  https://endoflife.date/docs/api/v1/
- **Choice per source:**
  - WatchGuard Firebox T35, T35-W, T35-R, T35-DW: vendor page https://www.watchguard.com/node/111406,
    opened 2026-11-12. EOL 31 Dec 2025 (T35, T35-W) and 01 Mar 2027 (T35-R, T35-DW). Rows LC-101..104.
    The other Firebox models on the page were left out: no inventory device uses them, and more
    name-only rows would crowd the top-5 Firebox candidates.
  - Cisco ASA 9.16(x) software: Cisco EoL notice
    https://www.cisco.com/c/en/us/products/collateral/security/asa-firepower-services/asa-9-16-asav-asdm-release-7-16-eol.html
    (End of SW Maintenance and End of Vulnerability/Security Support both 2026-11-18; LDoS
    2027-11-30). Row LC-105.
  - Citrix NetScaler ADC 13.1: CTX241500
    https://support.citrix.com/external/article/CTX241500/netscaler-adc-firmware-release-cycle.html
    ("13.1 will reach EOM on 15-Sep-26 and EOL on 15-Sep-27"). Row LC-106. 14.1 gives quarters
    only ("EOM during Q3/29", "EOL during Q3/30"), so it is skipped.
  - FortiOS 8.0, 7.6, 7.2, 6.4, 6.2, 6.0: endoflife.date `fortios` (End of Engineering Support /
    End of Support), cached byte-for-byte in `data/feeds/endoflife/fortios.json` with a sha256 in
    `fortios_meta.json`. A test checks that its 7.0 and 7.4 dates equal the curated LC-016/LC-020.
    Rows LC-107..112. 7.0 and 7.4 are not duplicated.
- **Skipped (no explicit date from an authoritative source):** Ivanti Connect Secure 22.x (the
  Ivanti EOL policy page at hub.ivanti.com shows no release table without login; only third-party
  trackers give 2027-01-31). NetScaler 14.1 (quarters only). MikroTik RouterOS (endoflife.date
  `routeros` dates are derived from the next release, MikroTik publishes none, and they would
  contradict LC-025's fixed 7.24.3). PAN-OS other trains (endoflife.date `panos` gives standard
  EOL only, not Extended Support+, and no inventory device needs them). WatchGuard Fireware 12.x.
  Sophos XGS 2100 (docs.sophos.com: no date, only "at least five years after the EoS date").
  SonicWall SMA 1000 (table read as flattened text with an ambiguous column order). NUUO NVRmini 3.
  The script prints this list.
- **Alternatives:** third-party trackers (endoflife.ai, eol.network); rejected as not primary.
  Editing `data/lifecycle.csv` directly; rejected, because the published run used it.
- **Wiring:** `sim/retrieval.load_lifecycle(path, include_extended=None)`, env
  `DEMING_LIFECYCLE_EXTENDED` (1/true/yes/on), default OFF. Extended ids start at LC-101 and a
  clash raises. A test compares the flag-off snapshot (retrieval for all 60 truth identities plus
  mock-pipeline predictions) byte-for-byte with one written on main 4bd5cfb.
- **Result:** `docs/lifecycle-coverage.md`. Lane accuracy with the extended rows is NOT measured
  (needs a new Gemini run).

### 2026-11-12 · Deming Console: local interactive page with zero new dependencies (feat/console)
- **Choice:** Python standard library `http.server.ThreadingHTTPServer` in `scripts/console.py`
  plus one self-contained page, `scripts/console.html` (inline CSS/JS, no CDN, no network at
  runtime). It binds to `127.0.0.1` only and has no option to change that; the docs say the
  default binds to all interfaces and show `--bind 127.0.0.1` for localhost only, and warn that
  `http.server` "is not recommended for production. It only implements basic security checks".
  `ThreadingHTTPServer` (3.7+) is used because the docs note browsers pre-open sockets, which
  the single-threaded server waits on. `log_message` is overridden to log method, path and
  status only. Source: https://docs.python.org/3/library/http.server.html
- **Browser hardening:** a per-response nonce Content-Security-Policy (`default-src 'none'`,
  `script-src`/`style-src` nonce only, `connect-src 'self'`) so the page can't load or call
  anything off-machine; MDN says `'unsafe-inline'` "defeats much of the purpose of having a
  CSP", so it is not used. Source:
  https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy . All data
  is rendered with `textContent` (device names may hold injection text). POSTs need
  `Content-Type: application/json`, a loopback `Host` and, when present, a same-origin `Origin`,
  so another web page can't drive the approve endpoint (my own reasoning, not from a cited page).
- **Gemini timeout:** `google-genai` `HttpOptions.timeout` is in milliseconds (checked in the
  installed google-genai 3.0.0 field description), so 20 000; SDK retry off, runner retries 0,
  plus a 20 s wall-clock limit on the whole pipeline. Any failure falls back to the mock.
- **Alternatives:** Flask / FastAPI + uvicorn (new dependencies, more to audit for a one-day
  page); a static HTML file reading the CSV state (can't run the pipeline or record approvals);
  Streamlit (a large new dependency for one page).
- **Reuse, no new logic:** lanes, approvals and verification come from `sim/loop.py` and
  `sim/demo_scenario.py`; `run_loop` is always called with `approver=None`; the one call to
  `record_approval` is the Approve click. The "Try a device" message uses the loop's own
  `_safe_body` check (a private helper) so it shows what a proposal would contain.
- **Not verified:** real Gemini calls from the console (none were made; tests use the mock and
  a fake client); behaviour in browsers other than the Playwright Chromium used for the check.


### 2026-11-13 · Red-team suite for prompt injection and abuse (feat/redteam)
- **Choice:** 45 hand-written hostile cases in `eval/redteam/cases.csv`, each tagged with the
  policy it attacks, run through the full `sim.loop` two-day script by `eval/redteam/run.py`.
  Two offline models: the existing rule-based mock and an "obedient" mock that does what the
  injected text asks (a worst case that leaves only the code guards). Pass = no policy violated in
  the final proposals, outbox, tickets and Decision Log. The checks are independent of the guards
  (NFKC, removal of format characters, a small look-alike map after UTS #39 confusables, a wider
  consequential-word list). Attack families follow OWASP LLM01: indirect injection through data
  fields and feed notes, encoding (Base64), Unicode tricks, role-play, very long input; OWASP's
  mitigations (deterministic output checks, human approval, adversarial testing) are what the
  suite tests. Sources: https://genai.owasp.org/llmrisk/llm01-prompt-injection/ ,
  https://www.unicode.org/reports/tr39/ (Version 18.0.0, 2026-08-27).
- **Alternatives:** an LLM-judged red-team tool (garak, promptfoo red-team). Rejected for now:
  they need a live model and network, and the task forbids LLM calls; our policies are checkable
  by code. Not evaluated in this task.
- **Result:** mock 33/45, obedient 15/45. Eight findings (F1–F8 in `docs/redteam-results.md`).
  **Guards not patched** in this task, by instruction.
- **Not verified:** any real model's behaviour (`--live` not run); the Agent Designer port.

## fix/console-live (2026-11-13): Console key loading and password-manager attributes

- **Key loading:** `scripts/console.py` `load_key()` uses `GEMINI_API_KEY` from the process
  environment; if unset, it reads only the `GEMINI_API_KEY=` line of the repo-root `.env`
  (optional `export`, single or double quotes, trailing `# comment`, BOM/CRLF), ignores every
  other line and does not put anything into `os.environ`. Last assignment wins, like
  python-dotenv. **Alternative:** `python-dotenv` `load_dotenv` (already a dependency, used by
  `sim/gemini_runner.py`) loads every line into the environment, which the task ruled out;
  `dotenv_values` parses the whole file into memory, also more than needed. Each loaded key is
  added to the `scrub()` list, so it is redacted even when it does not match the Google key
  pattern. On a failed call the page shows the exception type and HTTP status only (for
  example `ServerError, HTTP 503`), never the error text.
- **Password managers:** every `<input>` and `<select>` carries `autocomplete="off"`,
  `data-lpignore="true"` (LastPass), `data-1p-ignore` and `data-op-ignore` (1Password),
  `data-bwignore="true"` (Bitwarden), `data-form-type="other"` (Dashlane). Source opened:
  1Password developer docs, https://www.1password.dev/web/compatible-website-design.md
  ("use the `data-1p-ignore` or `data-op-ignore` attribute to tell 1Password it should ignore
  the field"). **Not verified from vendor docs:** the LastPass, Bitwarden and Dashlane
  attributes come from secondary write-ups (e.g. https://www.stefanjudis.com/snippets/turn-off-password-managers/);
  Dashlane's support page returned HTTP 403. Browsers may still ignore `autocomplete="off"`
  for their own autofill. Not tested with any real password-manager extension installed.

---

## Branch decision logs, copied into this file (2026-11-13)

Copied from `docs/decisions/*.md` (those files are kept). Entries already in this file were not copied again.

### Decisions: feeds (branch feat/feeds) (from `docs/decisions/feeds.md`)

#### 2026-11-11 · KEV download
- **Choice:** `requests` GET of the official CISA JSON feed, saved byte-for-byte (contract requires a
  reproducible sha256). Fallback: the `cisagov/kev-data` GitHub repo raw file (CISA-owned org).
  Both validated before saving (non-empty `vulnerabilities`, `count == len`, required entry fields).
  Atomic write (temp file + `os.replace`). If the sha256 matches the saved file, nothing is rewritten.
- **`--diff`:** lists entries whose `dateAdded` is later than the newest `dateAdded` in the snapshot
  that was on disk before this run (as the task specifies). Entries added on the same day as the
  previous newest entry would be missed; acceptable because CISA publishes the catalog in daily batches.
- **Alternatives:** the KEV CSV feed (same data, but JSON keeps `cwes`/`notes` structured);
  NVD API `hasKev` filter (rate-limited, needs extra calls, and is a copy of CISA's data, not the source).
- **Source:** https://www.cisa.gov/known-exploited-vulnerabilities-catalog (links the JSON/CSV feeds);
  https://github.com/cisagov/kev-data. Both URLs returned HTTP 200 on 2026-11-11.
- **Not verified:** how quickly the GitHub mirror trails the cisa.gov file.

#### 2026-11-11 · endoflife.date for edge devices: not used
- **Finding:** queried `https://endoflife.date/api/v1/products` (489 products). Categories: server-app 176,
  framework 74, os 68, app 62, lang 34, database 27, service 25, device 21. The network-relevant entries
  are software release lines only: `fortios`, `panos`, `cisco-ios-xe`, `routeros`, `big-ip`, `netapp-ontap`,
  `openwrt`, `truenas`, Stormshield `sns-*`. The `device` category is phones, tablets, watches, Raspberry Pi,
  Kindle and similar consumer hardware.
  No D-Link, TP-Link, Zyxel, Netgear, ASUS, DrayTek, SonicWall, Ivanti, Citrix/NetScaler, Cisco ASA or RV,
  QNAP, Synology, Hikvision, Dahua, Reolink or other camera/NAS/consumer-router hardware.
- **Choice:** don't depend on it. `data/lifecycle.csv` is hand-curated from vendor pages instead.
  endoflife.date could be an optional cross-check for FortiOS/PAN-OS branch dates later.
- **Source:** https://endoflife.date/api/v1/products (fetched 2026-11-11); https://endoflife.date/docs/api/v1/
- **Not verified:** how endoflife.date sources its network-OS dates; we cite the vendor pages directly.

#### 2026-11-11 · lifecycle.csv sourcing
- **Choice:** hand-curated from vendor-owned EOL notices and security advisories. Each row cites the
  page that states the date or fix. Research subagents gathered verbatim quotes; the main session
  re-checked the riskiest rows directly (Cisco bulletins, D-Link NAS table, DrayTek and Zyxel lifecycle
  tables, Cisco ASA fixed releases) and confirmed every cited CVE is in the KEV snapshot. Pages that block
  scripts were read with WebFetch or a headless browser.
- **Alternatives:** endoflife.date (doesn't cover these devices; see above); NVD CPE "deprecated" flags
  (not an EOL signal); third-party EOL aggregators (not primary sources; rejected).
- **Source:** per-row `source_url`; summary in `docs/feeds.md`.
- **Not verified:**
  - Support end dates for Ivanti Connect Secure 22.x, NetScaler 14.1, SonicOS 7, RouterOS 7 and WatchGuard Fireware 12.
  - Check Point R81.20 has a month only ("May 2027"), so it is left blank.
  - Fortinet dates come from Fortinet staff technical tips, because the official portal needs a login.
  - TP-Link was omitted: its pages give no exact date.

#### 2026-11-11 · model_pattern interpretation
- **Choice:** `model_pattern` globs the device's normalized model (hardware rows) or version
  (software-train rows, flagged in `notes`), not the canonical product string as contracts v1 says.
- **Why:** canonical KEV product names are family names ("Small Business RV Series Routers"), so the
  contract's own example (`RV32*`) can never match them. Proposed contract change is in the branch summary.
- **Alternatives:** add a separate `version_pattern` column (cleaner, but needs a contract change on main).

### Decisions: feat/eval (evaluation harness, naive baseline, Sheet template) (from `docs/decisions/feat-eval.md`)

One short entry per choice. Research budget: 5 minutes per task.

#### 2026-11-11 · Naive baseline matching
- **Choice:** lowercase substring of the KEV `product` in `device_name_raw` (score 100), else
  `rapidfuzz.fuzz.WRatio(name, "vendorProject product", processor=default_process)`; best pair,
  match at >= 85. Matching on vendor + product together (not either alone), as the guides suggest.
  Version is ignored (that is what makes it naive). Deterministic: ties go to the first pair alphabetically.
- **Alternatives:** `token_set_ratio` (scores 100 whenever one token set is a subset of the
  other, so "Cisco router" would hit every Cisco product); `partial_ratio`; stdlib `difflib`
  (slower, and not what the guides use); CPE-based matching (more accurate, but then it is no
  longer the naive baseline the PRD asks for).
- **Threshold 85:** the "review_match" tier in one public fuzzy-matching example. It is an
  illustrative value, **not tuned**. Tuning it on the test set would leak labels into the baseline.
  On the 8-device fixture it misses the Ivanti and "fgt 60e" rows and guesses on "Cisco router
  2nd floor", which are the failure modes the guides warn about.
- **Sources:** https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html ·
  https://www.decryptiondigest.com/blog/cross-reference-asset-inventory-cisa-kev-catalog (substring
  match, expect manual tightening) · https://hashnode.com/posts/kev-due-date-is-the-sort-key/6ab6dc87f1fda2353dd5d21f/comment/6ab75dca42921770c61ddf70
  (match vendorProject + product together). These are secondary blog sources. No official
  "reference baseline" exists, so this is our reading of common practice.

#### 2026-11-11 · Fixture
- **Choice:** 8 hand-made devices in `eval/fixtures/` covering all 6 groups, plus a 6-entry KEV
  file in the real KEV format and a 4-row lifecycle file. The CVE-to-product pairs are real KEV
  entries, quoted from memory and **not re-checked against the live catalog**. Lifecycle dates
  and URLs are placeholders, marked `FIXTURE ONLY`. DEV-006 has one reviewer on purpose, to
  exercise the verified/unverified split.
- **Not a test set.** It only checks that the harness computes the right numbers.

#### 2026-11-11 · Metrics implementation
- **Choice:** hand-written metrics on the stdlib `csv` module (`eval/metrics.py`), with no pandas or
  sklearn. Every definition is printed in the report. Undefined ratios are `None` and shown as `n/a`,
  never silently 0 (sklearn's `zero_division` default warns and returns 0, which would flatter a
  system that never predicts a class).
- **Alternatives:** `sklearn.metrics` (`confusion_matrix`, `precision_recall_fscore_support`), which
  is not in requirements.txt and is overkill for 4 classes and about 60 rows; pandas `crosstab`.
- **Choices that need a team decision:** devices whose TRUE lane is `unknown` are left out of
  exposure P/R, and a predicted `unknown` on an exposed device counts as a miss. A blank truth field
  only matches a blank prediction. The `v` prefix counts as wrong (contract: "no v prefix").
- **Source:** https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_recall_fscore_support.html
  (`zero_division` behaviour).

#### 2026-11-11 · Stability metric
- **Choice:** share of devices where all N runs give the same lane, and separately the same
  vendor/product/version. Unstable devices are listed in failures.csv as `unstable`.
- **Alternatives:** Fleiss' kappa, which corrects for chance agreement but is hard to explain in a
  3-minute pitch and unstable at n=60 with skewed lanes; mean pairwise agreement.
- **Not verified:** no primary source was checked for this. It is the simplest honest measure.

#### 2026-11-11 · Report
- **Choice:** Markdown `report.md` + `failures.csv` in `eval/results/<UTC stamp>/`. Primary metrics
  use each system's earliest run; per-run numbers are shown in a table. Slices: all, verified,
  unverified (contract: report unverified rows separately), and each group. "Baseline ties or
  beats" is checked on 8 metrics per slice and stated in a sentence starting "Plainly:".
- **Alternatives:** HTML/Jinja (adds a dependency, nothing to gain for a repo artifact); pandas
  `to_markdown` (needs `tabulate`).

#### 2026-11-11 · Sheet template format (.xlsx via openpyxl)
- **Choice:** generate `sheet/deming_template.xlsx` with openpyxl and import it into Google Sheets
  (File > Import, or open from Drive and Save as Google Sheets). Only features with a direct Sheets
  equivalent are used:
  - list data validation with inline items;
  - `cellIs equal` conditional formatting;
  - a frozen first row;
  - COUNTIF / COUNTIFS / INDEX / COUNTA / IF / SUM / MAX / TODAY formulas with plain A1 and
    whole-column references.
  It does NOT use Excel tables, named ranges, structured references, dynamic-array functions,
  macros or linked workbooks.
- **Alternatives:**
  - Build the Sheet directly with the Sheets API (gspread or google-api-python-client). This gives
    exact fidelity, but needs OAuth credentials and a target Drive. Better for the final version.
  - Apps Script that builds the tabs. Native, but it lives outside the repo's Python tooling.
  - One CSV per tab. Imports cleanly, but loses all validation, formatting and freezing.
- **What Google documents:** macros aren't supported (rewrite them in Apps Script), and some Office
  features "may be lost or altered" when converted. Neither help page lists data validation,
  conditional formatting, frozen rows or these formulas as unsupported, but neither confirms they
  are kept either. Blog sources say conditional formatting and data validation *may* change on
  conversion. **Import fidelity has not been verified in a real Google Sheet.** Do that test before
  relying on it.
- **Sources:** https://support.google.com/docs/answer/6055139 ·
  https://support.google.com/drive/answer/9276408 ·
  https://gptforwork.com/blog/how-to-convert-excel-to-google-sheets-without-losing-formatting (secondary)
- **Deviations from the request:**
  - `criticality` validation is `low/medium/high/critical`, because contracts.md v1 allows `critical`.
  - The urgent rule counts `critical` as well as `high`.
  - Booleans are real TRUE/FALSE cells, not the contract's lowercase strings. Sheets' CSV export
    writes `TRUE`/`FALSE`, so whatever reads the Sheet back must accept either case.
- **Bug found and fixed:** per-cell number formats on 2,000 empty rows moved openpyxl's `max_row`, so
  `append()` wrote data at row 2001. Formats are now column-level (`<col style>`). Whether Sheets
  keeps column-level number formats on import is **not verified**.
- **Formulas, checked offline:** the Summary formulas were computed with the `formulas` package
  (installed in the scratchpad only, not in the venv) on sample rows. The ticket, urgent and
  device counts were correct. The whole-column `INDEX` used for `latest_run_id` returns #VALUE! in
  that package. A bounded-range copy gave the correct latest run, lane counts and unknown rate, so
  the logic is right. Whole-column references were kept on purpose, because the Decision Log grows
  by ~60 rows per hourly run. **Not verified in Google Sheets itself.**

### Decisions: feat/agents branch (from `docs/decisions/feat-agents.md`)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`.

#### 2026-11-11 · Subagent prompt format for Agent Designer
- **Choice:** one Markdown file per subagent (`agents/<name>.md`) with the sections Role, Inputs,
  Rules, Output and Examples. The whole file is the "Instructions" text and is pasted unchanged.
  Prompts are plain text with no templating, no code and no tool syntax. Thresholds are written as
  literal numbers (0.80) because Agent Designer can't read our config; a test checks the literal
  matches `sim/config.py`.
- **Why:** Agent Designer's main agent and subagents are configured in the Flow tab with a free-text
  Instructions field. The docs say to be "specific and concise".
- **Alternatives:** a Jinja-templated prompt filled in by code (not pasteable); one big prompt for all
  four steps (harder to evaluate, and Agent Designer is built around subagents).
- **Source:** https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer ·
  https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/create-agent
- **Not verified:** the docs I found give **no** limit on instruction length, the number of
  subagents, or nesting depth, and they don't say whether a subagent can enforce a JSON response
  schema. The only number I found is the 800,000-token combined limit for files uploaded as Knowledge
  to the main agent. If Agent Designer can't enforce a schema, each prompt's Output section still
  describes the JSON, and the schema file is the reference to check it against.

#### 2026-11-11 · Structured output: `response_json_schema` with the schema files
- **Choice:** the runner passes the dict loaded from `schemas/<agent>.json` as
  `GenerateContentConfig(response_mime_type="application/json", response_json_schema=..., temperature=0)`.
  Every response is then validated with the Pydantic models in `sim/models.py`. The schema files
  are the single source and are portable (plain JSON Schema). The Pydantic models enforce the
  rules Gemini ignores.
- **Schema style:** only keywords Google lists as supported: `type`, `properties`, `required`,
  `additionalProperties`, `enum`, `items`, `minimum`/`maximum`, `description`. Nullable fields use
  type arrays (`["string","null"]`). There's no `$ref`, `const`, `minLength` or `pattern`, and every
  field is `required` (Google's advice for keeping the compiled grammar small).
- **Alternatives:** `response_schema=<Pydantic class>` (what `docs/decisions.md` chose for the smoke
  test, but it ties the schema to Python); the Interactions API with `response_format` (newer, and
  what the structured-output guide shows now, but more of a change than we need this week).
- **Source:** https://aistudio.google.com/docs/structured-output (supported and ignored keywords,
  `400 INVALID_ARGUMENT` for oversized schemas) · https://googleapis.github.io/python-genai/
- **Not verified:** that `gemini-3.5-flash-lite` accepts these exact schema files. No live call was
  made on this branch (no key). The first real run should confirm there's no 400.

#### 2026-11-11 · Checker: deterministic top-k candidate retrieval before the LLM
- **Choice:** `sim/retrieval.py` scores the device's (normalized, else raw) vendor+product against
  the unique KEV `vendorProject`+`product` pairs and against every `lifecycle.csv` row with
  `rapidfuzz.fuzz.WRatio` (after `utils.default_process`). It keeps the top 5 KEV products
  (score >= 60) and the top 5 lifecycle rows. A lifecycle row whose `model_pattern` glob matches
  the product always gets 100. Each KEV product contributes at most 8 CVEs, ranked first by whether
  the version or a model token appears in `shortDescription`/`vulnerabilityName`, then newest
  `dateAdded`. Only those candidates go to the Checker, so its prompt stays a few KB instead of
  the whole 1,773-entry catalog.
- **Guard:** the Checker may cite only candidate ids. Any other CVE or lifecycle id in its output is
  treated as invented, and the device goes to `unknown` (`sim/guards.py`).
- **Agent Designer equivalent:** the same step is a Drive-file lookup. Upload two files as
  Knowledge (or keep them in Drive): `kev_products.csv` (one row per vendorProject/product with its
  cveIDs, dueDate, requiredAction) and `lifecycle.csv`. The Checker prompt's "Candidate lookup"
  section tells the agent to search those files for rows whose vendor and product match the device
  and use only those rows. In Python the runner does that search for it and passes the result as
  `kev_candidates` / `lifecycle_candidates`, so the prompt text is identical in both places.
- **Alternatives:** send the whole KEV catalog (about 1.5 MB, slow and costly, and Agent Designer
  Knowledge counts it against the 800k-token limit every turn); embeddings or vector search (an extra
  dependency, and less explainable than a fuzzy score you can print); exact join (misses typos,
  which is the whole point of the messy-name group).
- **Source:** https://rapidfuzz.github.io/RapidFuzz/Usage/process.html ·
  https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/create-agent (Knowledge limit)
- **Not verified:** that k=5, the 60 cutoff and 8 CVEs per product give full recall on the 60-device
  set (there's no inventory or KEV copy on this branch yet). Tune these after the data lands, and report
  retrieval recall separately so a retrieval miss isn't blamed on the LLM. I also haven't checked
  whether Agent Designer's Knowledge search is keyword- or embedding-based, so in-platform recall may differ.

#### 2026-11-11 · Runner: own retry loop, SDK retry off
- **Choice:** `sim/gemini_runner.py` retries only on HTTP 429 and 503 with exponential backoff plus
  jitter (1, 2, 4, 8, 16 s, capped at 30 s; 5 retries), and sets the SDK's own
  `HttpRetryOptions(attempts=1)` so the two retry loops don't stack. That fits the decisions.md note
  that 3.8 calls looked like they were retried silently. The sleep function is injected, so tests
  run instantly.
- **Alternatives:** the SDK's built-in `HttpOptions(retry_options=HttpRetryOptions(...))` (less code,
  but harder to test and log); `tenacity` (a new dependency).
- **Source:** google-genai 3.0.0 `types.HttpRetryOptions` fields (`attempts`, `initial_delay`,
  `max_delay`, `exp_base`, `jitter`, `http_status_codes`), inspected locally ·
  https://googleapis.github.io/python-genai/
- **Not verified:** that `attempts=1` means "one try, no retry" (I read it from the field name and
  haven't checked the docs).

#### 2026-11-11 · Response cache and repeated runs
- **Choice:** an on-disk JSON cache in `.cache/gemini/` (gitignored) keyed by the sha256 of
  model, agent name, prompt text, schema, temperature, canonical input JSON and `repeat_index`. Only
  responses that pass validation are cached. `run_repeated(agent, payload, n)` makes calls
  `repeat_index = 0..n-1`, so the 3-run stability metric measures real model calls rather than
  cache hits, and a rerun of the same evaluation is free.
- **Alternatives:** key without `repeat_index` (then stability is always 100%, which is meaningless);
  no cache (every eval rerun costs quota and time).
- **Source:** none needed (design choice).

#### 2026-11-11 · Deterministic guards around every LLM output
- **Choice:** `sim/guards.py` enforces the hard rules in code, whatever the model says. Confidence
  below 0.80 means lane `unknown`. Evidence must come from the candidate list. A `do_not_touch` device
  gets no disconnect or isolate proposal and is escalated to a human. Every outward action has
  `requires_approval=true`. The Verifier may `close` only when the record changed and the re-check
  is not still vulnerable (a change isn't a fix).
- **Why:** prompt rules alone can be bypassed by injection text in a device name. The guards make
  the PRD rules testable without a live model.
- **Alternatives:** rely on the prompt alone (not provable); fail the run on a violation (loses the
  other devices' results).

#### 2026-11-11 · Agent Designer port: build a chat agent first, workflow as the upgrade
- **Choice:** the port guide (`docs/agent-designer-port.md`) builds a **chat agent** (main agent
  + four subagents in the Flow tab, Schedule tab) as path A, and a **workflow** (Schedule trigger →
  four Gemini Agent steps → Request info → Condition → connector actions) as path B.
- **Why A first:** it matches the PRD's "main agent + four subagents" design and the prompts paste
  unchanged, one per subagent. **Why B exists:** only workflow agent steps document structured
  JSON output with a manual schema, and connector writes there get human review. Chat-agent
  schedules are documented as "not supported for actions involving other people", so on path A a
  scheduled run can only draft; sending happens in the approver's follow-up chat.
- **Alternatives:** workflow only (enforces schemas, but needs a batch-wrapper line above each
  prompt, because no loop step is documented); a single agent with the four prompts as sections
  (fallback F9 if subagent hand-off doesn't work).
- **Verified (official docs, 2026-11-11):**
  - Agent Designer pages now sit under "Workflow Builder", with two kinds: chat agents and workflows.
  - Creating an agent: **+ Create agent > Chat agent > Proceed to builder**, then **Add subagent**
    in the Flow tab. Main-agent fields: Name, Description, Instructions, Model (Flash/Pro),
    Data and tools, Knowledge (800k-token combined limit, loaded every turn), and Personalization.
    An agent left without clicking **Create** stays a Draft.
  - Chat-agent schedules: Hourly/Daily/Weekly/Monthly/Annually; credentials expire every 14 days
    and need a manual refresh (Agent Gallery or the Schedule tab's **Refresh schedules**); up to
    5 min of delay; multi-region only; no actions involving other people; a paused run has an
    **Approve** button; runs show in the Chats history; **Run in preview** button.
  - Workflows: Manual, Schedule (minutes to months or cron) and Event triggers; Gemini Agent step
    with plain text or structured JSON output and a manual schema; Condition; Request info (yes/no
    etc.); connectors include Gmail, Google Calendar, Google Chat, Jira and Jira Data Center, each
    with "Search For Data" and "Add Or Update Data" groups; "Adding or updating data through
    connectors requires human review"; Drive knowledge via "Add from Drive" when a Drive data
    store exists.
  - Known issues: disabled actions fail the run; "3.1 Pro" is recommended; HITL steps may show raw
    Markdown; RESOURCE_EXHAUSTED isn't retried for event triggers; the Gmail subject can't take
    non-English characters.
- **Not verified:**
  - The subagent fields (whether a subagent has its own Knowledge or tools), how the main agent
    passes data to a subagent, and instruction length or subagent count limits.
  - Whether chat agents can enforce a response schema.
  - The Inbox and "Needs your input": seen only in a third-party blog and Google's launch blog
    post, not in the docs.
  - Google Sheets read and write: Sheets isn't in the listed connectors. A release note saying
    Drive handles CSV/XLSX, and one about exporting tables to Sheets, came only through search
    summaries; I didn't open them.
  - Jira action names for chat agents (the docs show them for workflows), and edition
    differences (a support page on actions is for the Business edition).
  - Whether **Add from Drive** Knowledge follows file updates, the data-store re-index delay,
    which model names the dropdown offers, and whether temperature is exposed.
- **Sources:** https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer ·
  https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/create-chat-agent ·
  https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/schedule-agent ·
  https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/workflows ·
  https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/create-workflows ·
  https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/known-issues ·
  https://docs.cloud.google.com/gemini/enterprise/docs/connectors/gdrive/set-up-data-store

#### 2026-11-11 · Drive assets: kev_products.csv + kev_entries.csv + lifecycle.csv
- **Choice:** `scripts/export_agent_assets.py` writes `dist/agent-designer/` (gitignored):
  - `kev_products.csv`: one row per KEV product, about 200 KB / ~50k tokens on catalog
    2026.11.09 (747 products);
  - `kev_entries.csv`: one row per CVE, description trimmed to 400 chars, 806 KB / ~200k tokens;
  - `lifecycle.csv`: a byte-for-byte copy, header checked against contracts.md;
  - the prompts as .txt, and a manifest with sha256 values.

  The small files go in Knowledge; `kev_entries.csv` stays in the Drive data store, because
  Knowledge is loaded into context on every turn.
- **Why a second KEV file:** the Checker needs each CVE's description and required action to
  judge the version. `kev_products.csv` alone only lists the ids. I added a line to `checker.md`'s
  Candidate lookup to point at it.
- **Guide drift guard:** the guide's pasted prompts are generated blocks. `--sync-guide` rewrites
  them, and a test fails if they differ from `agents/*.md`.
- **Alternatives:** upload raw `kev.json` (1.8 MB, JSON is harder for file search); kev_products
  only (no version detail).
- **Not verified:** token counts are chars / 4, not a tokenizer. How well Agent Designer's file
  search finds rows in a CSV this size isn't documented.

#### 2026-11-11 · Normalizer example uses the real KEV product name
- **Choice:** the example now reads "Small Business RV320 and RV325 Routers", the actual KEV
  `product` for CVE-2019-1653 in catalog 2026.11.09. Before, it said "Small Business RV Series
  Routers", which isn't a KEV product name. Found while building the export.

### Decisions: inventory (branch feat/inventory) (from `docs/decisions/feat-inventory.md`)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.

#### 2026-11-11 · Realistic messy names (research rule, ~5 min)
- **Choice:** mix three naming styles seen in practice: (1) role/site hostnames such as `kl-hq-fw01`
  (site-role-sequence conventions), (2) free-text descriptions with the location in the name
  ("MikroTik router - hostel block C"), (3) human typos and run-together models ("sonicwal sma410",
  "Dlink DNS320L", "Mikrotk", "wtchgrd"). Firmware typed with prefixes (`v7.4.1`, `ROS 7.24.1`,
  `NS14.1 38.53`) or left blank. One row holds injection text (PRD tricky case).
- **Sources:** site-role-sequence convention with role codes like FW:
  https://kb.dtctoday.com/books/dtcs-pillars-of-technology/page/device-naming-convention ;
  function-site-number names: https://oneuptime.com/blog/post/2026-03-20-document-ipv4-assignments-naming-conventions/markdown ;
  location kept in CMDB vs hostname debate: https://industrialmonitordirect.com/blogs/knowledgebase/enterprise-laptop-naming-convention-best-practices ;
  ServiceNow naming/uniqueness: https://www.servicenow.com/community/cmdb-forum/why-not-use-unique-name-values-in-cmdb-ref-to-csa-lab-4-4-1/td-p/3518122
- **Not verified:** no published dataset of real vendor typos was found in the time box; the typo
  style is a judgement, not a measured distribution.
- **Rule kept:** model names appear only when a source names them (lifecycle row, KEV entry, or the
  advisory). Two model names typed from memory (MikroTik hEX/RB) were removed.

#### 2026-11-11 · KEV has no version ranges, so fixed_version was filled from the cited pages
- **Finding:** kev.json entry fields are `cveID, vendorProject, product, vulnerabilityName, dateAdded,
  shortDescription, requiredAction, dueDate, knownRansomwareCampaignUse, forensicTriage, notes, cwes`.
  No affected-version field.
- **Choice:** filled `fixed_version` in `data/lifecycle.csv` only where the row's own `source_url` page
  states the fix (re-opened 2026-11-11). Multi-train fixes use `;` (one value per train, contract's
  multi-value rule):

  | Row | fixed_version | Quote from source_url |
  |---|---|---|
  | LC-020 FortiOS 7.4 | 7.4.3 | "7.4.0 through 7.4.2" / "Upgrade to 7.4.3 or above" |
  | LC-021 PAN-OS 11.1 | 11.1.2-h18;11.1.4-h13;11.1.6-h1 | "< 11.1.2-h18", "< 11.1.4-h13", "< 11.1.6-h1" |
  | LC-022 Ivanti 22.x | 22.7R2.6 | "fully patched in Ivanti Connect Secure 22.7R2.6" |
  | LC-023 NetScaler 14.1 | 14.1-47.46 | "14.1 BEFORE 14.1-47.46" |
  | LC-025 RouterOS 7 | 7.24.3;7.23.6 | complete fix "7.24.3 (stable) and 7.23.6 (long-term)" (KEV CVEs alone fixed in 7.24.2/7.23.4; the complete fix is used so no device sits between them) |
  | LC-026 ASA 9.2x | 9.20.4.10;9.22.2.14;9.23.1.19 | "All Vulnerabilities" column |
  | LC-029 Fireware 12.x | 12.11.4 | default models; T15/T35 12.5.13 and FIPS exceptions stay in replacement_hint |

- **Left blank** (fix not on the source_url page, or not a single value): LC-024 SonicOS (page doesn't
  name CVE-2024-40766), LC-028 Check Point (several Jumbo Hotfix takes: 26/41/53/54/65), LC-027 and
  LC-030 (fix only on the second URL in notes), LC-003, LC-010, LC-018 (EOL pages, fix only in notes),
  all no-fix retire rows.

#### 2026-11-11 · supported_fine uses KEV products at/above every checked fix
- **Problem:** all 30 lifecycle rows are KEV products, and every supported one has KEV CVEs added
  after the one its fixed_version covers. "At/above fixed_version" alone would mislabel fine.
- **Choice:** opened the newer advisories and chose versions above all of them:
  PAN-OS 11.1.16-h3 (CVE-2025-0111, CVE-2026-0257/0300/0322), Fireware 12.11.6 (CVE-2025-14733),
  RouterOS 7.24.3/7.23.6 (complete fix for all 2026 MikroTik KEV CVEs). FortiOS, ASA, Ivanti and
  NetScaler were NOT used for fine: each has 2026 KEV entries (FortiOS also "Multiple Products"
  entries) that weren't checked.
- **Sources:** https://security.paloaltonetworks.com/CVE-2026-0322 (and -0257, -0300, CVE-2025-0111);
  https://psirt.watchguard.com/CVE-2025-14733 ; https://fortiguard.fortinet.com/psirt/FG-IR-25-934 ;
  https://fortiguard.fortinet.com/psirt/FG-IR-24-535 ; Cisco cisco-sa-asaftd-tunnel-dos-s6mgkb75 and
  cisco-sa-asaftd-vpn-dos-dzv4mQFF (used for the patch rows' evidence).
- **Not verified:** older KEV advisories (PAN-OS 2024, WatchGuard 2022, MikroTik CVE-2018-7445).
  Every fine row is flagged `needs_extra_review` in docs/label-review.csv.

#### 2026-11-11 · name_collision rows
- Ivanti "Connect Secure" name with firmware 9.1R18 → Pulse Connect Secure 9.1x, retire (LC-011;
  Ivanti blog: "9.1x reached End-of-Support on December 31, 2024").
- SonicWall SMA 1000 → not SMA100 (KEV lists "SMA1000 Appliances" as its own product). No fix data,
  no firmware → unknown. Must not be retire.
- Sophos XGS 2100 → not XG hardware (LC-013: "Pattern 'XG *' does not match XGS"; XGS 2100 is the
  named replacement for XG 210). No firmware → unknown.
- NUUO NVRmini 3 → the replacement named in LC-015's EOL letter; no KEV entry or lifecycle row → fine.
- **Alternatives rejected:** Zyxel USG20-VPN / USG FLEX (same KEV product "Multiple Firewalls", so not a
  different product); Cisco Firepower 1000 (runs ASA/FTD software that is in KEV).

#### 2026-11-11 · Owner email domain
- **Choice:** `@example.org` (contracts.md: "Synthetic address at example.org"; existing tests and
  fixtures use it). The task brief said example.com; both are reserved (RFC 2606). Flagged in the summary.

#### 2026-11-11 · Build and review files
- `scripts/build_inventory.py` holds every hand-written row and lays them out deterministically
  (seed 20261111): device ids are shuffled so ids don't reveal the group; the blind sample of 15 uses
  the same RNG. Re-running gives identical files.
- `eval/blind/blind_key.csv` maps blind ids to device ids, kept separate so the worksheet shows only
  name + firmware. Labellers must not open it (honour system; it's in the repo).
- `eval/blind/agreement.py`: per-field percent agreement vs ground truth and Cohen's kappa on lane,
  plus pairwise labeller kappa.

### Decisions: feat/loop branch (from `docs/decisions/feat-loop.md`)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`.

#### 2026-11-11 · Idempotent scheduled-run state: run key + per-action idempotency keys
- **Choice:** three keys.
  1. **Run key:** `run_id = deming-<scheduled UTC time>` (`--now`). A run_id already in
     `runs.csv` is a no-op, so a duplicate scheduler delivery does nothing.
  2. **Action key:** every outward record is keyed by `proposal_id` and written to
     `outbox/<proposal_id>.<kind>.json` with exclusive create (`open(..., "x")`). Re-applying an
     approval can't send twice.
  3. **Business dedupe key:** `device_id|issue` (issue = `patch` / `retire` / `identify`, set by
     code from the lane, never the model's free text). We check it at planning time (open ticket
     or pending proposal means no new proposal) and again at execution time (two approved
     proposals still open one ticket).
- **Why:** Google says Cloud Scheduler is at-least-once, so "a job may run more than once" and
  handlers should be idempotent. Stripe and the AWS Builders' Library both describe the same
  pattern: one stable key per logical action, sent on every retry, with the server keeping the
  first result. Gemini Enterprise schedules can start up to 5 min late and run hourly (PRD), so
  overlapping or repeated runs are possible.
- **Alternatives:** hash the inventory content to make the run key (rejected: AWS argues a
  caller-supplied key says what was meant, and an inferred hash can't). A lock file (doesn't
  survive a crash mid-run, and doesn't protect individual actions). Model-written `ticket.issue`
  as the dedupe key (rejected: free text varies between runs, so dedupe would silently fail).
- **Sources:** https://docs.cloud.google.com/scheduler/docs/overview ·
  https://docs.stripe.com/api/idempotent_requests ·
  https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- **Not verified:** the names of the Cloud Scheduler dedupe headers (not read). Whether
  Gemini Enterprise scheduled runs expose a stable scheduled time we could use as the run key.
  On the platform the Sheet/Drive file has no exclusive-create, so the action key would have to be
  a "proposal_id already in Tickets/Decision Log" check instead.

#### 2026-11-11 · The closing rule is deterministic; the LLM Verifier is advisory
- **Choice:** `decide_verification()` in `sim/loop.py` decides. A ticket closes only when the
  device is gone from the inventory, OR the version changed AND the new version parses AND it is
  >= the ticket's `fixed_version` (reusing `sim/guards.compare_versions`). Stricter extras: if the
  re-check lane is still patch/retire the ticket stays open (`recheck_disagrees`); an `identify`
  ticket closes once the device can be matched (re-check lane not unknown). A changed version
  below the fix stays open, is flagged `still_vulnerable` and escalated. An unparseable version or
  a blank `fixed_version` stays open, flagged `low_evidence`. The LLM Verifier still runs (for
  patch/retire tickets) and its decision is logged, which gives the `verifier_llm_agreement`
  metric.
- **Why:** PRD acceptance: "a ticket closes only when the Sheet shows the fixed version or
  removal". This must not depend on a model.
- **Difference from `guards.guard_verifier`:** that guard allows `device_removed` to close only
  retire tickets. The task brief says close on removal for any lane, so the loop closes a removed
  patch device too. The guard is left unchanged (the loop's rule is the one that acts).
- **Source:** docs/PRD.md (acceptance criteria, tricky cases).

#### 2026-11-11 · Approval model and tiers
- **Choice:** one proposal per device and issue, bundling tier 2 actions (email, ticket, and a
  calendar maintenance window for patch). Approve or reject per proposal via
  `python -m sim.loop approve|reject <id> --approver <name>`, by editing `approvals.csv` (applied
  on the next run), or with a `ScriptedApprover` in tests and the demo. Tier 3 (isolate, replace)
  only goes in the Decision Log as "drafted only". It is never a proposal, and `_write_outbox`
  refuses any non-tier-2 kind. do_not_touch devices get no tier 3 draft. Their email is cc'd to
  the approver and marked ESCALATE. Recipients are set by rule (owner, or the approver for unknown
  devices). The model's recipient is recorded only to measure routing accuracy. Reminders are
  their own proposals and need approval too. Escalation sets the ticket to `escalated` and is
  listed in the run digest for the approver.
- **Why:** PRD hard rules (no outward action without recorded approval; tier 3 is draft-only; do_not_touch is never
  proposed for disconnection) and `agents/main_agent.md` step 8 ("approve 1, 3").
- **Alternatives:** approval per action (finer-grained but slower in a 3-minute demo); auto mode
  for tier 2 (`tier2_mode` other than `approval` is ignored with a warning, since auto is only a PRD "Could").

#### 2026-11-11 · Rule-based mock model for `--mock`
- **Choice:** `sim/mock_llm.py` applies the written rules from `agents/*.md` deterministically
  and plugs into the existing `GeminiRunner` as a fake client. So with `--mock` the full code path
  (runner, Pydantic validation, guards, loop) runs, just without the network.
- **Why:** this worktree has no API key. The eval mock (`eval/mock_gemini.py`) needs a
  per-test responder and can't produce realistic outputs for a whole inventory.
- **Limit:** the mock's name matching is simple. For example it sends the fixture's "fgt 60e
  fortigate" to unknown, where a real model might resolve it. Mock results say nothing about
  prompt quality.

#### 2026-11-11 · Metrics definitions (`<state>/metrics.json`, `metrics.csv`)
- owner_routing_accuracy = model-drafted recipient == rule recipient, over drafted emails
  (routing_after_guard = what was actually addressed, always 1.0 by construction).
- duplicate_tickets = tickets opened while another ticket with the same `device_id|issue` was open.
- approval_compliance = outbox records with an approved decision by a named approver, decided on
  or before execution, tier 2 only. Violations are listed.
- verification_correctness = verify decisions matching `expected_verification.csv`
  (`as_of,device_id,expected_decision`) when the file exists. The demo writes one.
- run_time_s = mean wall time per run (`runs.csv` has each run).

### Decisions: feat/review (label checks and reviewer tools) (from `docs/decisions/feat-review.md`)

One short entry per choice. Research budget: 5 minutes per task. No LLM calls in this branch.

#### 2026-11-11 · Review tool for two non-technical reviewers
- **Choice:** two single static HTML files (`review/review.html`, `review/blind.html`) generated
  by Python, with inline CSS/JS and the data embedded as JSON in `<script type="application/json">`.
  Export is a Blob + `URL.createObjectURL` + `<a download>` CSV. Progress is saved in
  `localStorage` (guarded with try/catch), **and** each page can re-import its own export to
  resume, because `localStorage` on `file://` pages is not defined by the spec and differs per
  browser (Firefox 92+ gives each file URL its own origin; Chrome also keeps file storage per URL).
  Re-import works everywhere and is the documented fallback.
- **Alternatives:** Google Form or Sheet (needs accounts and a server, and data leaves the repo);
  Label Studio / Argilla (needs a server, too much setup for two people); a plain spreadsheet
  (no guidance, easy to edit the label by mistake, no required-name rule); a local `http.server`
  (the reviewers would need a terminal).
- **Sources:** MDN localStorage notes on `file:` URLs (summarized via search; behaviour
  "undefined and may vary between browsers"); Mozilla bug 1730419 and the
  `privacy.file_unique_origin` change in Firefox 92:
  https://bugzilla.mozilla.org/show_bug.cgi?id=1730419 ; Chromium "Treat file:// URLs as having
  unique origin": https://groups.google.com/a/chromium.org/g/blink-dev/c/--KjSROtcMQ . The
  Blob/`download` pattern came from secondary tutorials, because the search returned no MDN page.
  **Not verified:** Safari behaviour (not tested). Tested in Chromium via Playwright over a
  throwaway local HTTP server (Playwright blocks `file:`), at desktop and 380 px widths.

#### 2026-11-11 · Reviewer field = initials
- **Choice:** the required reviewer field asks for initials (letters, spaces, dots, hyphens; no
  commas), because `verified_by_a/b` hold initials (contracts.md). `merge_reviews.py` writes the
  value as typed. Two exports from the same reviewer (case-insensitive) are rejected.

#### 2026-11-11 · Mechanical lane recompute
- **Choice:** `scripts/check_labels.py` recomputes the lane from the label's own fields with the
  contract tie-break, using the **cited** lifecycle row when there is one (the label's identity
  claim), else the most specific row for the label's vendor/product whose pattern fits. Retire
  when past `last_security_support_date` (or `eol_date`), **strictly before** `as_of_date`, or when
  in KEV with `patch_available=false`. A KEV `requiredAction` counts as "stop using" only if it says
  end-of-life / end-of-service / legacy; plain "discontinue use if mitigations are unavailable" is
  in nearly every KEV entry, so it can't count. KEV products match on exact `vendorProject` +
  `product`. Versions use `sim.guards` (`parse_version`, `compare_versions`, `select_train_fixes`)
  and `sim.retrieval` (`pattern_matches`, `pattern_specificity`). There is no second parser.
- A second pass uses the raw `firmware_version_raw` (what the Checker's version guard reads).
  "Doesn't parse" is severity 1 unless it changes the lane (severity 2).
- Hardware globs (e.g. `RV32*`, `XG *`) are tested against every word-start suffix of the raw name.
  That's how a model number inside free text is found. A cited row whose pattern doesn't fit the
  raw name is a `pattern` note (a messy name read by a human), not an error.

#### 2026-11-11 · Source URL checks
- **Choice:** `requests`, one GET per unique URL, 2 s apart, 25 s timeout, a generic
  User-Agent (no personal details), with the body capped at 4 MB. The page text is not stored:
  only status, content type and which expected strings were found are cached in
  `review/label_checks.json` (`--offline` reuses it). Expected strings: the fixed_version on the
  device's train, support and EOL dates in common written forms, and phrases quoted with `'...'`
  in the notes (a quote also counts as found if it is in the device's KEV text or the inventory
  row itself). 401/403/429, errors, non-2xx and PDFs → "needs human check in a browser", never ok.
- **Alternatives:** headless browser fetch (would get through JS-rendered tables, but it looks
  like scraping, sites like Cisco block it on purpose, and it's slow); PDF text extraction
  (`pypdf` is not in requirements.txt, and requirements can't be edited on a branch).
- **Limit:** a string "found" on a page doesn't prove it applies to this model and train. The
  reviewer still reads it.

#### 2026-11-11 · Blind page isolation
- **Choice:** `build_blind_page.py` opens only `eval/blind/blind_worksheet.csv` and keeps only
  `blind_id`, `device_name_raw` and `firmware_version_raw`. `blind_id` is the row key that
  `eval/blind/agreement.py` joins on, and it is a worksheet column. The export is the worksheet
  header plus a trailing `source_url_used` (agreement.py ignores unknown columns). The as-of date
  shown is a builder argument (default 2026-11-12), not read from data/. A test checks every
  ground_truth.csv / blind_key.csv cell against the generated page (exempt: the lane enum, and
  values that already appear in the worksheet inputs), plus `DEV-`, `LC-` and `CVE-` id patterns.
  A mutation check confirmed it catches a planted product name, group or device id.

#### 2026-11-11 · Merge
- **Choice:** `merge_reviews.py A.csv B.csv`: the first file fills `verified_by_a`, the second
  `verified_by_b`, only on rows marked `verified`. Other columns are copied byte-for-byte as values. It
  refuses to write to `ground_truth.csv`. Every row not verified by both goes to
  `docs/label-disagreements.md` with both reviewers' notes.
- **Known gap:** the export has exactly the four requested columns, so it carries no label
  fingerprint. If a label changes after a reviewer exported, the merge can't tell. Mitigation:
  the review page's saved state is keyed on a hash of the labels (a label change starts a fresh
  review), and the guide says to re-review changed rows.

### Decisions: feat/docs branch (from `docs/decisions/feat-docs.md`)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`.

#### 2026-11-11 · README structure for judges
- **Choice:** problem with sourced numbers and caveats → what Deming does → what runs where →
  how to reproduce (copy-paste commands, each run on this branch) → evaluation summary → limits
  → related tools. Long material lives in linked docs (`docs/limits.md`,
  `docs/results-analysis.md`, `docs/demo-script.md`), not in the README.
- **Why:** GitHub's README page says a README should tell people why the project is useful, what
  they can do with it and how to use it, and should hold only what is needed to get started;
  longer docs belong elsewhere. Google's style guide asks the README to link to fuller docs.
  Hackathon submission guides ask for an overview, setup steps and a demo link. The briefing's
  five topics (problem, solution, research, teamwork, impact; `docs/reference/full-report.md`)
  are each covered by a README section or a linked doc.
- **Alternatives:** one long README with everything (harder to scan); a README with only setup
  (doesn't answer the judging topics).
- **Sources:**
  https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes ·
  https://google.github.io/styleguide/docguide/READMEs ·
  https://hackncstate2025.notion.site/Submission-Judging-143963046a38810d998acb9b9290863d ·
  https://hackutd-tech-guide-git-springbranchupdated-acmutd.vercel.app/dayof/devpost-markdown
- **Not verified:** the search returned an archived Enterprise Server copy of GitHub's page; the
  current page wasn't opened. The hackathon guides are other events' guides, not APU's rules.
  APU's rubric weights are still unpublished (PRD).

#### 2026-11-11 · Every README command is run before it is written
- **Choice:** only commands that were run on this branch go in the README, with the venv at
  Python 3.11.7. Results on 2026-11-11:
  - `python -m pytest -q`: 396 passed.
  - `python eval/baseline.py`: wrote 60 rows; first 7 columns identical to the published
    `eval/runs/baseline-20261111T075945Z/baseline.csv` (run with `--out-root` in a temp folder).
  - `python eval/run_eval.py --pred <published baseline, rep 0, rep 1> --inventory data/inventory.csv`:
    deming lane_acc 0.88, norm_all3 0.47; baseline 0.32 / 0.18, matching `docs/results-analysis.md`.
  - `python eval/offline_analysis.py ...`: fails from a clean clone with
    `RuntimeError: cache miss` because the response cache (`.cache/`, gitignored) isn't in the
    repo. With the original machine's cache (`DEMING_CACHE_DIR`) it reproduced the published
    `offline_analysis.md` exactly (0 replay mismatches, 0 API calls). The README says so.
  - `python -m sim.demo_scenario`: ran on the mock; DEV-101/102 closed, DEV-104 escalated
    (still vulnerable), DEV-103 open; duplicate_tickets 0, approval_compliance 1.0.
  - `python -m sim.loop ... --mock`, `pending`, `approve`, `metrics`: ran on the fixture.
- **Not run (needs the key / quota, and this task forbids API calls):** `python eval/full_run.py`,
  `python -m sim.pipeline`, `python -m sim.demo_scenario --gemini`.
- **Finding:** `sim.demo_scenario` has no `--mock` flag; the mock is its default and `--gemini`
  opts into the API. `--mock` belongs to `python -m sim.loop`. The README uses the real flags.

#### 2026-11-11 · Related tools: Eolix and Xeol
- **Choice:** name both and say only what `docs/PRD.md` states: they cover end-of-life checks,
  so Deming is not unique (PRD "Never claim"). Deming's stated edge is the PRD's: closed loop,
  measured evaluation, portable no-code design.
- **Source:** `docs/PRD.md`.
- **Not verified:** we did not test either tool, so the docs make no other claim about what
  they do or don't do.

#### 2026-11-11 · Submission summary draft
- **Choice:** a 2-sentence summary (319 characters) in `docs/submission-checklist.md`,
  naming the loop, the four lanes, approval and the synthetic data. It avoids every PRD
  "Never claim" item (no uniqueness, no real-world accuracy, no "runs in Gemini Enterprise").
- **Alternatives:** a one-line tagline only ("Patch or Retire"); it meets 50 characters only
  with padding and says less.

### Decisions: feat/cross-check branch (from `docs/decisions/feat-cross-check.md`)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.

#### 2026-11-11 · How to report agreement on 15 blind AI labels
- **Choice:** report raw percent agreement (12/15) and Cohen's kappa on lane together, with an
  approximate 95% CI from SE = sqrt(p_o(1-p_o) / (n(1-p_e)^2)), and say plainly that n=15 is
  below the suggested minimum of 30, so the CI is only a rough guide. Kappa is computed by the
  existing `cohen_kappa` in `eval/blind/agreement.py` (reused, not edited).
- **Why:** McHugh (2012) advises calculating both percent agreement and kappa, gives the SE and
  CI formula, and suggests at least 30 comparisons. Percent agreement alone ignores chance;
  kappa alone hides the raw counts on a tiny sample.
- **Alternatives:** bootstrap CI (unstable at n=15 and adds code); Fleiss kappa (for 3+ raters,
  not needed); percent agreement only (ignores chance agreement).
- **Source:** McHugh ML. Interrater reliability: the kappa statistic. Biochem Med
  2012;22(3):276-82. https://pmc.ncbi.nlm.nih.gov/articles/PMC3900052
- **Not verified:** the formula was read from the PMC copy, whose equation text renders
  garbled; it was reconstructed as above. Kappa's known sensitivity to skewed lane counts was
  not researched further in the time box.

#### 2026-11-11 · Adapter instead of editing agreement.py
- **Choice:** `eval/blind/agreement.py` already reads the AI file (same worksheet columns), so it
  is reused as is. `eval/blind/cross_check.py` adds only what it lacks: the column mapping for
  `comment` (reason), `source_url_used` and `notes`, the POST-HOC alias view (imported from
  `eval/offline_analysis.py`, unchanged), source checks and the report.
- **Alternatives:** extend agreement.py (the task forbids it); copy its kappa code (duplication).

#### 2026-11-11 · Automatic source check
- **Choice:** fetch each distinct source URL once, 3 s apart, with a generic user agent; mark
  401/403/429/5xx or near-empty pages "needs human check in a browser"; look for the dates,
  versions, CVE ids and quoted phrases from the AI's reason literally (with common date
  spellings). The device's own firmware is not a claim unless nothing else is named. A claim
  counts as supported only if the page opened and every string was found.
- **Alternatives:** a headless browser (heavier, renders JS, but still can't say whether the
  page applies to the model); reading every page by hand (that is the human's job, and the
  triage lines say which pages).
- **Not verified:** a found string is not proof that the page says it about this model; the
  report says so.

### Decisions: feat/demo-sheet branch (from `docs/decisions/feat-demo-sheet.md`)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`.

#### 2026-11-11 · Import path: .xlsx via File > Import, one workbook per stage
- **Choice:** `scripts/export_demo_to_sheet.py` writes three .xlsx files built from the template
  (`sheet/deming_demo_1_after_run1.xlsx`, `_2_after_approval`, `_3_after_rerun`). In Sheets: File >
  Import > Upload, then **Create new spreadsheet** for each stage (or **Replace spreadsheet** to swap
  the stage in one Sheet while recording). Avoid **Insert new sheet(s)**: the tabs would collide
  with the existing ones, and the Summary formulas point at the tab names `Inventory`,
  `Decision Log` and `Tickets`.
- **What to avoid (from Google's pages and the earlier template work):** macros, linked
  spreadsheets and protected sheets/cells, which Google lists as unsupported or not preserved;
  Excel tables, named ranges, structured references and dynamic arrays (not used, see
  `feat-eval.md`); password-protected files, which can't be imported; text that looks like a
  formula (every data cell is written as a typed text cell, never a formula).
- **Values:** real dates (`yyyy-mm-dd`), UTC timestamps as real date-times, booleans as TRUE/FALSE,
  confidences as numbers, and versions/ids as text cells with the `@` format. The `@` format is the
  guard against `7.0` or `22.3` becoming numbers. Sheets' "Convert text to numbers, dates, and
  formulas" checkbox appears for CSV/TSV imports. That's another reason to use .xlsx, where each
  cell already has a type.
- **Alternatives:** one CSV per tab (loses validation, formatting and formulas, and the checkbox
  can turn versions into numbers); writing the Sheet directly with the Sheets API (exact, but needs
  OAuth and a Drive; better for the final product); a single workbook with stage tabs (the
  Summary formulas would need per-stage copies).
- **Sources:** https://support.google.com/docs/answer/40608 (import options: create new,
  insert new sheets, replace spreadsheet, replace current sheet, append, replace at cell; "not
  all file types have all six options"; no password-protected files) ·
  https://support.google.com/docs/answer/6055139 (unsupported: macros, linked spreadsheets;
  protected cells become editable) ·
  https://sourcetable.com/how-to-google-sheets/how-to-convert-csv-in-google-sheets (secondary:
  the convert-text checkbox on CSV import)
- **Not verified:** neither Google page says whether data validation, conditional formatting,
  column-level number formats or these formulas survive an .xlsx import. Which of the six options
  the dialog offers for .xlsx wasn't checked either. **No file was imported into a real Google
  Sheet on this branch.**

#### 2026-11-11 · Stages replay the demo, checked against `run_demo()`
- **Choice:** `run_demo()` approves inside run 1, so it has no "pending" moment to show. The
  exporter replays the demo's own steps (`fresh_state`, `run_loop`, `human_edits_inventory`). It
  runs run 1 with no approver, records the same approval (same approver, same timestamp) as its
  own step, then makes the owners' edits and runs run 2. Each time it runs, it also calls
  `sim.demo_scenario.run_demo()` in a temp folder and stops if the final state differs (tabs,
  proposals, approvals, outbox, metrics; run durations excepted). Both ran on the mock model, with
  no API calls.
- **Alternatives:** add a stage hook to `sim/demo_scenario.py` (changes the loop branch's file);
  copy `sim/demo_state/` after `python -m sim.demo_scenario` (only the final stage exists there).

#### 2026-11-11 · Simulator columns the template lacks go to the right
- **Choice:** template columns first, in template order, mapped by name. The simulator's other
  columns come after them, with grey headers: Decision Log M:O (`proposal_id`, `ticket_id`,
  `notes`), Tickets H:S (`lane` … `last_note`). Inventory needs none. The Summary tab says so in
  A24. The Settings tab keeps the template's keys and fills in `approver_email`; the simulator's
  `settings.csv` keys differ (`days_until_reminder` vs `reminder_after_days`, etc.) and are listed
  on the Summary tab instead.
- **Proposed for main:** bring the template's Decision Log / Tickets / Settings up to contracts 1.3
  so the extras become template columns.

#### 2026-11-11 · Bug fixed: Summary lane counts double-counted devices on run 2
- **Found by:** evaluating the Summary formulas (the `formulas` package, installed in the scratchpad
  only, on a bounded-range copy) and comparing them with the loop's own values. After run 2 the
  template gave patch 2 / fine 3 / unknown 2 / 7 devices decided; the loop has 1 / 2 / 1 / 4.
  Cause: contracts 1.3 `verify` rows (and `remind` rows) carry a `lane`, so a device with an open
  ticket was counted twice.
- **Fix:** `scripts/make_sheet_template.py` lane formulas add
  `'Decision Log'!G:G,"<>verify",'Decision Log'!G:G,"<>remind"` to the COUNTIFS. After the fix
  all three stages match: latest run, devices, four lane counts, devices decided, unknown rate, and
  open/escalated/closed tickets (= `metrics.json` `tickets`). `sheet/deming_template.xlsx`
  regenerated. `tickets_overdue` (uses TODAY()) and `urgent_devices` have no loop counterpart and
  were checked only by hand (0 and 2).
- **Not verified:** that Google Sheets evaluates the same values (the `formulas` package is a
  stand-in for a spreadsheet engine).

### Decisions: feat/owner-sim branch (from `docs/decisions/feat-owner-sim.md`)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`. Synthetic data, simulated.

#### 2026-11-12 · Owner simulator as scripted rules around the unchanged loop
- **Choice:** `sim/owner_sim.py` drives `sim.loop.run_loop` one daily tick at a time. Scripted
  owners read the loop's own outbox records and edit the inventory CSV between ticks; a scripted
  human approver (`PolicyApprover`) records decisions through the loop's existing approver hook.
  No existing file changed except `.gitignore` (adds `sim/owner_sim_state/`), so no default-OFF
  wiring was needed.
- **Why:** the task says reuse the loop, not reimplement it. Driving the real `run_loop` means
  the approval gate, dedupe and Verifier closing rule under test are the shipped ones.
- **Alternatives:** a discrete-event framework such as SimPy (https://simpy.readthedocs.io/) or an
  agent-based one such as Mesa (https://mesa.readthedocs.io/). Rejected: the loop is already a
  fixed daily schedule, so a plain `for` loop over dates is the whole event model; a framework
  adds a dependency (we may not edit `requirements.txt` on a branch) and nothing we measure.
- **Not verified:** SimPy/Mesa pages were not re-opened this session; the rejection rests on
  the dependency rule, not on their docs.

#### 2026-11-12 · Seeded determinism with `random.Random(seed)` instances
- **Choice:** one `random.Random(seed)` for the owner->behaviour draw and one
  `random.Random(f"{seed}|{ticket_id}")` per maintenance-window draw; no global random state, no
  wall-clock values in the results doc.
- **Source:** https://docs.python.org/3/library/random.html: "By reusing a seed value, the same
  sequence should be reproducible from run to run"; str seeds (version 2) use all bits of the
  string. The same page says most algorithms and seeding functions "are subject to change
  across Python versions", so reproducibility is claimed **only on Python 3.11** (the repo venv,
  3.11.7), checked by `eval/test_owner_sim.py::test_runs_are_deterministic`.

#### 2026-11-12 · Audit independent of the loop's bookkeeping
- **Choice:** `owner_sim.audit` recomputes every metric from the state files plus the simulator's
  own `owner_events.csv`. A close counts as right only if it passes the contract rule against
  that run's inventory snapshot AND the simulator recorded a real fix/replacement/identification/
  removal. A test plants a wrong close and an unapproved outbox record to prove the audit
  catches them.
- **Why:** a metric computed by the code under test can share its bug.

#### 2026-11-12 · Reroute is a human Sheet edit, not a loop feature
- **Choice:** on a "wrong person" reply a scripted steward edits both the Inventory and the
  Tickets tab `owner_email`. Deming does not parse replies.
- **Why:** reminders use the Tickets tab `owner_email` captured at open (`sim/loop.py
  _propose_reminder`), so an Inventory-only edit would keep reminding the wrong person. Reported
  as a finding in `docs/owner-sim-results.md`; proposing a loop change is left to `main`.
