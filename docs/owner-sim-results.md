# Owner-reply simulation results (synthetic data, simulated)

**Read this first.** The owners in this simulation are scripted rules, not people. Each owner address is dealt one fixed behaviour by a seeded random draw. These numbers measure how Deming's closed loop (`sim/loop.py`, unchanged) handles those scripted behaviours on the synthetic 60-device inventory with the rule-based mock model. **They say nothing about how real owners behave, how fast real devices get fixed, or how a real Gemini model would label the devices.** No real device, email system or ticket system was touched; every outward action is a JSON record in a local outbox.

Reproduce (no API key, no network):

```
python scripts/run_owner_sim.py --seeds 1 2 3 4 5 --ticks 21 --write-doc
```

Reproducible byte-for-byte on Python 3.11 (repo venv). Python's `random` docs say seeded sequences may change across Python versions, so other versions may deal behaviours differently.

Setup: `data/inventory.csv` (60 devices), `data/feeds/kev.json`, `data/lifecycle.csv`, mock model (`sim/mock_llm.py`), 21 daily scheduled ticks from 2026-11-12, Settings defaults (reminder after 3 days, escalation after 7). Code: `sim/owner_sim.py`, `scripts/run_owner_sim.py`; tests: `eval/test_owner_sim.py`.

## How it works

Each tick: (1) scripted owners read the outbox emails sent to them on earlier ticks and edit the inventory CSV (the Sheet stand-in); (2) one `run_loop` tick runs Normalizer, Checker, Planner and the Verifier; (3) a scripted human approver records decisions, which the loop executes under its own approval gate.

| Behaviour | What the scripted owner does |
|---|---|
| prompt | Acts on the tick after the first Deming email about the ticket reaches them |
| after_reminder | Ignores the first email; acts on the tick after a reminder reaches them |
| later_window | Replies with a maintenance window 2-14 days out (seeded); acts on that date |
| wrong_person | Replies "not mine, ask `<name>.deputy@example.org`"; a scripted steward edits the Inventory and Tickets `owner_email`; the deputy acts on the first email that reaches them |
| never_replies | Nothing |
| still_vulnerable | Changes the firmware to a version that is not a fix (patch: still below the fixed version on its train; retire/identify: firmware bumped only) |
| removes_device | Deletes the device row |

"Acts": patch = firmware set to the fixed version on its own train; retire = row removed (replaced); identify = name and firmware rewritten to the device's identity in `data/ground_truth.csv` (AI-drafted labels, not human-verified).

Approval policy of the scripted human (`approver@example.org`): approve a device proposal when its recipient is an `@example.org` address; reject a reminder while the owner has an agreed maintenance window still in the future, otherwise approve; no decision on anything else. The runner never approves outside this policy, and the audit re-checks every outbox record against `approvals.csv`.

## Metric definitions

All metrics are recomputed from the state files and the simulator's own `owner_events.csv` (`owner_sim.audit`), not from the loop's in-memory bookkeeping.

- **Closure rate**: closed tickets / tickets opened during the run. Also shown: closure rate over tickets where the scripted owner actually fixed, replaced, identified or removed the device.
- **Escalation correctness**: of tickets that became `escalated`, the share that were overdue (age >= `days_until_escalation`, or past `due`) or carried the `still_vulnerable` flag for a change the simulator knows was not a fix. Also: missed escalations (overdue verify rows that were not escalated).
- **Duplicate tickets** (target 0): `sim.loop.compute_metrics`.
- **Approval violations** (target 0): `compute_metrics` violations + rejected proposals executed + outbox records not approved by the scripted approver + reminders approved inside an agreed window.
- **Closed on wrong evidence** (target 0): a close must pass the contract rule against that run's inventory snapshot (removed; or version changed and >= fixed on its train; or identify with a re-check lane other than unknown) AND the simulator must have recorded an owner fix, replacement, identification or removal for that device.
- **Reroute success**: wrong-person replies where a later Deming email reached the alternate AND the ticket then closed on correct evidence.

## Summary across seeds

| Seed | Tickets | Closed | Closure rate | Closure rate when owner acted | Escalations (correct) | Missed escalations | Duplicates | Approval violations | Closed on wrong evidence | Reroute success | Wrong cases |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 69 | 40 | 58.0% | 71.4% (56 acted) | 31 (31, 100.0%) | 0 | 0 | 0 | 0 | 9/12 (75.0%) | 16 |
| 2 | 65 | 31 | 47.7% | 67.4% (46 acted) | 36 (36, 100.0%) | 0 | 0 | 0 | 0 | 2/4 (50.0%) | 15 |
| 3 | 70 | 37 | 52.9% | 69.8% (53 acted) | 35 (35, 100.0%) | 0 | 0 | 0 | 0 | 5/14 (35.7%) | 16 |
| 4 | 66 | 23 | 34.8% | 59.0% (39 acted) | 45 (45, 100.0%) | 0 | 0 | 0 | 0 | 7/12 (58.3%) | 16 |
| 5 | 67 | 27 | 40.3% | 61.4% (44 acted) | 43 (43, 100.0%) | 0 | 0 | 0 | 0 | 5/9 (55.6%) | 17 |

Target-zero metrics (duplicates, approval violations, closed on wrong evidence) are 0 on every seed.

## Seed 1

Behaviour per owner: `admin-it@example.org` later_window; `branch-johor@example.org` never_replies; `branch-penang@example.org` removes_device; `exams-it@example.org` removes_device; `facilities@example.org` wrong_person; `finance-it@example.org` still_vulnerable; `lab@example.org` never_replies; `library-it@example.org` after_reminder; `netops@example.org` prompt; `research-it@example.org` still_vulnerable; `secops@example.org` after_reminder; `security-office@example.org` later_window; `student-union@example.org` wrong_person; `webteam@example.org` prompt.

| Tick | Date | Opened | Closed | Reminded | Escalated | Open at end | Escalated at end | Closed total | Owner events | Approved | Rejected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-12 | 60 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 60 | 0 |
| 2 | 2026-11-13 | 0 | 1 | 0 | 0 | 59 | 0 | 1 | 7 | 0 | 0 |
| 3 | 2026-11-14 | 0 | 0 | 0 | 0 | 59 | 0 | 1 | 0 | 0 | 0 |
| 4 | 2026-11-15 | 0 | 0 | 58 | 0 | 59 | 0 | 1 | 0 | 58 | 1 |
| 5 | 2026-11-16 | 6 | 23 | 0 | 0 | 42 | 0 | 24 | 48 | 6 | 1 |
| 6 | 2026-11-17 | 0 | 2 | 0 | 0 | 40 | 0 | 26 | 2 | 0 | 1 |
| 7 | 2026-11-18 | 0 | 0 | 31 | 0 | 40 | 0 | 26 | 0 | 31 | 5 |
| 8 | 2026-11-19 | 3 | 5 | 4 | 31 | 7 | 31 | 31 | 8 | 7 | 0 |
| 9 | 2026-11-20 | 0 | 7 | 0 | 0 | 0 | 31 | 38 | 7 | 0 | 0 |
| 10 | 2026-11-21 | 0 | 0 | 0 | 0 | 0 | 31 | 38 | 0 | 0 | 0 |
| 11 | 2026-11-22 | 0 | 1 | 0 | 0 | 0 | 30 | 39 | 1 | 0 | 0 |
| 12 | 2026-11-23 | 0 | 0 | 0 | 0 | 0 | 30 | 39 | 1 | 0 | 0 |
| 13 | 2026-11-24 | 0 | 0 | 0 | 0 | 0 | 30 | 39 | 0 | 0 | 0 |
| 14 | 2026-11-25 | 0 | 1 | 0 | 0 | 0 | 29 | 40 | 1 | 0 | 0 |
| 15 | 2026-11-26 | 0 | 0 | 0 | 0 | 0 | 29 | 40 | 1 | 0 | 0 |
| 16 | 2026-11-27 | 0 | 0 | 0 | 0 | 0 | 29 | 40 | 0 | 0 | 0 |
| 17 | 2026-11-28 | 0 | 0 | 0 | 0 | 0 | 29 | 40 | 0 | 0 | 0 |
| 18 | 2026-11-29 | 0 | 0 | 0 | 0 | 0 | 29 | 40 | 1 | 0 | 0 |
| 19 | 2026-11-30 | 0 | 0 | 0 | 0 | 0 | 29 | 40 | 0 | 0 | 0 |
| 20 | 2026-12-01 | 0 | 0 | 0 | 0 | 0 | 29 | 40 | 0 | 0 | 0 |
| 21 | 2026-12-02 | 0 | 0 | 0 | 0 | 0 | 29 | 40 | 0 | 0 | 0 |

Outcome by the behaviour of the ticket's first owner:

| Behaviour | Tickets | Closed | Escalated | Open |
|---|---|---|---|---|
| after_reminder | 14 | 10 | 4 | 0 |
| later_window | 5 | 2 | 3 | 0 |
| never_replies | 9 | 0 | 9 | 0 |
| prompt | 13 | 7 | 6 | 0 |
| removes_device | 9 | 9 | 0 | 0 |
| rerouted/deputy | 3 | 3 | 0 | 0 |
| still_vulnerable | 4 | 0 | 4 | 0 |
| wrong_person | 12 | 9 | 3 | 0 |

Wrong cases (16):

- T-0001 DEV-001 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 7.4.0. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0010 DEV-010 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0011 DEV-011 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 13.0-92.31. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0014 DEV-014 (identify, owner prompt): owner acted but ticket is escalated. The inventory record changed from version v7.4.1 to 7.4.1. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0015 DEV-015 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 7.0.12. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0018 DEV-018 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version 12.9.2. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0021 DEV-021 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 14.1-43.50. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0025 DEV-025 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 12.5.9. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0028 DEV-028 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0030 DEV-030 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0040 DEV-040 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0045 DEV-045 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record changed from version NS14.1 38.53 to 14.1-38.53. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0050 DEV-050 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 14.1-29.72. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0051 DEV-051 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0052 DEV-052 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 12.5.15. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0053 DEV-053 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.

Reroute failures (3):

- T-0025 DEV-025 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 12.5.9.)
- T-0052 DEV-052 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 12.5.15.)
- T-0053 DEV-053 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version (blank).)

## Seed 2

Behaviour per owner: `admin-it@example.org` still_vulnerable; `branch-johor@example.org` never_replies; `branch-penang@example.org` after_reminder; `exams-it@example.org` after_reminder; `facilities@example.org` prompt; `finance-it@example.org` later_window; `lab@example.org` later_window; `library-it@example.org` still_vulnerable; `netops@example.org` removes_device; `research-it@example.org` prompt; `secops@example.org` never_replies; `security-office@example.org` wrong_person; `student-union@example.org` wrong_person; `webteam@example.org` removes_device.

| Tick | Date | Opened | Closed | Reminded | Escalated | Open at end | Escalated at end | Closed total | Owner events | Approved | Rejected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-12 | 60 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 60 | 0 |
| 2 | 2026-11-13 | 0 | 4 | 0 | 0 | 56 | 0 | 4 | 6 | 0 | 0 |
| 3 | 2026-11-14 | 0 | 0 | 0 | 0 | 56 | 0 | 4 | 0 | 0 | 0 |
| 4 | 2026-11-15 | 0 | 0 | 55 | 0 | 56 | 0 | 4 | 0 | 55 | 1 |
| 5 | 2026-11-16 | 2 | 19 | 0 | 0 | 39 | 0 | 23 | 42 | 2 | 1 |
| 6 | 2026-11-17 | 0 | 2 | 0 | 0 | 37 | 0 | 25 | 2 | 0 | 1 |
| 7 | 2026-11-18 | 0 | 0 | 32 | 0 | 37 | 0 | 25 | 0 | 32 | 5 |
| 8 | 2026-11-19 | 1 | 1 | 0 | 36 | 1 | 36 | 26 | 4 | 1 | 0 |
| 9 | 2026-11-20 | 0 | 1 | 0 | 0 | 0 | 36 | 27 | 1 | 0 | 0 |
| 10 | 2026-11-21 | 0 | 0 | 0 | 0 | 0 | 36 | 27 | 1 | 0 | 0 |
| 11 | 2026-11-22 | 0 | 1 | 0 | 0 | 0 | 35 | 28 | 1 | 0 | 0 |
| 12 | 2026-11-23 | 1 | 1 | 0 | 0 | 1 | 34 | 29 | 1 | 1 | 0 |
| 13 | 2026-11-24 | 0 | 0 | 0 | 0 | 1 | 34 | 29 | 1 | 0 | 0 |
| 14 | 2026-11-25 | 0 | 0 | 0 | 0 | 1 | 34 | 29 | 0 | 0 | 0 |
| 15 | 2026-11-26 | 0 | 0 | 0 | 0 | 1 | 34 | 29 | 0 | 0 | 1 |
| 16 | 2026-11-27 | 0 | 0 | 0 | 0 | 1 | 34 | 29 | 0 | 0 | 1 |
| 17 | 2026-11-28 | 1 | 1 | 0 | 0 | 2 | 33 | 30 | 1 | 1 | 1 |
| 18 | 2026-11-29 | 0 | 0 | 0 | 0 | 2 | 33 | 30 | 1 | 0 | 1 |
| 19 | 2026-11-30 | 0 | 1 | 0 | 0 | 1 | 33 | 31 | 1 | 0 | 0 |
| 20 | 2026-12-01 | 0 | 0 | 0 | 0 | 1 | 33 | 31 | 0 | 0 | 1 |
| 21 | 2026-12-02 | 0 | 0 | 0 | 0 | 1 | 33 | 31 | 0 | 0 | 1 |

Outcome by the behaviour of the ticket's first owner:

| Behaviour | Tickets | Closed | Escalated | Open |
|---|---|---|---|---|
| after_reminder | 9 | 2 | 7 | 0 |
| later_window | 7 | 4 | 2 | 1 |
| never_replies | 13 | 0 | 13 | 0 |
| prompt | 15 | 11 | 4 | 0 |
| removes_device | 11 | 11 | 0 | 0 |
| rerouted/deputy | 1 | 1 | 0 | 0 |
| still_vulnerable | 5 | 0 | 5 | 0 |
| wrong_person | 4 | 2 | 2 | 0 |

Wrong cases (15):

- T-0007 DEV-007 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 7.4.2. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0010 DEV-010 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0013 DEV-013 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0016 DEV-016 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 1.5.1.4. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0017 DEV-017 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0020 DEV-020 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0022 DEV-022 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0023 DEV-023 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0024 DEV-024 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 12.10.3. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0025 DEV-025 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 12.5.9. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0028 DEV-028 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0039 DEV-039 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 9.16.4.19. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0052 DEV-052 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 12.5.15. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0053 DEV-053 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0057 DEV-057 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 18.5.4. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.

Reroute failures (2):

- T-0010 DEV-010 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version (blank).)
- T-0028 DEV-028 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version (blank).)

## Seed 3

Behaviour per owner: `admin-it@example.org` still_vulnerable; `branch-johor@example.org` prompt; `branch-penang@example.org` wrong_person; `exams-it@example.org` removes_device; `facilities@example.org` removes_device; `finance-it@example.org` later_window; `lab@example.org` later_window; `library-it@example.org` after_reminder; `netops@example.org` never_replies; `research-it@example.org` still_vulnerable; `secops@example.org` wrong_person; `security-office@example.org` prompt; `student-union@example.org` after_reminder; `webteam@example.org` never_replies.

| Tick | Date | Opened | Closed | Reminded | Escalated | Open at end | Escalated at end | Closed total | Owner events | Approved | Rejected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-12 | 60 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 60 | 0 |
| 2 | 2026-11-13 | 0 | 5 | 0 | 0 | 55 | 0 | 5 | 8 | 0 | 0 |
| 3 | 2026-11-14 | 0 | 0 | 0 | 0 | 55 | 0 | 5 | 0 | 0 | 0 |
| 4 | 2026-11-15 | 0 | 0 | 54 | 0 | 55 | 0 | 5 | 0 | 54 | 1 |
| 5 | 2026-11-16 | 5 | 18 | 0 | 0 | 42 | 0 | 23 | 43 | 5 | 1 |
| 6 | 2026-11-17 | 0 | 3 | 0 | 0 | 39 | 0 | 26 | 3 | 0 | 1 |
| 7 | 2026-11-18 | 0 | 0 | 32 | 0 | 39 | 0 | 26 | 0 | 32 | 5 |
| 8 | 2026-11-19 | 3 | 3 | 2 | 34 | 5 | 34 | 29 | 12 | 5 | 0 |
| 9 | 2026-11-20 | 0 | 5 | 0 | 0 | 0 | 34 | 34 | 5 | 0 | 0 |
| 10 | 2026-11-21 | 0 | 1 | 0 | 0 | 0 | 33 | 35 | 1 | 0 | 0 |
| 11 | 2026-11-22 | 0 | 0 | 0 | 0 | 0 | 33 | 35 | 0 | 0 | 0 |
| 12 | 2026-11-23 | 0 | 0 | 0 | 0 | 0 | 33 | 35 | 1 | 0 | 0 |
| 13 | 2026-11-24 | 0 | 0 | 0 | 0 | 0 | 33 | 35 | 0 | 0 | 0 |
| 14 | 2026-11-25 | 1 | 1 | 0 | 0 | 1 | 32 | 36 | 1 | 1 | 0 |
| 15 | 2026-11-26 | 0 | 0 | 0 | 0 | 1 | 32 | 36 | 1 | 0 | 0 |
| 16 | 2026-11-27 | 1 | 1 | 0 | 0 | 2 | 31 | 37 | 1 | 1 | 0 |
| 17 | 2026-11-28 | 0 | 0 | 0 | 0 | 2 | 31 | 37 | 2 | 0 | 1 |
| 18 | 2026-11-29 | 0 | 0 | 0 | 0 | 2 | 31 | 37 | 0 | 0 | 1 |
| 19 | 2026-11-30 | 0 | 0 | 0 | 0 | 2 | 31 | 37 | 0 | 0 | 2 |
| 20 | 2026-12-01 | 0 | 0 | 0 | 0 | 2 | 31 | 37 | 0 | 0 | 2 |
| 21 | 2026-12-02 | 0 | 0 | 0 | 1 | 1 | 32 | 37 | 0 | 0 | 1 |

Outcome by the behaviour of the ticket's first owner:

| Behaviour | Tickets | Closed | Escalated | Open |
|---|---|---|---|---|
| after_reminder | 6 | 5 | 1 | 0 |
| later_window | 7 | 3 | 3 | 1 |
| never_replies | 11 | 0 | 11 | 0 |
| prompt | 12 | 8 | 4 | 0 |
| removes_device | 13 | 13 | 0 | 0 |
| rerouted/deputy | 3 | 3 | 0 | 0 |
| still_vulnerable | 4 | 0 | 4 | 0 |
| wrong_person | 14 | 5 | 9 | 0 |

Wrong cases (16):

- T-0002 DEV-002 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 9.1R18. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0007 DEV-007 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 7.4.2. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0010 DEV-010 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0013 DEV-013 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0015 DEV-015 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 7.0.12. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0016 DEV-016 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 1.5.1.4. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0017 DEV-017 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0019 DEV-019 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 1.4.2.22. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0020 DEV-020 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0021 DEV-021 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 14.1-43.50. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0022 DEV-022 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0023 DEV-023 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0028 DEV-028 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0030 DEV-030 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0045 DEV-045 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record changed from version NS14.1 38.53 to 14.1-38.53. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0057 DEV-057 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 18.5.4. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.

Reroute failures (9):

- T-0007 DEV-007 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 7.4.2.)
- T-0016 DEV-016 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 1.5.1.4.)
- T-0017 DEV-017 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 12.11.6.)
- T-0020 DEV-020 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version (blank).)
- T-0021 DEV-021 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 14.1-43.50.)
- T-0023 DEV-023 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version (blank).)
- T-0030 DEV-030 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version (blank).)
- T-0045 DEV-045 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record changed from version NS14.1 38.53 to 14.1-38.53.)
- T-0057 DEV-057 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 18.5.4.)

## Seed 4

Behaviour per owner: `admin-it@example.org` removes_device; `branch-johor@example.org` never_replies; `branch-penang@example.org` after_reminder; `exams-it@example.org` removes_device; `facilities@example.org` still_vulnerable; `finance-it@example.org` later_window; `lab@example.org` wrong_person; `library-it@example.org` later_window; `netops@example.org` wrong_person; `research-it@example.org` prompt; `secops@example.org` still_vulnerable; `security-office@example.org` prompt; `student-union@example.org` after_reminder; `webteam@example.org` never_replies.

| Tick | Date | Opened | Closed | Reminded | Escalated | Open at end | Escalated at end | Closed total | Owner events | Approved | Rejected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-12 | 60 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 60 | 0 |
| 2 | 2026-11-13 | 0 | 1 | 0 | 1 | 58 | 1 | 1 | 7 | 0 | 0 |
| 3 | 2026-11-14 | 0 | 0 | 0 | 0 | 58 | 1 | 1 | 0 | 0 | 0 |
| 4 | 2026-11-15 | 0 | 0 | 57 | 0 | 58 | 1 | 1 | 0 | 57 | 1 |
| 5 | 2026-11-16 | 1 | 7 | 0 | 0 | 52 | 1 | 8 | 45 | 1 | 1 |
| 6 | 2026-11-17 | 0 | 0 | 0 | 0 | 52 | 1 | 8 | 0 | 0 | 1 |
| 7 | 2026-11-18 | 0 | 0 | 46 | 0 | 52 | 1 | 8 | 0 | 46 | 5 |
| 8 | 2026-11-19 | 4 | 7 | 1 | 44 | 5 | 45 | 15 | 12 | 5 | 0 |
| 9 | 2026-11-20 | 0 | 5 | 0 | 0 | 0 | 45 | 20 | 5 | 0 | 0 |
| 10 | 2026-11-21 | 0 | 1 | 0 | 0 | 0 | 44 | 21 | 1 | 0 | 0 |
| 11 | 2026-11-22 | 0 | 0 | 0 | 0 | 0 | 44 | 21 | 0 | 0 | 0 |
| 12 | 2026-11-23 | 0 | 0 | 0 | 0 | 0 | 44 | 21 | 1 | 0 | 0 |
| 13 | 2026-11-24 | 0 | 0 | 0 | 0 | 0 | 44 | 21 | 1 | 0 | 0 |
| 14 | 2026-11-25 | 0 | 0 | 0 | 0 | 0 | 44 | 21 | 0 | 0 | 0 |
| 15 | 2026-11-26 | 1 | 2 | 0 | 0 | 1 | 42 | 23 | 2 | 1 | 0 |
| 16 | 2026-11-27 | 0 | 0 | 0 | 0 | 1 | 42 | 23 | 1 | 0 | 0 |
| 17 | 2026-11-28 | 0 | 0 | 0 | 0 | 1 | 42 | 23 | 0 | 0 | 0 |
| 18 | 2026-11-29 | 0 | 0 | 0 | 0 | 1 | 42 | 23 | 0 | 0 | 1 |
| 19 | 2026-11-30 | 0 | 0 | 0 | 0 | 1 | 42 | 23 | 0 | 0 | 1 |
| 20 | 2026-12-01 | 0 | 0 | 0 | 0 | 1 | 42 | 23 | 0 | 0 | 1 |
| 21 | 2026-12-02 | 0 | 0 | 0 | 0 | 1 | 42 | 23 | 0 | 0 | 1 |

Outcome by the behaviour of the ticket's first owner:

| Behaviour | Tickets | Closed | Escalated | Open |
|---|---|---|---|---|
| after_reminder | 9 | 3 | 6 | 0 |
| later_window | 6 | 3 | 2 | 1 |
| never_replies | 8 | 0 | 8 | 0 |
| prompt | 5 | 2 | 3 | 0 |
| removes_device | 4 | 4 | 0 | 0 |
| rerouted/deputy | 4 | 4 | 0 | 0 |
| still_vulnerable | 18 | 0 | 18 | 0 |
| wrong_person | 12 | 7 | 5 | 0 |

Wrong cases (16):

- T-0001 DEV-001 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 7.4.0. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0007 DEV-007 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 7.4.2. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0010 DEV-010 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0013 DEV-013 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0014 DEV-014 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record changed from version v7.4.1 to 7.4.1. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0015 DEV-015 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version 7.0.12. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0016 DEV-016 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 1.5.1.4. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0017 DEV-017 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0020 DEV-020 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0022 DEV-022 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0023 DEV-023 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0024 DEV-024 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 12.10.3. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0028 DEV-028 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0040 DEV-040 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0051 DEV-051 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0057 DEV-057 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 18.5.4. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.

Reroute failures (5):

- T-0001 DEV-001 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 7.4.0.)
- T-0013 DEV-013 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 12.11.6.)
- T-0014 DEV-014 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record changed from version v7.4.1 to 7.4.1.)
- T-0040 DEV-040 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version (blank).)
- T-0051 DEV-051 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 12.11.6.)

## Seed 5

Behaviour per owner: `admin-it@example.org` after_reminder; `branch-johor@example.org` still_vulnerable; `branch-penang@example.org` prompt; `exams-it@example.org` after_reminder; `facilities@example.org` still_vulnerable; `finance-it@example.org` wrong_person; `lab@example.org` removes_device; `library-it@example.org` prompt; `netops@example.org` later_window; `research-it@example.org` removes_device; `secops@example.org` wrong_person; `security-office@example.org` never_replies; `student-union@example.org` later_window; `webteam@example.org` never_replies.

| Tick | Date | Opened | Closed | Reminded | Escalated | Open at end | Escalated at end | Closed total | Owner events | Approved | Rejected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-12 | 60 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 60 | 0 |
| 2 | 2026-11-13 | 0 | 1 | 0 | 0 | 59 | 0 | 1 | 7 | 0 | 0 |
| 3 | 2026-11-14 | 0 | 0 | 0 | 0 | 59 | 0 | 1 | 0 | 0 | 0 |
| 4 | 2026-11-15 | 0 | 0 | 59 | 0 | 59 | 0 | 1 | 0 | 59 | 0 |
| 5 | 2026-11-16 | 1 | 11 | 0 | 0 | 49 | 0 | 12 | 50 | 1 | 0 |
| 6 | 2026-11-17 | 0 | 1 | 0 | 0 | 48 | 0 | 13 | 1 | 0 | 0 |
| 7 | 2026-11-18 | 0 | 0 | 38 | 0 | 48 | 0 | 13 | 0 | 38 | 10 |
| 8 | 2026-11-19 | 3 | 5 | 0 | 43 | 3 | 43 | 18 | 9 | 3 | 0 |
| 9 | 2026-11-20 | 0 | 4 | 0 | 0 | 0 | 42 | 22 | 5 | 0 | 0 |
| 10 | 2026-11-21 | 0 | 0 | 0 | 0 | 0 | 42 | 22 | 1 | 0 | 0 |
| 11 | 2026-11-22 | 0 | 0 | 0 | 0 | 0 | 42 | 22 | 0 | 0 | 0 |
| 12 | 2026-11-23 | 1 | 1 | 0 | 0 | 1 | 41 | 23 | 2 | 1 | 0 |
| 13 | 2026-11-24 | 1 | 1 | 0 | 0 | 2 | 40 | 24 | 2 | 1 | 0 |
| 14 | 2026-11-25 | 0 | 0 | 0 | 0 | 2 | 40 | 24 | 1 | 0 | 0 |
| 15 | 2026-11-26 | 1 | 2 | 0 | 0 | 2 | 39 | 26 | 2 | 1 | 0 |
| 16 | 2026-11-27 | 0 | 1 | 0 | 0 | 1 | 39 | 27 | 2 | 0 | 0 |
| 17 | 2026-11-28 | 0 | 0 | 0 | 0 | 1 | 39 | 27 | 0 | 0 | 0 |
| 18 | 2026-11-29 | 0 | 0 | 0 | 0 | 1 | 39 | 27 | 1 | 0 | 1 |
| 19 | 2026-11-30 | 0 | 0 | 0 | 0 | 1 | 39 | 27 | 0 | 0 | 1 |
| 20 | 2026-12-01 | 0 | 0 | 0 | 0 | 1 | 39 | 27 | 0 | 0 | 1 |
| 21 | 2026-12-02 | 0 | 0 | 0 | 0 | 1 | 39 | 27 | 0 | 0 | 1 |

Outcome by the behaviour of the ticket's first owner:

| Behaviour | Tickets | Closed | Escalated | Open |
|---|---|---|---|---|
| after_reminder | 4 | 2 | 2 | 0 |
| later_window | 13 | 8 | 4 | 1 |
| never_replies | 5 | 0 | 5 | 0 |
| prompt | 11 | 4 | 7 | 0 |
| removes_device | 5 | 5 | 0 | 0 |
| rerouted/deputy | 3 | 3 | 0 | 0 |
| still_vulnerable | 17 | 0 | 17 | 0 |
| wrong_person | 9 | 5 | 4 | 0 |

Wrong cases (17):

- T-0001 DEV-001 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version 7.4.0. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0007 DEV-007 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 7.4.2. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0014 DEV-014 (identify, owner later_window): owner acted but ticket is escalated. The inventory record changed from version v7.4.1 to 7.4.1. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0015 DEV-015 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 7.0.12. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0016 DEV-016 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 1.5.1.4. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0017 DEV-017 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0018 DEV-018 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 12.9.2. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0020 DEV-020 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0021 DEV-021 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 14.1-43.50. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0022 DEV-022 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0023 DEV-023 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0030 DEV-030 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0039 DEV-039 (identify, owner after_reminder): owner acted but ticket is escalated. The inventory record still shows version 9.16.4.19. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0040 DEV-040 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version (blank). Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0045 DEV-045 (identify, owner wrong_person): owner acted but ticket is escalated. The inventory record changed from version NS14.1 38.53 to 14.1-38.53. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0051 DEV-051 (identify, owner later_window): owner acted but ticket is escalated. The inventory record still shows version 12.11.6. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.
- T-0057 DEV-057 (identify, owner prompt): owner acted but ticket is escalated. The inventory record still shows version 18.5.4. Re-check lane on the last run is unknown: the mock model still cannot match the identity the owner wrote, so the identify ticket stays open.

Reroute failures (4):

- T-0021 DEV-021 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 14.1-43.50.)
- T-0022 DEV-022 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version 12.11.6.)
- T-0030 DEV-030 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record still shows version (blank).)
- T-0045 DEV-045 (identify): a Deming email reached the alternate but the ticket is escalated (The inventory record changed from version NS14.1 38.53 to 14.1-38.53.)

## What this shows, and what it does not

Observed behaviour of the loop under these scripts (each follows from `sim/loop.py` as it is):

- Deming does not read owner replies. A requested later maintenance window does not pause the
  Settings escalation clock, so a window more than 7 days out is escalated first and closed
  later. The scripted approver's only lever is rejecting reminders during the window.
- Identify tickets (lane `unknown`) email the approver, not the owner (rule recipient). An
  owner first hears about an identify ticket from a reminder, so "prompt" owners act on day 4.
- Reminders go to the Tickets tab `owner_email` captured when the ticket opened. A reroute works
  here only because the scripted steward edits the Tickets tab as well as the Inventory; editing
  the Inventory alone would leave reminders going to the wrong person.
- Reminders are only proposed between the reminder and escalation thresholds (days 3-6). After
  escalation no further reminders go out, so an after_reminder owner whose reminder was
  rejected, or a rerouted ticket that escalates first, never gets another email.
- A retire ticket has no fixed version, so a firmware change never closes it (flagged
  `low_evidence`); only removal does. A still-vulnerable patch change escalates at once.
- With the mock model most of the 60 devices come out `unknown`, so most tickets are identify
  tickets; an owner's rewrite to the true identity closes the ticket only if the mock can then
  match it. The mock is not the real model; lane mix with Gemini would differ.

Not measured: real owner behaviour or reply rates; real email, ticket or calendar delivery;
Gemini (no LLM call was made); time to fix on real devices; whether any device is secure (the
Verifier only confirms the inventory record changed); behaviour beyond the simulated days.
