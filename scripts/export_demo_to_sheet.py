"""Export the closed-loop demo (sim/demo_scenario.py, mock model) to Google-Sheets-ready .xlsx files.

One workbook per stage, so the video can show each one (import with File > Import):

    sheet/deming_demo_1_after_run1.xlsx       run 1: lanes decided, proposals pending approval
    sheet/deming_demo_2_after_approval.xlsx   the approver approved; tickets opened, outbox written
    sheet/deming_demo_3_after_rerun.xlsx      owners edited the inventory; run 2 verified the tickets

    python scripts/export_demo_to_sheet.py               # all three, into sheet/
    python scripts/export_demo_to_sheet.py --out-dir X   # somewhere else

No API calls: the mock model only. The stages replay the demo's own steps (sim.demo_scenario:
fresh_state, run_loop, human_edits_inventory). The approval that run_demo() records inside run 1
is recorded here as a separate step, with the same approver and timestamp. To check that the
split changes nothing, the script also runs sim.demo_scenario.run_demo() in a temp folder and
stops if its final state differs from stage 3 (run durations excepted).

Each workbook starts from the template (scripts/make_sheet_template.py), so validation,
conditional formatting, frozen headers and Summary formulas are the template's. Simulator
columns the template lacks go in extra columns at the right; the Summary tab says which.
Values are typed: dates are real dates, timestamps real date-times (UTC), booleans TRUE/FALSE,
confidences numbers, and every other value (versions, ids, free text) a text cell, never a
formula. All devices and data are synthetic.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import make_sheet_template as mst  # noqa: E402
from sim import demo_scenario as demo  # noqa: E402
from sim import loop  # noqa: E402

DEFAULT_OUT_DIR = REPO / "sheet"
STAGES = [
    ("1_after_run1", "Stage 1 of 3: after run 1 (lanes decided; proposals wait for a human)"),
    ("2_after_approval", "Stage 2 of 3: after approval (tickets opened; outbox records written, simulated)"),
    ("3_after_rerun", "Stage 3 of 3: after the owners' fix and run 2 (Verifier checked the inventory record)"),
]
APPROVED_AT = f"{demo.DAY1}T01:00:00Z"  # what run_demo's scripted approver records in run 1
FIXED_PROPERTIES_TIME = dt.datetime(2026, 11, 13, 0, 0, 0)  # stable file metadata across rebuilds

DATE_COLS = {"last_updated", "opened", "due", "last_reminder", "closed_on", "last_updated_at_open"}
DATETIME_COLS = {"timestamp"}
BOOL_COLS = {"internet_facing", "do_not_touch"}
NUMBER_COLS = {"match_confidence", "confidence"}
EXTRA_HEADER_FILL = PatternFill("solid", fgColor="FF7F7F7F")

# Tab -> (template columns, simulator columns).
TABS = {
    "Inventory": (mst.INVENTORY, loop.INVENTORY_COLUMNS + loop.AGENT_COLUMNS),
    "Decision Log": (mst.DECISION_LOG, loop.DECISION_LOG_COLUMNS),
    "Tickets": (mst.TICKETS, loop.TICKET_COLUMNS),
}
STATE_FILE = {"Inventory": "inventory.csv", "Decision Log": "decision_log.csv", "Tickets": "tickets.csv"}

# Summary rows whose formula has a value the loop itself reports; checked by the tests.
SUMMARY_ROW = {name: i for i, name in enumerate(
    ["latest_run_id", "devices_in_inventory", "lane_patch", "lane_retire", "lane_fine",
     "lane_unknown", "devices_decided_latest_run", "unknown_rate", "tickets_open",
     "tickets_escalated", "tickets_overdue", "tickets_closed", "urgent_devices"], start=2)}


# ---- running the demo in stages -----------------------------------------------------------------
def snapshot(state: loop.State) -> dict:
    root = state.root
    snap = {tab: loop.read_rows(root / f) for tab, f in STATE_FILE.items()}
    snap["runs"] = loop.read_rows(root / "runs.csv")
    snap["proposals"] = loop.read_rows(root / "proposals.csv")
    snap["approvals"] = loop.read_rows(root / "approvals.csv")
    snap["settings"] = loop.read_rows(root / "settings.csv")
    snap["metrics"] = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    snap["outbox"] = sorted(p.name for p in state.outbox.glob("*.json"))
    return snap


def run_stages(root: Path) -> list[dict]:
    """Replay sim.demo_scenario.run_demo() with a snapshot after each stage."""
    state = demo.fresh_state(root)
    common = dict(mock=True, kev_path=demo.KEV, lifecycle_path=root / "lifecycle.csv")
    approver = loop.ScriptedApprover("approver@example.org")

    loop.run_loop(state, as_of=demo.DAY1, now=f"{demo.DAY1}T01:00:00Z", approver=None, **common)
    stages = [snapshot(state)]

    for p in [p for p in state.proposals if p["status"] == "pending"]:
        if (d := approver.rule(p)):
            loop.record_approval(state, p["proposal_id"], d, approver.name, APPROVED_AT)
    loop.apply_approvals(state, demo.DAY1)
    state.save()
    loop.save_metrics(state)
    stages.append(snapshot(state))

    demo.human_edits_inventory(root)
    loop.run_loop(state, as_of=demo.DAY2, now=f"{demo.DAY2}T01:00:00Z", approver=approver, **common)
    stages.append(snapshot(state))
    return stages


def _comparable(snap: dict) -> dict:
    s = json.loads(json.dumps(snap))
    for r in s["runs"]:
        r.pop("duration_s", None)
    s["metrics"].pop("run_time_s", None)
    return s


def check_against_run_demo(final: dict, root: Path) -> None:
    """Stop if the staged replay ends anywhere other than where run_demo() ends."""
    ref = snapshot(demo.run_demo(root, mock=True, quiet=True))
    a, b = _comparable(final), _comparable(ref)
    diff = [k for k in a if a[k] != b[k]]
    if diff:
        raise SystemExit(f"staged replay differs from sim.demo_scenario.run_demo() in: {diff}")


# ---- writing cells ------------------------------------------------------------------------------
def typed(column: str, raw: str):
    raw = (raw or "").strip()
    if raw == "":
        return None
    if column in BOOL_COLS:
        return mst.to_cell_value(column, raw)
    if column in DATE_COLS:
        return dt.date.fromisoformat(raw)
    if column in DATETIME_COLS:  # '2026-11-12T01:00:00Z' -> naive date-time, UTC
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    if column in NUMBER_COLS:
        return float(raw)
    return raw


def write_cell(ws, row: int, col: int, column: str, raw: str) -> None:
    c = ws.cell(row=row, column=col)
    c.value = typed(column, raw)
    if isinstance(c.value, bool):
        return
    if isinstance(c.value, str):
        c.data_type = "s"  # data, never a formula, even when it starts with '='
        c.number_format = "@"
    elif isinstance(c.value, dt.datetime):
        c.number_format = "yyyy-mm-dd hh:mm:ss"
    elif isinstance(c.value, dt.date):
        c.number_format = "yyyy-mm-dd"
    elif isinstance(c.value, float):
        c.number_format = "0.00"


def fill_tab(ws, template_cols: list[str], sim_cols: list[str], rows: list[dict]) -> list[str]:
    """Write rows under the template header; returns the extra columns added at the right."""
    missing = [c for c in template_cols if c not in sim_cols]
    if missing:
        raise ValueError(f"{ws.title}: simulator has no column for template {missing}")
    extras = [c for c in sim_cols if c not in template_cols]
    columns = template_cols + extras
    for i, name in enumerate(extras, start=len(template_cols) + 1):
        h = ws.cell(row=1, column=i, value=name)
        h.font, h.fill = mst.HEADER_FONT, EXTRA_HEADER_FILL
        h.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(40, len(name) + 4))
    for r, row in enumerate(rows, start=2):
        for i, name in enumerate(columns, start=1):
            write_cell(ws, r, i, name, row.get(name, ""))
    return extras


def loop_values(snap: dict) -> dict:
    """What the loop itself says, for the Summary rows that have a loop counterpart."""
    runs = snap["runs"]
    latest = runs[-1]["run_id"] if runs else ""
    device_rows = [r for r in snap["Decision Log"]
                   if r["run_id"] == latest and r["proposed_action"] not in ("verify", "remind")]
    lanes = {lane: sum(r["lane"] == lane for r in device_rows) for lane in mst.LANES}
    decided = sum(lanes.values())
    t = snap["metrics"]["tickets"]
    return {
        "latest_run_id": latest,
        "devices_in_inventory": len(snap["Inventory"]),
        **{f"lane_{k}": v for k, v in lanes.items()},
        "devices_decided_latest_run": decided,
        "unknown_rate": lanes["unknown"] / decided if decided else "",
        "tickets_open": t["open"], "tickets_escalated": t["escalated"], "tickets_closed": t["closed"],
    }


def fill_summary(ws, title: str, snap: dict, extras: dict[str, list[str]]) -> None:
    ws["D1"] = "loop value (static, from sim/loop.py)"
    ws["D1"].font, ws["D1"].fill = mst.HEADER_FONT, EXTRA_HEADER_FILL
    ws.column_dimensions["D"].width = 36
    for name, value in loop_values(snap).items():
        c = ws.cell(row=SUMMARY_ROW[name], column=4, value=value)
        c.alignment = Alignment(horizontal="right")
        if name == "unknown_rate" and value != "":
            c.number_format = "0.0%"
        if isinstance(value, str):
            c.data_type = "s"

    ws["A22"] = title
    ws["A22"].font = Font(bold=True)
    ws["A23"] = ("Demo export: sim/demo_scenario.py on the mock model, written by "
                 "scripts/export_demo_to_sheet.py. Column B is live formulas; column D is what the "
                 "loop computed at this stage and should match B (tickets_overdue and "
                 "urgent_devices have no loop counterpart; tickets_overdue depends on TODAY()).")
    note = ["Extra columns (grey headers) hold simulator columns the template doesn't have; "
            "they sit to the right of the template's columns:"]
    for tab, cols in extras.items():
        if cols:
            first = get_column_letter(len(TABS[tab][0]) + 1)
            last = get_column_letter(len(TABS[tab][0]) + len(cols))
            note.append(f"{tab} {first}:{last} = {', '.join(cols)}.")
    ws["A24"] = " ".join(note)
    ws["A25"] = ("Settings tab: the template's keys, not the simulator's settings.csv (listed below). "
                 "Timestamps are UTC.")
    for a in ("A23", "A24", "A25"):
        ws[a].alignment = Alignment(wrap_text=False)

    ws["A27"], ws["B27"], ws["C27"] = "loop metric (sim/loop.py compute_metrics)", "value", "numerator / denominator"
    for c in ("A27", "B27", "C27"):
        ws[c].font, ws[c].fill = mst.HEADER_FONT, EXTRA_HEADER_FILL
    r = 28
    for k, v in snap["metrics"].items():
        if isinstance(v, dict) and "value" in v:
            val = "" if v["value"] is None else v["value"]
            nd = f"{v['num']} / {v['den']}" if "num" in v and "den" in v else v.get("note", "")
        elif isinstance(v, dict):
            val, nd = "; ".join(f"{a}={b}" for a, b in v.items()), ""
        else:
            val, nd = v, ""
        ws.cell(row=r, column=1, value=k)
        ws.cell(row=r, column=2, value=val).alignment = Alignment(horizontal="right")
        ws.cell(row=r, column=3, value=nd)
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="simulator setting (settings.csv)").font = Font(bold=True)
    for s in snap["settings"]:
        r += 1
        ws.cell(row=r, column=1, value=s["key"])
        c = ws.cell(row=r, column=2, value=s["value"])
        c.data_type = "s"


def build_workbook(snap: dict, title: str):
    wb = mst.new_workbook()
    extras = {tab: fill_tab(wb[tab], tcols, scols, snap[tab]) for tab, (tcols, scols) in TABS.items()}
    approver = next((s["value"] for s in snap["settings"] if s["key"] == "approver_email"), "")
    settings = wb["Settings"]
    for row in settings.iter_rows(min_row=2):
        if row[0].value == "approver_email" and approver:
            row[1].value = approver
    fill_summary(wb["Summary"], title, snap, extras)
    wb.properties.created = wb.properties.modified = FIXED_PROPERTIES_TIME
    return wb


def export(out_dir: Path = DEFAULT_OUT_DIR, quiet: bool = False) -> list[Path]:
    say = (lambda *a: None) if quiet else print
    with tempfile.TemporaryDirectory(prefix="deming-sheet-") as tmp:
        stages = run_stages(Path(tmp) / "staged")
        check_against_run_demo(stages[-1], Path(tmp) / "run_demo")
    say("staged replay matches sim.demo_scenario.run_demo() (run durations excepted)")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for (key, title), snap in zip(STAGES, stages):
        path = out_dir / f"deming_demo_{key}.xlsx"
        build_workbook(snap, title).save(path)
        lv = loop_values(snap)
        say(f"wrote {path}: {len(snap['Inventory'])} devices, {len(snap['Decision Log'])} log rows, "
            f"{len(snap['Tickets'])} tickets, {len(snap['outbox'])} outbox records; "
            f"lanes {', '.join(f'{k[5:]}={lv[k]}' for k in lv if k.startswith('lane_'))}")
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> list[Path]:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = p.parse_args(argv)
    return export(args.out_dir)


if __name__ == "__main__":
    main()
