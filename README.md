# Deming: Patch or Retire

A scheduled agent that reads a device inventory, checks each device against CISA KEV (known
exploited vulnerabilities) and end-of-life data, drafts the right action for the owner, waits
for a human to approve it, and on the next run checks that the inventory record changed.
Built for the APU Cloud Innovation Hackathon 2026, track 2 (Intelligent Automation and Digital
Transformation). The name comes from the Deming cycle (Plan-Do-Check-Act).

**All device data in this repo is synthetic.** Deming never scans, probes or touches a real
device. It reads the inventory file and public data feeds only.

## The problem

People who run connected devices (IT staff, lab technicians, facilities teams) have no
low-effort way to learn which devices are exposed or unsupported, who owns each one, what to do
about it, and whether it was done. Two published numbers, each with its caveat:

- **43 days:** the median time to fully fix a known-exploited vulnerability in the 2026 Verizon
  DBIR. *Caveat: taken from a secondary summary (watchTowr); we did not open the Verizon PDF.*
- **42.5%** of vulnerabilities exploited in 2025 hit end-of-life or likely-end-of-life devices
  (VulnCheck 2026 report). *Caveat: vendor research, and "likely end of life" is VulnCheck's own
  heuristic.*

The same VulnCheck report says only 23.7% of the exploited edge-device vulnerabilities it found
are in CISA KEV, so Deming treats KEV as a baseline, not the full picture. Not verified: that APU
has such devices, or that an agent like this shortens time to fix. No real user has validated
the problem. Sources: `docs/PRD.md` and the sources table in `docs/reference/full-report.md`.

## What Deming does

Each run, every device gets exactly one lane:

| Lane | When | What Deming does |
|---|---|---|
| **patch** | A fix exists | Drafts update instructions with a deadline and maintenance window; next run checks the version reached the fix |
| **retire** | The vendor no longer supports it | Drafts a replacement request and interim mitigation; next run checks the device was removed |
| **fine** | No known issue | Logs it |
| **unknown** | It can't match the device confidently | Asks a human to identify it. It never guesses |

Four narrow subagents, called by one main agent:

| Subagent | Job |
|---|---|
| **Normalizer** | Messy name → vendor, product, version, with a confidence score. Below 0.80 → `unknown` |
| **Checker** | Compares with KEV and lifecycle data; assigns the lane with evidence (CVE ids, lifecycle row) |
| **Planner** | Drafts the owner message, ticket and calendar proposal; ranks priority; avoids duplicate tickets |
| **Verifier** | Next run: closes, reminds or escalates. It confirms only that **the inventory record changed**, never that a device is secure |

Autonomy tiers (`docs/PRD.md`): 0 read-only and 1 draft run on their own; 2 outward actions
(email, calendar, ticket) need a recorded human approval; 3 consequential actions (isolate,
disconnect, replace) are only ever drafted, and a named human decides. A device flagged
`do_not_touch` is never proposed for disconnection; it is escalated. Device fields are treated
as data, never as instructions (the test inventory contains an injection string on purpose).

## What runs where

**Python prototype (this repo): runs today.**
- Normalizer, Checker and Planner are real Gemini API calls through `google-genai`, with
  structured JSON output, model `gemini-3.5-flash-lite` at temperature 0 (`sim/config.py`).
- Prompts are plain text in `agents/*.md`; output schemas are in `schemas/`.
- Candidate retrieval (`sim/retrieval.py`) and the safety rules (`sim/guards.py`, `sim/loop.py`)
  are deterministic code applied after every model call: confidence threshold, version
  comparison per release train, approval before any outward action, no tier-3 execution,
  one open ticket per device and issue, ticket closes only on the fixed version or removal.
- The closed loop (`sim/loop.py`) keeps state in CSV files that stand in for the Sheet tabs
  (Inventory, Decision Log, Settings, Tickets) plus a proposals file that stands in for the
  approval Inbox. Outward actions are written as JSON records to an `outbox/` folder inside the
  state folder (`sim/state/outbox/` or `sim/demo_state/outbox/`). **Nothing is sent**:
  no email, calendar invite or ticket leaves the machine.
- A rule-based mock model (`sim/mock_llm.py`) lets the loop and demo run with no API key. It is
  not an evaluation of the prompts.

**Gemini Enterprise Agent Designer: described, not yet built.**
- `docs/agent-designer-port.md` is a step-by-step port guide (chat agent with a main agent and
  four subagents, Drive data store, Gmail / Calendar / Chat / Jira connectors, schedule).
  `agents/main_agent.md` is the main-agent prompt; `scripts/export_agent_assets.py` builds the
  files to upload.
- **As of this commit (11 Nov 2026), nothing has been built or run in Agent Designer.** The repo
  has no record of a working license. The 13 Nov prototype doesn't need Gemini Enterprise; the
  17 Nov final does (`docs/PRD.md`).
- Platform findings read from Google's docs but **not confirmed on a live license**: Google
  Sheets is not a listed connector (fallback: a CSV copy in Drive); scheduled chat agents can't
  act on other people's behalf, so owner emails would go out only after approval in the run's
  chat, never unattended; schedules run hourly at best and need a credential refresh every 14
  days.

## How to reproduce (Windows PowerShell)

Every command below was run on this branch on 2026-11-11 unless marked otherwise
(`docs/decisions/feat-docs.md`).

**Requirements**

- **Python 3.11.** Tested on 3.11.7 only (Windows 11). Other versions weren't tried.
- **git**, to clone the repo and for the commit hooks below. **gh** (GitHub CLI) only if you
  want to open pull requests from the command line.
- No API key for anything except the full run at the end of this section.

**Install**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
git config core.hooksPath "$(git rev-parse --show-toplevel)/scripts/githooks"   # blocks committing .env or Google keys
```

- If `Activate.ps1` fails with "running scripts is disabled on this system", allow local scripts
  for your user once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or for this window
  only: `Set-ExecutionPolicy -Scope Process Bypass`. Then activate again.
- pip may print a red or yellow "A new release of pip is available" notice. It is harmless;
  the install still succeeded.
- `requirements-lock.txt` pins every package to the version the tests pass with.
  `requirements.txt` lists only the direct dependencies, unpinned. `requirements-dev.txt` adds
  the optional `formulas` package (offline check of the Sheet formulas); you don't need it.

**Safety hooks.** Two hooks run the same scanner, `scripts/block_secrets.py`:
1. The git hooks in `scripts/githooks` (pre-commit and pre-merge-commit; enabled by the
   `git config` line above) block a commit whose staged files include a file named `.env` or a
   Google API key pattern (`AIza...` / `AQ....`).
2. A Claude Code `PreToolUse` hook in `.claude/settings.json` runs before every Bash or
   PowerShell command Claude Code issues. On commands containing `git commit` it blocks the
   command if its text holds a key pattern or runs `git add` on `.env`, or if staged, unstaged or
   untracked files would add a `.env` file or a key pattern. It does nothing outside Claude Code.

Don't bypass either one with `--no-verify`.

**Tests** (no key needed): `python -m pytest -q`. All tests should pass (one is skipped unless the
optional `formulas` package from `requirements-dev.txt` is installed).

**Offline baseline and scoring** (no key needed):

```powershell
python eval/baseline.py          # naive KEV matcher → eval/runs/baseline-<UTC>/baseline.csv
python eval/run_eval.py --inventory data/inventory.csv --pred `
  eval/runs/baseline-20261111T075945Z/baseline.csv `
  eval/runs/deming-20261111T075938Z/deming.csv `
  eval/runs/deming-20261111T081026Z/deming.csv
# → eval/results/<UTC>/report.md and failures.csv
```

**This `run_eval.py` command scores the published files**, including the published baseline
`baseline-20261111T075945Z`, not the baseline you just generated. It reproduces the published
report `eval/results/20261111T141730Z/report.md` (Deming primary metrics = repeat 0). To score
your own baseline, replace the first `--pred` path with the path `baseline.py` printed; the
baseline is deterministic, so the numbers should match. Running `run_eval.py` with no `--pred`
scores every CSV under `eval/runs/`; if you generated a baseline, there are then two baseline
runs and the earlier (published) one is the primary.

**What a fresh clone cannot reproduce.** The model's responses for the published run are in a
local response cache (`.cache/`, gitignored), which is not in the repo. Without it:
- `eval/offline_analysis.py` stops with `cache miss` (it never calls the API). So the
  **repeat 1 column** of the evaluation table below (strict product match, exposure precision
  and recall), the per-group tables per repeat, the three-repeat stability footnote and the
  **post-hoc alias numbers** (0.30 / 0.90 / 0.95) can't be regenerated from a clone.
  Published output: `eval/results/20261111T141730Z/offline_analysis.md` and `.json`.
- Repeat 1's lane accuracy (0.88), all-three match (0.52) and unknown rate (0.17) are
  reproducible: they are in the per-run table of the `run_eval.py` report above.
- A new `eval/full_run.py` with a key makes new model calls, so its numbers can differ from the
  published run (the model isn't deterministic across calls, and google-genai in the lock file
  is 3.0.0, while the published run used 2.4.0; `docs/prompts-freeze.md`).

**Demo scenario** (no key needed; the mock model is the default):

```powershell
python -m sim.demo_scenario      # 5 devices, 2 runs; state in sim/demo_state/
```

Run 1 assigns patch / retire / unknown / patch / fine, a scripted approver approves, and the
outbox gets email, ticket and calendar records. Between runs the inventory is edited. Run 2
closes the patched and removed devices' tickets, escalates DEV-104 (changed to 7.0.12, still
below the fix 7.0.14: a change is not a fix) and leaves the unknown device's ticket open.
Outward actions are written as JSON to `sim/demo_state/outbox/` (created on the first run).
`python -m sim.demo_scenario --gemini` uses the real API instead (not run for this README).

Step by step, with your own approvals:

```powershell
python -m sim.loop --as-of 2026-11-12 --inventory eval/fixtures/inventory.csv --mock
python -m sim.loop pending
python -m sim.loop approve P-001-DEV-004 --approver approver@example.org
python -m sim.loop metrics
```

(State goes to `sim/state/`, created on the first run; approved actions land in
`sim/state/outbox/`. Both state folders are gitignored. The rule-based mock sends most fixture devices to `unknown`; it is a
loop demo, not a model.)

**Full run with a key** (not run for this README):

```powershell
Copy-Item .env.example .env      # then put GEMINI_API_KEY in .env yourself; never commit it
python eval/full_run.py          # 60 devices × 3 repeats on data/
```

Quota caveat: the published run made about 500 real calls in a day before a 429 naming the
per-day quota stopped the third repeat at 40/60 devices. `eval/full_run.py` stops on that error
by design. The exact daily limit for this model wasn't verified. Runs are sequential and took
about 52 minutes of active time for the first attempt.

## Evaluation summary

From `docs/results-analysis.md` (prompts frozen at tag `prompts-v1` before the run). **Read the
caveats first:** the 60-device inventory is synthetic and was built with hard cases on purpose;
**all 60 ground-truth labels are unverified drafts** (no row has a human reviewer yet). No claim
is made about real-world accuracy or time saved.

| Metric (all 60) | Naive baseline | Deming rep 0 | Deming rep 1 |
|---|---|---|---|
| Product match, strict (headline) | 0.18 | 0.47 | 0.52 |
| Lane accuracy | 0.32 | 0.88 | 0.88 |
| Exposure precision | 0.70 | 1.00 | 0.97 |
| Exposure recall | **0.95** | 0.88 | 0.88 |
| Unknown rate | 0.00 | 0.17 | 0.17 |

- Deming sent 10 devices to `unknown` per repeat: all 4 true unknowns, plus 6 that a human would
  have to look at but didn't need to.
- One unsafe miss: DEV-011 (rep 0), a retire device called `fine` after the Checker misread a
  past support date. One false alarm: DEV-052 (rep 1), a fine device called `patch`.
- Lane agreement between the two complete repeats: 0.95 (57/60).
- **Where the baseline wins:** exposure recall overall (0.95 vs 0.88), in clear_retire (1.00 vs
  0.83 / 0.92) and in messy_name (0.88 vs 0.62 / 0.50), because it calls almost everything
  `patch`; strict product match in critical_dnt (0.50 vs 0.25). Version match is close to a tie
  (0.97 vs 0.98).
- **Post-hoc view (defined after seeing the results, not the headline):** after mapping
  spelling-only aliases of the same product line, applied to both systems, product match is
  0.30 for the baseline and 0.90 / 0.95 for Deming.

Every wrong case is listed and explained in `docs/results-analysis.md`. Candidate fixes are
listed there and **not applied**.

Fifteen of the draft labels were cross-checked blind by a separate AI session (Claude, the same
model family; not human verification): lane agreement 12/15, Cohen's kappa 0.68, with the three
disagreements triaged for a human in `docs/ai-cross-check.md`.

## Limits and honest caveats

- Synthetic inventory; ground-truth labels drafted by an AI from cited sources and not yet
  verified by people.
- Known misses: unparseable firmware strings (DEV-027, DEV-045), past support dates misread
  (DEV-011, DEV-012, DEV-016), gaps in the hand-curated lifecycle data (DEV-028, DEV-052).
- KEV covers only part of what is exploited. Lifecycle data is a hand-curated 30-row file.
- The Verifier confirms the inventory record changed, not that a device is secure.
- In the prototype the rules are enforced by code; in an Agent Designer port they would only be
  requested in prompts.
- Nothing has run in Gemini Enterprise; Sheets access and approved owner emails there are
  unconfirmed. Nothing is actually sent by the prototype.

Details with device ids: `docs/limits.md`.

## Related tools

Deming is not unique. **Eolix** and **Xeol** already cover end-of-life checks. We did not
test them. What Deming tries to add is the closed loop (approval, owner action, next-run
verification of the record), a published evaluation against a naive baseline with every failure
listed, and prompts written to be portable to a no-code platform. Source: `docs/PRD.md`.

## More

- `docs/PRD.md`: condensed spec · `docs/contracts.md`: file formats
- `docs/results-analysis.md`: full evaluation · `docs/limits.md`: limits
- `docs/demo-script.md`: 3-minute demo · `docs/agent-designer-port.md`: port guide
- `docs/ai-and-teamwork.md`: AI use and team roles · `docs/decisions.md`: decisions with sources

Layout: `data/` inventory and feeds · `agents/` prompts · `schemas/` JSON schemas · `sim/`
pipeline and loop · `eval/` baseline, metrics, tests, published runs · `scripts/` tools ·
`docs/` documentation.
