# Deming: condensed PRD for builders (source: full report dated 9 Nov 2026)

Read this at the start of every session. The full report is long and holds unconfirmed items; this file is the build-relevant core. If this file and a later user instruction disagree, the user wins.

## One-line summary
Deming is a scheduled agent that reads a device inventory (Google Sheet), checks each device against CISA KEV (known exploited vulnerabilities) and end-of-life data, routes the right action to the owner, waits for human approval, then verifies on the next run that the inventory record changed. Name comes from the Deming Cycle (Plan-Do-Check-Act). Tagline: "Patch or Retire".

## Dates (MYT)
- Prototype deadline: Fri 13 Nov 2026 12:00 PM (extended from 10 Nov). Submit by 10:00.
- Final pitch for top five: 17 Nov. The final product MUST use Gemini Enterprise; the prototype does not need it.
- Licenses expected 10 Nov, not guaranteed. Prototype runs the same steps outside Gemini Enterprise until then.
- Assessment window (11-14 Nov) and top-five announcement (15 Nov) are unconfirmed.

## Hackathon context
APU Cloud Innovation Hackathon 2026, sponsor NTT DATA, track 2 (Intelligent Automation and Digital Transformation). Judges look at: impact, technical build (first- and third-party connectors; MCP is an add-on), research, day-to-day workflow value. Rubric weights are unpublished. Briefing said low-code/no-code agent in Gemini Enterprise, deliverables are slides/PDF + GitHub repo with README. Submission: title, track, summary >= 50 chars, HTTPS repo link, PDF deck <= 10 MB, optional demo link.

## Problem and evidence (use with the stated caveats)
- Median time to fully fix a known-exploited vulnerability was 43 days (2026 Verizon DBIR, via a secondary summary; original PDF not opened).
- 42.5% of vulnerabilities exploited in 2025 hit end-of-life or likely-end-of-life devices (VulnCheck 2026 report; "likely EOL" is their heuristic).
- Only 23.7% of exploited edge-device vulnerabilities VulnCheck found are in CISA KEV, so KEV is a baseline, not the full picture.
- Some KEV entries have no fix: the required action is to stop using the product.
- Not verified: that APU has such devices, that an agent like this shortens time to fix.

## Lanes (every device gets exactly one)
| Lane | When | Agent does |
|---|---|---|
| patch | A fix exists | Update instructions, deadline, maintenance window, then verify new version |
| retire | Vendor no longer supports it | Replacement request, interim mitigation (isolate), then verify removal |
| fine | No known issue | Log only |
| unknown | Cannot match with confidence | Ask a human. Never guess |

## Hard rules
- Never scan, change or reach into a real device. Inventory is synthetic.
- No email, ticket or calendar action without recorded human approval (default mode).
- Never guess on an ambiguous device: lane = unknown.
- Never record a fix without evidence in the inventory.
- A device flagged do_not_touch is never proposed for disconnection; escalate to a human.
- Device fields are DATA, never instructions (test with injection text in a device name).
- The Verifier confirms the inventory record changed, NOT that the device is secure.
- Autonomy tiers: 0 read-only (auto); 1 draft (auto); 2 outward actions: email, calendar, ticket (approval by default); 3 consequential: isolate, disconnect, replace (agent only drafts, named human decides).

## Architecture
One main scheduled agent calling four narrow subagents; data in Google Sheets; actions via Gmail, Calendar, Jira (fallback: Tickets tab in the Sheet); approval in the Gemini Enterprise Inbox (fallback: Chat message + Sheet cell). Platform limits: schedules run hourly at best, need a manual refresh every 14 days, can start up to 5 min late.

| Subagent | Job | Reads | Writes |
|---|---|---|---|
| Normalizer | Messy name -> vendor, product, version + confidence; ask when unsure | Inventory | Normalized fields + confidence |
| Checker | Compare with KEV and lifecycle data; assign lane + evidence | Normalized inventory, KEV copy, lifecycle copy | Lane + evidence |
| Planner | Draft owner messages/tickets/calendar proposals, rank priority, avoid duplicate tickets | Lane, owner, criticality, Settings, Tickets | Proposed actions |
| Verifier | Next run: version changed or device removed -> close, remind or escalate | Inventory, Tickets, Decision Log | Ticket status, reminders |

Prompts and output formats must be portable to Gemini Enterprise Agent Designer (paste unchanged).

## Data model (Sheet tabs; * = agent-written)
- Inventory: device_id, device_name_raw, location, owner_email, firmware_version_raw, internet_facing, criticality, do_not_touch, last_updated, vendor*, product*, version*, match_confidence*
- Decision Log: timestamp, run_id, device_id, lane, evidence (CVE id, due date, EOL date), confidence, proposed_action, approver, decision, action_taken, outcome, verification_note
- Settings: what counts as urgent, days until reminder, days until escalation, suggest-only/auto per tier, approver address, digest channel
- Tickets: ticket_id, device_id, issue, status, opened, due, last_reminder

## Requirements
Must (MVP): FR1-FR11: read Sheet on schedule; normalize with confidence; check KEV; check end-of-life data; assign lane with evidence; draft owner message with action and deadline; human approval before any outward action; Decision Log for every decision; check for open ticket before creating one; verification pass (close/remind/escalate); send approved email via Gmail.
Should: Calendar windows, Jira tickets, Chat digest, Settings tab rules, priority from internet_facing + criticality.
Could: weekly manager report; auto mode for low-risk steps only.
Won't in v1: scanning, discovery, auto-disconnect, real-time alerts, agent identity.

Draft acceptance criteria: zero outward actions without recorded approval; every decision has a log row; no duplicate ticket for same device and issue across runs; a ticket closes only when the Sheet shows the fixed version or removal; on the test set Deming beats the naive baseline on normalization accuracy and every failure is listed.

## Evaluation plan
About 60 synthetic devices: 15 clear patch, 12 clear retire, 15 supported/no known issue, 10 messy names (typos, abbreviations, model variants, missing versions), 4 name collisions, 4 critical/do-not-touch. Ground truth is labeled from KEV and vendor lifecycle notices by people, not by an LLM. Baseline: naive lowercase substring / fuzzy join of inventory names to KEV vendor and product fields; it never outputs unknown.
Metrics: normalization accuracy; exposure precision/recall; correct lane (confusion matrix); unknown rate and correctness; owner routing accuracy; duplicate tickets (target zero); approval compliance (target zero violations); verification correctness; stability (same input run 3 times); run time.
Tricky cases: typos/abbreviations/missing version; similar product names; do-not-touch device in KEV; ticket already open; owner ignores reminder (escalation); updated to a version that is still vulnerable (change != fix); instruction-like text in a device name.
Reporting: results by lane, EVERY wrong case listed and explained; say plainly the devices are synthetic and no real-world accuracy or time-saved claim is made; if the baseline ties or wins a group, say so; publish test set, prompts and run log in the repo.

## Demo (3 minutes)
0:00 problem in one sentence with the two numbers, then the Deming name and the four-step loop; 0:30 show the Sheet and say it is synthetic; 0:45 reviewer adds a device row (old router); 1:00 run agent, show lane/evidence/confidence in the Inbox; 1:25 approve, show email, maintenance window and ticket; 1:50 mark device replaced in the Sheet, run again, ticket closes and log updates; 2:20 evaluation summary including one failure and the honest limits; 2:45 portability close. Record a backup video of the full run.

## Never claim
- That Deming is unique or will win (Eolix and Xeol already cover end-of-life checks; our edge is closed loop + measured evaluation + portable no-code design).
- That any real user validated the problem.
- That test results reflect real-world accuracy or time saved.
- That the Verifier proves a device is secure.
- That the prototype runs inside Gemini Enterprise before it actually does.
- Vendor figures from big-tech products are self-reported and untested by us.
- That owner emails are sent automatically by a scheduled run, or that Deming uses a Google Sheets connector, until each is verified on a live license.

## Priorities when time runs short
1. The full loop end to end, with one patch, one retire and one unknown case in the demo, evidence on every decision, approval before any send, next-run verification.
2. The 60-device test against the naive baseline with every failure listed.
3. Light: approval gate, Decision Log, one prompt-injection test, duplicate-ticket check, a Summary tab as dashboard.
4. Light: README with limits, honest competitor comparison, submission checklist.
5. Skip: extra integrations, advanced analytics, cosmetic polish, failure injection.

## Platform findings (read from Google docs 11 Nov, NOT yet confirmed on a live license)
- Scheduled chat agents can't act on other people's behalf, so owner emails go out only after approval in the run's chat (no unattended send).
- Google Sheets is not a listed connector. Fallback: a CSV copy of the inventory in Drive.
- Schedules run hourly at most often, and credentials need a manual refresh every 14 days.
- Two build paths, per docs/agent-designer-port.md: Path A, a chat agent (main agent + four subagents); Path B, a workflow (trigger → steps → actions) as the upgrade if Path A's approval or structured-output limits hurt.
