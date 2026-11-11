# AI usage: feat/cross-check

| Date | Tool | What for |
|---|---|---|
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Wrote `eval/blind/cross_check.py` (adapter around `eval/blind/agreement.py`, lane metrics, source checks, report), `eval/test_cross_check.py`, `docs/ai-cross-check.md` (generated), `docs/decisions/feat-cross-check.md`; fetched the 12 distinct AI source URLs once each; added one sentence each to the README and `docs/ai-and-teamwork.md`. |
| 2026-11-11 | Claude (separate session, outside this repo) | Produced `eval/blind/external/blind_ai_claude.csv`: 15 blind labels with reasons and sources. Committed here as input. |

No Gemini or other LLM calls were made by this branch's code. No label in `data/` was written or
changed; `verified_by_a` / `verified_by_b` are untouched. The cross-check is not human
verification.
