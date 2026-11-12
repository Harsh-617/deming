# Submission checklist

Deadline: **Fri 13 Nov 2026, 12:00 MYT** (target 10:00). Only the team leader submits, and the
final submission **locks the project and PDF** (`docs/reference/full-report.md`). Required
fields: title, track, summary of at least 50 characters, HTTPS repo link, PDF deck up to 10 MB;
demo link optional (`docs/PRD.md`).

## Form fields

- [ ] **Title:** `Deming: Patch or Retire`
- [ ] **Track:** Intelligent Automation and Digital Transformation (track 2)
- [ ] **Summary** (draft, 319 characters; edit freely, keep it at 50+):

  > Deming is a scheduled agent that checks a device inventory against CISA's known-exploited
  > list and end-of-life data, puts every device in one lane (patch, retire, fine or unknown),
  > drafts the owner's action, waits for human approval, and on the next run checks the
  > inventory record changed. Prototype on synthetic data.

  It avoids every PRD "Never claim" item: no "unique", no real-world accuracy, no "runs in
  Gemini Enterprise" until it does.
- [ ] **Repo link (HTTPS):** `https://github.com/Harsh-617/deming`
- [ ] **PDF deck** attached, **under 10 MB** (check the file size before upload)
- [ ] **Demo link** (optional): the backup video (`docs/demo-script.md`), tested while logged out

## Open items for a human (not done; nobody may tick these for you)

State on 2026-11-12, after `fix/final-polish`. None of these can be done by the code or by an AI
session. Each needs a named person.

- [ ] **T35 end-of-life check for DEV-052 and DEV-025.** On 2026-11-12 an AI session
      (fix/t35-labels) opened https://www.watchguard.com/node/111406 (Firebox T35 EOL 31 Dec
      2025; T35-R / T35-DW 01 Mar 2027) and changed both draft lanes to `retire`. The change is
      logged with before/after numbers in `docs/results-analysis.md`, "Ground-truth corrections".
      **Still for a person:** confirm the page and that both raw names mean a plain T35, not a
      T35-R or T35-DW. The labels stay `ai_drafted_unverified`. Not done by a human.
- [ ] **Human review of the labels.** `data/ground_truth_meta.json` says
      `label_status: ai_drafted_unverified`, and `verified_by_a` / `verified_by_b` are blank on
      all 60 rows. Two people other than the author follow `docs/review-instructions.md` (blind
      page first, then the review page). The AI cross-check is **not** a human review. Not done.
- [ ] **Sheets import test.** No .xlsx has been imported into a real Google Sheet yet. Import
      `sheet/deming_template.xlsx` and the three `sheet/deming_demo_*.xlsx` (File > Import >
      Upload > Create new spreadsheet). Check that the dropdowns, lane colours, frozen headers,
      text versions (`7.0` stays `7.0`) and the Summary formulas survive, and that Summary
      column B equals column D. Also check that the blank lane on DEV-102's verify row (stage 3)
      is not flagged as invalid. Not done.
- [ ] **Coordinator message.** Write and send it (the team decides the content; the open topics in
      `docs/reference/full-report.md` are Gemini Enterprise license status for the 17 Nov final
      and how judges get access to the repo). Not done.
- [ ] **Backup video.** Record it using the checklist in `docs/demo-script.md` ("Backup-video
      checklist"), upload it, and test the link while logged out. Not done.

## Repo visibility and judge access (decide)

On 2026-11-12 the repo was made **PUBLIC** after a clean full-history secret scan
(`gh repo view`: visibility PUBLIC, license MIT; an unauthenticated `git ls-remote` works).
- [x] **Make it public** before submitting. Done 2026-11-12 on `fix/submit-ready`. The whole
      history is now visible, so keep running the secret checks below before every push.
- Not chosen: keep it private and add the judges as collaborators (no judge usernames given).

Other access notes:
- [ ] The briefing said reviewers will be invited into each team's Gemini Enterprise app
      (`docs/reference/full-report.md`). That applies to the 17 Nov final, once the Agent Designer
      build exists.
- [x] **License:** MIT, in `LICENSE` at the repo root (added 2026-11-12 on `fix/submit-ready`).

## Last-minute checks (run on the commit you submit)

- [ ] `main` has every branch merged and is pushed (`git branch --no-merged main` prints nothing;
      true on 2026-11-12 after `fix/final-polish`, re-check on the day).
- [ ] **Tests pass:** `python -m pytest -q`. All tests should pass; one is skipped
      unless the optional `formulas` package is installed.
- [ ] **README commands tested** on a fresh clone with a fresh venv: install, tests,
      `python eval/baseline.py`, the `run_eval` command, `python -m sim.demo_scenario`.
- [ ] **No secrets:**
  - [ ] `git ls-files .env` prints nothing; `.env.example` holds only `GEMINI_API_KEY=`.
  - [ ] Scan the whole history, not just the tree:
        `git log -p --all | Select-String -Pattern 'AIza[0-9A-Za-z_-]{35}'` prints nothing.
  - [ ] The commit hook is on: `git config core.hooksPath` shows `.../scripts/githooks`.
- [ ] **No real data:** owner emails are all `@example.org`; no real device names of APU.
- [ ] **Claims check:** README, deck and video say "synthetic", "unverified labels", "the
      Verifier confirms the record changed", and don't say Deming runs in Gemini Enterprise
      unless it has by then.
- [ ] If any ground-truth label was corrected after the run: logged with old/new values and
      evidence, and numbers reported before and after (`docs/results-analysis.md`).
- [ ] If labels got reviewer initials before submission, the README's "all 60 unverified"
      line is updated to match.
- [ ] **Tag** the submitted commit: `git tag submission-2026-11-13` then
      `git push origin submission-2026-11-13`.
- [ ] Repo link opens in a private/incognito window (if public).
- [ ] Submit by 10:00 MYT; check the confirmation page before the 12:00 lock.
