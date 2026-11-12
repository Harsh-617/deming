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
