"""Ivanti Connect Secure (22.7R2.6) and Citrix NetScaler (14.1-47.46) version forms (contracts v1.4).

Exact forms only, ordered as the vendor advisories order them (LC-022 / LC-023 source_url):
Ivanti "22.7R2.5 and earlier" affected, fixed in 22.7R2.6; Citrix "14.1 BEFORE 14.1-47.46" affected,
"14.1-47.46 and later releases" fixed. Uses the real data/ rows for DEV-009, 034, 021, 050.
"""
import csv

import pytest

from sim import config, guards, retrieval
from sim.models import CheckerOutput

DATA = config.ROOT / "data"
INV = {r["device_id"]: r for r in csv.DictReader(open(DATA / "inventory.csv", encoding="utf-8", newline=""))}
GT = {r["device_id"]: r for r in csv.DictReader(open(DATA / "ground_truth.csv", encoding="utf-8", newline=""))}
LC = {r["lifecycle_id"]: r for r in retrieval.load_lifecycle(DATA / "lifecycle.csv")}
KEV = {v["cveID"]: v for v in retrieval.load_kev(DATA / "feeds" / "kev.json")}
REAL = ["DEV-009", "DEV-034", "DEV-021", "DEV-050"]


@pytest.mark.parametrize("s,family,parsed", [
    ("22.7R2.6", "ivanti", (22, 7, 2, 6)), ("22.7R2.5", "ivanti", (22, 7, 2, 5)),
    ("22.7R2.4", "ivanti", (22, 7, 2, 4)), ("22.7R1.10", "ivanti", (22, 7, 1, 10)),
    ("14.1-47.46", "netscaler", (14, 1, 47, 46)), ("14.1-43.50", "netscaler", (14, 1, 43, 50)),
    ("14.1-29.72", "netscaler", (14, 1, 29, 72)), ("13.1-59.19", "netscaler", (13, 1, 59, 19)),
    ("1.5.1.5", "dotted", (1, 5, 1, 5)), ("11.1.4-h7", "dotted", (11, 1, 4, 7)),
])
def test_exact_forms_parse(s, family, parsed):
    assert guards.parse_version(s) == parsed and guards.version_family(s) == family


@pytest.mark.parametrize("s", [
    # Ivanti near-misses
    "22.7r2.6", "22.7R2", "22.3R1", "v22.7R2.6", "22.7 R2.6", "22.7R2.6.1", "22.7R2.6 build 1",
    "22R2.6", "22.7R.6", "22.7RR2.6", "22.7R2.6a", "9.1x", "9.1R18", "22.7R2.٦",
    # NetScaler near-misses
    "14.1-47", "14.1-47.46-FIPS", "13.1-37.236-FIPS", "14-47.46", "14.1-47.46.1", "v14.1-47.46",
    "14.1 -47.46", "14.1-47-46", "14.1_47.46", "14.1-47.46a", "14.1-h47.46",
    # other vendor suffixes stay out
    "7.0.1-5161", "7.0.12 build 523", "11.1.4-H7",
])
def test_near_misses_do_not_parse(s):
    assert guards.parse_version(s) is None and guards.version_family(s) is None


@pytest.mark.parametrize("a,b,expected", [
    ("22.7R2.5", "22.7R2.6", -1), ("22.7R2.4", "22.7R2.6", -1), ("22.7R2.6", "22.7R2.6", 0),
    ("22.7R2.10", "22.7R2.6", 1), ("22.7R1.9", "22.7R2.6", -1), ("22.7R3.1", "22.7R2.6", 1),
    ("14.1-43.50", "14.1-47.46", -1), ("14.1-29.72", "14.1-47.46", -1),
    ("14.1-47.46", "14.1-47.46", 0), ("14.1-47.100", "14.1-47.46", 1), ("14.1-51.1", "14.1-47.46", 1),
    # never compared across formats, even when the numbers coincide
    ("22.7.2.6", "22.7R2.6", None), ("14.1.47.46", "14.1-47.46", None),
    ("22.7R2.6", "14.1-47.46", None), ("14.1-47.46", "14.1.4-h7", None),
])
def test_compare_within_family_only(a, b, expected):
    assert guards.compare_versions(a, b) == expected


def _device(did):
    t = GT[did]
    return {**INV[did], "vendor": t["vendor"], "product": t["product"], "model": None, "version": t["version"]}


@pytest.mark.parametrize("did", REAL)
def test_real_devices_now_reach_patch(did):
    """DEV-009/034 (Ivanti 22.7R2.4/.5 < 22.7R2.6) and DEV-021/050 (NetScaler 14.1-43.50 /
    14.1-29.72 < 14.1-47.46): the guard compares them and agrees with the human label patch."""
    t, d = GT[did], _device(did)
    row = LC[t["evidence_lifecycle_id"]]
    kev = [KEV[c] for c in t["evidence_cve"].split(";")]
    assert guards.parse_version(INV[did]["firmware_version_raw"]) is not None
    for model_lane in ("patch", "fine"):  # a wrong "fine" is overridden; a right "patch" is kept
        out = CheckerOutput(device_id=did, lane=model_lane, evidence_cve=[], evidence_lifecycle_id=None,
                            due_date=None, confidence=0.95, injection_detected=False, reason="r.")
        out, notes = guards.guard_checker(out, kev, [row], device=d)
        assert out.lane == "patch", notes
        assert out.evidence_lifecycle_id == row["lifecycle_id"]
        assert set(t["evidence_cve"].split(";")) <= set(out.evidence_cve)


@pytest.mark.parametrize("did,fixed_fw", [("DEV-009", "22.7R2.6"), ("DEV-021", "14.1-47.46")])
def test_real_devices_at_the_fix_are_fine(did, fixed_fw):
    t = GT[did]
    d = {**_device(did), "firmware_version_raw": fixed_fw}
    kev = [KEV[c] for c in t["evidence_cve"].split(";")]
    out = CheckerOutput(device_id=did, lane="patch", evidence_cve=t["evidence_cve"].split(";"),
                        evidence_lifecycle_id=t["evidence_lifecycle_id"], due_date=None,
                        confidence=0.95, injection_detected=False, reason="r.")
    out, _ = guards.guard_checker(out, kev, [LC[t["evidence_lifecycle_id"]]], device=d)
    assert out.lane == "fine" and out.evidence_cve == []


@pytest.mark.parametrize("did,fw", [
    ("DEV-034", "22.7r2.5"), ("DEV-034", "22.7R2"), ("DEV-034", "22.7.2.5"),
    ("DEV-050", "14.1-29.72-FIPS"), ("DEV-050", "14.1.29.72"), ("DEV-050", "14.1-29"),
])
def test_real_devices_with_near_miss_firmware_go_unknown(did, fw):
    t = GT[did]
    d = {**_device(did), "firmware_version_raw": fw}
    kev = [KEV[c] for c in t["evidence_cve"].split(";")]
    out = CheckerOutput(device_id=did, lane="patch", evidence_cve=t["evidence_cve"].split(";"),
                        evidence_lifecycle_id=t["evidence_lifecycle_id"], due_date=None,
                        confidence=0.95, injection_detected=False, reason="r.")
    out, notes = guards.guard_checker(out, kev, [LC[t["evidence_lifecycle_id"]]], device=d)
    assert out.lane == "unknown", notes
