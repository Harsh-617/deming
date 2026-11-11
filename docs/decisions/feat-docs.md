# Decisions: feat/docs branch

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`.

---

### 2026-11-11 · README structure for judges
- **Choice:** problem with sourced numbers and caveats → what Deming does → what runs where →
  how to reproduce (copy-paste commands, each run on this branch) → evaluation summary → limits
  → related tools. Long material lives in linked docs (`docs/limits.md`,
  `docs/results-analysis.md`, `docs/demo-script.md`), not in the README.
- **Why:** GitHub's README page says a README should tell people why the project is useful, what
  they can do with it and how to use it, and should hold only what is needed to get started;
  longer docs belong elsewhere. Google's style guide asks the README to link to fuller docs.
  Hackathon submission guides ask for an overview, setup steps and a demo link. The briefing's
  five topics (problem, solution, research, teamwork, impact; `docs/reference/full-report.md`)
  are each covered by a README section or a linked doc.
- **Alternatives:** one long README with everything (harder to scan); a README with only setup
  (doesn't answer the judging topics).
- **Sources:**
  https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes ·
  https://google.github.io/styleguide/docguide/READMEs ·
  https://hackncstate2025.notion.site/Submission-Judging-143963046a38810d998acb9b9290863d ·
  https://hackutd-tech-guide-git-springbranchupdated-acmutd.vercel.app/dayof/devpost-markdown
- **Not verified:** the search returned an archived Enterprise Server copy of GitHub's page; the
  current page wasn't opened. The hackathon guides are other events' guides, not APU's rules.
  APU's rubric weights are still unpublished (PRD).

### 2026-11-11 · Every README command is run before it is written
- **Choice:** only commands that were run on this branch go in the README, with the venv at
  Python 3.11.7. Results on 2026-11-11:
  - `python -m pytest -q`: 396 passed.
  - `python eval/baseline.py`: wrote 60 rows; first 7 columns identical to the published
    `eval/runs/baseline-20261111T075945Z/baseline.csv` (run with `--out-root` in a temp folder).
  - `python eval/run_eval.py --pred <published baseline, rep 0, rep 1> --inventory data/inventory.csv`:
    deming lane_acc 0.88, norm_all3 0.47; baseline 0.32 / 0.18, matching `docs/results-analysis.md`.
  - `python eval/offline_analysis.py ...`: fails from a clean clone with
    `RuntimeError: cache miss` because the response cache (`.cache/`, gitignored) isn't in the
    repo. With the original machine's cache (`DEMING_CACHE_DIR`) it reproduced the published
    `offline_analysis.md` exactly (0 replay mismatches, 0 API calls). The README says so.
  - `python -m sim.demo_scenario`: ran on the mock; DEV-101/102 closed, DEV-104 escalated
    (still vulnerable), DEV-103 open; duplicate_tickets 0, approval_compliance 1.0.
  - `python -m sim.loop ... --mock`, `pending`, `approve`, `metrics`: ran on the fixture.
- **Not run (needs the key / quota, and this task forbids API calls):** `python eval/full_run.py`,
  `python -m sim.pipeline`, `python -m sim.demo_scenario --gemini`.
- **Finding:** `sim.demo_scenario` has no `--mock` flag; the mock is its default and `--gemini`
  opts into the API. `--mock` belongs to `python -m sim.loop`. The README uses the real flags.

### 2026-11-11 · Related tools: Eolix and Xeol, described from their own listings
- **Choice:** name both, say what each covers, and say Deming is not unique (PRD "Never claim").
  Eolix: an IT asset lifecycle product that checks software found via Intune / Jamf or a CSV /
  Excel export against vendor lifecycle data. Xeol: an open-source (Apache-2.0) scanner for
  end-of-life software in container images, filesystems and SBOMs; HeroDevs acquired it in
  February 2025. Deming's stated edge is the PRD's: closed loop, measured evaluation, portable
  no-code design.
- **Sources:** https://www.g2.com/products/eolix/discuss ·
  https://www.herodevs.com/blog-posts/herodevs-acquires-xeol-to-help-users-of-end-of-life-open-source-software-secure-their-applications-and-protect-their-data ·
  https://awesome.ecosyste.ms/projects/github.com%2Fxeol-io%2Fxeol ·
  `docs/reference/full-report.md` (sources table)
- **Not verified:** read from search-result excerpts, not from the products' own docs; neither
  tool was installed or tried. Whether either covers network edge devices, KEV, approvals or
  re-verification wasn't checked, so the README doesn't claim they lack those.

### 2026-11-11 · Submission summary draft
- **Choice:** a 2-sentence summary (319 characters) in `docs/submission-checklist.md`,
  naming the loop, the four lanes, approval and the synthetic data. It avoids every PRD
  "Never claim" item (no uniqueness, no real-world accuracy, no "runs in Gemini Enterprise").
- **Alternatives:** a one-line tagline only ("Patch or Retire"); it meets 50 characters only
  with padding and says less.
