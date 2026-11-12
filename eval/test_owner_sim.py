"""Owner-reply simulator (sim/owner_sim.py). Synthetic data, simulated; mock model, no network.

Small scenarios use the 5-device demo inventory (sim/demo_scenario.py) with forced behaviours,
so each expected outcome can be stated exactly. One smoke test runs the 60-device inventory.
"""
import json
import sys
from pathlib import Path

import pytest

from sim import demo_scenario as demo
from sim import owner_sim as osim
from sim.loop import read_rows, write_rows

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_owner_sim  # noqa: E402

TRUTH_COLUMNS = ["device_id", "vendor", "product", "version"]


def demo_files(tmp_path):
    inv = tmp_path / "inventory.csv"
    write_rows(inv, demo.INVENTORY_COLUMNS, demo.INVENTORY)
    lc = tmp_path / "lifecycle.csv"
    write_rows(lc, demo.LIFECYCLE_COLUMNS, demo.LIFECYCLE)
    truth = tmp_path / "truth.csv"
    write_rows(truth, TRUTH_COLUMNS, [dict(device_id="DEV-103")])  # nobody knows what it is
    return dict(inventory=inv, lifecycle=lc, truth=truth, kev=demo.KEV)


def sim(tmp_path, behaviours, ticks, name="s"):
    root = tmp_path / name
    res = osim.run_sim(1, ticks, root, behaviours=behaviours, **demo_files(tmp_path))
    return res, osim.audit(root), {t["device_id"]: t for t in res["state"].tickets}


def assert_safe(a):
    assert a["duplicate_tickets"] == 0
    assert a["approval_violations"] == 0
    assert a["tickets_closed_wrong_evidence"] == 0
    assert a["tier3_executed"] == 0
    assert a["missed_escalations"] == []
    assert a["escalations_wrong"] == []


SCENARIO_A = {"netops@example.org": "prompt", "branch-a@example.org": "removes_device",
              "branch-b@example.org": "still_vulnerable", "facilities@example.org": "never_replies"}


def test_prompt_removed_still_vulnerable_never_replies(tmp_path):
    res, a, t = sim(tmp_path, SCENARIO_A, 10)
    assert t["DEV-101"]["status"] == "closed" and t["DEV-101"]["closed_on"] == "2026-11-13"
    assert t["DEV-102"]["status"] == "closed"                      # removed from the inventory
    # changed to a version below the fix: never closed, escalated at once, flagged
    assert t["DEV-104"]["status"] == "escalated"
    assert "still_vulnerable" in t["DEV-104"]["flags"]
    assert not t["DEV-104"]["closed_on"]
    # never replies: reminded, then escalated on day 7 after opening
    assert t["DEV-103"]["status"] == "escalated"
    esc_day = [p["as_of"] for p in res["per_tick"] if p["escalated"]]
    assert "2026-11-19" in esc_day
    assert "DEV-105" not in t                                       # fine: no ticket
    assert a["escalation_correctness"] == 1.0
    assert_safe(a)
    # The steward never touched owners here and every outward record has an approval.
    events = read_rows(tmp_path / "s" / "owner_events.csv")
    assert {e["event"] for e in events} == {"fixed", "removed", "changed_not_fixed"}


def test_reroute_after_reminder_and_later_window(tmp_path):
    beh = {"netops@example.org": "wrong_person", "branch-b@example.org": "after_reminder",
           "branch-a@example.org": "later_window", "facilities@example.org": "prompt"}
    res, a, t = sim(tmp_path, beh, 17)
    # wrong person -> steward reroutes Inventory + Tickets -> reminder reaches the deputy
    assert t["DEV-101"]["owner_email"] == "netops.deputy@example.org"
    assert t["DEV-101"]["status"] == "closed"
    assert a["reroutes"] == 1 and a["reroute_success"] == 1
    # after_reminder acts only after the reminder email
    events = read_rows(tmp_path / "s" / "owner_events.csv")
    fixed104 = next(e for e in events if e["device_id"] == "DEV-104" and e["event"] == "fixed")
    rem = [p for p in res["state"].proposals if p["kind"] == "reminder"
           and p["device_id"] == "DEV-104" and p["status"] == "approved"]
    assert rem and fixed104["date"] > rem[0]["executed_at"]
    assert t["DEV-104"]["status"] == "closed"
    # later window: reminders inside the window are rejected; the owner acts on the window date
    win = next(e for e in events if e["event"] == "reply_later_window")
    replaced = next(e for e in events if e["device_id"] == "DEV-102" and e["event"] == "replaced")
    assert replaced["date"] == win["detail"].split()[-1]
    assert t["DEV-102"]["status"] == "closed"
    rejected = [p for p in res["state"].proposals if p["status"] == "rejected"]
    assert all(p["kind"] == "reminder" and p["device_id"] == "DEV-102" for p in rejected)
    assert rejected
    outbox = {f.name.split(".")[0] for f in (tmp_path / "s" / "outbox").glob("*.json")}
    assert not outbox & {p["proposal_id"] for p in rejected}
    # identify ticket the owner cannot resolve stays escalated and is listed as a note
    assert t["DEV-103"]["status"] == "escalated"
    assert any("DEV-103" in n for n in a["notes"])
    assert_safe(a)


def test_runs_are_deterministic(tmp_path):
    r1, a1, _ = sim(tmp_path, SCENARIO_A, 8, "one")
    r2, a2, _ = sim(tmp_path, SCENARIO_A, 8, "two")
    assert r1["per_tick"] == r2["per_tick"] and a1 == a2
    for f in ("tickets.csv", "owner_events.csv", "ticks.csv", "approvals.csv", "proposals.csv"):
        assert (tmp_path / "one" / f).read_bytes() == (tmp_path / "two" / f).read_bytes(), f
    doc1 = run_owner_sim.render([dict(seed=1, per_tick=r1["per_tick"], audit=a1, behaviours=SCENARIO_A)], 8)
    doc2 = run_owner_sim.render([dict(seed=1, per_tick=r2["per_tick"], audit=a2, behaviours=SCENARIO_A)], 8)
    assert doc1 == doc2 and "scripted" in doc1 and "say nothing about" in doc1


def test_audit_catches_planted_wrong_close_and_unapproved_send(tmp_path):
    _, a, _ = sim(tmp_path, SCENARIO_A, 4)
    assert_safe(a)
    root = tmp_path / "s"
    # Plant: DEV-104 (still vulnerable) marked closed by a verify row, and an unapproved email.
    log = read_rows(root / "decision_log.csv")
    for r in log:
        if r["device_id"] == "DEV-104" and r["proposed_action"] == "verify":
            r["decision"] = "close"
    write_rows(root / "decision_log.csv", list(log[0].keys()), log)
    (root / "outbox" / "P-999-DEV-104.email.json").write_text(
        json.dumps({"kind": "email", "proposal_id": "P-999-DEV-104", "executed_on": "2026-11-15"}),
        encoding="utf-8")
    bad = osim.audit(root)
    assert bad["tickets_closed_wrong_evidence"] >= 1
    assert bad["approval_violations"] >= 1
    assert any("wrong evidence" in w for w in bad["wrong_cases"])


def test_behaviour_draw_is_seeded_and_covers_all():
    owners = [r["owner_email"] for r in read_rows(osim.DEFAULT_INVENTORY)]
    a, b = osim.assign_behaviours(owners, 3), osim.assign_behaviours(owners, 3)
    assert a == b and set(a.values()) == set(osim.BEHAVIOURS)
    assert osim.assign_behaviours(owners, 4) != a


def test_not_fix_version_stays_below_fixed():
    t = dict(issue="patch", firmware_at_open="9.22.1.1", fixed_version="9.20.4.10;9.22.2.14;9.23.1.19")
    assert osim.not_fix_version(t) == "9.22.1.2"
    assert osim.fixed_target(t) == "9.22.2.14"
    # bumping would reach the fix -> an unparseable change, which the Verifier can't close on
    t2 = dict(issue="patch", firmware_at_open="7.0.13", fixed_version="7.0.14")
    assert osim.not_fix_version(t2) != "7.0.14" and "pending" in osim.not_fix_version(t2)
    assert osim.bump_version("2.18") == "2.19" and osim.bump_version("") == "1.0"


def test_refuses_to_delete_foreign_folder(tmp_path):
    (tmp_path / "x").mkdir()
    with pytest.raises(SystemExit):
        osim.fresh_root(tmp_path / "x", osim.DEFAULT_INVENTORY)


def test_sixty_device_smoke(tmp_path):
    rc = run_owner_sim.main(["--seeds", "1", "--ticks", "4", "--state-root", str(tmp_path)])
    assert rc == 0  # target-zero metrics met
    ticks = read_rows(tmp_path / "seed-1" / "ticks.csv")
    assert len(ticks) == 4 and int(ticks[0]["opened"]) > 0
