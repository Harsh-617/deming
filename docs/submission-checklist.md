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

## Repo visibility and judge access (decide)

On 2026-11-11 the repo is **PRIVATE** (`gh repo view`). Judges can't open a private link.
Choose one:
- [ ] **Make it public** before submitting. Then re-run the secret checks below first, because
      the whole history becomes visible, not just the last commit.
- [ ] **Keep it private** and add the judges as collaborators. Only if the organizers give you
      their GitHub usernames; nothing in the repo says they will.

Other access notes:
- [ ] The briefing said reviewers will be invited into each team's Gemini Enterprise app
      (`docs/reference/full-report.md`). That applies to the 17 Nov final, once the Agent Designer
      build exists.
- [ ] No LICENSE file exists. Decide whether to add one before making the repo public.

## Last-minute checks (run on the commit you submit)

- [ ] `main` has every branch merged (feat/docs included) and is pushed.
- [ ] **Tests pass:** `python -m pytest -q` (396 passed on feat/docs, 2026-11-11; the count
      grows once feat/review's tests are on the same branch).
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
