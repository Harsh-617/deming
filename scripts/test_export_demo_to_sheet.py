"""Read the three demo workbooks back with openpyxl and check them against the loop's own state."""
import datetime as dt
import re
import tempfile
from pathlib import Path

import openpyxl
import pytest

import export_demo_to_sheet as ex
import make_sheet_template as mst

STAGE_KEYS = [k for k, _ in ex.STAGES]
PATHS: dict = {}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    paths = ex.export(out, quiet=True)
    PATHS.update(zip(STAGE_KEYS, paths))
    with tempfile.TemporaryDirectory() as tmp:
        stages = ex.run_stages(Path(tmp) / "s")
    return {k: (openpyxl.load_workbook(p), snap) for k, p, snap in zip(STAGE_KEYS, paths, stages)}


def header(ws):
    return [c.value for c in ws[1] if c.value is not None]


def as_csv_text(column, v):
    """Turn a read-back cell into the simulator's CSV text, to compare with the state files."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if column in ex.DATETIME_COLS:
        return v.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, float):
        return f"{v:.2f}"
    return v


def test_three_files_with_template_tabs(built):
    assert list(built) == STAGE_KEYS
    for wb, _ in built.values():
        assert wb.sheetnames == ["Inventory", "Decision Log", "Settings", "Tickets", "Summary"]
        for name in wb.sheetnames:
            assert wb[name].freeze_panes == "A2", name


def test_headers_are_exactly_the_template(built):
    """Contracts 1.3 columns are template columns now: no extra (grey) columns in any tab."""
    for wb, _ in built.values():
        assert header(wb["Inventory"]) == mst.INVENTORY
        assert header(wb["Decision Log"]) == mst.DECISION_LOG
        assert header(wb["Tickets"]) == mst.TICKETS
        assert "no extra columns" in wb["Summary"]["A24"].value


def test_extra_columns_still_go_right_if_the_simulator_adds_one():
    wb = mst.new_workbook()
    extras = ex.fill_tab(wb["Tickets"], mst.TICKETS, mst.TICKETS + ["new_col"], [{"new_col": "x"}])
    assert extras == ["new_col"]
    assert wb["Tickets"].cell(row=1, column=len(mst.TICKETS) + 1).value == "new_col"


def test_cells_round_trip_to_the_state_files(built):
    for key, (wb, snap) in built.items():
        for tab in ex.TABS:
            ws = wb[tab]
            cols = header(ws)
            rows = list(ws.iter_rows(min_row=2, values_only=True))
            assert len(rows) == len(snap[tab]), (key, tab)
            for got, want in zip(rows, snap[tab]):
                assert {c: as_csv_text(c, v) for c, v in zip(cols, got)} == \
                       {c: want.get(c, "") for c in cols}, (key, tab)


def test_types_dates_versions_booleans(built):
    wb, _ = built["3_after_rerun"]
    inv = wb["Inventory"]
    cols = header(inv)
    for row in inv.iter_rows(min_row=2):
        cell = dict(zip(cols, row))
        assert isinstance(cell["last_updated"].value, dt.datetime)
        assert cell["last_updated"].number_format == "yyyy-mm-dd"
        assert isinstance(cell["internet_facing"].value, bool)
        assert isinstance(cell["do_not_touch"].value, bool)
        for c in ("firmware_version_raw", "version"):
            if cell[c].value is not None:
                assert isinstance(cell[c].value, str) and cell[c].number_format == "@", c
    fw = {r[0]: r[cols.index("firmware_version_raw")] for r in inv.iter_rows(min_row=2, values_only=True)}
    assert fw["DEV-101"] == "7.0.14" and fw["DEV-104"] == "7.0.12" and fw["DEV-105"] == "002.2310A"

    t = wb["Tickets"]
    tc = header(t)
    for row in t.iter_rows(min_row=2):
        cell = dict(zip(tc, row))
        for c in ("opened", "last_updated_at_open"):
            assert isinstance(cell[c].value, dt.datetime), c
        # identify tickets have no deadline; the others carry a real date
        assert isinstance(cell["due"].value, dt.datetime) or cell["issue"].value == "identify"
        for c in ("fixed_version", "firmware_at_open"):
            assert cell[c].value is None or (isinstance(cell[c].value, str) and cell[c].number_format == "@")
    log = wb["Decision Log"]
    assert all(isinstance(r[0], dt.datetime) for r in log.iter_rows(min_row=2, values_only=True))


def test_no_formulas_outside_summary(built):
    for wb, _ in built.values():
        for name in ("Inventory", "Decision Log", "Settings", "Tickets"):
            for row in wb[name].iter_rows():
                for c in row:
                    assert c.data_type != "f", (name, c.coordinate)


def test_values_fit_the_template_validation(built):
    for wb, _ in built.values():
        log = wb["Decision Log"]
        # blank lane = verify row of a removed device; the template's lane rule allows blank
        assert {r[3] for r in log.iter_rows(min_row=2, values_only=True)} <= set(mst.LANES) | {None}
        status = mst.TICKETS.index("status")
        assert {r[status] for r in wb["Tickets"].iter_rows(min_row=2, values_only=True)} \
            <= set(mst.TICKET_STATUS)
        inv = wb["Inventory"]
        assert {r[6] for r in inv.iter_rows(min_row=2, values_only=True)} <= set(mst.CRITICALITY)
        assert all(0 <= r[12] <= 1 for r in inv.iter_rows(min_row=2, values_only=True))
        assert len(inv.data_validations.dataValidation) == 4


def test_stage_story(built):
    def tickets(key):
        wb, _ = built[key]
        cols = header(wb["Tickets"])
        return {r[1]: dict(zip(cols, r)) for r in wb["Tickets"].iter_rows(min_row=2, values_only=True)}

    wb1, snap1 = built["1_after_run1"]
    assert tickets("1_after_run1") == {}
    assert [r[8] for r in wb1["Decision Log"].iter_rows(min_row=2, values_only=True)] == \
           ["pending", "pending", "pending", "pending", "n/a"]
    assert snap1["outbox"] == []

    t2 = tickets("2_after_approval")
    assert {d: t["status"] for d, t in t2.items()} == dict.fromkeys(
        ["DEV-101", "DEV-102", "DEV-103", "DEV-104"], "open")
    wb2, _ = built["2_after_approval"]
    log2 = list(wb2["Decision Log"].iter_rows(min_row=2, values_only=True))
    assert [(r[7], r[8]) for r in log2[:4]] == [("approver@example.org", "approved")] * 4

    t3 = tickets("3_after_rerun")
    assert {d: t["status"] for d, t in t3.items()} == {
        "DEV-101": "closed", "DEV-102": "closed", "DEV-103": "open", "DEV-104": "escalated"}
    assert t3["DEV-104"]["flags"] == "still_vulnerable"
    assert "confirms the record only, not the device" in t3["DEV-101"]["last_note"]
    wb3, _ = built["3_after_rerun"]
    assert "DEV-102" not in [r[0] for r in wb3["Inventory"].iter_rows(min_row=2, values_only=True)]


def test_settings_tab_holds_the_simulator_settings(built):
    for wb, snap in built.values():
        s = {r[0]: r[1] for r in wb["Settings"].iter_rows(min_row=2, values_only=True)}
        assert s["approver_email"] == "approver@example.org"
        assert {k: "" if v is None else str(v) for k, v in s.items()} == \
               {r["key"]: r["value"] for r in snap["settings"]}


def test_removed_device_has_blank_lane_in_stage_3(built):
    wb, _ = built["3_after_rerun"]
    rows = [r for r in wb["Decision Log"].iter_rows(min_row=2, values_only=True)
            if r[2] == "DEV-102" and r[6] == "verify"]
    assert rows and all(r[3] is None and r[10] == "device_removed" for r in rows)


def mirror(wb, name):
    """Python reading of each Summary formula over the read-back cells."""
    log = list(wb["Decision Log"].iter_rows(min_row=2, values_only=True))
    tk = list(wb["Tickets"].iter_rows(min_row=2, values_only=True))
    st = mst.TICKETS.index("status")
    inv = list(wb["Inventory"].iter_rows(min_row=2, values_only=True))
    latest = log[-1][1] if log else ""
    lanes = {l: sum(r[1] == latest and r[3] == l and r[6] not in ("verify", "remind") for r in log)
             for l in mst.LANES}
    decided = sum(lanes.values())
    return {"latest_run_id": latest, "devices_in_inventory": len(inv),
            **{f"lane_{k}": v for k, v in lanes.items()},
            "devices_decided_latest_run": decided,
            "unknown_rate": lanes["unknown"] / decided if decided else "",
            "tickets_open": sum(r[st] == "open" for r in tk),
            "tickets_escalated": sum(r[st] == "escalated" for r in tk),
            "tickets_closed": sum(r[st] == "closed" for r in tk)}[name]


def test_summary_loop_column_matches_formula_logic(built):
    """Column D (loop values) equals the formulas' logic applied to the written cells."""
    for key, (wb, snap) in built.items():
        ws = wb["Summary"]
        loop_vals = ex.loop_values(snap)
        for name, row in ex.SUMMARY_ROW.items():
            assert ws.cell(row=row, column=1).value == name
            assert str(ws.cell(row=row, column=2).value).startswith("=")
            if name in loop_vals:
                assert ws.cell(row=row, column=4).value == loop_vals[name] == mirror(wb, name), (key, name)
        tk = snap["metrics"]["tickets"]
        assert (loop_vals["tickets_open"], loop_vals["tickets_escalated"], loop_vals["tickets_closed"]) == \
               (tk["open"], tk["escalated"], tk["closed"])
    assert ex.loop_values(built["3_after_rerun"][1])["devices_decided_latest_run"] == 4


def test_summary_formulas_evaluate_to_loop_values(built, tmp_path):
    """Evaluate column B with the `formulas` package (not in requirements; skipped if absent)."""
    formulas = pytest.importorskip("formulas")
    for key in built:
        wb = openpyxl.load_workbook(PATHS[key])  # a fresh copy: the fixture's stays untouched
        ws = wb["Summary"]
        for r in range(2, 15):  # whole-column INDEX is #VALUE! in `formulas`; bound the ranges
            c = ws.cell(row=r, column=2)
            c.value = re.sub(r"(!|[^A-Z])\$?([A-Z]{1,2}):\$?([A-Z]{1,2})(?![0-9])",
                             lambda m: f"{m.group(1)}{m.group(2)}1:{m.group(3)}500", c.value)
        path = tmp_path / f"{key}.xlsx"
        wb.save(path)
        sol = formulas.ExcelModel().loads(str(path)).finish().calculate()
        for name, row in ex.SUMMARY_ROW.items():
            want = ws.cell(row=row, column=4).value
            if want is None:
                continue
            got = next(v for k, v in sol.items() if k.upper().endswith(f"SUMMARY'!B{row}")).value[0, 0]
            assert got == pytest.approx(want) if not isinstance(want, str) else got == want, (key, name)
