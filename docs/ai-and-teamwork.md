# AI use and teamwork

Pulled from `docs/ai-usage-log.md` and the per-branch logs in `docs/ai-usage/` (plus
`docs/ai-usage/feat-review.md` on `main`). Dates are 2026-11-11 unless stated.

## How AI tools were used

### Claude Code (Claude Opus 5.5): implementation

Claude Code wrote the code and documents in this repo, branch by branch:

| Branch | What Claude Code did |
|---|---|
| main (scaffold) | Repo layout, CLAUDE.md, the secret-blocking commit hook and its tests, venv smoke test, `docs/contracts.md` (v1 to v1.4), merges |
| feat/feeds | `scripts/fetch_kev.py`, feed tests, `docs/feeds.md`. Research subagents found and quoted vendor end-of-life notices for `data/lifecycle.csv`; every kept row was checked against its vendor URL |
| feat/eval | Naive baseline, metrics, report writer, `run_eval` CLI, 8-device fixture, Sheet template generator |
| feat/agents | The four subagent prompts (`agents/*.md`), JSON schemas, retrieval, guards, Gemini runner, pipeline, the Agent Designer port guide and asset export |
| feat/inventory | The 60 synthetic devices and their **draft** ground-truth labels, each from a cited source; re-opened vendor advisories for `fixed_version` |
| feat/loop | Closed-loop simulator, rule-based mock model, demo scenario, loop tests |
| feat/review (on main) | Label-check scripts, review and blind-review pages. It did not write or change any label |
| main (fixes, eval) | Rule fixes, the prompts-v1 freeze, `eval/full_run.py`, `eval/offline_analysis.py`, `docs/results-analysis.md` |
| feat/docs | This README, `docs/limits.md`, this file, `docs/demo-script.md`, `docs/submission-checklist.md` |

Claude Code also did the short research passes the project rule asks for (official docs first)
and logged each choice with its source in `docs/decisions.md` and `docs/decisions/`.

### Gemini API: the product's model, not a build tool

`gemini-3.5-flash-lite` (and `gemini-3.8-flash` in one smoke test) is what Deming itself runs on.
Logged uses: a 6-call smoke test, two live 8-device fixture runs (69 calls each), and the full
evaluation run (about 500 calls). These calls are the system under test.

### Other models as cross-checks

**Nothing is recorded in the logs.** No other AI model appears in `docs/ai-usage-log.md` or the
branch logs. If the team used other models to cross-check work, add them here with the date and
what was checked:

| Date | Tool | What it cross-checked | Outcome |
|---|---|---|---|
| _to fill_ | | | |

## What stayed human

From the logs and the PRD:
- **Ground-truth verification.** Labels count as verified only with two human reviewers'
  initials in `verified_by_a` / `verified_by_b`. Both columns are blank on all 60 rows on this
  branch, so verification has not happened yet (`data/ground_truth.csv`).
- **Approvals.** Every outward action needs a recorded approval by a named human; tier-3 actions
  (isolate, disconnect, replace) are only drafted (`docs/PRD.md`, `sim/loop.py`). In the demo the
  approver is scripted.
- **Secrets.** A person puts the API key in `.env` (CLAUDE.md); `scripts/block_secrets.py` blocks
  committing it.
- **Problem choice, scope and the PRD** came from the full report (`docs/reference/full-report.md`).
  _Team: say here who chose the problem and wrote or reviewed the report._

## Team roles

Fill this in yourselves. Teams are 2 to 5 people including the leader
(`docs/reference/full-report.md`).

| Name | Role | What they did |
|---|---|---|
| _to fill_ | Team leader (submits) | |
| _to fill_ | | |
| _to fill_ | | |
| _to fill_ | | |
| _to fill_ | | |
