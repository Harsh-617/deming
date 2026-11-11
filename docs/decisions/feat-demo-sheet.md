# Decisions: feat/demo-sheet branch

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`.

---

### 2026-11-11 · Import path: .xlsx via File > Import, one workbook per stage
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

### 2026-11-11 · Stages replay the demo, checked against `run_demo()`
- **Choice:** `run_demo()` approves inside run 1, so it has no "pending" moment to show. The
  exporter replays the demo's own steps (`fresh_state`, `run_loop`, `human_edits_inventory`). It
  runs run 1 with no approver, records the same approval (same approver, same timestamp) as its
  own step, then makes the owners' edits and runs run 2. Each time it runs, it also calls
  `sim.demo_scenario.run_demo()` in a temp folder and stops if the final state differs (tabs,
  proposals, approvals, outbox, metrics; run durations excepted). Both ran on the mock model, with
  no API calls.
- **Alternatives:** add a stage hook to `sim/demo_scenario.py` (changes the loop branch's file);
  copy `sim/demo_state/` after `python -m sim.demo_scenario` (only the final stage exists there).

### 2026-11-11 · Simulator columns the template lacks go to the right
- **Choice:** template columns first, in template order, mapped by name. The simulator's other
  columns come after them, with grey headers: Decision Log M:O (`proposal_id`, `ticket_id`,
  `notes`), Tickets H:S (`lane` … `last_note`). Inventory needs none. The Summary tab says so in
  A24. The Settings tab keeps the template's keys and fills in `approver_email`; the simulator's
  `settings.csv` keys differ (`days_until_reminder` vs `reminder_after_days`, etc.) and are listed
  on the Summary tab instead.
- **Proposed for main:** bring the template's Decision Log / Tickets / Settings up to contracts 1.3
  so the extras become template columns.

### 2026-11-11 · Bug fixed: Summary lane counts double-counted devices on run 2
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
