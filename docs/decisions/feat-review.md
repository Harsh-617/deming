# Decisions: feat/review (label checks and reviewer tools)

One short entry per choice. Research budget: 5 minutes per task. No LLM calls in this branch.

### 2026-11-11 · Review tool for two non-technical reviewers
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

### 2026-11-11 · Reviewer field = initials
- **Choice:** the required reviewer field asks for initials (letters, spaces, dots, hyphens; no
  commas), because `verified_by_a/b` hold initials (contracts.md). `merge_reviews.py` writes the
  value as typed. Two exports from the same reviewer (case-insensitive) are rejected.

### 2026-11-11 · Mechanical lane recompute
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

### 2026-11-11 · Source URL checks
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

### 2026-11-11 · Blind page isolation
- **Choice:** `build_blind_page.py` opens only `eval/blind/blind_worksheet.csv` and keeps only
  `blind_id`, `device_name_raw` and `firmware_version_raw`. `blind_id` is the row key that
  `eval/blind/agreement.py` joins on, and it is a worksheet column. The export is the worksheet
  header plus a trailing `source_url_used` (agreement.py ignores unknown columns). The as-of date
  shown is a builder argument (default 2026-11-12), not read from data/. A test checks every
  ground_truth.csv / blind_key.csv cell against the generated page (exempt: the lane enum, and
  values that already appear in the worksheet inputs), plus `DEV-`, `LC-` and `CVE-` id patterns.
  A mutation check confirmed it catches a planted product name, group or device id.

### 2026-11-11 · Merge
- **Choice:** `merge_reviews.py A.csv B.csv`: the first file fills `verified_by_a`, the second
  `verified_by_b`, only on rows marked `verified`. Other columns are copied byte-for-byte as values. It
  refuses to write to `ground_truth.csv`. Every row not verified by both goes to
  `docs/label-disagreements.md` with both reviewers' notes.
- **Known gap:** the export has exactly the four requested columns, so it carries no label
  fingerprint. If a label changes after a reviewer exported, the merge can't tell. Mitigation:
  the review page's saved state is keyed on a hash of the labels (a label change starts a fresh
  review), and the guide says to re-review changed rows.
