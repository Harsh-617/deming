"""Closed-loop simulator: Normalizer -> Checker -> Planner, human approval, Verifier next run.

State lives in CSV files that stand in for the Sheet tabs (one folder, default sim/state/):

    inventory.csv      Inventory tab: contract input columns + agent-written vendor, product,
                       version, match_confidence. Edit this file to "change the Sheet".
    settings.csv       Settings tab (key,value)
    decision_log.csv   Decision Log tab: one row per device per run, one per ticket check
    proposals.csv      drafted actions waiting for a human (the Inbox stand-in)
    approvals.csv      recorded human decisions: proposal_id,decision,approver,decided_at,note
    tickets.csv        Tickets tab
    runs.csv           one row per run (run time, call counts)
    outbox/            outward actions (email, calendar, ticket) as JSON records. Nothing is sent.
    runs/<run_id>/     deming.csv (contract predictions CSV), inventory_snapshot.csv, digest.md
    metrics.json / metrics.csv   loop metrics (see compute_metrics)

Safety rules enforced here, whatever the model says:
- An outward action is written to outbox/ only while executing a proposal that has a recorded
  approval with a named approver. No approval, no record. A rejection executes nothing.
- Tier 3 actions (isolate, disconnect, replace) are only ever drafted into the Decision Log.
  They are never proposals, so they can't be approved or executed.
- do_not_touch devices get no tier 3 draft at all; they are escalated to a named human.
- One open ticket per dedupe key (device_id|issue), checked at planning AND at execution.
- Email recipients are fixed by rule (owner, or approver for unknown devices); the model's
  recipient is recorded only to measure routing accuracy.
- A ticket closes only when the device is removed from the inventory, or its version changed
  AND the new version parses AND is >= the ticket's fixed_version on its own release train
  (sim/guards.select_train_fixes + compare_versions).
  The Verifier only confirms what the inventory record shows, never that a device is secure.

Idempotency (docs/decisions/feat-loop.md): run_id comes from the scheduled time (`--now`); a
run_id already in runs.csv is a no-op, so a duplicate scheduler delivery does nothing. Every
outward record is keyed by proposal_id and created with exclusive-create, so re-executing an
approval can't send twice.

CLI (no API key needed with --mock):
    python -m sim.loop --as-of 2026-11-12 --inventory eval/fixtures/inventory.csv --mock
    python -m sim.loop pending
    python -m sim.loop approve P-001-DEV-003 --approver approver@example.org
    python -m sim.loop reject  P-001-DEV-001 --approver approver@example.org --note "not now"
    python -m sim.loop metrics
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import config, guards, retrieval
from .gemini_runner import GeminiRunner
from .mock_llm import INJECTION, rule_based_client
from .pipeline import DEVICE_FIELDS, run_device, verify_ticket

DEFAULT_STATE = config.ROOT / "sim" / "state"
FIXTURE_KEV = config.ROOT / "eval" / "fixtures" / "feeds" / "kev.json"

INVENTORY_COLUMNS = list(DEVICE_FIELDS)
AGENT_COLUMNS = ["vendor", "product", "version", "match_confidence"]
DECISION_LOG_COLUMNS = ["timestamp", "run_id", "device_id", "lane", "evidence", "confidence",
                        "proposed_action", "approver", "decision", "action_taken", "outcome",
                        "verification_note", "proposal_id", "ticket_id", "notes"]
PROPOSAL_COLUMNS = ["proposal_id", "run_id", "created_on", "kind", "device_id", "issue",
                    "dedupe_key", "lane", "priority", "deadline", "actions", "to", "cc",
                    "subject", "body", "drafted_to", "expected_to", "escalate_to_human",
                    "ticket_id", "evidence", "fixed_version", "firmware_at_open",
                    "device_name_at_open", "last_updated_at_open", "owner_email", "status",
                    "decided_by", "decided_at", "executed_at"]
APPROVAL_COLUMNS = ["proposal_id", "decision", "approver", "decided_at", "note"]
TICKET_COLUMNS = ["ticket_id", "device_id", "issue", "lane", "dedupe_key", "status", "opened",
                  "due", "last_reminder", "owner_email", "evidence", "fixed_version",
                  "firmware_at_open", "device_name_at_open", "last_updated_at_open",
                  "proposal_id", "closed_on", "flags", "last_note"]
RUN_COLUMNS = ["run_seq", "run_id", "as_of", "started_at", "duration_s", "mode", "devices",
               "tickets_checked", "proposals_created", "llm_calls"]
PREDICTION_COLUMNS = ["device_id", "vendor", "product", "version", "confidence", "lane",
                      "evidence", "run_id"]
SETTINGS_DEFAULTS = {
    "approver_email": "approver@example.org",
    "days_until_reminder": "3",
    "days_until_escalation": "7",
    "urgent": "internet_facing is true and criticality is high or critical",
    "tier2_mode": "approval",   # email, calendar, ticket: needs recorded approval
    "tier3_mode": "draft_only",  # isolate, disconnect, replace: never executed by Deming
    "maintenance_lead_days": "2",
    "kev_overdue_grace_days": "14",  # KEV dueDate already passed: deadline = as_of + this
    "retire_days": "30",             # retire: deadline = as_of + this (support end is evidence)
    "retire_isolation_days": "7",    # retire: interim isolation advice within this many days
    "digest_channel": "",
}
ISSUE_BY_LANE = guards.ISSUE_BY_LANE
INT_SETTINGS = ("days_until_reminder", "days_until_escalation", "maintenance_lead_days",
                "kev_overdue_grace_days", "retire_days", "retire_isolation_days")
TIER2_ACTIONS = {"email", "ticket", "calendar"}
TIER3_ACTIONS = {"isolate_until_replaced", "replace_device", "disconnect"}
OPEN = ("open", "escalated")


# ---- CSV state ------------------------------------------------------------------------------
def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items() if k is not None}
                for r in csv.DictReader(f)]


def write_rows(path: Path, columns: list[str], rows: list[dict]) -> None:
    """UTF-8, no BOM, RFC 4180, exact column order; written to a temp file then renamed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: "" if r.get(c) is None else r.get(c) for c in columns})
    tmp.replace(path)


class State:
    def __init__(self, root: str | Path = DEFAULT_STATE):
        self.root = Path(root)
        self.outbox = self.root / "outbox"
        self.root.mkdir(parents=True, exist_ok=True)
        self.outbox.mkdir(exist_ok=True)
        if not (self.root / "settings.csv").exists():
            write_rows(self.root / "settings.csv", ["key", "value"],
                       [{"key": k, "value": v} for k, v in SETTINGS_DEFAULTS.items()])
        self.load()

    def load(self):
        self.settings_raw = {r["key"]: r["value"] for r in read_rows(self.root / "settings.csv")}
        self.inventory = read_rows(self.root / "inventory.csv")
        self.decision_log = read_rows(self.root / "decision_log.csv")
        self.proposals = read_rows(self.root / "proposals.csv")
        self.approvals = read_rows(self.root / "approvals.csv")
        self.tickets = read_rows(self.root / "tickets.csv")
        self.runs = read_rows(self.root / "runs.csv")

    def save(self):
        write_rows(self.root / "decision_log.csv", DECISION_LOG_COLUMNS, self.decision_log)
        write_rows(self.root / "proposals.csv", PROPOSAL_COLUMNS, self.proposals)
        write_rows(self.root / "approvals.csv", APPROVAL_COLUMNS, self.approvals)
        write_rows(self.root / "tickets.csv", TICKET_COLUMNS, self.tickets)
        write_rows(self.root / "runs.csv", RUN_COLUMNS, self.runs)

    @property
    def settings(self) -> dict:
        return typed_settings(self.settings_raw)

    def open_tickets(self, device_id: str | None = None) -> list[dict]:
        return [t for t in self.tickets if t["status"] in OPEN
                and (device_id is None or t["device_id"] == device_id)]

    def proposal(self, pid: str) -> dict | None:
        return next((p for p in self.proposals if p["proposal_id"] == pid), None)

    def last_as_of(self) -> str | None:
        return self.runs[-1]["as_of"] if self.runs else None


def typed_settings(raw: dict | None = None) -> dict:
    """Settings with defaults filled in and the day counts as ints (also used by eval runs)."""
    s = {**SETTINGS_DEFAULTS, **{k: v for k, v in (raw or {}).items() if v not in (None, "")}}
    for k in INT_SETTINGS:
        s[k] = int(s[k])
    return s


def _truthy(v) -> bool:
    return str(v).strip().lower() == "true"


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def read_inventory(path: Path) -> list[dict]:
    rows = read_rows(path)
    if rows:
        missing = [c for c in INVENTORY_COLUMNS if c not in rows[0]]
        if missing:
            raise ValueError(f"{path}: missing inventory columns {missing}")
    ids = [r["device_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate device_id")
    return [{c: r.get(c, "") for c in INVENTORY_COLUMNS} for r in rows]


# ---- approvals and execution ----------------------------------------------------------------
def record_approval(state: State, proposal_id: str, decision: str, approver: str,
                    decided_at: str, note: str = "") -> None:
    """Record one human decision. Doesn't execute anything; apply_approvals() does."""
    if decision not in ("approved", "rejected"):
        raise ValueError(f"decision must be approved or rejected, not {decision!r}")
    if not approver.strip():
        raise ValueError("an approval needs a named approver")
    p = state.proposal(proposal_id)
    if p is None:
        raise KeyError(f"no proposal {proposal_id}")
    if p["status"] != "pending":
        raise ValueError(f"{proposal_id} is already {p['status']}")
    if any(a["proposal_id"] == proposal_id for a in state.approvals):
        raise ValueError(f"{proposal_id} already has a recorded decision")
    state.approvals.append(dict(proposal_id=proposal_id, decision=decision,
                                approver=approver.strip(), decided_at=decided_at, note=note))


def _write_outbox(state: State, proposal: dict, kind: str, record: dict) -> Path:
    """Exclusive create: the same proposal can never produce the same record twice."""
    if kind not in TIER2_ACTIONS:
        raise PermissionError(f"{kind} is not a tier 2 action; Deming never executes it")
    path = state.outbox / f"{proposal['proposal_id']}.{kind}.json"
    try:
        with open(path, "x", encoding="utf-8") as f:
            json.dump({"kind": kind, "proposal_id": proposal["proposal_id"], **record,
                       "note": "SIMULATED: written to the outbox, not sent."}, f, indent=1)
    except FileExistsError:
        pass
    return path


def apply_approvals(state: State, on_date: str) -> list[str]:
    """Execute every recorded decision whose proposal is still pending. Returns log lines."""
    out = []
    for a in state.approvals:
        p = state.proposal(a["proposal_id"])
        if p is None or p["status"] != "pending":
            continue
        if not a["approver"] or a["decision"] not in ("approved", "rejected"):
            out.append(f"{a['proposal_id']}: invalid approval row ignored")
            continue
        p.update(status=a["decision"], decided_by=a["approver"], decided_at=a["decided_at"])
        if a["decision"] == "rejected":
            _update_log(state, p, approver=a["approver"], decision="rejected",
                        action_taken="none", outcome="rejected by a human; nothing sent")
            out.append(f"{p['proposal_id']}: rejected by {a['approver']}, nothing executed")
            continue
        taken = _execute(state, p, a, on_date)
        p["executed_at"] = on_date
        _update_log(state, p, approver=a["approver"], decision="approved",
                    action_taken=";".join(taken), outcome="outbox records written (simulated)")
        out.append(f"{p['proposal_id']}: approved by {a['approver']}, executed {';'.join(taken)}")
    return out


def _execute(state: State, p: dict, approval: dict, on_date: str) -> list[str]:
    actions = [x for x in p["actions"].split(";") if x]
    taken = []
    stamp = {"approved_by": approval["approver"], "approved_at": approval["decided_at"],
             "executed_on": on_date}
    ticket = None
    if p["kind"] == "reminder":
        ticket = next((t for t in state.tickets if t["ticket_id"] == p["ticket_id"]), None)
        if ticket is not None:
            ticket["last_reminder"] = on_date
    if "ticket" in actions:
        # Dedupe at execution too: two approved proposals must not open two tickets.
        ticket = next((t for t in state.open_tickets() if t["dedupe_key"] == p["dedupe_key"]), None)
        if ticket is None:
            ticket = dict(ticket_id=f"T-{len(state.tickets) + 1:04d}", device_id=p["device_id"],
                          issue=p["issue"], lane=p["lane"], dedupe_key=p["dedupe_key"],
                          status="open", opened=on_date, due=p["deadline"], last_reminder="",
                          owner_email=p["owner_email"], evidence=p["evidence"],
                          fixed_version=p["fixed_version"], firmware_at_open=p["firmware_at_open"],
                          device_name_at_open=p["device_name_at_open"],
                          last_updated_at_open=p["last_updated_at_open"],
                          proposal_id=p["proposal_id"], closed_on="", flags="", last_note="")
            state.tickets.append(ticket)
            _write_outbox(state, p, "ticket", {**stamp, "ticket_id": ticket["ticket_id"],
                                               "device_id": p["device_id"], "issue": p["issue"],
                                               "due": p["deadline"]})
            taken.append(f"ticket:{ticket['ticket_id']}")
        else:
            taken.append(f"ticket:{ticket['ticket_id']}(already open, not duplicated)")
        p["ticket_id"] = ticket["ticket_id"]
    if "email" in actions:
        _write_outbox(state, p, "email", {**stamp, "to": p["to"], "cc": p["cc"],
                                          "subject": p["subject"], "body": p["body"]})
        taken.append("email")
    if "calendar" in actions:
        window = min(_d(on_date) + dt.timedelta(days=state.settings["maintenance_lead_days"]),
                     _d(p["deadline"]) if p["deadline"] else dt.date.max)
        _write_outbox(state, p, "calendar", {**stamp, "attendees": [p["to"]],
                                             "title": f"Maintenance window: {p['device_id']}",
                                             "date": window.isoformat()})
        taken.append("calendar")
    return taken


def _log(state: State, row: dict) -> None:
    """Append a Decision Log row with every column present (blank = unknown)."""
    state.decision_log.append({c: row.get(c, "") for c in DECISION_LOG_COLUMNS})


def _update_log(state: State, p: dict, **fields):
    for r in state.decision_log:
        if r["proposal_id"] == p["proposal_id"] and r["proposed_action"] != "verify":
            prior = r.get("action_taken", "")
            r.update(fields)
            if prior and "action_taken" in fields:  # keep the tier 3 / escalation note
                r["action_taken"] = f"{fields['action_taken']} | {prior}"
            if p.get("ticket_id"):
                r["ticket_id"] = p["ticket_id"]


# ---- verification -----------------------------------------------------------------------------
@dataclass
class Verification:
    decision: str            # close | remind | escalate | keep_open
    observed_change: str     # device_removed | version_changed | no_change
    note: str
    flags: list[str] = field(default_factory=list)


def _train_compare(cur: str, fixed: str) -> tuple[int | None, str]:
    """Compare the new version with the fixed version(s) on its own release train (contracts
    v1.2, sim/guards.select_train_fixes). Returns (cmp, fixed_used) or (None, reason)."""
    train, why = guards.select_train_fixes(fixed, cur)
    if why:
        return None, why
    if any(guards.parse_version(f) is None for f in train):
        return None, f"fixed version {';'.join(train)} does not parse"
    if any(guards.compare_versions(cur, f) is None for f in train):
        return None, (f"version {cur} and fixed version {';'.join(train)} are in different "
                      "version formats")
    signs = {guards.compare_versions(cur, f) < 0 for f in train}
    if len(signs) > 1:
        return None, f"version {cur} is between fixed versions {';'.join(train)} on its train"
    return (-1 if signs == {True} else 1), ";".join(train)


def decide_verification(ticket: dict, record_now: dict | None, recheck_lane: str | None,
                        today: str, settings: dict) -> Verification:
    """The deterministic closing rule. The LLM Verifier's answer is logged but this decides."""
    if record_now is None:
        return Verification("close", "device_removed",
                            "The device no longer appears in the inventory record.")
    prev = (ticket.get("firmware_at_open") or "").strip()
    cur = (record_now.get("firmware_version_raw") or "").strip()
    changed = prev.casefold() != cur.casefold()
    observed = "version_changed" if changed else "no_change"
    flags: list[str] = []
    note = (f"The inventory record changed from version {prev or '(blank)'} to {cur or '(blank)'}"
            if changed else f"The inventory record still shows version {cur or '(blank)'}")
    if ticket["issue"] == "identify":
        if recheck_lane and recheck_lane != "unknown":
            return Verification("close", observed, "The inventory record can now be matched to a "
                                f"product (re-check lane {recheck_lane}); identification request closed.")
    elif changed:
        fixed = (ticket.get("fixed_version") or "").strip()
        if not fixed:
            flags.append("low_evidence")
            note += "; no fixed version is documented, so the record can't show a fix (low evidence)"
        elif guards.parse_version(cur) is None:
            flags.append("low_evidence")
            note += f"; the new version {cur!r} does not parse, so it can't be compared (low evidence)"
        elif (sel := _train_compare(cur, fixed))[0] is None:
            flags.append("low_evidence")
            note += f"; {sel[1]} (low evidence)"
        else:
            cmp, fixed = sel
            if cmp < 0:
                flags.append("still_vulnerable")
                note += f", which is still below the fixed version {fixed}; a change is not a fix"
            elif recheck_lane in ("patch", "retire"):
                flags.append("recheck_disagrees")
                note += f", at or above {fixed}, but the re-check lane is {recheck_lane}; kept open"
            else:
                return Verification("close", observed, note + f", at or above the fixed version "
                                    f"{fixed}. This confirms the record only, not the device.")
    opened = _d(ticket["opened"])
    last = max(opened, _d(ticket["last_reminder"])) if ticket.get("last_reminder") else opened
    now = _d(today)
    if now >= opened + dt.timedelta(days=settings["days_until_escalation"]) or "still_vulnerable" in flags:
        decision = "escalate"
    elif now >= last + dt.timedelta(days=settings["days_until_reminder"]):
        decision = "remind"
    else:
        decision = "keep_open"
    return Verification(decision, observed, note + ".", flags)


# ---- one run ------------------------------------------------------------------------------------
@dataclass
class ScriptedApprover:
    """Stand-in for a human in tests and the demo. `rule(proposal) -> approved|rejected|None`."""
    name: str
    rule: Callable[[dict], str | None] = lambda p: "approved"

    def __call__(self, proposals: list[dict]) -> dict[str, str]:
        return {p["proposal_id"]: d for p in proposals if (d := self.rule(p))}


@dataclass
class RunReport:
    run_id: str
    as_of: str
    skipped: bool = False
    lanes: dict = field(default_factory=dict)
    proposals: list[str] = field(default_factory=list)
    verifications: dict = field(default_factory=dict)
    log: list[str] = field(default_factory=list)


def make_runner(mock: bool, kev_index: retrieval.KevIndex, lifecycle_rows: list[dict]) -> GeminiRunner:
    if mock:
        catalog = list(kev_index.keys) + [(r["vendor"], r["product"]) for r in lifecycle_rows]
        return GeminiRunner(rule_based_client(catalog), cache_dir=None)
    return GeminiRunner()


def run_loop(state: State | str | Path = DEFAULT_STATE, *, as_of: str | None = None,
             inventory: str | Path | None = None, mock: bool = True,
             now: str | None = None, runner: GeminiRunner | None = None,
             approver: Callable[[list[dict]], dict[str, str]] | None = None,
             kev_path: str | Path | None = None, lifecycle_path: str | Path | None = None,
             write_metrics: bool = True) -> RunReport:
    state = state if isinstance(state, State) else State(state)
    as_of = config.load_as_of_date(as_of)
    started = (dt.datetime.fromisoformat(now.replace("Z", "+00:00")) if now
               else dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    run_id = "deming-" + started.strftime("%Y%m%dT%H%M%SZ")
    report = RunReport(run_id, as_of)
    if any(r["run_id"] == run_id for r in state.runs):
        report.skipped = True
        report.log.append(f"{run_id} already recorded: duplicate delivery, nothing done")
        return report
    t0 = time.perf_counter()
    stamp = started.strftime("%Y-%m-%dT%H:%M:%SZ")
    settings = state.settings
    if settings["tier2_mode"] != "approval":
        report.log.append(f"tier2_mode {settings['tier2_mode']!r} is not supported; approval required")
    run_seq = len(state.runs) + 1

    # Decisions recorded in approvals.csv since the last run (the file-based approval path).
    report.log += apply_approvals(state, as_of)

    inv_path = Path(inventory) if inventory else state.root / "inventory.csv"
    devices = read_inventory(inv_path)
    kev_path = Path(kev_path or (config.ROOT / "data/feeds/kev.json"))
    lifecycle_rows = retrieval.load_lifecycle(lifecycle_path or config.ROOT / "data/lifecycle.csv")
    kev_index = retrieval.KevIndex.build(retrieval.load_kev(kev_path))
    runner = runner or make_runner(mock, kev_index, lifecycle_rows)
    calls_before = runner.stats["calls"] + runner.stats["cache_hits"]

    # 1. Normalizer -> Checker -> Planner for every device.
    results, failures = {}, {}
    for d in devices:
        open_t = [{k: t[k] for k in ("ticket_id", "issue", "status", "due")}
                  for t in state.open_tickets(d["device_id"])]
        try:
            results[d["device_id"]] = run_device(
                runner, d, kev_index, lifecycle_rows, today=as_of, settings=settings,
                open_tickets=open_t, as_of_date=as_of)
        except Exception as exc:  # noqa: BLE001 - one bad answer must not stop the run
            failures[d["device_id"]] = f"{type(exc).__name__}: {str(exc)[:200]}"
    by_id = {d["device_id"]: d for d in devices}

    # 2. Verifier for every open ticket (this is "run N+1" for tickets opened earlier).
    for t in state.open_tickets():
        rec_now = by_id.get(t["device_id"])
        res = results.get(t["device_id"])
        recheck_lane = res.check.lane if res else ("unknown" if rec_now else None)
        llm_note, notes = "", []
        if t["issue"] in ("patch", "retire"):
            slim = lambda r: r and {k: r.get(k, "") for k in ("device_name_raw",
                                                              "firmware_version_raw", "last_updated")}
            try:
                llm, notes = verify_ticket(
                    runner, today=as_of,
                    ticket={k: t[k] for k in ("ticket_id", "device_id", "issue", "lane", "status",
                                              "opened", "due", "last_reminder")},
                    record_at_ticket={"device_name_raw": t["device_name_at_open"],
                                      "firmware_version_raw": t["firmware_at_open"],
                                      "last_updated": t["last_updated_at_open"]},
                    record_now=slim(rec_now),
                    recheck=({"lane": res.check.lane, "evidence_cve": res.check.evidence_cve}
                             if res else None), settings=settings)
                llm_note = f"llm_decision={llm.decision}"
            except Exception as exc:  # noqa: BLE001
                llm_note = f"llm_verifier_error={type(exc).__name__}"
        v = decide_verification(t, rec_now, recheck_lane, as_of, settings)
        t["last_note"] = v.note
        t["flags"] = ";".join(sorted(set(filter(None, t["flags"].split(";"))) | set(v.flags)))
        if v.decision == "close":
            t.update(status="closed", closed_on=as_of)
        elif v.decision == "escalate":
            t["status"] = "escalated"
        elif v.decision == "remind":
            _propose_reminder(state, t, run_id, run_seq, as_of, settings, report, stamp)
        report.verifications[t["ticket_id"]] = v.decision
        _log(state, dict(
            timestamp=stamp, run_id=run_id, device_id=t["device_id"],
            lane=res.check.lane if res else "", evidence=t["evidence"], confidence="",
            proposed_action="verify", decision=v.decision, outcome=v.observed_change,
            verification_note=v.note, ticket_id=t["ticket_id"],
            notes=";".join(filter(None, [llm_note, *notes, *v.flags]))))

    # 3. Turn plans into proposals (or log why not).
    for d in devices:
        did = d["device_id"]
        if did in failures:
            report.lanes[did] = "unknown"
            _log(state, dict(timestamp=stamp, run_id=run_id, device_id=did,
                                           lane="unknown", proposed_action="none",
                                           decision="n/a", notes="agent error: " + failures[did]))
            continue
        r = results[did]
        report.lanes[did] = r.check.lane
        evidence = ";".join(r.check.evidence_cve + ([r.check.evidence_lifecycle_id]
                                                    if r.check.evidence_lifecycle_id else []))
        row = dict(timestamp=stamp, run_id=run_id, device_id=did, lane=r.check.lane,
                   evidence=evidence, confidence=f"{r.normalized.confidence:.2f}",
                   proposed_action=r.plan.action, decision="n/a",
                   notes=";".join(r.guard_notes + (["injection_detected"]
                                                   if r.normalized.injection_detected
                                                   or r.plan.injection_detected else [])))
        if r.check.lane != "fine":
            pid, why = _propose_device(state, d, r, evidence, run_id, run_seq, as_of, settings,
                                       lifecycle_rows)
            row.update(proposal_id=pid or "", decision="pending" if pid else "n/a",
                       outcome=why)
            if pid:
                report.proposals.append(pid)
                if r.check.lane != "unknown" and (bad := guards.owner_email_problem(d["owner_email"])):
                    row["notes"] = ";".join(filter(None, [row["notes"], f"{bad}: sent to the approver"]))
            if _truthy(d["do_not_touch"]):
                row["action_taken"] = "escalated to a named human (do_not_touch)"
            elif r.check.lane == "retire":
                row["action_taken"] = ("drafted only (tier 3, a named human decides): "
                                       "isolate_until_replaced;replace_device")
        _log(state, row)

    # 4. Scripted approver (tests and demo) records decisions, then they are executed.
    if approver is not None:
        pending = [p for p in state.proposals if p["status"] == "pending"]
        decided_at = f"{as_of}T{started.strftime('%H:%M:%S')}Z"  # simulated day of the run
        for pid, decision in approver(pending).items():
            record_approval(state, pid, decision, getattr(approver, "name", "scripted"), decided_at)
        report.log += apply_approvals(state, as_of)

    # 5. Write the Sheet tabs, per-run files and metrics.
    annotated = []
    for d in devices:
        r = results.get(d["device_id"])
        annotated.append({**d, "vendor": r.normalized.vendor if r else "",
                          "product": r.normalized.product if r else "",
                          "version": r.normalized.version if r else "",
                          "match_confidence": f"{r.normalized.confidence:.2f}" if r else ""})
    write_rows(state.root / "inventory.csv", INVENTORY_COLUMNS + AGENT_COLUMNS, annotated)
    run_dir = state.root / "runs" / run_id
    write_rows(run_dir / "inventory_snapshot.csv", INVENTORY_COLUMNS, devices)
    write_rows(run_dir / "deming.csv", PREDICTION_COLUMNS, [
        dict(device_id=a["device_id"], vendor=a["vendor"], product=a["product"],
             version=a["version"], confidence=a["match_confidence"] or "0.00",
             lane=report.lanes.get(a["device_id"], "unknown"),
             evidence="" if report.lanes.get(a["device_id"]) in ("fine", "unknown") else
             next((x["evidence"] for x in state.decision_log if x["run_id"] == run_id
                   and x["device_id"] == a["device_id"] and x["proposed_action"] != "verify"), ""),
             run_id=run_id) for a in annotated])
    state.runs.append(dict(run_seq=run_seq, run_id=run_id, as_of=as_of, started_at=stamp,
                           duration_s=f"{time.perf_counter() - t0:.3f}",
                           mode="mock" if mock else "gemini", devices=len(devices),
                           tickets_checked=len(report.verifications),
                           proposals_created=len(report.proposals),
                           llm_calls=runner.stats["calls"] + runner.stats["cache_hits"] - calls_before))
    state.save()
    (run_dir / "digest.md").write_text(_digest(state, report), encoding="utf-8")
    if write_metrics:
        save_metrics(state)
    return report


def _expected_to(lane: str, owner: str, settings: dict) -> str:
    return guards.recipient(lane, {"owner_email": owner}, settings)


def _safe_body(body: str, did: str, lane: str, evidence: str, deadline: str, dnt: bool,
               passed: str = "") -> tuple[str, str]:
    """Rebuild the message body when it carries injected text or (do_not_touch) disconnect words."""
    if INJECTION.search(body) or (dnt and guards._DISCONNECT.search(body)):
        ask = ("a named person must decide the next step; Deming proposes no change"
               if dnt else "please review and act by the deadline")
        return (f"Device {did}: lane {lane}. Evidence: {evidence or 'none'}. Deadline: "
                f"{deadline or 'none'}. {ask[0].upper() + ask[1:]}." + (f" {passed}" if passed else "")
                ), "message body rebuilt by loop guard"
    return body, ""


def _propose_device(state, d, r, evidence, run_id, run_seq, as_of, settings, lifecycle_rows):
    did, lane = d["device_id"], r.check.lane
    issue = ISSUE_BY_LANE[lane]
    key = f"{did}|{issue}"
    open_t = next((t for t in state.open_tickets() if t["dedupe_key"] == key), None)
    if open_t:
        return None, f"tracked by open ticket {open_t['ticket_id']}; no new proposal"
    pend = next((p for p in state.proposals if p["dedupe_key"] == key and p["status"] == "pending"), None)
    if pend:
        return None, f"awaiting a decision on {pend['proposal_id']}; no new proposal"
    rej = [p for p in state.proposals if p["dedupe_key"] == key and p["status"] == "rejected"]
    if rej:
        until = _d(rej[-1]["created_on"]) + dt.timedelta(days=settings["days_until_reminder"])
        if _d(as_of) < until:
            return None, f"{rej[-1]['proposal_id']} was rejected; not re-proposed before {until}"
    dnt = _truthy(d["do_not_touch"])
    plan = r.plan
    expected = _expected_to(lane, d["owner_email"], settings)
    # F1: an owner_email that is not one well-formed address is never a recipient; the approver
    # gets the message and reviews the record (guards.owner_email_problem).
    bad_owner = guards.owner_email_problem(d["owner_email"]) if lane != "unknown" else None
    drafted_to = ""  # the Planner no longer drafts a recipient (contracts v1.4); code routes by rule
    deadline = plan.deadline.isoformat() if plan.deadline else ""
    body = plan.message.body if plan.message else ""
    subject = plan.message.subject if plan.message else f"[Deming] {lane}: {did}"
    # The deadline sentence (CISA date passed; retire support end + isolation) is rebuilt from
    # trusted fields if the body is rebuilt.
    passed = guards.deadline_sentence(r.check, as_of, settings, dnt)
    body, guard_note = _safe_body(body or "-", did, lane, evidence, deadline, dnt, passed)
    if not plan.message:
        guard_note = "planner drafted no message; loop wrote a minimal one"
    if bad_owner:
        guard_note = "; ".join(filter(None, [guard_note, f"{bad_owner}: sent to the approver for review"]))
    if INJECTION.search(subject):
        subject = f"[Deming] {lane}: {did}"
    actions = ["email", "ticket"] + (["calendar"] if lane == "patch" and not dnt else [])
    # fixed_version comes from the governing lifecycle row, used later to judge a version change.
    row = guards._governing_row(r.check, {**d, **r.normalized.model_dump()}, r.lifecycle_candidates)
    fixed = (row or {}).get("fixed_version", "") if lane == "patch" else ""
    pid = f"P-{run_seq:03d}-{did}"
    state.proposals.append(dict(
        proposal_id=pid, run_id=run_id, created_on=as_of, kind="device", device_id=did,
        issue=issue, dedupe_key=key, lane=lane, priority=plan.priority, deadline=deadline,
        actions=";".join(actions), to=expected,
        cc=settings["approver_email"] if (plan.escalate_to_human or dnt) and expected != settings["approver_email"] else "",
        subject=subject, body=body, drafted_to=drafted_to, expected_to=expected,
        escalate_to_human=str(plan.escalate_to_human or dnt or bool(bad_owner)).lower(), ticket_id="",
        evidence=evidence, fixed_version=fixed, firmware_at_open=d["firmware_version_raw"],
        device_name_at_open=d["device_name_raw"], last_updated_at_open=d["last_updated"],
        owner_email=d["owner_email"], status="pending", decided_by="", decided_at="",
        executed_at=""))
    why = "proposal drafted; needs a recorded approval"
    return pid, "; ".join(filter(None, [why, guard_note]))


def _reminder_to(t: dict, settings: dict) -> str:
    """Reminders go to the ticket's owner_email, or to the approver if it is not one valid address (F1)."""
    return settings["approver_email"] if guards.owner_email_problem(t["owner_email"]) else t["owner_email"]


def _propose_reminder(state, t, run_id, run_seq, as_of, settings, report, stamp):
    key = f"{t['ticket_id']}|remind"
    if any(p["dedupe_key"] == key and p["status"] == "pending" for p in state.proposals):
        return
    pid = f"P-{run_seq:03d}-{t['ticket_id']}-R"
    state.proposals.append(dict(
        proposal_id=pid, run_id=run_id, created_on=as_of, kind="reminder",
        device_id=t["device_id"], issue=t["issue"], dedupe_key=key, lane=t["lane"],
        priority="", deadline=t["due"], actions="email", to=_reminder_to(t, settings), cc="",
        subject=f"[Deming] reminder: {t['ticket_id']} ({t['device_id']})",
        body=(f"Reminder: ticket {t['ticket_id']} for device {t['device_id']} ({t['issue']}) is "
              f"still open. The inventory record does not yet show the requested change. "
              f"Due: {t['due'] or 'none'}."),
        drafted_to="", expected_to=_reminder_to(t, settings), escalate_to_human="false",
        ticket_id=t["ticket_id"], evidence=t["evidence"], fixed_version=t["fixed_version"],
        firmware_at_open=t["firmware_at_open"], device_name_at_open=t["device_name_at_open"],
        last_updated_at_open=t["last_updated_at_open"], owner_email=t["owner_email"],
        status="pending", decided_by="", decided_at="", executed_at=""))
    report.proposals.append(pid)
    _log(state, dict(timestamp=stamp, run_id=run_id, device_id=t["device_id"], lane=t["lane"],
                     evidence=t["evidence"], proposed_action="remind", decision="pending",
                     outcome="reminder drafted; needs a recorded approval", proposal_id=pid,
                     ticket_id=t["ticket_id"]))


def _digest(state: State, report: RunReport) -> str:
    lines = [f"# Deming run {report.run_id} (as of {report.as_of})", "",
             "Synthetic inventory. Nothing below was sent; outward actions wait for approval.", "",
             "## Lanes", ""]
    for did, lane in sorted(report.lanes.items()):
        lines.append(f"- {did}: {lane}")
    lines += ["", "## Proposals awaiting approval", ""]
    for p in state.proposals:
        if p["status"] == "pending":
            esc = " ESCALATE: a named person must decide" if p["escalate_to_human"] == "true" else ""
            lines.append(f"- {p['proposal_id']} [{p['kind']}] {p['device_id']} {p['lane']} -> "
                         f"{p['to']} actions={p['actions']} deadline={p['deadline'] or '-'}{esc}")
    lines += ["", "## Verification (inventory record only, not device security)", ""]
    for r in state.decision_log:
        if r["run_id"] == report.run_id and r["proposed_action"] == "verify":
            lines.append(f"- {r['ticket_id']} {r['device_id']}: {r['decision']} - {r['verification_note']}")
    lines += [""] + [f"- {x}" for x in report.log]
    return "\n".join(lines) + "\n"


# ---- metrics ------------------------------------------------------------------------------------
def _ratio(n, d):
    return None if d == 0 else round(n / d, 4)


def compute_metrics(state: State) -> dict:
    """Loop metrics, from the state files only (an audit, not the loop's own bookkeeping).

    - owner_routing_accuracy: share of emails whose MODEL-drafted recipient equals the rule, over
      proposals that still carry one (state from before contracts v1.4). Since v1.4 the Planner
      drafts no recipient, so this is null on new state.
    - routing_after_guard: share of emails actually addressed by the rule (owner for
      patch/retire/reminder, approver for unknown).
    - duplicate_tickets: tickets opened while another ticket with the same device_id|issue was
      still open (target 0).
    - approval_compliance: outbox records with a matching approved decision by a named approver,
      for a tier 2 action, decided no later than the record; violations listed (target 0).
    - verification_correctness: verify rows whose decision matches expected_verification.csv
      (as_of,device_id,expected_decision) when that file exists; else null.
    - run_time: per-run wall time from runs.csv.
    """
    m: dict = {}
    emails = [p for p in state.proposals if "email" in p["actions"].split(";")]
    drafted = [p for p in emails if p["drafted_to"]]
    ok = sum(p["drafted_to"].casefold() == p["expected_to"].casefold() for p in drafted)
    m["owner_routing_accuracy"] = dict(value=_ratio(ok, len(drafted)), num=ok, den=len(drafted))
    ok2 = sum(p["to"].casefold() == p["expected_to"].casefold() for p in emails)
    m["routing_after_guard"] = dict(value=_ratio(ok2, len(emails)), num=ok2, den=len(emails))

    dups = []
    for t in state.tickets:
        for o in state.tickets:
            if (o is not t and o["dedupe_key"] == t["dedupe_key"]
                    and int(o["ticket_id"][2:]) < int(t["ticket_id"][2:])
                    and (not o["closed_on"] or o["closed_on"] > t["opened"])):
                dups.append(t["ticket_id"])
                break
    m["duplicate_tickets"] = dict(value=len(dups), ids=dups)

    approvals = {a["proposal_id"]: a for a in state.approvals}
    records, violations = list(sorted(state.outbox.glob("*.json"))), []
    for path in records:
        rec = json.loads(path.read_text(encoding="utf-8"))
        a = approvals.get(rec.get("proposal_id"))
        if rec.get("kind") not in TIER2_ACTIONS:
            violations.append(f"{path.name}: not a tier 2 action")
        elif a is None or a["decision"] != "approved" or not a["approver"]:
            violations.append(f"{path.name}: no recorded approval")
        elif a["decided_at"][:10] > rec.get("executed_on", "9999"):
            violations.append(f"{path.name}: executed before the approval")
    m["approval_compliance"] = dict(value=_ratio(len(records) - len(violations), len(records)),
                                    num=len(records) - len(violations), den=len(records),
                                    violations=len(violations), details=violations)
    m["rejected_proposals_executed"] = sum(
        1 for p in state.proposals if p["status"] == "rejected" and p["executed_at"])

    exp_path = state.root / "expected_verification.csv"
    seq = {r["run_id"]: r["as_of"] for r in state.runs}
    verify = [r for r in state.decision_log if r["proposed_action"] == "verify"]
    if exp_path.exists():
        exp = {(e["as_of"], e["device_id"]): e["expected_decision"] for e in read_rows(exp_path)}
        judged = [(r, exp[(seq.get(r["run_id"]), r["device_id"])]) for r in verify
                  if (seq.get(r["run_id"]), r["device_id"]) in exp]
        right = sum(r["decision"] == e for r, e in judged)
        wrong = [f"{seq.get(r['run_id'])} {r['device_id']}: got {r['decision']}, expected {e}"
                 for r, e in judged if r["decision"] != e]
        m["verification_correctness"] = dict(value=_ratio(right, len(judged)), num=right,
                                             den=len(judged), wrong=wrong)
    else:
        m["verification_correctness"] = dict(value=None, note="no expected_verification.csv")
    llm = [r for r in verify if "llm_decision=" in r["notes"]]
    agree = sum(f"llm_decision={r['decision']}" in r["notes"] for r in llm)
    m["verifier_llm_agreement"] = dict(value=_ratio(agree, len(llm)), num=agree, den=len(llm))

    durations = [float(r["duration_s"]) for r in state.runs]
    m["run_time_s"] = dict(value=round(sum(durations) / len(durations), 3) if durations else None,
                           max=max(durations, default=None), runs=len(durations))
    m["tier3_executed"] = sum(1 for p in records if p.name.split(".")[-2] in TIER3_ACTIONS)
    m["tickets"] = {s: sum(t["status"] == s for t in state.tickets) for s in ("open", "escalated", "closed")}
    return m


def save_metrics(state: State) -> dict:
    m = compute_metrics(state)
    (state.root / "metrics.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    rows = []
    for k, v in m.items():
        if isinstance(v, dict) and "value" in v:
            rows.append(dict(metric=k, value="" if v["value"] is None else v["value"],
                             numerator=v.get("num", ""), denominator=v.get("den", ""),
                             note=v.get("note", "") or "; ".join(map(str, v.get("details") or v.get("wrong") or v.get("ids") or []))))
        elif not isinstance(v, dict):
            rows.append(dict(metric=k, value=v))
    write_rows(state.root / "metrics.csv", ["metric", "value", "numerator", "denominator", "note"], rows)
    return m


# ---- CLI --------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv.pop(0) if argv and argv[0] in ("run", "approve", "reject", "pending", "metrics") else "run"
    p = argparse.ArgumentParser(prog=f"python -m sim.loop {cmd}")
    p.add_argument("--state", type=Path, default=DEFAULT_STATE)
    if cmd == "run":
        p.add_argument("--as-of", default=None, help="YYYY-MM-DD; default data/ground_truth_meta.json")
        p.add_argument("--inventory", type=Path, default=None,
                       help="inventory CSV; default: <state>/inventory.csv")
        p.add_argument("--mock", action="store_true", help="rule-based mock model, no API key")
        p.add_argument("--now", default=None, help="scheduled time (ISO, UTC); sets the run_id")
        p.add_argument("--kev", type=Path, default=None)
        p.add_argument("--lifecycle", type=Path, default=None)
    elif cmd in ("approve", "reject"):
        p.add_argument("proposal_ids", nargs="+")
        p.add_argument("--approver", required=True, help="the named human deciding")
        p.add_argument("--note", default="")
        p.add_argument("--on", default=None, help="date the action executes; default last run's as_of")
    args = p.parse_args(argv)
    state = State(args.state)

    if cmd == "run":
        kev = args.kev or (config.ROOT / "data/feeds/kev.json")
        if not Path(kev).exists():
            kev = FIXTURE_KEV
            print(f"data/feeds/kev.json not found; using {kev}")
        rep = run_loop(state, as_of=args.as_of, inventory=args.inventory, mock=args.mock,
                       now=args.now, kev_path=kev, lifecycle_path=args.lifecycle)
        print((state.root / "runs" / rep.run_id / "digest.md").read_text(encoding="utf-8")
              if not rep.skipped else "\n".join(rep.log))
    elif cmd in ("approve", "reject"):
        on = args.on or state.last_as_of() or dt.date.today().isoformat()
        # Simulated date: the approval is recorded on the day it executes.
        stamp = on + dt.datetime.now(dt.timezone.utc).strftime("T%H:%M:%SZ")
        for pid in args.proposal_ids:
            record_approval(state, pid, "approved" if cmd == "approve" else "rejected",
                            args.approver, stamp, args.note)
        print("\n".join(apply_approvals(state, on)))
        state.save()
        save_metrics(state)
    elif cmd == "pending":
        for x in state.proposals:
            if x["status"] == "pending":
                print(f"{x['proposal_id']}\t{x['kind']}\t{x['device_id']}\t{x['lane']}\t"
                      f"to={x['to']}\tactions={x['actions']}\n    {x['body']}")
    elif cmd == "metrics":
        print(json.dumps(save_metrics(state), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
