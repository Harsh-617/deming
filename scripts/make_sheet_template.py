"""Build sheet/deming_template.xlsx: the Deming Google Sheet as an .xlsx to import.

Tabs: Inventory, Decision Log, Settings, Tickets, Summary. Columns follow docs/contracts.md
(Inventory) and docs/PRD.md "Data model" (the rest).

Only features that map 1:1 to Google Sheets are used (see docs/decisions/feat-eval.md):
list-type data validation with inline items, "cell is equal to" conditional formatting,
frozen first row, and plain COUNTIF/COUNTIFS/INDEX/COUNTA/IF/TODAY formulas. No Excel tables,
named ranges, structured references, dynamic arrays or macros.

  python scripts/make_sheet_template.py                       # empty template
  python scripts/make_sheet_template.py --fill-from-csv       # + rows from data/inventory.csv
  python scripts/make_sheet_template.py --fill-from-csv path/to/inventory.csv --out other.xlsx

Device fields are DATA: every inventory value is written as a literal string/bool/date, never
as a formula, even if it starts with '=' (injection test rows).
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "sheet/deming_template.xlsx"
DEFAULT_CSV = REPO / "data/inventory.csv"
MAX_ROW = 2000  # validation range for Inventory / Tickets
LOG_MAX_ROW = 20000  # Decision Log grows ~60 rows per hourly run

INVENTORY_INPUT = ["device_id", "device_name_raw", "location", "owner_email", "firmware_version_raw",
                   "internet_facing", "criticality", "do_not_touch", "last_updated"]
INVENTORY_AGENT = ["vendor", "product", "version", "match_confidence"]
INVENTORY = INVENTORY_INPUT + INVENTORY_AGENT
DECISION_LOG = ["timestamp", "run_id", "device_id", "lane", "evidence", "confidence", "proposed_action",
                "approver", "decision", "action_taken", "outcome", "verification_note"]
TICKETS = ["ticket_id", "device_id", "issue", "status", "opened", "due", "last_reminder"]
SETTINGS = ["key", "value", "description"]

LANES = ["patch", "retire", "fine", "unknown"]
# contracts.md v1 allows `critical` too; dropping it would mark valid inventory rows invalid.
CRITICALITY = ["low", "medium", "high", "critical"]
TICKET_STATUS = ["open", "closed", "escalated"]

# Distinct, readable fills (light backgrounds, dark text).
LANE_COLOURS = {"patch": "FFF4B183", "retire": "FFF8A5A5", "fine": "FFB6E3B6", "unknown": "FFC9C9C9"}
HEADER_FILL = PatternFill("solid", fgColor="FF1F3864")
AGENT_HEADER_FILL = PatternFill("solid", fgColor="FF5B6F8F")
HEADER_FONT = Font(bold=True, color="FFFFFFFF")

SETTINGS_ROWS = [
    ("urgent_rule", "internet_facing = TRUE AND criticality in (high, critical)",
     "Which devices count as urgent. Default: internet-facing and high (or critical) criticality."),
    ("reminder_after_days", 3, "Days after a ticket's due date before the owner is reminded."),
    ("escalation_after_days", 7, "Days after a ticket's due date before it is escalated to the approver."),
    ("tier0_read_only", "auto", "Tier 0: read inventory and feeds. Always automatic."),
    ("tier1_draft", "auto", "Tier 1: draft messages and proposals. Automatic."),
    ("tier2_outward", "approval_required",
     "Tier 2: email, calendar, ticket. Needs recorded human approval (suggest-only)."),
    ("tier3_consequential", "draft_only",
     "Tier 3: isolate, disconnect, replace. Agent only drafts; a named human decides."),
    ("approver_email", None, "Who approves tier 2/3 actions. Fill in before the first run."),
    ("digest_channel", None, "Chat space for the run digest. Blank = no digest."),
]


def style_header(ws, columns: list[str], agent_cols: set[str] = frozenset()) -> None:
    ws.append(columns)
    for i, name in enumerate(columns, start=1):
        c = ws.cell(row=1, column=i)
        c.font = HEADER_FONT
        c.fill = AGENT_HEADER_FILL if name in agent_cols else HEADER_FILL
        c.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(40, len(name) + 4))
    ws.freeze_panes = "A2"


def col(columns: list[str], name: str) -> str:
    return get_column_letter(columns.index(name) + 1)


def add_list_validation(ws, columns: list[str], name: str, items: list[str], allow_blank=True,
                        max_row: int = MAX_ROW) -> None:
    letter = col(columns, name)
    dv = DataValidation(type="list", formula1='"' + ",".join(items) + '"', allow_blank=allow_blank,
                        showErrorMessage=True, errorTitle="Invalid value",
                        error=f"{name} must be one of: {', '.join(items)}")
    dv.add(f"{letter}2:{letter}{max_row}")
    ws.add_data_validation(dv)


def _column_format(ws, columns: list[str], names: list[str], fmt: str) -> None:
    """Column-level number format (a <col style>), NOT per-cell: touching thousands of empty
    cells would move ws.max_row, so appends from openpyxl-based writers would land below them."""
    for name in names:
        ws.column_dimensions[col(columns, name)].number_format = fmt


def text_format(ws, columns: list[str], names: list[str]) -> None:
    """Keep versions/ids as text so '7.0' or '22.3' typed later don't turn into numbers."""
    _column_format(ws, columns, names, "@")


def date_format(ws, columns: list[str], names: list[str], fmt="yyyy-mm-dd") -> None:
    _column_format(ws, columns, names, fmt)


def build_inventory(wb: Workbook):
    ws = wb.active
    ws.title = "Inventory"
    style_header(ws, INVENTORY, set(INVENTORY_AGENT))
    # Booleans: real TRUE/FALSE values, which both Excel and Sheets treat as booleans.
    add_list_validation(ws, INVENTORY, "internet_facing", ["TRUE", "FALSE"], allow_blank=False)
    add_list_validation(ws, INVENTORY, "do_not_touch", ["TRUE", "FALSE"], allow_blank=False)
    add_list_validation(ws, INVENTORY, "criticality", CRITICALITY, allow_blank=False)
    conf = col(INVENTORY, "match_confidence")
    dv = DataValidation(type="decimal", operator="between", formula1="0", formula2="1", allow_blank=True,
                        showErrorMessage=True, error="match_confidence is a decimal from 0 to 1")
    dv.add(f"{conf}2:{conf}{MAX_ROW}")
    ws.add_data_validation(dv)
    text_format(ws, INVENTORY, ["device_id", "firmware_version_raw", "version"])
    date_format(ws, INVENTORY, ["last_updated"])
    _column_format(ws, INVENTORY, ["match_confidence"], "0.00")
    return ws


def build_decision_log(wb: Workbook):
    ws = wb.create_sheet("Decision Log")
    style_header(ws, DECISION_LOG)
    add_list_validation(ws, DECISION_LOG, "lane", LANES, allow_blank=False, max_row=LOG_MAX_ROW)
    lane = col(DECISION_LOG, "lane")
    rng = f"{lane}1:{lane}1048576"  # whole column; the header text 'lane' matches no rule
    for name, colour in LANE_COLOURS.items():
        fill = PatternFill("solid", start_color=colour, end_color=colour)
        ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[f'"{name}"'], fill=fill))
    text_format(ws, DECISION_LOG, ["run_id", "device_id", "evidence"])
    return ws


def build_settings(wb: Workbook):
    ws = wb.create_sheet("Settings")
    style_header(ws, SETTINGS)
    for row in SETTINGS_ROWS:
        ws.append(list(row))
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 55
    ws.column_dimensions["C"].width = 80
    return ws


def build_tickets(wb: Workbook):
    ws = wb.create_sheet("Tickets")
    style_header(ws, TICKETS)
    add_list_validation(ws, TICKETS, "status", TICKET_STATUS, allow_blank=False)
    text_format(ws, TICKETS, ["ticket_id", "device_id"])
    date_format(ws, TICKETS, ["opened", "due", "last_reminder"])
    return ws


def build_summary(wb: Workbook):
    """Formulas only; Sheets recalculates them on import. Lane counts use the LATEST run_id
    (last non-blank row of Decision Log), so repeated runs aren't double-counted."""
    ws = wb.create_sheet("Summary")
    dl = "'Decision Log'"
    lane_c, run_c = col(DECISION_LOG, "lane"), col(DECISION_LOG, "run_id")
    st_c, due_c = col(TICKETS, "status"), col(TICKETS, "due")
    inet_c, crit_c = col(INVENTORY, "internet_facing"), col(INVENTORY, "criticality")
    run_rng, lane_rng = f"{dl}!{run_c}:{run_c}", f"{dl}!{lane_c}:{lane_c}"

    ws.append(["metric", "value", "how it is computed"])
    for i in (1, 2, 3):
        c = ws.cell(row=1, column=i)
        c.font, c.fill = HEADER_FONT, HEADER_FILL
    ws.freeze_panes = "A2"
    rows = [
        ("latest_run_id", f'=IF(COUNTA({run_rng})<2,"",INDEX({run_rng},COUNTA({run_rng})))',
         "run_id in the last filled Decision Log row (rows are appended in run order)"),
        ("devices_in_inventory", "=MAX(COUNTA(Inventory!A:A)-1,0)", "Inventory rows below the header"),
    ]
    for lane in LANES:
        rows.append((f"lane_{lane}", f'=IF($B$2="",0,COUNTIFS({lane_rng},"{lane}",{run_rng},$B$2))',
                     f"Decision Log rows in the latest run with lane = {lane}"))
    rows += [
        ("devices_decided_latest_run", "=SUM(B4:B7)", "patch + retire + fine + unknown"),
        ("unknown_rate", '=IF(B8=0,"",B7/B8)', "unknown / devices decided in the latest run"),
        ("tickets_open", f'=COUNTIF(Tickets!{st_c}:{st_c},"open")', "status = open"),
        ("tickets_escalated", f'=COUNTIF(Tickets!{st_c}:{st_c},"escalated")', "status = escalated"),
        ("tickets_overdue",
         f'=COUNTIFS(Tickets!{st_c}:{st_c},"open",Tickets!{due_c}:{due_c},"<"&TODAY())'
         f'+COUNTIFS(Tickets!{st_c}:{st_c},"escalated",Tickets!{due_c}:{due_c},"<"&TODAY())',
         "not closed and due date before today (due must be a real date, not text)"),
        ("tickets_closed", f'=COUNTIF(Tickets!{st_c}:{st_c},"closed")', "status = closed"),
        ("urgent_devices",
         f'=COUNTIFS(Inventory!{inet_c}:{inet_c},TRUE,Inventory!{crit_c}:{crit_c},"high")'
         f'+COUNTIFS(Inventory!{inet_c}:{inet_c},TRUE,Inventory!{crit_c}:{crit_c},"critical")',
         "Settings urgent_rule default: internet-facing and high/critical"),
    ]
    for r in rows:
        ws.append(list(r))
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=2).alignment = Alignment(horizontal="right")
    ws["B9"].number_format = "0.0%"
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 75
    ws["A20"] = "All data in this sheet is synthetic. Counts describe the sheet, not real devices."
    ws["A20"].font = Font(italic=True)
    return ws


def to_cell_value(column: str, raw: str):
    raw = (raw or "").strip()
    if raw == "":
        return None
    if column in ("internet_facing", "do_not_touch"):
        low = raw.casefold()
        if low in ("true", "false"):
            return low == "true"
        raise ValueError(f"{column}: expected true/false, got {raw!r}")
    if column == "last_updated":
        return date.fromisoformat(raw)
    return raw


def fill_inventory(ws, csv_path: Path) -> int:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != INVENTORY_INPUT:
            raise ValueError(f"{csv_path}: header {reader.fieldnames} != contract {INVENTORY_INPUT}")
        n = 0
        for n, row in enumerate(reader, start=1):
            r = n + 1
            for i, name in enumerate(INVENTORY_INPUT, start=1):
                cell = ws.cell(row=r, column=i)
                cell.value = to_cell_value(name, row.get(name, ""))
                if isinstance(cell.value, str):
                    cell.data_type = "s"  # never a formula, even if it starts with '='
                    cell.number_format = "@"
                elif name == "last_updated" and cell.value is not None:
                    cell.number_format = "yyyy-mm-dd"
    return n


def build(out: Path = DEFAULT_OUT, fill_csv: Path | None = None) -> Path:
    wb = Workbook()
    inv = build_inventory(wb)
    build_decision_log(wb)
    build_settings(wb)
    build_tickets(wb)
    build_summary(wb)
    if fill_csv is not None:
        n = fill_inventory(inv, fill_csv)
        print(f"filled Inventory with {n} rows from {fill_csv}")
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"wrote {out}")
    return out


def main(argv: list[str] | None = None) -> Path:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--fill-from-csv", nargs="?", type=Path, const=DEFAULT_CSV, default=None,
                   metavar="CSV", help=f"load inventory rows (default {DEFAULT_CSV.relative_to(REPO).as_posix()})")
    args = p.parse_args(argv)
    if args.fill_from_csv is not None and not args.fill_from_csv.exists():
        sys.exit(f"{args.fill_from_csv} does not exist yet (another branch builds it). "
                 "Run without --fill-from-csv, or pass --fill-from-csv <path>.")
    return build(args.out, args.fill_from_csv)


if __name__ == "__main__":
    main()
