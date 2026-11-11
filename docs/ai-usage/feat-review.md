# AI usage: feat/review

| Date | Tool | What for |
|---|---|---|
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Wrote `scripts/check_labels.py`, `scripts/build_review_page.py`, `scripts/build_blind_page.py`, `scripts/review_common.py`, `scripts/merge_reviews.py`, `tests/test_review_tools.py`, `docs/review-instructions.md`, `docs/decisions/feat-review.md`; ran the URL check and generated `docs/label-check-report.md` and the two review pages; tested the pages in a Playwright-driven Chromium. |

The ground-truth labels were **not** written or changed by an AI in this branch. The scripts only
read `data/`. The mechanical check is deterministic code, with no LLM calls (no Gemini API use in
this branch). Label verification is left to the two human reviewers.
