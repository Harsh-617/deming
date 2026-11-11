# AI-usage log

**Branch logs** (kept as separate files):
- [feat/feeds](ai-usage/feat-feeds.md)
- [feat/eval](ai-usage/feat-eval.md)
- [feat/agents](ai-usage/feat-agents.md)
- [feat/inventory](ai-usage/feat-inventory.md)
- [feat/loop](ai-usage/feat-loop.md)
- [feat/review](ai-usage/feat-review.md)
- [feat/docs](ai-usage/feat-docs.md)
- [feat/cross-check](ai-usage/feat-cross-check.md)

| Date | Tool | What for |
|---|---|---|
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Scaffolded the repo: folders, CLAUDE.md, README, docs, .gitignore, .env.example, requirements, the secret-blocking commit hook and its tests, the venv and smoke test. Also checked Google's Gemini docs for the current model and structured-output API. |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Added the read-PRD rule to CLAUDE.md, key-scanned and committed the PRD and full report, and added the tracked git pre-commit/pre-merge-commit hook with tests (including worktrees). |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Wrote and ran eval/smoke_test.py (live Gemini key and model check) and recorded the eval model choice in decisions.md. |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Drafted docs/contracts.md (shared file formats); checked the live CISA KEV JSON structure. |
| 2026-11-11 | Gemini API (gemini-3.5-flash-lite, gemini-3.8-flash) | Smoke test: 6 calls extracting vendor/product/version from one synthetic device name. |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Added `jsonschema` to requirements.txt (commit 74d7fb3) and checked its Python requirement and `pip check` from the installed package metadata. |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Merged feat/feeds, feat/eval and feat/agents into main; added `openpyxl` to requirements; indexed the branch logs; amended docs/contracts.md to v1.1 (lifecycle `fixed_version` column, `ground_truth_meta.json`); added the platform findings to the PRD. |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Fix task: urgency wording, most-specific model_pattern retrieval, fixed_version/as_of_date Checker rules, deterministic version guard + tests, --as-of CLIs |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Merged feat/inventory; contracts v1.2 (per-train fixed_version, example.org, urgency note); per-train version guard fix + tests on real rows; checker prompt + guide sync; offline baseline run. |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Merged feat/loop; contracts v1.3 (Decision Log/Tickets columns, proposals/approvals/expected_verification formats); PAN-OS `-h<n>` hotfix parsing with real-device tests; overdue KEV deadline rule (prompt, guard, mock, tests); Verifier removal-close fix; per-train fix in loop verification; prompt + guide sync. |
| 2026-11-11 | Gemini API (gemini-3.5-flash-lite), Claude Code (Claude Opus 5.5) | Live smoke test on the 8-device fixture: 69 real Normalizer/Checker/Planner calls (1 run + 2 more repeats), sequential; wrote `eval/live_fixture_run.py`; checked the official rate-limits page. No prompt or schema changes. |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Rule/consistency fix task: Ivanti `22.7R2.6` and NetScaler `14.1-47.46` exact version forms (vendor pages read); retire deadline = as_of + retire_days; Planner recipient removed, ticket issue enum; evidence ids filled from candidates; KEV with no lifecycle row → unknown; fixture truth DEV-001/002/007 → unknown; structured vs free-text stability; contracts v1.4; prompts + guide sync. No prompt tuning on data/inventory.csv. |
| 2026-11-11 | Gemini API (gemini-3.5-flash-lite) | Live fixture run, 8 devices x 3 repeats, default Settings, fresh cache (all calls live), sequential. |
| 2026-11-11 | Gemini API (gemini-3.5-flash-lite) | Second live fixture run (8 devices x 3 repeats, 69 live calls) after a checker.md wording fix for a regression the first run showed. |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Froze prompts-v1 (tag, docs/prompts-freeze.md with sha256s); wrote eval/full_run.py (quota stop rule) and eval/offline_analysis.py (cache-only replay, per-repeat/group scores, stability, post-hoc alias view); scored baseline vs Deming; wrote docs/results-analysis.md. No prompt, schema, guard or data change. |
| 2026-11-11 | Gemini API (gemini-3.5-flash-lite) | Full evaluation run on data/inventory.csv, prompts-v1: about 500 Normalizer/Checker/Planner calls, sequential, default Settings. Repeats 0-1 complete; repeat 2 stopped at 40/60 (network drop, then daily quota). |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Merged feat/review and feat/docs into main; trimmed Eolix/Xeol text in README and `docs/decisions/feat-docs.md` to the PRD statement plus "we did not test them"; added feat-review/feat-docs index links; ran a read-only, redacted secret and large-file scan of the full git history. |
