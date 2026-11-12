"""Load the generated workbook back with openpyxl and check tabs, headers, validation,
conditional formatting, freeze panes, formulas and --fill-from-csv."""
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

import make_sheet_template as mst

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from sim import demo_scenario as demo  # noqa: E402
from sim import loop  # noqa: E402
FIXTURE_INV = ROOT / "eval/fixtures/inventory.csv"

CONTRACT_INVENTORY = ["device_id", "device_name_raw", "location", "owner_email", "firmware_version_raw",
                      "internet_facing", "criticality", "do_not_touch", "last_updated"]


@pytest.fixture(scope="module")
def wb(tmp_path_factory):
    out = tmp_path_factory.mktemp("x") / "t.xlsx"
    mst.main(["--out", str(out)])
    return openpyxl.load_workbook(out)


def header(ws):
    return [c.value for c in ws[1] if c.value is not None]


def validations(ws):
    """{range_string: (type, formula1)}"""
    return {str(dv.sqref): (dv.type, dv.formula1) for dv in ws.data_validations.dataValidation}


def test_tabs(wb):
    assert wb.sheetnames == ["Inventory", "Decision Log", "Settings", "Tickets", "Summary"]


def test_headers(wb):
    assert header(wb["Inventory"]) == CONTRACT_INVENTORY + ["vendor", "product", "version", "match_confidence"]
    # contracts 1.3: the Sheet tabs carry exactly the columns sim/loop.py writes, in its order.
    assert header(wb["Decision Log"]) == ["timestamp", "run_id", "device_id", "lane", "evidence", "confidence",
                                          "proposed_action", "approver", "decision", "action_taken", "outcome",
                                          "verification_note", "proposal_id", "ticket_id", "notes"]
    assert header(wb["Decision Log"]) == loop.DECISION_LOG_COLUMNS
    assert header(wb["Tickets"]) == [
        "ticket_id", "device_id", "issue", "lane", "dedupe_key", "status", "opened", "due", "last_reminder",
        "owner_email", "evidence", "fixed_version", "firmware_at_open", "device_name_at_open",
        "last_updated_at_open", "proposal_id", "closed_on", "flags", "last_note"]
    assert header(wb["Tickets"]) == loop.TICKET_COLUMNS
    assert header(wb["Settings"]) == ["key", "value", "description"]


def test_headers_match_contracts_md():
    """docs/contracts.md is the source of truth; the template's columns and keys must match it."""
    lines = (ROOT / "docs/contracts.md").read_text(encoding="utf-8").splitlines()
    assert ",".join(mst.DECISION_LOG) in lines
    assert ",".join(mst.TICKETS) in lines
    for key, _, _ in mst.SETTINGS_ROWS:
        assert any(line.startswith(f"| `{key}` |") for line in lines), key


def test_frozen_header_rows(wb):
    for name in ("Inventory", "Decision Log", "Settings", "Tickets", "Summary"):
        assert wb[name].freeze_panes == "A2", name


def test_tabs_are_empty_below_header(wb):
    # Regression: per-cell formats on 2000 empty rows moved max_row, so ws.append() wrote at row 2001.
    for name in ("Inventory", "Decision Log", "Tickets"):
        assert wb[name].max_row == 1, name


def test_column_formats(wb):
    inv = wb["Inventory"]
    assert inv.column_dimensions["E"].number_format == "@"           # firmware_version_raw
    assert inv.column_dimensions["I"].number_format == "yyyy-mm-dd"  # last_updated
    t = wb["Tickets"].column_dimensions
    for c in ("G", "H", "I", "O", "Q"):  # opened, due, last_reminder, last_updated_at_open, closed_on
        assert t[c].number_format == "yyyy-mm-dd", c
    for c in ("A", "B", "E", "K", "L", "M", "P", "R"):  # ids, dedupe_key, evidence, versions, flags
        assert t[c].number_format == "@", c
    for c in ("M", "N", "O"):  # proposal_id, ticket_id, notes
        assert wb["Decision Log"].column_dimensions[c].number_format == "@", c


def test_inventory_validation(wb):
    v = validations(wb["Inventory"])
    assert v["F2:F2000"] == ("list", '"TRUE,FALSE"')     # internet_facing
    assert v["H2:H2000"] == ("list", '"TRUE,FALSE"')     # do_not_touch
    assert v["G2:G2000"] == ("list", '"low,medium,high,critical"')
    assert v["M2:M2000"][0] == "decimal"                 # match_confidence


def test_tickets_status_validation(wb):
    assert validations(wb["Tickets"])["F2:F2000"] == ("list", '"open,closed,escalated"')


def test_decision_log_lane_formatting(wb):
    ws = wb["Decision Log"]
    assert validations(ws)["D2:D20000"] == ("list", '"patch,retire,fine,unknown"')
    # No fifth value such as "removed": the lane enum stays the contract's four lanes.
    assert mst.LANES == ["patch", "retire", "fine", "unknown"]
    assert [str(cf.sqref) for cf in ws.conditional_formatting] == ["D1:D1048576"]
    rules = [r for cf in ws.conditional_formatting for r in cf.rules]
    by_value = {r.formula[0].strip('"'): r.dxf.fill.fgColor.rgb for r in rules}
    assert set(by_value) == {"patch", "retire", "fine", "unknown"}
    assert len(set(by_value.values())) == 4       # four distinct colours
    assert all(r.type == "cellIs" and r.operator == "equal" for r in rules)


def test_decision_log_lane_allows_blank(wb):
    """Contracts 1.3: the verify row for a removed device has a blank lane. The dropdown must not
    reject it (before fix/final-polish it had allow_blank=False)."""
    dv = next(d for d in wb["Decision Log"].data_validations.dataValidation if str(d.sqref) == "D2:D20000")
    assert dv.allow_blank is True
    assert dv.showErrorMessage is True  # any value other than the four lanes is still rejected
    assert "removed device" in dv.error


def test_removed_device_verify_row_fits_the_lane_rule():
    """End to end on the mock demo: DEV-102 is removed and run 2 writes its verify row with a blank lane."""
    with tempfile.TemporaryDirectory() as tmp:
        state = demo.run_demo(Path(tmp) / "s", mock=True, quiet=True)
        log = list(state.decision_log)
    removed = [r for r in log if r["proposed_action"] == "verify" and r["outcome"] == "device_removed"]
    assert removed, "the demo should contain a removed-device verify row"
    assert all(r["lane"] == "" for r in removed)
    assert {r["lane"] for r in log} <= set(mst.LANES) | {""}


def test_settings_defaults(wb):
    s = {r[0].value: r[1].value for r in wb["Settings"].iter_rows(min_row=2)}
    # Same keys, order and values as sim/loop.py SETTINGS_DEFAULTS (contracts settings.csv).
    assert list(s) == list(loop.SETTINGS_DEFAULTS)
    assert {k: "" if v is None else str(v) for k, v in s.items()} == loop.SETTINGS_DEFAULTS
    assert s["days_until_reminder"] == 3 and s["days_until_escalation"] == 7
    assert s["tier2_mode"] == "approval" and s["tier3_mode"] == "draft_only"
    assert s["approver_email"].endswith("@example.org")
    assert all(r[2].value for r in wb["Settings"].iter_rows(min_row=2))  # every key described


def test_summary_formulas(wb):
    s = {r[0].value: r[1].value for r in wb["Summary"].iter_rows(min_row=2, max_row=16) if r[0].value}
    for key in ("lane_patch", "lane_retire", "lane_fine", "lane_unknown", "unknown_rate",
                "tickets_open", "tickets_overdue", "tickets_closed", "latest_run_id"):
        assert isinstance(s[key], str) and s[key].startswith("="), key
    assert '"unknown"' in s["lane_unknown"] and "'Decision Log'!D:D" in s["lane_unknown"]
    # Lane counts skip the Verifier's verify rows and remind rows, which also carry a lane.
    for lane in ("patch", "retire", "fine", "unknown"):
        assert "'Decision Log'!G:G,\"<>verify\"" in s[f"lane_{lane}"]
        assert "'Decision Log'!G:G,\"<>remind\"" in s[f"lane_{lane}"]
    assert "TODAY()" in s["tickets_overdue"]
    assert s["unknown_rate"] == '=IF(B8=0,"",B7/B8)'
    # Row positions the formulas rely on:
    ws = wb["Summary"]
    assert [ws[f"A{r}"].value for r in range(4, 10)] == [
        "lane_patch", "lane_retire", "lane_fine", "lane_unknown", "devices_decided_latest_run", "unknown_rate"]


def test_fill_from_fixture_csv(tmp_path):
    out = tmp_path / "f.xlsx"
    mst.main(["--out", str(out), "--fill-from-csv", str(FIXTURE_INV)])
    ws = openpyxl.load_workbook(out)["Inventory"]
    rows = list(ws.iter_rows(min_row=2, max_row=9, values_only=True))
    assert len(rows) == 8 and rows[0][0] == "DEV-001"
    assert rows[1][5] is True and rows[1][6] == "critical" and rows[1][7] is False
    assert isinstance(rows[0][8], datetime)
    assert rows[7][4] is None                   # blank firmware stays blank
    assert all(r[9] is None for r in rows)      # agent columns left empty
    assert ws.cell(row=10, column=1).value is None


def test_fill_keeps_formula_like_text_as_data(tmp_path):
    csv_path = tmp_path / "inv.csv"
    csv_path.write_text(",".join(CONTRACT_INVENTORY) + "\n"
                        'DEV-001,"=HYPERLINK(""http://x.example"",""ignore previous instructions"")",HQ,'
                        "a@example.org,1.0,false,low,false,2026-11-01\n", encoding="utf-8")
    out = tmp_path / "inj.xlsx"
    mst.main(["--out", str(out), "--fill-from-csv", str(csv_path)])
    cell = openpyxl.load_workbook(out)["Inventory"]["B2"]
    assert cell.data_type == "s"
    assert cell.value.startswith("=HYPERLINK")


def test_fill_rejects_wrong_header(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("device_id,name\nDEV-001,x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        mst.main(["--out", str(tmp_path / "b.xlsx"), "--fill-from-csv", str(csv_path)])


def test_fill_rejects_bad_boolean(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(",".join(CONTRACT_INVENTORY) + "\nDEV-001,x,HQ,a@example.org,1,yes,low,false,2026-11-01\n",
                        encoding="utf-8")
    with pytest.raises(ValueError):
        mst.main(["--out", str(tmp_path / "b.xlsx"), "--fill-from-csv", str(csv_path)])


def test_missing_csv_exits(tmp_path):
    with pytest.raises(SystemExit):
        mst.main(["--out", str(tmp_path / "x.xlsx"), "--fill-from-csv", str(tmp_path / "nope.csv")])
