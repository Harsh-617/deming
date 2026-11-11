"""Demo scenario for the closed loop (PRD demo steps 1:00-2:20), runnable without an API key.

    python -m sim.demo_scenario            # mock model, state in sim/demo_state/
    python -m sim.demo_scenario --gemini   # real Gemini via .env (not tested on this branch)

Day 1 (run 1): five synthetic devices.
    DEV-101 FortiOS 7.0.1         -> patch   (KEV CVE-2024-21762, fixed in 7.0.14)
    DEV-102 Cisco RV320           -> retire  (past end of security support)
    DEV-103 "Cisco router 2nd fl" -> unknown (no model, no version: ask a human)
    DEV-104 FortiOS 7.0.5         -> patch
    DEV-105 HP LaserJet           -> fine    (log only)
  A scripted approver approves the four proposals; the outbox gets email/ticket/calendar records.
Between runs a human edits the inventory:
    DEV-101 updated to 7.0.14 (the fixed version), DEV-102 removed (replaced),
    DEV-104 updated to 7.0.12 (changed, but still below 7.0.14).
Day 2 (run 2): the Verifier closes DEV-101's and DEV-102's tickets; DEV-104's ticket does NOT
close (still vulnerable, escalated); DEV-103's identify ticket stays open.

All devices and data are synthetic. The lifecycle rows below are demo rows, not vendor facts.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from . import config
from .loop import (AGENT_COLUMNS, INVENTORY_COLUMNS, ScriptedApprover, State, read_rows,
                   run_loop, write_rows)

DEMO_STATE = config.ROOT / "sim" / "demo_state"
MARKER = ".deming_demo_state"
KEV = config.ROOT / "eval" / "fixtures" / "feeds" / "kev.json"
DAY1, DAY2 = "2026-11-12", "2026-11-13"

INVENTORY = [
    dict(device_id="DEV-101", device_name_raw="Fortinet FortiOS firewall", location="HQ edge",
         owner_email="netops@example.org", firmware_version_raw="7.0.1", internet_facing="true",
         criticality="high", do_not_touch="false", last_updated="2026-10-01"),
    dict(device_id="DEV-102", device_name_raw="Cisco RV320 router", location="Branch A",
         owner_email="branch-a@example.org", firmware_version_raw="1.4.2.15",
         internet_facing="true", criticality="medium", do_not_touch="false",
         last_updated="2026-09-15"),
    dict(device_id="DEV-103", device_name_raw="Cisco router 2nd floor", location="Floor 2",
         owner_email="facilities@example.org", firmware_version_raw="", internet_facing="false",
         criticality="medium", do_not_touch="false", last_updated="2026-07-11"),
    dict(device_id="DEV-104", device_name_raw="Fortinet FortiGate 60F (FortiOS)",
         location="Branch B", owner_email="branch-b@example.org", firmware_version_raw="7.0.5",
         internet_facing="true", criticality="high", do_not_touch="false",
         last_updated="2026-08-30"),
    dict(device_id="DEV-105", device_name_raw="HP LaserJet Pro M404 printer", location="Floor 2",
         owner_email="facilities@example.org", firmware_version_raw="002.2310A",
         internet_facing="false", criticality="low", do_not_touch="false",
         last_updated="2026-10-05"),
]

LIFECYCLE_COLUMNS = ["lifecycle_id", "vendor", "product", "model_pattern", "eol_date",
                     "last_security_support_date", "patch_available", "replacement_hint",
                     "source_url", "verified_on", "notes", "fixed_version"]
LIFECYCLE = [
    dict(lifecycle_id="LC-901", vendor="Fortinet", product="FortiOS", model_pattern="7.0.*",
         patch_available="true", source_url="https://example.org/demo-not-a-real-source",
         verified_on="2026-11-11",
         notes="model_pattern is a version glob. DEMO ROW: synthetic, not a vendor fact",
         fixed_version="7.0.14"),
    dict(lifecycle_id="LC-902", vendor="Cisco", product="Small Business RV320 and RV325 Routers",
         eol_date="2020-12-31", last_security_support_date="2021-12-31", patch_available="false",
         replacement_hint="Replace with a supported router",
         source_url="https://example.org/demo-not-a-real-source", verified_on="2026-11-11",
         notes="DEMO ROW: dates not verified"),
    dict(lifecycle_id="LC-903", vendor="HP", product="LaserJet Pro M404", patch_available="true",
         source_url="https://example.org/demo-not-a-real-source", verified_on="2026-11-11",
         notes="DEMO ROW"),
]

EXPECTED = [  # what run 2's Verifier must decide, for the verification_correctness metric
    dict(as_of=DAY2, device_id="DEV-101", expected_decision="close"),
    dict(as_of=DAY2, device_id="DEV-102", expected_decision="close"),
    dict(as_of=DAY2, device_id="DEV-103", expected_decision="keep_open"),
    dict(as_of=DAY2, device_id="DEV-104", expected_decision="escalate"),
]


def fresh_state(root: Path) -> State:
    """Recreate the demo folder. Only deletes a folder this script created (marker file)."""
    if root.exists():
        if not (root / MARKER).exists():
            raise SystemExit(f"{root} exists and is not a demo state folder; not deleting it")
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / MARKER).write_text("created by sim/demo_scenario.py\n", encoding="utf-8")
    write_rows(root / "inventory.csv", INVENTORY_COLUMNS, INVENTORY)
    write_rows(root / "lifecycle.csv", LIFECYCLE_COLUMNS, LIFECYCLE)
    write_rows(root / "expected_verification.csv", ["as_of", "device_id", "expected_decision"],
               EXPECTED)
    return State(root)


def human_edits_inventory(root: Path) -> None:
    """What the owners do between runs (in the real demo: edits in the Sheet)."""
    rows = read_rows(root / "inventory.csv")
    out = []
    for r in rows:
        if r["device_id"] == "DEV-102":
            continue  # replaced: the row is removed
        if r["device_id"] == "DEV-101":
            r.update(firmware_version_raw="7.0.14", last_updated=DAY2)
        if r["device_id"] == "DEV-104":
            r.update(firmware_version_raw="7.0.12", last_updated=DAY2)  # changed, still vulnerable
        out.append(r)
    write_rows(root / "inventory.csv", INVENTORY_COLUMNS + AGENT_COLUMNS, out)


def run_demo(root: Path = DEMO_STATE, mock: bool = True, quiet: bool = False) -> State:
    say = (lambda *a: None) if quiet else print
    state = fresh_state(root)
    common = dict(mock=mock, kev_path=KEV, lifecycle_path=root / "lifecycle.csv")
    approver = ScriptedApprover("approver@example.org")

    say(f"== Run 1 ({DAY1}): normalize, check, plan; approver approves every proposal")
    r1 = run_loop(state, as_of=DAY1, now=f"{DAY1}T01:00:00Z", approver=approver, **common)
    for did, lane in sorted(r1.lanes.items()):
        say(f"   {did}: {lane}")
    for line in r1.log:
        say("   " + line)
    say(f"   outbox: {sorted(p.name for p in state.outbox.glob('*.json'))}")

    say("== Owners edit the inventory: DEV-101 -> 7.0.14, DEV-102 removed, DEV-104 -> 7.0.12")
    human_edits_inventory(root)

    say(f"== Run 2 ({DAY2}): Verifier checks every open ticket")
    r2 = run_loop(state, as_of=DAY2, now=f"{DAY2}T01:00:00Z", approver=approver, **common)
    for t in state.tickets:
        say(f"   {t['ticket_id']} {t['device_id']} {t['issue']}: {t['status']}"
            f"{' [' + t['flags'] + ']' if t['flags'] else ''} - {t['last_note']}")
    m = state.root / "metrics.csv"
    say(f"== Metrics ({m}):")
    for row in read_rows(m):
        say(f"   {row['metric']}: {row['value']}")
    return state


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", type=Path, default=DEMO_STATE)
    p.add_argument("--gemini", action="store_true", help="use the real Gemini API (needs .env)")
    args = p.parse_args(argv)
    run_demo(args.state, mock=not args.gemini)


if __name__ == "__main__":
    main()
