"""Load the generated workbook back with openpyxl and check tabs, headers, validation,
conditional formatting, freeze panes, formulas and --fill-from-csv."""
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

import make_sheet_template as mst

ROOT = Path(__file__).resolve().parents[1]
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
    assert header(wb["Decision Log"]) == ["timestamp", "run_id", "device_id", "lane", "evidence", "confidence",
                                          "proposed_action", "approver", "decision", "action_taken", "outcome",
                                          "verification_note"]
    assert header(wb["Tickets"]) == ["ticket_id", "device_id", "issue", "status", "opened", "due", "last_reminder"]
    assert header(wb["Settings"]) == ["key", "value", "description"]


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
    assert wb["Tickets"].column_dimensions["F"].number_format == "yyyy-mm-dd"


def test_inventory_validation(wb):
    v = validations(wb["Inventory"])
    assert v["F2:F2000"] == ("list", '"TRUE,FALSE"')     # internet_facing
    assert v["H2:H2000"] == ("list", '"TRUE,FALSE"')     # do_not_touch
    assert v["G2:G2000"] == ("list", '"low,medium,high,critical"')
    assert v["M2:M2000"][0] == "decimal"                 # match_confidence


def test_tickets_status_validation(wb):
    assert validations(wb["Tickets"])["D2:D2000"] == ("list", '"open,closed,escalated"')


def test_decision_log_lane_formatting(wb):
    ws = wb["Decision Log"]
    assert validations(ws)["D2:D20000"] == ("list", '"patch,retire,fine,unknown"')
    assert [str(cf.sqref) for cf in ws.conditional_formatting] == ["D1:D1048576"]
    rules = [r for cf in ws.conditional_formatting for r in cf.rules]
    by_value = {r.formula[0].strip('"'): r.dxf.fill.fgColor.rgb for r in rules}
    assert set(by_value) == {"patch", "retire", "fine", "unknown"}
    assert len(set(by_value.values())) == 4       # four distinct colours
    assert all(r.type == "cellIs" and r.operator == "equal" for r in rules)


def test_settings_defaults(wb):
    s = {r[0].value: r[1].value for r in wb["Settings"].iter_rows(min_row=2)}
    assert s["reminder_after_days"] == 3
    assert s["escalation_after_days"] == 7
    assert s["tier2_outward"] == "approval_required"
    assert s["tier3_consequential"] == "draft_only"
    assert s["approver_email"] is None
    assert "internet_facing" in s["urgent_rule"] and "high" in s["urgent_rule"]


def test_summary_formulas(wb):
    s = {r[0].value: r[1].value for r in wb["Summary"].iter_rows(min_row=2, max_row=16) if r[0].value}
    for key in ("lane_patch", "lane_retire", "lane_fine", "lane_unknown", "unknown_rate",
                "tickets_open", "tickets_overdue", "tickets_closed", "latest_run_id"):
        assert isinstance(s[key], str) and s[key].startswith("="), key
    assert '"unknown"' in s["lane_unknown"] and "'Decision Log'!D:D" in s["lane_unknown"]
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
