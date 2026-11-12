"""Run the owner-reply simulator (sim/owner_sim.py) over the 60-device test inventory.

Synthetic data, simulated. Owners are scripted, not people. Mock model only, no API key, no
network. Each seed gets its own state folder under sim/owner_sim_state/seed-<n>/.

    python scripts/run_owner_sim.py                          # seeds 1-5, 21 daily ticks
    python scripts/run_owner_sim.py --seeds 7 --ticks 10
    python scripts/run_owner_sim.py --write-doc              # also rewrite docs/owner-sim-results.md

The doc contains no wall-clock times, so two runs with the same arguments write the same bytes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim import owner_sim  # noqa: E402

DOC = ROOT / "docs" / "owner-sim-results.md"
TARGET_ZERO = ("duplicate_tickets", "approval_violations", "tickets_closed_wrong_evidence")


def _pct(v) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def run(seeds: list[int], ticks: int, root: Path) -> list[dict]:
    out = []
    for seed in seeds:
        folder = root / f"seed-{seed}"
        res = owner_sim.run_sim(seed, ticks, folder)
        a = owner_sim.audit(folder)
        behaviours = {r["owner"]: r["behaviour"] for r in
                      owner_sim.read_rows(folder / "owner_behaviours.csv")}
        out.append(dict(seed=seed, per_tick=res["per_tick"], audit=a, behaviours=behaviours))
        (folder / "owner_sim_audit.json").write_text(json.dumps(a, indent=1), encoding="utf-8")
    return out


def render(results: list[dict], ticks: int) -> str:
    seeds = [r["seed"] for r in results]
    L = []
    w = L.append
    w("# Owner-reply simulation results (synthetic data, simulated)")
    w("")
    w("**Read this first.** The owners in this simulation are scripted rules, not people. Each "
      "owner address is dealt one fixed behaviour by a seeded random draw. These numbers measure "
      "how Deming's closed loop (`sim/loop.py`, unchanged) handles those scripted behaviours on "
      "the synthetic 60-device inventory with the rule-based mock model. **They say nothing about "
      "how real owners behave, how fast real devices get fixed, or how a real Gemini model "
      "would label the devices.** No real device, email system or ticket system was touched; "
      "every outward action is a JSON record in a local outbox.")
    w("")
    w("Reproduce (no API key, no network):")
    w("")
    w("```")
    w(f"python scripts/run_owner_sim.py --seeds {' '.join(map(str, seeds))} --ticks {ticks} --write-doc")
    w("```")
    w("")
    w("Reproducible byte-for-byte on Python 3.11 (repo venv). Python's `random` docs say seeded "
      "sequences may change across Python versions, so other versions may deal behaviours "
      "differently.")
    w("")
    w(f"Setup: `data/inventory.csv` (60 devices), `data/feeds/kev.json`, `data/lifecycle.csv`, "
      f"mock model (`sim/mock_llm.py`), {ticks} daily scheduled ticks from {owner_sim.START}, "
      "Settings defaults (reminder after 3 days, escalation after 7). Code: `sim/owner_sim.py`, "
      "`scripts/run_owner_sim.py`; tests: `eval/test_owner_sim.py`.")
    w("")
    w("## How it works")
    w("")
    w("Each tick: (1) scripted owners read the outbox emails sent to them on earlier ticks and "
      "edit the inventory CSV (the Sheet stand-in); (2) one `run_loop` tick runs Normalizer, "
      "Checker, Planner and the Verifier; (3) a scripted human approver records decisions, "
      "which the loop executes under its own approval gate.")
    w("")
    w("| Behaviour | What the scripted owner does |")
    w("|---|---|")
    w("| prompt | Acts on the tick after the first Deming email about the ticket reaches them |")
    w("| after_reminder | Ignores the first email; acts on the tick after a reminder reaches them |")
    w("| later_window | Replies with a maintenance window 2-14 days out (seeded); acts on that date |")
    w("| wrong_person | Replies \"not mine, ask `<name>.deputy@example.org`\"; a scripted steward "
      "edits the Inventory and Tickets `owner_email`; the deputy acts on the first email that reaches them |")
    w("| never_replies | Nothing |")
    w("| still_vulnerable | Changes the firmware to a version that is not a fix (patch: still below "
      "the fixed version on its train; retire/identify: firmware bumped only) |")
    w("| removes_device | Deletes the device row |")
    w("")
    w("\"Acts\": patch = firmware set to the fixed version on its own train; retire = row removed "
      "(replaced); identify = name and firmware rewritten to the device's identity in "
      "`data/ground_truth.csv` (AI-drafted labels, not human-verified).")
    w("")
    w("Approval policy of the scripted human (`approver@example.org`): approve a device proposal "
      "when its recipient is an `@example.org` address; reject a reminder while the owner has an "
      "agreed maintenance window still in the future, otherwise approve; no decision on anything "
      "else. The runner never approves outside this policy, and the audit re-checks every outbox "
      "record against `approvals.csv`.")
    w("")
    w("## Metric definitions")
    w("")
    w("All metrics are recomputed from the state files and the simulator's own `owner_events.csv` "
      "(`owner_sim.audit`), not from the loop's in-memory bookkeeping.")
    w("")
    w("- **Closure rate**: closed tickets / tickets opened during the run. Also shown: closure "
      "rate over tickets where the scripted owner actually fixed, replaced, identified or "
      "removed the device.")
    w("- **Escalation correctness**: of tickets that became `escalated`, the share that were "
      "overdue (age >= `days_until_escalation`, or past `due`) or carried the `still_vulnerable` "
      "flag for a change the simulator knows was not a fix. Also: missed escalations (overdue "
      "verify rows that were not escalated).")
    w("- **Duplicate tickets** (target 0): `sim.loop.compute_metrics`.")
    w("- **Approval violations** (target 0): `compute_metrics` violations + rejected proposals "
      "executed + outbox records not approved by the scripted approver + reminders approved "
      "inside an agreed window.")
    w("- **Closed on wrong evidence** (target 0): a close must pass the contract rule against "
      "that run's inventory snapshot (removed; or version changed and >= fixed on its train; or "
      "identify with a re-check lane other than unknown) AND the simulator must have recorded "
      "an owner fix, replacement, identification or removal for that device.")
    w("- **Reroute success**: wrong-person replies where a later Deming email reached the "
      "alternate AND the ticket then closed on correct evidence.")
    w("")
    w("## Summary across seeds")
    w("")
    w("| Seed | Tickets | Closed | Closure rate | Closure rate when owner acted | Escalations (correct) | Missed escalations | Duplicates | Approval violations | Closed on wrong evidence | Reroute success | Wrong cases |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        a = r["audit"]
        w(f"| {r['seed']} | {a['tickets_opened']} | {a['tickets_closed']} | {_pct(a['closure_rate'])} "
          f"| {_pct(a['closure_rate_when_owner_acted'])} ({a['owner_acted_tickets']} acted) "
          f"| {a['escalations']} ({a['escalations_correct']}, {_pct(a['escalation_correctness'])}) "
          f"| {len(a['missed_escalations'])} | {a['duplicate_tickets']} | {a['approval_violations']} "
          f"| {a['tickets_closed_wrong_evidence']} "
          f"| {a['reroute_success']}/{a['reroutes']} ({_pct(a['reroute_success_rate'])}) "
          f"| {len(a['wrong_cases'])} |")
    w("")
    fails = [(r["seed"], k) for r in results for k in TARGET_ZERO if r["audit"][k] != 0]
    if fails:
        w("**Target-zero metrics NOT met:** " + ", ".join(f"seed {s} {k}" for s, k in fails) + ".")
    else:
        w("Target-zero metrics (duplicates, approval violations, closed on wrong evidence) are 0 "
          "on every seed.")
    w("")
    for r in results:
        a = r["audit"]
        w(f"## Seed {r['seed']}")
        w("")
        w("Behaviour per owner: " + "; ".join(f"`{o}` {b}" for o, b in sorted(r["behaviours"].items())) + ".")
        w("")
        w("| Tick | Date | Opened | Closed | Reminded | Escalated | Open at end | Escalated at end | Closed total | Owner events | Approved | Rejected |")
        w("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for t in r["per_tick"]:
            w(f"| {t['tick']} | {t['as_of']} | {t['opened']} | {t['closed']} | {t['reminded']} "
              f"| {t['escalated']} | {t['open_end']} | {t['escalated_end']} | {t['closed_total']} "
              f"| {t['owner_events']} | {t['approved']} | {t['rejected']} |")
        w("")
        w("Outcome by the behaviour of the ticket's first owner:")
        w("")
        w("| Behaviour | Tickets | Closed | Escalated | Open |")
        w("|---|---|---|---|---|")
        for b, d in sorted(a["by_behaviour"].items()):
            w(f"| {b} | {d['tickets']} | {d['closed']} | {d['escalated']} | {d['open']} |")
        w("")
        w(f"Wrong cases ({len(a['wrong_cases'])}):")
        w("")
        for x in a["wrong_cases"] or ["none"]:
            w(f"- {x}")
        w("")
        if a["reroute_failures"]:
            w(f"Reroute failures ({len(a['reroute_failures'])}):")
            w("")
            for x in a["reroute_failures"]:
                w(f"- {x}")
            w("")
        if a["notes"]:
            w(f"Owner could not act ({len(a['notes'])}):")
            w("")
            for x in a["notes"]:
                w(f"- {x}")
            w("")
    w(FINDINGS)
    return "\n".join(L).rstrip() + "\n"


FINDINGS = """## What this shows, and what it does not

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
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--ticks", type=int, default=21)
    p.add_argument("--state-root", type=Path, default=owner_sim.DEFAULT_ROOT)
    p.add_argument("--write-doc", action="store_true")
    p.add_argument("--doc", type=Path, default=DOC)
    args = p.parse_args(argv)
    results = run(args.seeds, args.ticks, args.state_root)
    for r in results:
        print(f"== seed {r['seed']} (synthetic, simulated; owners are scripted)")
        for t in r["per_tick"]:
            print(f"  tick {t['tick']:>2} {t['as_of']}: opened {t['opened']}, closed {t['closed']}, "
                  f"reminded {t['reminded']}, escalated {t['escalated']}")
        a = r["audit"]
        print(f"  closure {_pct(a['closure_rate'])}, escalation correctness "
              f"{_pct(a['escalation_correctness'])}, duplicates {a['duplicate_tickets']}, "
              f"approval violations {a['approval_violations']}, closed on wrong evidence "
              f"{a['tickets_closed_wrong_evidence']}, reroute {a['reroute_success']}/{a['reroutes']}, "
              f"wrong cases {len(a['wrong_cases'])}")
    if args.write_doc:
        args.doc.write_text(render(results, args.ticks), encoding="utf-8", newline="\n")
        print(f"wrote {args.doc}")
    bad = any(r["audit"][k] != 0 for r in results for k in TARGET_ZERO)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
