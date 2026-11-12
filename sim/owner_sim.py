"""Owner-reply simulator on top of the closed loop (sim/loop.py). Synthetic data, simulated.

The owners here are SCRIPTED, not people. Each owner address gets one fixed behaviour from a
seeded draw; the results say nothing about how real owners behave.

Behaviours (per owner email):
    prompt          acts on the first tick after a Deming email about the ticket reaches them
    after_reminder  ignores the first email; acts on the tick after a REMINDER reaches them
    later_window    replies "do it in my maintenance window on <date>"; acts on that date
    wrong_person    replies "not mine, ask <alternate>"; a scripted steward reroutes the device
                    (Inventory owner_email AND the Tickets tab owner_email) to the alternate,
                    who acts on the first Deming email that reaches the alternate
    never_replies   does nothing, ever
    still_vulnerable updates the inventory to a CHANGED version that is not a fix (patch: still
                    below the fixed version on its train; retire/identify: firmware bumped only)
    removes_device  deletes the device's inventory row

"Acts" means: patch -> firmware set to the fixed version on its own train; retire -> device
row removed (replaced); identify -> device name and firmware rewritten to the device's true
identity from data/ground_truth.csv (the owner knows their own device). Nothing else changes.

How a tick works (`run_sim`):
    1. Owners read the outbox records written on EARLIER ticks (emails to or cc them) and do
       their scripted action on the state's inventory.csv (the Sheet stand-in). Every reply and
       edit is logged in owner_events.csv (the simulator's own truth, used by the audit).
    2. sim.loop.run_loop runs one scheduled tick (mock model) with a scripted human approver
       (`PolicyApprover`, policy below). The loop itself is unchanged and is not bypassed.

Approval policy of the scripted human (`PolicyApprover`, name approver@example.org):
    - device proposal: approve when `to` is an @example.org address, else leave pending;
    - reminder: reject while the ticket's owner has an agreed maintenance window that is still
      in the future (the human knows the owner asked to wait); otherwise approve;
    - anything else: no decision (stays pending).
The approver only records decisions; sim.loop executes them under its own approval gate.

The audit (`audit`) reads only the state files plus owner_events.csv, never the loop's
bookkeeping in memory.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import config, guards
from .loop import (AGENT_COLUMNS, INVENTORY_COLUMNS, State, _train_compare, compute_metrics,
                   read_rows, run_loop, write_rows)

BEHAVIOURS = ("prompt", "after_reminder", "later_window", "wrong_person", "never_replies",
              "still_vulnerable", "removes_device")
APPROVER = "approver@example.org"
MARKER = ".deming_owner_sim_state"
DEFAULT_ROOT = config.ROOT / "sim" / "owner_sim_state"
DEFAULT_INVENTORY = config.ROOT / "data" / "inventory.csv"
DEFAULT_TRUTH = config.ROOT / "data" / "ground_truth.csv"
DEFAULT_KEV = config.ROOT / "data" / "feeds" / "kev.json"
DEFAULT_LIFECYCLE = config.ROOT / "data" / "lifecycle.csv"
START = "2026-11-12"
EVENT_COLUMNS = ["date", "tick", "owner", "behaviour", "device_id", "ticket_id", "issue",
                 "event", "detail"]
TICK_COLUMNS = ["seed", "tick", "as_of", "opened", "closed", "reminded", "escalated",
                "open_end", "escalated_end", "closed_total", "owner_events", "proposals",
                "approved", "rejected"]
WINDOW_DAYS = (2, 14)  # later_window: window = reply date + randint(*WINDOW_DAYS)


def alternate_for(owner: str) -> str:
    local, _, domain = owner.partition("@")
    return f"{local}.deputy@{domain}"


def assign_behaviours(owners: list[str], seed: int) -> dict[str, str]:
    """Seeded, deterministic. Owners are shuffled, then dealt behaviours round-robin, so every
    behaviour appears at least once when there are >= 7 owners."""
    order = sorted(set(owners))
    random.Random(seed).shuffle(order)
    return {o: BEHAVIOURS[i % len(BEHAVIOURS)] for i, o in enumerate(order)}


# ---- inventory edits the owners make ----------------------------------------------------------
_LAST_INT = re.compile(r"(\d+)(?!.*\d)")


def bump_version(v: str) -> str:
    """Increment the last integer in the string (`9.22.1.1` -> `9.22.1.2`); append `.1` if none."""
    v = (v or "").strip()
    if not _LAST_INT.search(v):
        return (v + ".1") if v else "1.0"
    return _LAST_INT.sub(lambda m: str(int(m.group(1)) + 1), v, count=1)


def fixed_target(ticket: dict) -> str | None:
    """The fixed version on the firmware's own train (the highest one there), else None."""
    train, why = guards.select_train_fixes(ticket.get("fixed_version"), ticket["firmware_at_open"])
    if why or not train:
        return None
    best = train[0]
    for f in train[1:]:
        if (guards.compare_versions(f, best) or 0) > 0:
            best = f
    return best


def not_fix_version(ticket: dict) -> str:
    """A changed firmware that is NOT a fix. For patch tickets it is checked to compare below
    the fixed version on its train; if bumping can't stay below, the result does not parse
    (so the Verifier can't close on it either)."""
    cur = ticket["firmware_at_open"]
    new = bump_version(cur)
    if ticket["issue"] == "patch" and ticket.get("fixed_version"):
        cmp, _ = _train_compare(new, ticket["fixed_version"])
        if cmp is None or cmp >= 0:
            new = f"{cur} (vendor hotfix pending)"  # changed, does not parse
    return new


# ---- simulator state ----------------------------------------------------------------------------
@dataclass
class OwnerSim:
    seed: int
    behaviours: dict[str, str]
    truth: dict[str, dict]
    windows: dict[str, str] = field(default_factory=dict)       # ticket_id -> agreed window date
    done: set = field(default_factory=set)                       # ticket_ids the owner handled
    replied: set = field(default_factory=set)                    # ticket_ids with a reply logged
    rerouted: dict[str, str] = field(default_factory=dict)       # ticket_id -> alternate
    events: list[dict] = field(default_factory=list)

    def behaviour(self, owner: str) -> str:
        if owner in self.rerouted.values() or owner.endswith(".deputy@example.org"):
            return "prompt"  # an alternate acts on the first email that reaches them
        return self.behaviours.get(owner, "never_replies")


def _received(state: State, today: str) -> dict[str, list[dict]]:
    """ticket_id -> outbox emails about it delivered before today, oldest first."""
    by_pid = {p["proposal_id"]: p for p in state.proposals}
    out: dict[str, list[dict]] = {}
    for path in sorted(state.outbox.glob("*.email.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("executed_on", "9999") >= today:
            continue
        p = by_pid.get(rec["proposal_id"])
        if p is None or not p.get("ticket_id"):
            continue
        rec["kind_of_proposal"] = p["kind"]
        out.setdefault(p["ticket_id"], []).append(rec)
    for v in out.values():
        v.sort(key=lambda r: (r["executed_on"], r["proposal_id"]))
    return out


def _to(rec: dict) -> set[str]:
    return {x.strip().casefold() for x in (rec.get("to", ""), rec.get("cc", "")) if x.strip()}


def owners_act(sim: OwnerSim, state: State, today: str, tick: int) -> int:
    """Step 1 of a tick. Returns the number of owner events logged."""
    inv_path = state.root / "inventory.csv"
    inv = read_rows(inv_path)
    by_id = {r["device_id"]: r for r in inv}
    received = _received(state, today)
    removed: set[str] = set()
    n0 = len(sim.events)

    def log(owner, beh, t, event, detail=""):
        sim.events.append(dict(date=today, tick=tick, owner=owner, behaviour=beh,
                               device_id=t["device_id"], ticket_id=t["ticket_id"],
                               issue=t["issue"], event=event, detail=detail))

    def act(owner, beh, t):
        dev = by_id.get(t["device_id"])
        if dev is None:
            return
        if t["issue"] == "patch":
            target = fixed_target(t)
            if target is None:
                log(owner, beh, t, "cannot_act", "no fixed version on this train")
                return
            dev.update(firmware_version_raw=target, last_updated=today)
            log(owner, beh, t, "fixed", f"firmware -> {target}")
        elif t["issue"] == "retire":
            removed.add(t["device_id"])
            log(owner, beh, t, "replaced", "device row removed (replaced)")
        else:  # identify
            g = sim.truth.get(t["device_id"], {})
            if not g.get("vendor"):
                log(owner, beh, t, "cannot_act", "owner does not know the product either")
                return
            dev.update(device_name_raw=f"{g['vendor']} {g['product']}", last_updated=today,
                       firmware_version_raw=g.get("version") or dev["firmware_version_raw"])
            log(owner, beh, t, "identified", f"name -> {g['vendor']} {g['product']}; "
                f"firmware -> {dev['firmware_version_raw'] or '(blank)'}")
        sim.done.add(t["ticket_id"])

    for t in state.open_tickets():
        tid = t["ticket_id"]
        if tid in sim.done or t["device_id"] not in by_id:
            continue
        owner = t["owner_email"]
        beh = sim.behaviour(owner)
        mails = [m for m in received.get(tid, []) if owner.casefold() in _to(m)]
        reminders = [m for m in mails if m["kind_of_proposal"] == "reminder"]
        if beh == "never_replies" or not mails:
            continue
        if beh == "prompt":
            act(owner, beh, t)
        elif beh == "after_reminder":
            if reminders:
                act(owner, beh, t)
        elif beh == "later_window":
            if tid not in sim.windows:
                rng = random.Random(f"{sim.seed}|{tid}")
                win = (dt.date.fromisoformat(today)
                       + dt.timedelta(days=rng.randint(*WINDOW_DAYS))).isoformat()
                sim.windows[tid] = win
                log(owner, beh, t, "reply_later_window", f"window {win}")
            if today >= sim.windows[tid]:
                act(owner, beh, t)
        elif beh == "wrong_person":
            if tid not in sim.rerouted:
                alt = alternate_for(owner)
                sim.rerouted[tid] = alt
                log(owner, beh, t, "reply_wrong_person", f"alternate {alt}")
                # The scripted steward edits the Sheet: Inventory and Tickets tabs.
                by_id[t["device_id"]]["owner_email"] = alt
                t["owner_email"] = alt
                sim.events[-1]["detail"] += "; steward rerouted Inventory + Tickets owner_email"
        elif beh == "still_vulnerable":
            dev = by_id[t["device_id"]]
            new = not_fix_version(t)
            dev.update(firmware_version_raw=new, last_updated=today)
            log(owner, beh, t, "changed_not_fixed", f"firmware {t['firmware_at_open']} -> {new}")
            sim.done.add(tid)
        elif beh == "removes_device":
            removed.add(t["device_id"])
            log(owner, beh, t, "removed", "device row removed")
            sim.done.add(tid)
    # A removed device's other tickets are handled too (the device is gone).
    inv = [r for r in inv if r["device_id"] not in removed]
    write_rows(inv_path, INVENTORY_COLUMNS + AGENT_COLUMNS, inv)
    state.save()  # the steward's Tickets-tab edits
    return len(sim.events) - n0


@dataclass
class PolicyApprover:
    """The scripted human approver. Policy in the module docstring. Never approves blindly."""
    sim: OwnerSim
    today: str = ""
    name: str = APPROVER
    decisions: list = field(default_factory=list)

    def __call__(self, proposals: list[dict]) -> dict[str, str]:
        out = {}
        for p in proposals:
            if p["kind"] == "device":
                if p["to"].strip().lower().endswith("@example.org"):
                    out[p["proposal_id"]] = "approved"
            elif p["kind"] == "reminder":
                waiting = (p["ticket_id"] in self.sim.windows
                           and self.sim.windows[p["ticket_id"]] > self.today)
                out[p["proposal_id"]] = "rejected" if waiting else "approved"
        self.decisions += [(self.today, k, v) for k, v in out.items()]
        return out


# ---- running --------------------------------------------------------------------------------------
def fresh_root(root: Path, inventory: Path) -> State:
    """Recreate a seed folder. Only deletes a folder this module created (marker file)."""
    if root.exists():
        if not (root / MARKER).exists():
            raise SystemExit(f"{root} exists and is not an owner-sim state folder; not deleting it")
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / MARKER).write_text("created by sim/owner_sim.py\n", encoding="utf-8")
    rows = read_rows(inventory)
    write_rows(root / "inventory.csv", INVENTORY_COLUMNS, rows)
    return State(root)


def _snap(state: State) -> dict[str, str]:
    return {t["ticket_id"]: t["status"] for t in state.tickets}


def run_sim(seed: int, ticks: int, root: Path, *, inventory: Path = DEFAULT_INVENTORY,
            truth: Path = DEFAULT_TRUTH, kev: Path = DEFAULT_KEV,
            lifecycle: Path = DEFAULT_LIFECYCLE, start: str = START,
            behaviours: dict[str, str] | None = None) -> dict:
    """Run `ticks` daily scheduled ticks. Returns {per_tick, sim, state}.
    `behaviours` (owner -> behaviour) overrides the seeded draw; tests use it."""
    state = fresh_root(root, inventory)
    owners = [r["owner_email"] for r in read_rows(inventory)]
    sim = OwnerSim(seed, behaviours or assign_behaviours(owners, seed),
                   {r["device_id"]: r for r in read_rows(truth)})
    approver = PolicyApprover(sim)
    per_tick = []
    for i in range(ticks):
        today = (dt.date.fromisoformat(start) + dt.timedelta(days=i)).isoformat()
        n_events = owners_act(sim, state, today, i + 1)
        state.load()
        before = _snap(state)
        out_before = {p.name for p in state.outbox.glob("*.json")}
        approver.today = today
        rep = run_loop(state, as_of=today, now=f"{today}T01:00:00Z", mock=True,
                       approver=approver, kev_path=kev, lifecycle_path=lifecycle,
                       write_metrics=False)
        after = _snap(state)
        new_out = {p.name for p in state.outbox.glob("*.json")} - out_before
        reminders = {p["proposal_id"] for p in state.proposals if p["kind"] == "reminder"}
        dec_today = [d for d in approver.decisions if d[0] == today]
        per_tick.append(dict(
            seed=seed, tick=i + 1, as_of=today,
            opened=sum(1 for t in after if t not in before),
            closed=sum(1 for t, s in after.items() if s == "closed" and before.get(t) != "closed"),
            reminded=sum(1 for n in new_out if n.endswith(".email.json")
                         and n.split(".")[0] in reminders),
            escalated=sum(1 for t, s in after.items()
                          if s == "escalated" and before.get(t) != "escalated"),
            open_end=sum(s == "open" for s in after.values()),
            escalated_end=sum(s == "escalated" for s in after.values()),
            closed_total=sum(s == "closed" for s in after.values()),
            owner_events=n_events, proposals=len(rep.proposals),
            approved=sum(d[2] == "approved" for d in dec_today),
            rejected=sum(d[2] == "rejected" for d in dec_today)))
    write_rows(root / "owner_events.csv", EVENT_COLUMNS, sim.events)
    write_rows(root / "owner_behaviours.csv", ["owner", "behaviour", "alternate"],
               [dict(owner=o, behaviour=b,
                     alternate=alternate_for(o) if b == "wrong_person" else "")
                for o, b in sorted(sim.behaviours.items())])
    write_rows(root / "ticks.csv", TICK_COLUMNS, per_tick)
    return dict(per_tick=per_tick, sim=sim, state=state)


# ---- audit (state files + owner_events.csv only) -----------------------------------------------------
def _run_dates(state: State) -> dict[str, str]:
    return {r["run_id"]: r["as_of"] for r in state.runs}


def _snapshot(state: State, run_id: str) -> dict[str, dict]:
    return {r["device_id"]: r for r in read_rows(state.root / "runs" / run_id /
                                                   "inventory_snapshot.csv")}


def _lane_on(state: State, run_id: str, did: str) -> str | None:
    for r in read_rows(state.root / "runs" / run_id / "deming.csv"):
        if r["device_id"] == did:
            return r["lane"]
    return None


def audit(root: Path) -> dict:
    """Metrics and every wrong case, recomputed from the files in `root`."""
    state = State(root)
    events = read_rows(root / "owner_events.csv")
    beh = {r["owner"]: r["behaviour"] for r in read_rows(root / "owner_behaviours.csv")}
    settings = state.settings
    dates = _run_dates(state)
    verify = [r for r in state.decision_log if r["proposed_action"] == "verify"]
    ev_by_ticket: dict[str, list[dict]] = {}
    for e in events:
        ev_by_ticket.setdefault(e["ticket_id"], []).append(e)
    wrong: list[str] = []
    notes: list[str] = []

    # Closed on wrong evidence: contract rule against the run's own snapshot, AND the
    # simulator's truth (the owner must have fixed, replaced, identified or removed it).
    closed_wrong = []
    for r in verify:
        if r["decision"] != "close":
            continue
        t = next(x for x in state.tickets if x["ticket_id"] == r["ticket_id"])
        snap = _snapshot(state, r["run_id"])
        dev = snap.get(t["device_id"])
        ok_rule, why = False, ""
        if dev is None:
            ok_rule = True
        elif t["issue"] == "identify":
            lane = _lane_on(state, r["run_id"], t["device_id"])
            ok_rule, why = lane not in (None, "unknown"), f"re-check lane {lane}"
        else:
            cur = dev["firmware_version_raw"]
            fixed = t["fixed_version"]
            if cur.casefold() != t["firmware_at_open"].casefold() and fixed:
                cmp, _ = _train_compare(cur, fixed)
                ok_rule, why = cmp is not None and cmp >= 0, f"{cur} vs fixed {fixed}"
            else:
                why = "no version change or no fixed version"
        did_events = {e["event"] for e in ev_by_ticket.get(t["ticket_id"], [])
                      if e["date"] <= dates[r["run_id"]]}
        # Another ticket's owner action on the same device also counts (e.g. replaced).
        did_events |= {e["event"] for e in events if e["device_id"] == t["device_id"]
                       and e["date"] <= dates[r["run_id"]]}
        ok_truth = bool(did_events & {"fixed", "replaced", "identified", "removed"})
        if dev is not None and "changed_not_fixed" in did_events and t["issue"] != "identify":
            ok_truth = ok_truth and bool(did_events & {"fixed", "replaced"})
        if not (ok_rule and ok_truth):
            closed_wrong.append(t["ticket_id"])
            wrong.append(f"{t['ticket_id']} {t['device_id']} ({t['issue']}) closed on "
                         f"{dates[r['run_id']]} on wrong evidence: rule_ok={ok_rule} ({why}), "
                         f"owner events={sorted(did_events) or 'none'}")

    # Escalation correctness: every transition to escalated must be overdue (age >= the
    # escalation setting, or past due) or a flagged still-vulnerable change the owner made.
    esc_rows, esc_ok, esc_bad = [], 0, []
    seen = set()
    for r in verify:
        if r["decision"] != "escalate" or r["ticket_id"] in seen:
            continue
        seen.add(r["ticket_id"])
        t = next(x for x in state.tickets if x["ticket_id"] == r["ticket_id"])
        day = dt.date.fromisoformat(dates[r["run_id"]])
        overdue = (day >= dt.date.fromisoformat(t["opened"])
                   + dt.timedelta(days=settings["days_until_escalation"])
                   or (t["due"] and day > dt.date.fromisoformat(t["due"])))
        sv_flag = "still_vulnerable" in r["notes"]
        sv_truth = any(e["event"] == "changed_not_fixed" and e["date"] <= dates[r["run_id"]]
                       for e in ev_by_ticket.get(t["ticket_id"], []))
        ok = bool(overdue) or (sv_flag and sv_truth)
        esc_rows.append(t["ticket_id"])
        if ok:
            esc_ok += 1
        else:
            esc_bad.append(t["ticket_id"])
            wrong.append(f"{t['ticket_id']} {t['device_id']} escalated on {day} without being "
                         f"overdue (opened {t['opened']}) or a confirmed still-vulnerable change")
    # Missed escalations: overdue on a run, still open, not escalated.
    missed = []
    for r in verify:
        t = next(x for x in state.tickets if x["ticket_id"] == r["ticket_id"])
        day = dt.date.fromisoformat(dates[r["run_id"]])
        if (r["decision"] in ("keep_open", "remind")
                and day >= dt.date.fromisoformat(t["opened"])
                + dt.timedelta(days=settings["days_until_escalation"])):
            missed.append(f"{t['ticket_id']}@{day}")
    for m in missed:
        wrong.append(f"{m}: overdue but not escalated")

    # Loop-level checks reused from sim.loop.compute_metrics.
    m = compute_metrics(state)
    for d in m["approval_compliance"]["details"]:
        wrong.append(f"approval violation: {d}")
    for tid in m["duplicate_tickets"]["ids"]:
        wrong.append(f"duplicate ticket {tid}")
    # Extra approval check: every outbox record's approver is the scripted human, and no
    # reminder was sent to a ticket while its agreed window was still in the future.
    approvals = {a["proposal_id"]: a for a in state.approvals}
    extra_viol = []
    for path in sorted(state.outbox.glob("*.json")):
        pid = path.name.split(".")[0]
        a = approvals.get(pid)
        if a is None or a["approver"] != APPROVER or a["decision"] != "approved":
            extra_viol.append(f"{path.name}: not approved by {APPROVER}")
    # ticket_id -> (date the owner asked, window date): a breach is an approval on/after the
    # ask and before the window.
    windows = {e["ticket_id"]: (e["date"], e["detail"].split()[-1]) for e in events
               if e["event"] == "reply_later_window"}
    for p in state.proposals:
        w = windows.get(p["ticket_id"])
        if (p["kind"] == "reminder" and p["status"] == "approved" and w
                and w[0] <= p["decided_at"][:10] < w[1]):
            extra_viol.append(f"{p['proposal_id']}: reminder approved inside an agreed window "
                              "(policy breach)")
    wrong += [f"approval policy: {x}" for x in extra_viol]

    # Reroute success: a later Deming email reached the alternate AND the ticket then closed
    # on correct evidence.
    by_pid = {p["proposal_id"]: p for p in state.proposals}
    reroutes = [e for e in events if e["event"] == "reply_wrong_person"]
    rr_ok, rr_fail = 0, []
    for e in reroutes:
        alt = e["detail"].split()[1].rstrip(";")
        reached = False
        for path in state.outbox.glob("*.email.json"):
            rec = json.loads(path.read_text(encoding="utf-8"))
            p = by_pid.get(rec["proposal_id"])
            if (p and p["ticket_id"] == e["ticket_id"] and rec["executed_on"] >= e["date"]
                    and alt in _to(rec)):
                reached = True
        t = next(x for x in state.tickets if x["ticket_id"] == e["ticket_id"])
        closed_ok = t["status"] == "closed" and t["ticket_id"] not in closed_wrong
        if reached and closed_ok:
            rr_ok += 1
        else:
            why = ("no Deming email reached the alternate" if not reached else
                   f"a Deming email reached the alternate but the ticket is {t['status']}" +
                   (f" ({t['last_note']})" if t["status"] != "closed" else ""))
            rr_fail.append(f"{t['ticket_id']} {t['device_id']} ({t['issue']}): {why}")

    # Per-behaviour expectations -> every ticket whose outcome differs is listed.
    outcome_wrong = []
    for t in state.tickets:
        evs = ev_by_ticket.get(t["ticket_id"], [])
        first_owner = next((e["owner"] for e in evs), t["owner_email"])
        b = beh.get(first_owner) or ("prompt" if first_owner.endswith(".deputy@example.org")
                                      else "never_replies")
        kinds = {e["event"] for e in evs}
        if t["status"] == "closed":
            continue
        if kinds & {"fixed", "replaced", "identified", "removed"}:
            why = t["last_note"]
            if t["issue"] == "identify":
                lane = _lane_on(state, state.runs[-1]["run_id"], t["device_id"])
                why += (f" Re-check lane on the last run is {lane}: the mock model still cannot "
                        "match the identity the owner wrote, so the identify ticket stays open.")
            outcome_wrong.append(f"{t['ticket_id']} {t['device_id']} ({t['issue']}, owner "
                                 f"{b}): owner acted but ticket is {t['status']}. {why}")
        elif "cannot_act" in kinds:
            notes.append(f"{t['ticket_id']} {t['device_id']}: owner could not act "
                         f"({next(e['detail'] for e in evs if e['event'] == 'cannot_act')})")
    wrong += outcome_wrong

    opened = len(state.tickets)
    closed = sum(t["status"] == "closed" for t in state.tickets)
    acted = {e["ticket_id"] for e in events if e["event"] in ("fixed", "replaced", "identified", "removed")}
    closed_acted = sum(1 for t in state.tickets if t["ticket_id"] in acted and t["status"] == "closed")
    by_beh: dict[str, dict] = {}
    for t in state.tickets:
        evs = ev_by_ticket.get(t["ticket_id"], [])
        b = beh.get(next((e["owner"] for e in evs), t["owner_email"]), "rerouted/deputy")
        d = by_beh.setdefault(b, dict(tickets=0, closed=0, escalated=0, open=0))
        d["tickets"] += 1
        d[t["status"]] += 1
    return dict(
        tickets_opened=opened, tickets_closed=closed,
        closure_rate=None if not opened else round(closed / opened, 4),
        closure_rate_when_owner_acted=None if not acted else round(closed_acted / len(acted), 4),
        owner_acted_tickets=len(acted),
        escalations=len(esc_rows), escalations_correct=esc_ok,
        escalation_correctness=None if not esc_rows else round(esc_ok / len(esc_rows), 4),
        escalations_wrong=esc_bad, missed_escalations=missed,
        duplicate_tickets=m["duplicate_tickets"]["value"],
        approval_violations=m["approval_compliance"]["violations"]
        + m["rejected_proposals_executed"] + len(extra_viol),
        outbox_records=m["approval_compliance"]["den"],
        tickets_closed_wrong_evidence=len(closed_wrong),
        reroutes=len(reroutes), reroute_success=rr_ok,
        reroute_success_rate=None if not reroutes else round(rr_ok / len(reroutes), 4),
        reroute_failures=rr_fail, by_behaviour=by_beh, wrong_cases=wrong, notes=notes,
        tier3_executed=m["tier3_executed"])
