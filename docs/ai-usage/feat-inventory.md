# AI usage: feat/inventory

| Date | Tool | What for |
|---|---|---|
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Drafted the 60 synthetic devices and their **draft** ground-truth labels in `scripts/build_inventory.py`, each from a cited lifecycle row / KEV entry / vendor advisory. These labels are NOT yet human labels: `verified_by_a` / `verified_by_b` are blank until two people check `docs/label-review.csv` row by row (PRD: ground truth is labelled by people, not an LLM). |
| 2026-11-11 | Claude Code (web fetch) | Re-opened vendor advisories to fill `fixed_version` in `data/lifecycle.csv` (7 rows) and to check newer KEV CVEs before choosing fine versions. Quotes in `docs/decisions/feat-inventory.md`. |
| 2026-11-11 | Claude Code (web search) | 5-minute check of real device naming conventions for realistic messy names. |
| 2026-11-11 | Claude Code | Wrote `tests/test_inventory.py`, `eval/blind/agreement.py`, the blind worksheet and the label-review sheet. |
