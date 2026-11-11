"""Validate data/inventory.csv and data/ground_truth.csv against docs/contracts.md (v1.3).

Run: python -m pytest tests/test_inventory.py -q
Offline: reads only files in the repo.
"""
from __future__ import annotations

import csv
import fnmatch
import importlib.util
import json
import re
from datetime import date
from pathlib import Path

import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The ground-truth checks use the Checker's own version parser and train selection, so labels
# and the version guard can never disagree on what "below the fix" means.
from sim.guards import parse_version, select_train_fixes  # noqa: E402
INV = ROOT / "data" / "inventory.csv"
GT = ROOT / "data" / "ground_truth.csv"
LC = ROOT / "data" / "lifecycle.csv"
KEV = ROOT / "data" / "feeds" / "kev.json"
GT_META = ROOT / "data" / "ground_truth_meta.json"
REVIEW = ROOT / "docs" / "label-review.csv"
BLIND = ROOT / "eval" / "blind" / "blind_worksheet.csv"
BLIND_KEY = ROOT / "eval" / "blind" / "blind_key.csv"

INVENTORY_COLUMNS = ["device_id", "device_name_raw", "location", "owner_email", "firmware_version_raw",
                     "internet_facing", "criticality", "do_not_touch", "last_updated"]
GROUND_TRUTH_COLUMNS = ["device_id", "group", "vendor", "product", "version", "lane",
                        "evidence_cve", "evidence_lifecycle_id", "source_row_note", "verified_by_a", "verified_by_b"]
GROUP_COUNTS = {"clear_patch": 15, "clear_retire": 12, "supported_fine": 15,
                "messy_name": 10, "name_collision": 4, "critical_dnt": 4}
LANES = {"patch", "retire", "fine", "unknown"}
FORBIDDEN = {"n/a", "na", "none", "null", "-"}


def _read(path: Path) -> tuple[list[str], list[dict]]:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name}: BOM not allowed"
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


@pytest.fixture(scope="module")
def inv():
    header, rows = _read(INV)
    assert header == INVENTORY_COLUMNS
    return rows


@pytest.fixture(scope="module")
def gt():
    header, rows = _read(GT)
    assert header == GROUND_TRUTH_COLUMNS
    return rows


@pytest.fixture(scope="module")
def lifecycle():
    return {r["lifecycle_id"]: r for r in _read(LC)[1]}


@pytest.fixture(scope="module")
def kev_ids():
    return {v["cveID"] for v in json.loads(KEV.read_text(encoding="utf-8"))["vulnerabilities"]}


def test_inventory_schema(inv):
    assert len(inv) == 60
    for r in inv:
        did = r["device_id"]
        assert re.fullmatch(r"DEV-\d{3}", did), did
        assert r["device_name_raw"], did
        assert r["owner_email"].endswith("@example.org"), did
        assert r["internet_facing"].lower() in ("true", "false"), did
        assert r["do_not_touch"].lower() in ("true", "false"), did
        assert r["criticality"] in ("low", "medium", "high", "critical"), did
        date.fromisoformat(r["last_updated"])
        for col, val in r.items():
            assert val == val.strip(), f"{did}.{col}: stray whitespace"
            assert val.lower() not in FORBIDDEN, f"{did}.{col}: use blank, not {val!r}"


def test_no_duplicate_ids(inv, gt):
    assert len({r["device_id"] for r in inv}) == len(inv)
    assert len({r["device_id"] for r in gt}) == len(gt)


def test_ground_truth_covers_every_device(inv, gt):
    assert {r["device_id"] for r in inv} == {r["device_id"] for r in gt}


def test_group_counts(gt):
    counts = {g: sum(r["group"] == g for r in gt) for g in GROUP_COUNTS}
    assert counts == GROUP_COUNTS
    assert all(r["group"] in GROUP_COUNTS for r in gt)


def test_ground_truth_schema(gt, lifecycle, kev_ids):
    for r in gt:
        did = r["device_id"]
        assert r["lane"] in LANES, did
        assert r["vendor"], f"{did}: vendor should be knowable for every device"
        if r["evidence_cve"]:
            assert " " not in r["evidence_cve"], did
            for cve in r["evidence_cve"].split(";"):
                assert cve in kev_ids, f"{did}: {cve} not in kev.json"
        if r["evidence_lifecycle_id"]:
            assert r["evidence_lifecycle_id"] in lifecycle, did
        if r["lane"] in ("patch", "retire"):
            assert r["evidence_cve"] or r["evidence_lifecycle_id"], f"{did}: {r['lane']} needs evidence"
        if r["lane"] in ("fine", "unknown"):
            assert not r["evidence_cve"] and not r["evidence_lifecycle_id"], did
        if r["version"]:
            assert not re.match(r"[vV]\d", r["version"]), f"{did}: no v prefix"
        assert r["verified_by_a"] == "" and r["verified_by_b"] == "", f"{did}: reviewers fill these, not code"


def test_every_row_has_a_source(gt):
    review = {r["device_id"]: r for r in _read(REVIEW)[1]}
    assert set(review) == {r["device_id"] for r in gt}
    for r in gt:
        assert len(r["source_row_note"]) >= 20, f"{r['device_id']}: source_row_note too thin"
        urls = review[r["device_id"]]["source_url"].split(";")
        assert urls and all(u.startswith("https://") for u in urls), r["device_id"]


def test_label_review_matches_ground_truth(gt):
    review = {r["device_id"]: r for r in _read(REVIEW)[1]}
    for r in gt:
        for col in ("group", "vendor", "product", "version", "lane", "evidence_cve", "evidence_lifecycle_id"):
            assert review[r["device_id"]][col] == r[col], (r["device_id"], col)


def _as_of() -> date:
    return date.fromisoformat(json.loads(GT_META.read_text(encoding="utf-8"))["as_of_date"])


def test_lanes_follow_lifecycle_dates(gt, lifecycle):
    """retire iff the cited lifecycle row is past support (or says no patch) as of as_of_date."""
    as_of = _as_of()
    for r in gt:
        lc = lifecycle.get(r["evidence_lifecycle_id"])
        if not lc:
            continue
        cutoff = lc["last_security_support_date"] or lc["eol_date"]
        past = (bool(cutoff) and date.fromisoformat(cutoff) <= as_of) or lc["patch_available"].lower() == "false"
        if r["lane"] == "retire":
            assert past, f"{r['device_id']}: retire but {lc['lifecycle_id']} is still supported"
        if r["lane"] == "patch":
            assert not past, f"{r['device_id']}: patch but {lc['lifecycle_id']} is past support"


# clear_patch rows whose version the guard's strict grammar can't read (Ivanti 22.7R2.x,
# NetScaler 14.1-NN.NN build numbers). The labels say patch (from the vendor advisories), but the
# version guard sends these devices to unknown, so they are expected misses in the eval. Listed
# here so a new unparseable label fails the test instead of being skipped quietly.
UNPARSEABLE_PATCH_LABELS = {"DEV-009", "DEV-021", "DEV-034", "DEV-050"}


def _vkey(v: str) -> tuple:
    key = parse_version(v)
    assert key is not None, f"version {v!r} does not parse with sim.guards.parse_version"
    return key


def _train_fixes(fixed: str, version: str) -> list[str]:
    """Fixed versions on the version's release train (contracts v1.2), via the guard itself."""
    fixes, _why = select_train_fixes(fixed, version)
    return fixes


def test_clear_patch_below_fixed_version(gt, lifecycle):
    seen_unparseable: set[str] = set()
    for r in gt:
        if r["group"] != "clear_patch":
            continue
        lc = lifecycle[r["evidence_lifecycle_id"]]
        assert lc["fixed_version"], f"{r['device_id']}: clear_patch needs a documented fixed_version"
        assert fnmatch.fnmatch(r["version"].lower(), lc["model_pattern"].lower()), r["device_id"]
        if parse_version(r["version"]) is None:
            assert r["device_id"] in UNPARSEABLE_PATCH_LABELS, (
                f"{r['device_id']}: version {r['version']!r} does not parse; the guard would say unknown")
            seen_unparseable.add(r["device_id"])
            continue
        fixes = _train_fixes(lc["fixed_version"], r["version"])
        assert fixes, f"{r['device_id']}: no fixed version on the train of {r['version']}"
        assert _vkey(r["version"]) < min(_vkey(f) for f in fixes), f"{r['device_id']}: not below {fixes}"
    assert seen_unparseable == UNPARSEABLE_PATCH_LABELS


def test_supported_fine_at_or_above_fixed_version(gt, lifecycle):
    """Fine rows come from a supported row's train; except the documented T35 case, at/above the fix."""
    for r in gt:
        if r["group"] != "supported_fine":
            continue
        assert r["lane"] == "fine"
        if "T35" in r["source_row_note"]:
            continue
        lc = next(l for l in lifecycle.values()
                  if l["fixed_version"] and l["vendor"] == r["vendor"]
                  and fnmatch.fnmatch(r["version"].lower(), l["model_pattern"].lower()))
        fixes = _train_fixes(lc["fixed_version"], r["version"])
        assert fixes, f"{r['device_id']}: no fixed version on the train of {r['version']}"
        assert _vkey(r["version"]) >= max(_vkey(f) for f in fixes), r["device_id"]


def test_critical_dnt(inv, gt, kev_ids):
    inv_by = {r["device_id"]: r for r in inv}
    dnt = [r for r in gt if r["group"] == "critical_dnt"]
    for r in dnt:
        assert inv_by[r["device_id"]]["do_not_touch"] == "true"
        assert inv_by[r["device_id"]]["criticality"] == "critical"
    assert any(r["evidence_cve"] for r in dnt), "critical_dnt must include KEV devices"


def test_injection_row_present(inv):
    assert any("ignore previous instructions" in r["device_name_raw"].lower() for r in inv)


def test_blind_worksheet(gt):
    header, rows = _read(BLIND)
    assert header[:3] == ["blind_id", "device_name_raw", "firmware_version_raw"]
    assert len(rows) == 15
    for r in rows:
        assert all(r[c] == "" for c in header[3:]), "label columns must be empty"
        assert "DEV-" not in r["device_name_raw"]
    key = _read(BLIND_KEY)[1]
    gt_ids = {r["device_id"] for r in gt}
    assert len(key) == 15 and {k["blind_id"] for k in key} == {r["blind_id"] for r in rows}
    assert all(k["device_id"] in gt_ids for k in key)


def test_agreement_script(tmp_path, gt):
    spec = importlib.util.spec_from_file_location("agreement", ROOT / "eval" / "blind" / "agreement.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    gt_by = {r["device_id"]: r for r in gt}
    key = {k["blind_id"]: k["device_id"] for k in _read(BLIND_KEY)[1]}
    header, rows = _read(BLIND)
    perfect = tmp_path / "perfect.csv"
    with perfect.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            t = gt_by[key[r["blind_id"]]]
            w.writerow({**r, "labeller": "T", **{c: t[c] for c in ("vendor", "product", "version", "lane")}})
    truth_by_blind = {b: gt_by[d] for b, d in key.items()}
    s = mod.score(mod.read_csv(perfect), truth_by_blind)
    assert s["n"] == 15 and all(v == 1.0 for v in s["fields"].values()) and not s["disagreements"]
    assert mod.cohen_kappa(["a", "b"], ["a", "b"]) == 1.0
    assert mod.main([str(perfect)]) == 0
