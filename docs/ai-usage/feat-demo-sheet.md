# AI usage: feat/demo-sheet

| Date | Tool | What for |
|---|---|---|
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Checked Google's import help pages (.xlsx File > Import); wrote `scripts/export_demo_to_sheet.py` (three stage workbooks from the mock demo) and its openpyxl read-back tests; evaluated the Summary formulas offline with the `formulas` package (scratchpad only), found and fixed the lane double-count in `scripts/make_sheet_template.py`. Mock model only, no Gemini calls. |
