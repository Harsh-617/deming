"""data/lifecycle_extended.csv: format, sourcing, the default-OFF switch, and the coverage report.

No network, no LLM call: the mock pipeline uses the rule-based client in sim/mock_llm.py.
"""
import csv
import hashlib
import io
import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "eval"))

import build_lifecycle_extended as build  # noqa: E402
import lifecycle_coverage as cov  # noqa: E402
import lifecycle_snapshot as snap  # noqa: E402
from sim import retrieval  # noqa: E402

BASE = ROOT / "data" / "lifecycle.csv"
EXT = ROOT / "data" / "lifecycle_extended.csv"
GOLDEN = ROOT / "eval" / "fixtures" / "lifecycle_flag_off_golden.json"
# sha256 of data/lifecycle.csv as committed on main (4bd5cfb, LF line endings). This branch must
# not change it. Byte comparisons here go through _lf(): core.autocrlf checkouts write CRLF
# (contracts.md: readers accept LF or CRLF).
BASE_SHA256 = "dce3df656ba8e6e82c8ab3e2caaeff64727209425c6428107a67a467f0bf7414"


def _lf(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def _rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.delenv(retrieval.EXTENDED_LIFECYCLE_ENV, raising=False)


# ------------------------------------------------------------------ default OFF == main

def test_flag_off_snapshot_is_byte_identical_to_main(flag_off):
    """Retrieval results and mock-pipeline predictions for all 60 devices, flag off, equal the
    snapshot written on main before the switch existed."""
    assert snap.snapshot().encode("utf-8") == _lf(GOLDEN.read_bytes())


@pytest.mark.parametrize("value", ["", "0", "false", "off", "no"])
def test_env_values_that_keep_it_off(monkeypatch, value):
    monkeypatch.setenv(retrieval.EXTENDED_LIFECYCLE_ENV, value)
    assert retrieval.load_lifecycle(BASE) == _rows(BASE)
    assert snap.snapshot().encode("utf-8") == _lf(GOLDEN.read_bytes())


def test_explicit_false_beats_env(monkeypatch):
    monkeypatch.setenv(retrieval.EXTENDED_LIFECYCLE_ENV, "1")
    assert retrieval.load_lifecycle(BASE, include_extended=False) == _rows(BASE)


def test_default_load_is_the_30_rows(flag_off):
    rows = retrieval.load_lifecycle(BASE)
    assert len(rows) == 30 and rows == _rows(BASE)


# ------------------------------------------------------------------ switch ON

@pytest.mark.parametrize("how", ["arg", "env"])
def test_flag_on_appends_extended_rows(monkeypatch, how):
    monkeypatch.delenv(retrieval.EXTENDED_LIFECYCLE_ENV, raising=False)
    if how == "env":
        monkeypatch.setenv(retrieval.EXTENDED_LIFECYCLE_ENV, "1")
        rows = retrieval.load_lifecycle(BASE)
    else:
        rows = retrieval.load_lifecycle(BASE, include_extended=True)
    assert rows == _rows(BASE) + _rows(EXT)


def test_id_clash_is_refused(tmp_path, flag_off):
    clash = tmp_path / "ext.csv"
    clash.write_bytes(BASE.read_bytes())
    with pytest.raises(ValueError, match="LC-001"):
        retrieval.load_lifecycle(BASE, include_extended=True, extended_path=clash)


def test_t35_rows_reach_a_t35_device(flag_off):
    rows = retrieval.load_lifecycle(BASE, include_extended=True)
    dev = {"vendor": "WatchGuard", "product": "Firebox", "model": "T35", "version": "12.5.9"}
    got = {r["lifecycle_id"]: r for r in retrieval.lifecycle_candidates(dev, rows)}
    assert "LC-101" in got and got["LC-101"]["eol_date"] == "2025-12-31"
    assert not {"LC-102", "LC-103", "LC-104"} & set(got)  # *T35-W etc. tested and don't fit


# ------------------------------------------------------------------ the extended file

def test_base_lifecycle_unchanged():
    assert hashlib.sha256(_lf(BASE.read_bytes())).hexdigest() == BASE_SHA256
    assert len(_rows(BASE)) == 30


def test_extended_format_matches_contract():
    raw = EXT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    header = next(csv.reader(io.StringIO(raw.decode("utf-8"))))
    assert header == build.HEADER == next(csv.reader(io.StringIO(BASE.read_text(encoding="utf-8"))))
    rows = _rows(EXT)
    ids = [r["lifecycle_id"] for r in rows]
    assert len(ids) == len(set(ids)) and not set(ids) & {r["lifecycle_id"] for r in _rows(BASE)}
    forbidden = {"n/a", "na", "none", "null", "-"}
    for r in rows:
        assert re.fullmatch(r"LC-\d{3}", r["lifecycle_id"])
        assert None not in r and len(r) == len(build.HEADER)
        assert r["source_url"].startswith("https://"), r["lifecycle_id"]
        date.fromisoformat(r["verified_on"])
        assert r["eol_date"] or r["last_security_support_date"], f"{r['lifecycle_id']}: no date"
        for k in ("eol_date", "last_security_support_date"):
            if r[k]:
                date.fromisoformat(r[k])
        assert r["patch_available"].lower() in {"", "true", "false"}
        assert all(v.strip().lower() not in forbidden for v in r.values())
        if re.match(r"^\d", r["model_pattern"]):  # version glob -> software row
            assert retrieval.is_software_row(r), r["lifecycle_id"]


def test_watchguard_t35_rows_from_vendor_page():
    rows = {r["model_pattern"]: r for r in _rows(EXT) if r["vendor"] == "WatchGuard"}
    assert {k: rows[k]["eol_date"] for k in rows} == {
        "*T35": "2025-12-31", "*T35-W": "2025-12-31", "*T35-R": "2027-03-01", "*T35-DW": "2027-03-01"}
    assert {r["source_url"] for r in rows.values()} == {"https://www.watchguard.com/node/111406"}


def test_build_is_reproducible_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "fetch", lambda slug: pytest.fail("network fetch attempted"))
    out = tmp_path / "ext.csv"
    assert build.main(["--out", str(out)]) == 0
    assert out.read_bytes() == _lf(EXT.read_bytes())


def test_endoflife_fortios_agrees_with_curated_rows():
    """Source sanity: the cached endoflife.date FortiOS feed gives the same dates lifecycle.csv
    already has for 7.0 (LC-016) and 7.4 (LC-020)."""
    import json
    feed = json.loads((build.FEEDS / "fortios.json").read_text(encoding="utf-8"))["result"]
    rel = {r["name"]: r for r in feed["releases"]}
    lc = {r["lifecycle_id"]: r for r in _rows(BASE)}
    assert rel["7.0"]["eoasFrom"] == lc["LC-016"]["eol_date"]
    assert rel["7.0"]["eolFrom"] == lc["LC-016"]["last_security_support_date"]
    assert rel["7.4"]["eolFrom"] == lc["LC-020"]["last_security_support_date"]
    meta = json.loads((build.FEEDS / "fortios_meta.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((build.FEEDS / "fortios.json").read_bytes()).hexdigest() == meta["sha256"]


# ------------------------------------------------------------------ coverage report

def test_coverage_report_is_current(flag_off):
    text = (ROOT / "docs" / "lifecycle-coverage.md").read_text(encoding="utf-8")
    assert cov.render(cov.measure()) == text
    assert "NOT been measured" in text and "original 30 rows" in text


def test_coverage_counts(flag_off):
    m = cov.measure()
    d = m["devices"]
    assert m["n_before"] == 30 and m["n_after"] == 30 + len(_rows(EXT))
    assert len(d) == 60
    # The Cisco ASA 9.16 software row is the one dated gain (DEV-039 runs 9.16.4.19).
    assert [i for i, x in d.items() if x["after"]["dated"] and not x["before"]["dated"]] == ["DEV-039"]
    # With the flag off nothing changes: "before" is exactly what retrieval returns today.
    for i, x in d.items():
        assert all(r in x["before"]["returned"] for r in x["before"]["match"])
