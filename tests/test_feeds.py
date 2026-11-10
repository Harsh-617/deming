"""Validate the data feeds against docs/contracts.md.

Run: python -m pytest tests/test_feeds.py -q
Offline: reads only files already in data/. No network calls.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
KEV_PATH = ROOT / "data" / "feeds" / "kev.json"
META_PATH = ROOT / "data" / "feeds" / "kev_meta.json"
LIFECYCLE_PATH = ROOT / "data" / "lifecycle.csv"

LIFECYCLE_HEADER = [
    "lifecycle_id", "vendor", "product", "model_pattern", "eol_date",
    "last_security_support_date", "patch_available", "replacement_hint",
    "source_url", "verified_on", "notes",
]
FORBIDDEN_BLANKS = {"n/a", "na", "none", "null", "-"}


def _load_fetch_kev():
    spec = importlib.util.spec_from_file_location("fetch_kev", ROOT / "scripts" / "fetch_kev.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _iso_date(s: str) -> date:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s), f"not ISO YYYY-MM-DD: {s!r}"
    return date.fromisoformat(s)


# ---------------------------------------------------------------- KEV

@pytest.fixture(scope="module")
def kev_raw() -> bytes:
    assert KEV_PATH.exists(), "run scripts/fetch_kev.py first"
    return KEV_PATH.read_bytes()


@pytest.fixture(scope="module")
def kev(kev_raw) -> dict:
    return json.loads(kev_raw.decode("utf-8"))


def test_kev_has_vulnerabilities_list(kev):
    assert isinstance(kev.get("vulnerabilities"), list)
    assert len(kev["vulnerabilities"]) > 0
    assert kev["count"] == len(kev["vulnerabilities"])


def test_kev_entries_have_required_fields(kev):
    for v in kev["vulnerabilities"]:
        for field in ("vendorProject", "product", "cveID", "dateAdded"):
            assert isinstance(v.get(field), str) and v[field].strip(), f"{v.get('cveID')}: missing {field}"
        assert re.fullmatch(r"CVE-\d{4}-\d{4,}", v["cveID"]), v["cveID"]
        _iso_date(v["dateAdded"])


def test_kev_cve_ids_unique(kev):
    ids = [v["cveID"] for v in kev["vulnerabilities"]]
    assert len(ids) == len(set(ids))


def test_kev_meta_matches_file(kev_raw, kev):
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    assert set(meta) == {"fetched_at", "catalogVersion", "count", "sha256"}
    datetime.strptime(meta["fetched_at"], "%Y-%m-%dT%H:%M:%SZ")
    assert meta["catalogVersion"] == kev["catalogVersion"]
    assert meta["count"] == kev["count"] == len(kev["vulnerabilities"])
    assert re.fullmatch(r"[0-9a-f]{64}", meta["sha256"])
    assert meta["sha256"] == hashlib.sha256(kev_raw).hexdigest(), "kev.json bytes changed since download"


# ---------------------------------------------------------------- fetch_kev helpers

def _snapshot(*entries):
    vulns = [{"cveID": c, "vendorProject": "V", "product": "P", "dateAdded": d} for c, d in entries]
    return {"catalogVersion": "x", "count": len(vulns), "vulnerabilities": vulns}


def test_diff_lists_only_newer_entries():
    fk = _load_fetch_kev()
    old = _snapshot(("CVE-2020-0001", "2026-11-01"), ("CVE-2020-0002", "2026-11-05"))
    new = _snapshot(("CVE-2020-0001", "2026-11-01"), ("CVE-2020-0002", "2026-11-05"),
                    ("CVE-2020-0004", "2026-11-09"), ("CVE-2020-0003", "2026-11-07"))
    assert [v["cveID"] for v in fk.new_entries(old, new)] == ["CVE-2020-0003", "CVE-2020-0004"]
    assert fk.new_entries(new, new) == []
    assert fk.new_entries(None, new) == []


def test_validate_rejects_bad_feed():
    fk = _load_fetch_kev()
    with pytest.raises(ValueError):
        fk.parse_and_validate(b'{"catalogVersion": "x", "count": 0, "vulnerabilities": []}')
    bad_count = json.dumps(_snapshot(("CVE-2020-0001", "2026-11-01")) | {"count": 2}).encode()
    with pytest.raises(ValueError):
        fk.parse_and_validate(bad_count)
    ok = json.dumps(_snapshot(("CVE-2020-0001", "2026-11-01"))).encode()
    assert fk.parse_and_validate(ok)["count"] == 1


# ---------------------------------------------------------------- lifecycle.csv

@pytest.fixture(scope="module")
def lifecycle_raw() -> bytes:
    assert LIFECYCLE_PATH.exists()
    return LIFECYCLE_PATH.read_bytes()


@pytest.fixture(scope="module")
def lifecycle_rows(lifecycle_raw) -> list[dict]:
    text = lifecycle_raw.decode("utf-8")
    return list(csv.DictReader(text.splitlines()))


def test_lifecycle_encoding_and_header(lifecycle_raw):
    assert not lifecycle_raw.startswith(b"\xef\xbb\xbf"), "must be UTF-8 without BOM"
    header = next(csv.reader(lifecycle_raw.decode("utf-8").splitlines()))
    assert header == LIFECYCLE_HEADER


def test_lifecycle_row_count(lifecycle_rows):
    assert 25 <= len(lifecycle_rows) <= 30


def test_lifecycle_rows_valid(lifecycle_rows):
    today = date.today()
    ids = set()
    for r in lifecycle_rows:
        rid = r["lifecycle_id"]
        assert None not in r and len(r) == len(LIFECYCLE_HEADER), f"{rid}: wrong column count"
        assert re.fullmatch(r"LC-\d{3}", rid), rid
        assert rid not in ids, f"duplicate {rid}"
        ids.add(rid)
        assert r["vendor"].strip() and r["product"].strip(), rid
        for col in ("eol_date", "last_security_support_date"):
            if r[col]:
                _iso_date(r[col])
        assert r["patch_available"] in ("true", "false", ""), f"{rid}: patch_available {r['patch_available']!r}"
        assert r["source_url"].startswith("https://"), f"{rid}: source_url must be a non-empty https URL"
        assert r["verified_on"], f"{rid}: verified_on required"
        assert _iso_date(r["verified_on"]) <= today, f"{rid}: verified_on in the future"
        for col, val in r.items():
            assert val == val.strip(), f"{rid}.{col}: stray whitespace"
            assert val.lower() not in FORBIDDEN_BLANKS, f"{rid}.{col}: use blank, not {val!r}"


def _is_retire(r: dict, today: date) -> bool:
    cutoff = r["last_security_support_date"] or r["eol_date"]
    return (bool(cutoff) and date.fromisoformat(cutoff) <= today) or r["patch_available"] == "false"


def test_lifecycle_lane_mix(lifecycle_rows):
    today = date.today()
    retire = [r for r in lifecycle_rows if _is_retire(r, today)]
    supported = [r for r in lifecycle_rows if not _is_retire(r, today) and r["patch_available"] == "true"]
    assert len(retire) >= 12, f"only {len(retire)} end-of-life / no-patch rows"
    assert len(supported) >= 10, f"only {len(supported)} supported rows with a patch"
