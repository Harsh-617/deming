"""Deterministic firmware vs fixed_version comparison in sim/guards.py, and as_of_date wiring."""
import json

import pytest

from sim import config, guards, retrieval
from sim.models import CheckerOutput

SW = "model_pattern is a version glob (software train)."
ROW = {"lifecycle_id": "LC-030", "vendor": "DrayTek", "product": "Vigor Routers",
       "model_pattern": "Vigor2960*", "notes": "", "fixed_version": "1.5.1.5",
       "eol_date": "2021-12-09", "last_security_support_date": "2026-12-09"}
KEV = [{"cveID": "CVE-2024-12987", "vendorProject": "DrayTek", "product": "Vigor Routers",
        "dueDate": "2025-03-03"}]


def dev(fw, model="Vigor2960"):
    return {"device_id": "DEV-001", "vendor": "DrayTek", "product": "Vigor Routers",
            "model": model, "version": None, "firmware_version_raw": fw}


def check(lane, cves=(), lc=None):
    return CheckerOutput(device_id="DEV-001", lane=lane, evidence_cve=list(cves),
                         evidence_lifecycle_id=lc, due_date=None, confidence=0.95,
                         injection_detected=False, reason="model reason.")


@pytest.mark.parametrize("s,parsed", [
    ("1.5.1.5", (1, 5, 1, 5)), ("v1.4.2.22", (1, 4, 2, 22)), ("V1.4.2.22", (1, 4, 2, 22)),
    ("1.0.03.26", (1, 0, 3, 26)), (" 7.4 ", (7, 4)), ("1.5.1.0", (1, 5, 1)), ("0", (0,)),
    ("7.0.12 build 523", None), ("11.1.4-h13", None), ("13.0-92.19", None),
    ("7.0.1-5161", None), ("22.7R2.6", None), ("R81.20", None), ("", None), (None, None),
    ("1..2", None), ("1.2.", None), (".1", None), ("vv1.2", None), ("1.2 beta", None),
    ("１.２", None),  # full-width digits
    ("1.٢", None),  # Arabic-Indic digit
])
def test_parse_version(s, parsed):
    assert guards.parse_version(s) == parsed


@pytest.mark.parametrize("a,b,expected", [
    ("1.5.1.4", "1.5.1.5", -1), ("1.5.1.5", "1.5.1.5", 0), ("1.5.1.10", "1.5.1.5", 1),
    ("1.5.1", "1.5.1.0", 0), ("v1.4.2.22", "1.4.2.20", 1), ("1.0.03.26", "1.0.3.26", 0),
    ("7.0.12 build 523", "7.0.13", None), ("1.5.1.4", "", None),
])
def test_compare_versions(a, b, expected):
    assert guards.compare_versions(a, b) == expected


def test_model_says_fine_but_firmware_below_fix_overrides_to_patch():
    out, notes = guards.guard_version(check("fine"), dev("1.5.1.4"), KEV, [ROW])
    assert out.lane == "patch" and out.evidence_cve == ["CVE-2024-12987"]
    assert out.evidence_lifecycle_id == "LC-030" and str(out.due_date) == "2025-03-03"
    assert out.reason.startswith("[version guard override]") and "override" in notes[0]


def test_model_says_patch_but_firmware_at_fix_overrides_to_fine():
    out, notes = guards.guard_version(check("patch", ["CVE-2024-12987"], "LC-030"),
                                      dev("v1.5.1.5"), KEV, [ROW])
    assert out.lane == "fine" and out.evidence_cve == [] and out.evidence_lifecycle_id is None
    assert notes and "at or above" in notes[0]


def test_agreeing_lane_is_left_alone():
    c = check("patch", ["CVE-2024-12987"], "LC-030")
    out, notes = guards.guard_version(c, dev("1.5.1.4"), KEV, [ROW])
    assert out == c and notes == []


@pytest.mark.parametrize("fw", ["1.5.1.4 build 99", "fw 1.5.1.4", "1.5.1.4-beta", ""])
def test_messy_firmware_forces_unknown(fw):
    out, notes = guards.guard_version(check("fine"), dev(fw), KEV, [ROW])
    assert out.lane == "unknown" and out.evidence_cve == [] and out.due_date is None
    assert "does not parse" in notes[0]


def test_messy_fixed_version_forces_unknown():
    row = {**ROW, "fixed_version": "11.1.4-h13"}
    out, _ = guards.guard_version(check("patch", ["CVE-2024-12987"], "LC-030"),
                                  dev("1.5.1.4"), KEV, [row])
    assert out.lane == "unknown"


def test_blank_fixed_version_is_unknown_never_fine():
    row = {**ROW, "fixed_version": ""}
    for c in (check("fine"), check("patch", ["CVE-2024-12987"], "LC-030")):
        out, notes = guards.guard_version(c, dev("1.5.1.4"), KEV, [row])
        assert out.lane == "unknown" and "fixed version not documented" in out.reason
        assert "fixed version not documented" in notes[0]


def test_retire_and_unknown_are_not_touched():
    for c in (check("retire", [], "LC-030"), check("unknown")):
        assert guards.guard_version(c, dev("1.5.1.4"), KEV, [ROW]) == (c, [])


def test_not_kev_listed_is_not_touched():
    c = check("fine")
    assert guards.guard_version(c, dev("1.5.1.4"), [], [ROW]) == (c, [])


def test_no_matching_lifecycle_row_is_not_touched():
    c = check("fine")
    assert guards.guard_version(c, dev("1.5.1.4", model="Vigor2925"), KEV, [ROW]) == (c, [])


def test_software_row_uses_version_glob_and_most_specific_row():
    rows = [{"lifecycle_id": "LC-091", "vendor": "Fortinet", "product": "FortiOS",
             "model_pattern": "7.*", "notes": SW, "fixed_version": ""},
            {"lifecycle_id": "LC-020", "vendor": "Fortinet", "product": "FortiOS",
             "model_pattern": "7.4.*", "notes": SW, "fixed_version": "7.4.3"}]
    kev = [{"cveID": "CVE-2024-21762", "vendorProject": "Fortinet", "product": "FortiOS",
            "dueDate": "2024-02-16"}]
    d = {"vendor": "Fortinet", "product": "FortiOS", "version": "7.4.2",
         "firmware_version_raw": "7.4.2"}
    cands = retrieval.lifecycle_candidates(d, rows)
    assert cands[0]["lifecycle_id"] == "LC-020"
    out, _ = guards.guard_version(check("fine"), d, kev, cands)
    assert out.lane == "patch" and out.evidence_lifecycle_id == "LC-020"


def test_guard_checker_runs_version_guard_when_device_given():
    out, notes = guards.guard_checker(check("fine"), KEV, [ROW], device=dev("1.5.1.4"))
    assert out.lane == "patch" and any("version guard" in n for n in notes)
    out, _ = guards.guard_checker(check("fine"), KEV, [ROW])  # no device: old behaviour
    assert out.lane == "fine"


def test_as_of_date_default_and_override(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"as_of_date": "2026-11-12"}), encoding="utf-8")
    assert config.load_as_of_date(path=meta) == "2026-11-12"
    assert config.load_as_of_date("2026-12-10", path=meta) == "2026-12-10"
    with pytest.raises(ValueError):
        config.load_as_of_date("12/10/2026", path=meta)
    assert config.load_as_of_date() == json.loads(
        config.GROUND_TRUTH_META.read_text(encoding="utf-8"))["as_of_date"]
