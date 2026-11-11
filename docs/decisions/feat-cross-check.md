# Decisions: feat/cross-check branch

One short entry per decision: choice, alternatives, source, and what couldn't be verified.

---

### 2026-11-11 · How to report agreement on 15 blind AI labels
- **Choice:** report raw percent agreement (12/15) and Cohen's kappa on lane together, with an
  approximate 95% CI from SE = sqrt(p_o(1-p_o) / (n(1-p_e)^2)), and say plainly that n=15 is
  below the suggested minimum of 30, so the CI is only a rough guide. Kappa is computed by the
  existing `cohen_kappa` in `eval/blind/agreement.py` (reused, not edited).
- **Why:** McHugh (2012) advises calculating both percent agreement and kappa, gives the SE and
  CI formula, and suggests at least 30 comparisons. Percent agreement alone ignores chance;
  kappa alone hides the raw counts on a tiny sample.
- **Alternatives:** bootstrap CI (unstable at n=15 and adds code); Fleiss kappa (for 3+ raters,
  not needed); percent agreement only (ignores chance agreement).
- **Source:** McHugh ML. Interrater reliability: the kappa statistic. Biochem Med
  2012;22(3):276-82. https://pmc.ncbi.nlm.nih.gov/articles/PMC3900052
- **Not verified:** the formula was read from the PMC copy, whose equation text renders
  garbled; it was reconstructed as above. Kappa's known sensitivity to skewed lane counts was
  not researched further in the time box.

### 2026-11-11 · Adapter instead of editing agreement.py
- **Choice:** `eval/blind/agreement.py` already reads the AI file (same worksheet columns), so it
  is reused as is. `eval/blind/cross_check.py` adds only what it lacks: the column mapping for
  `comment` (reason), `source_url_used` and `notes`, the POST-HOC alias view (imported from
  `eval/offline_analysis.py`, unchanged), source checks and the report.
- **Alternatives:** extend agreement.py (the task forbids it); copy its kappa code (duplication).

### 2026-11-11 · Automatic source check
- **Choice:** fetch each distinct source URL once, 3 s apart, with a generic user agent; mark
  401/403/429/5xx or near-empty pages "needs human check in a browser"; look for the dates,
  versions, CVE ids and quoted phrases from the AI's reason literally (with common date
  spellings). The device's own firmware is not a claim unless nothing else is named. A claim
  counts as supported only if the page opened and every string was found.
- **Alternatives:** a headless browser (heavier, renders JS, but still can't say whether the
  page applies to the model); reading every page by hand (that is the human's job, and the
  triage lines say which pages).
- **Not verified:** a found string is not proof that the page says it about this model; the
  report says so.
