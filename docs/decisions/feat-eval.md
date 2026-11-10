# Decisions: feat/eval (evaluation harness, naive baseline, Sheet template)

One short entry per choice. Research budget: 5 minutes per task.

### 2026-11-11 · Naive baseline matching
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

### 2026-11-11 · Fixture
- **Choice:** 8 hand-made devices in `eval/fixtures/` covering all 6 groups, plus a 6-entry KEV
  file in the real KEV format and a 4-row lifecycle file. The CVE-to-product pairs are real KEV
  entries, quoted from memory and **not re-checked against the live catalog**. Lifecycle dates
  and URLs are placeholders, marked `FIXTURE ONLY`. DEV-006 has one reviewer on purpose, to
  exercise the verified/unverified split.
- **Not a test set.** It only checks that the harness computes the right numbers.

### 2026-11-11 · Metrics implementation
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

### 2026-11-11 · Stability metric
- **Choice:** share of devices where all N runs give the same lane, and separately the same
  vendor/product/version. Unstable devices are listed in failures.csv as `unstable`.
- **Alternatives:** Fleiss' kappa, which corrects for chance agreement but is hard to explain in a
  3-minute pitch and unstable at n=60 with skewed lanes; mean pairwise agreement.
- **Not verified:** no primary source was checked for this. It is the simplest honest measure.

### 2026-11-11 · Report
- **Choice:** Markdown `report.md` + `failures.csv` in `eval/results/<UTC stamp>/`. Primary metrics
  use each system's earliest run; per-run numbers are shown in a table. Slices: all, verified,
  unverified (contract: report unverified rows separately), and each group. "Baseline ties or
  beats" is checked on 8 metrics per slice and stated in a sentence starting "Plainly:".
- **Alternatives:** HTML/Jinja (adds a dependency, nothing to gain for a repo artifact); pandas
  `to_markdown` (needs `tabulate`).

### 2026-11-11 · Sheet template format (.xlsx via openpyxl)
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
