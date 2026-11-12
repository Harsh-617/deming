# Demo script (3 minutes)

The timeline is the PRD's (`docs/PRD.md`, "Demo"). There are two versions: the **prototype demo**
(Python, runs today, no key needed) and the **Agent Designer demo** (only once the license works).
Don't present the prototype as running inside Gemini Enterprise.

## Prototype demo: setup (before you present)

```powershell
.venv\Scripts\Activate.ps1
python -m pytest -q                 # expect 396 passed
python -m sim.demo_scenario         # dry run; state in sim/demo_state/
```

Open these beforehand in an editor or a second terminal:
- `sim/demo_state/inventory.csv`: the "Sheet" (Inventory tab stand-in)
- `sim/demo_state/proposals.csv`: the approval Inbox stand-in
- `sim/demo_state/outbox/`: the email / ticket / calendar records (nothing is sent)
- `sim/demo_state/tickets.csv` and `decision_log.csv`
- `docs/results-analysis.md`: for the evaluation slide

Each run of `python -m sim.demo_scenario` resets the demo folder and replays both days.

## Timeline

| Time | Say / show | Prototype action |
|---|---|---|
| 0:00 | Problem in one sentence with the two numbers **and their caveats**: 43-day median time to fully fix a known-exploited vulnerability (2026 Verizon DBIR, via a secondary summary); 42.5% of vulnerabilities exploited in 2025 hit end-of-life or likely-end-of-life devices (VulnCheck; "likely" is their heuristic). Then the name Deming and the loop: check → plan → approve → verify | Title slide |
| 0:30 | Show the Sheet; say **it is synthetic** | `sim/demo_state/inventory.csv` (5 devices) |
| 0:45 | Reviewer adds a device row (old router) | In the prototype demo the old router (DEV-102, Cisco RV320) is already in the scripted inventory; say so rather than pretend to type it. For a live add, see "Variant" below |
| 1:00 | Run the agent; show lane, evidence and confidence for each device | `python -m sim.demo_scenario` → Run 1: DEV-101 patch, DEV-102 retire, DEV-103 unknown, DEV-104 patch, DEV-105 fine. Show `proposals.csv` |
| 1:25 | Approve; show the email, maintenance window and ticket | The scripted approver approves; show `outbox/P-001-DEV-101.email.json`, `.calendar.json`, `.ticket.json`. Say: recorded, **not sent** |
| 1:50 | Mark the device replaced, run again; ticket closes and the log updates | Same output, Run 2: T-0001 (DEV-101 → 7.0.14) closed, T-0002 (DEV-102 removed) closed, T-0004 (DEV-104 → 7.0.12) **escalated: a change is not a fix**. Show `tickets.csv`, `decision_log.csv` |
| 2:20 | Evaluation summary, one failure, honest limits | Lane accuracy 0.87 vs 0.30 for the naive baseline on 60 **synthetic** devices with **unverified** labels (two T35 labels corrected to retire on 12 Nov; it was 0.88 vs 0.32 before); the baseline wins exposure recall (0.95 vs 0.85). One failure: DEV-011, a retire device called fine because the Checker misread a past date. Limits: `docs/limits.md` |
| 2:45 | Portability close | The prompts and schemas in `agents/` and `schemas/` are plain text for Agent Designer; port guide in `docs/agent-designer-port.md`. Say what has and hasn't been run there |

Words to keep exact:
- "The Verifier confirms the **inventory record** changed, not that the device is secure."
- "These results are on synthetic data; no real-world accuracy or time saved is claimed."
- Don't say Deming is unique or will win (Eolix and Xeol already do end-of-life checks).

### Variant: add the device row live (prototype)

State goes to `sim/state/` (gitignored). Delete that folder to start fresh.

```powershell
python -m sim.loop --inventory <your inventory.csv> --as-of 2026-11-12 --mock
python -m sim.loop pending
python -m sim.loop approve <proposal_id> --approver approver@example.org
# edit sim/state/inventory.csv (bump the version or delete the row), then run again with a later date
python -m sim.loop --as-of 2026-11-13 --mock
```

Tested on 2026-11-11 with `eval/fixtures/inventory.csv`: approved DEV-004's proposal, deleted
its row, and the second run closed T-0001 ("The device no longer appears in the inventory
record"). On that fixture the rule-based mock sends most devices to `unknown`, so rehearse with
your own inventory before showing it; the scripted scenario above is the safe default.

## Agent Designer demo: only once the license works

Not built yet. When the license works, follow `docs/agent-designer-port.md` (sections 1 and 5),
then use the same timeline:
- 0:30 the inventory in Drive (a CSV copy if the Sheets connector isn't available);
- 1:00 a run in Preview or a scheduled run; lanes in the chat;
- 1:25 approve **in the run's chat** (scheduled runs can't email other people unattended);
- 1:50 edit the inventory, run again, show the ticket closing.

Until each step works on the live license, say "the prototype does this; the Agent Designer
build is in progress" rather than showing a mock as the platform.

## Backup-video checklist

- [ ] Record the full prototype demo (both runs) in one take, 3 minutes or less.
- [ ] Terminal font large enough to read at 720p; close notifications and other windows.
- [ ] No `.env`, API key or real email address on screen (owners are `example.org`).
- [ ] Show the "synthetic data" statement on screen at 0:30.
- [ ] Narration uses the exact caveats above (sources for both numbers; Verifier wording).
- [ ] Include one failure (DEV-011) and the baseline-wins line.
- [ ] If an Agent Designer clip is included, it shows a real run on the live license, labelled
      with the date; otherwise leave it out.
- [ ] Export as MP4, check it plays from start to end, upload, test the link while logged out.
- [ ] Keep a local copy on the presenting laptop in case the network fails.
