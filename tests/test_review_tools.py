"""Tests for the label-review tooling: scripts/check_labels.py, scripts/build_blind_page.py,
scripts/build_review_page.py and scripts/merge_reviews.py.

Offline: no network (URL fetching uses a fake fetcher), no LLM. data/ is only read.
Run: python -m pytest tests/test_review_tools.py -q
"""
from __future__ import annotations

import csv
import datetime as dt
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import build_blind_page  # noqa: E402
import build_review_page  # noqa: E402
import check_labels as cl  # noqa: E402
import merge_reviews  # noqa: E402
import review_common  # noqa: E402
from sim import guards  # noqa: E402

GT = ROOT / "data" / "ground_truth.csv"
BLIND = ROOT / "eval" / "blind" / "blind_worksheet.csv"
BLIND_KEY = ROOT / "eval" / "blind" / "blind_key.csv"
AS_OF = dt.date(2026, 11, 12)


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ check_labels: lane recompute

def _row(**kw) -> dict:
    base = {"lifecycle_id": "LC-900", "vendor": "V", "product": "P", "model_pattern": "", "eol_date": "",
            "last_security_support_date": "", "patch_available": "", "fixed_version": "",
            "source_url": "https://example.org/", "notes": ""}
    return base | kw


def _label(**kw) -> dict:
    return {"device_id": "DEV-900", "vendor": "V", "product": "P", "version": "1.2.3", "lane": "fine",
            "evidence_cve": "", "evidence_lifecycle_id": "", "source_row_note": ""} | kw


KEV1 = [{"cveID": "CVE-2099-0001", "vendorProject": "V", "product": "P", "requiredAction": "Apply mitigations."}]


@pytest.mark.parametrize("label, row, kev, want", [
    (_label(product=""), _row(), KEV1, "unknown"),                                   # identity incomplete
    (_label(), _row(last_security_support_date="2026-01-01", fixed_version="9.0"), KEV1, "retire"),  # retire wins over KEV
    (_label(), _row(eol_date="2025-01-01"), [], "retire"),                           # eol_date when support blank
    (_label(), _row(last_security_support_date="2026-11-12"), [], "fine"),          # on the date: not yet past
    (_label(), _row(patch_available="false"), KEV1, "retire"),                       # KEV, no fix
    (_label(), _row(fixed_version="1.2.4"), KEV1, "patch"),
    (_label(), _row(fixed_version="1.2.3"), KEV1, "fine"),                           # at the fix
    (_label(), None, KEV1, "unknown"),                                               # KEV, no lifecycle row
    (_label(), _row(), KEV1, "unknown"),                                             # KEV, no fixed_version
    (_label(version="1.2.3 build 7"), _row(fixed_version="1.2.4"), KEV1, "unknown"), # doesn't parse
    (_label(version="7.25.1"), _row(fixed_version="7.24.3;7.23.6"), KEV1, "unknown"),  # no fix on its train
    (_label(version="7.23.3"), _row(fixed_version="7.24.3;7.23.6"), KEV1, "patch"),
    (_label(version="22.7.2.6"), _row(fixed_version="22.7R2.6"), KEV1, "unknown"),  # families never compared
    (_label(), None, [], "fine"),
])
def test_recompute_lane(label, row, kev, want):
    lane, why = cl.recompute_lane(label, row, kev, AS_OF, label["version"])
    assert lane == want, why


def test_uses_the_shared_parser():
    """No second version parser: check_labels imports sim.guards' own functions."""
    assert cl.parse_version is guards.parse_version
    assert cl.compare_versions is guards.compare_versions
    assert cl.select_train_fixes is guards.select_train_fixes
    src = (ROOT / "scripts" / "check_labels.py").read_text(encoding="utf-8")
    assert "def parse_version" not in src and "packaging" not in src


def _inputs(gt: list[dict], inv: dict, lifecycle: list[dict], kev: list[dict], urls=None) -> dict:
    return {"gt": gt, "inventory": inv, "lifecycle": lifecycle, "kev": {k["cveID"]: k for k in kev},
            "as_of": AS_OF, "review_urls": urls or {}}


def _inv(did="DEV-900", name="V thing", fw="1.2.3", **kw) -> dict:
    return {did: {"device_id": did, "device_name_raw": name, "firmware_version_raw": fw,
                  "internet_facing": "false", "criticality": "low", "do_not_touch": "false"} | kw}


def test_evidence_checks():
    kev = KEV1 + [{"cveID": "CVE-2099-0002", "vendorProject": "Other", "product": "Thing", "requiredAction": ""}]
    lab = _label(lane="patch", evidence_cve="CVE-2099-0001;CVE-2099-0002;CVE-2099-9999",
                 evidence_lifecycle_id="LC-404")
    d = cl.check_device(lab, _inputs([lab], _inv(), [_row(fixed_version="1.2.4")], kev))
    texts = " | ".join(f["text"] for f in d["findings"] if f["kind"] == "evidence")
    assert "CVE-2099-9999 is not in kev.json" in texts
    assert "CVE-2099-0002 is KEV 'Other / Thing'" in texts
    assert "LC-404 is not in lifecycle.csv" in texts
    assert "CVE-2099-0001" not in texts  # matching vendor/product: no flag


def test_firmware_that_does_not_parse_is_flagged_and_can_change_the_lane():
    lab = _label(lane="patch", version="7.24.1", evidence_cve="CVE-2099-0001", evidence_lifecycle_id="LC-900")
    rows = [_row(model_pattern="7.*", notes="model_pattern is a version glob (software train).",
                 fixed_version="7.24.3;7.23.6")]
    d = cl.check_device(lab, _inputs([lab], _inv(fw="ROS 7.24.1"), rows, KEV1))
    kinds = {f["kind"] for f in d["findings"]}
    assert d["recomputed_lane"] == "patch" and d["firmware_lane"] == "unknown"
    assert {"firmware_parse", "firmware"} <= kinds


def test_lane_mismatch_is_flagged():
    lab = _label(lane="fine", version="1.2.0")
    d = cl.check_device(lab, _inputs([lab], _inv(fw="1.2.0"), [_row(fixed_version="1.2.4")], KEV1))
    assert any(f["kind"] == "lane_mismatch" for f in d["findings"])


def test_hardware_pattern_matched_inside_the_raw_name():
    lab = _label(vendor="Cisco", product="RV", version="", lane="retire", evidence_lifecycle_id="LC-001")
    rows = [_row(lifecycle_id="LC-001", vendor="Cisco", product="RV", model_pattern="RV32*",
                 last_security_support_date="2025-01-31"),
            _row(lifecycle_id="LC-002", vendor="Cisco", product="RV", model_pattern="RV042*",
                 last_security_support_date="2025-01-31")]
    inv = _inv(name="Cisco RV320 Dual WAN router", fw="")
    d = cl.check_device(lab, _inputs([lab], inv, rows, []))
    assert d["governing_lifecycle_id"] == "LC-001" and d["recomputed_lane"] == "retire"
    assert not [f for f in d["findings"] if f["kind"] in ("pattern", "evidence")]


def test_real_data_known_flags():
    """Pins the mechanical findings documented in docs/label-check-report.md."""
    res = cl.run(cl.load_inputs(), fetcher=None, log=lambda *_: None)
    by = {d["device_id"]: d for d in res["devices"]}
    assert len(by) == 60 and all(d["mechanical"] in ("pass", "flag") for d in by.values())
    kinds = lambda did: {f["kind"] for f in by[did]["findings"]}  # noqa: E731
    assert "lane_mismatch" in kinds("DEV-052")       # T35 model fix, below the generic fixed_version
    assert "firmware" in kinds("DEV-027") and "firmware" in kinds("DEV-045")
    assert "evidence" in kinds("DEV-002")            # KEV product differs from the label's product
    # risk order: flags sorted by severity first
    sev = [d["max_severity"] for d in res["devices"]]
    assert sev == sorted(sev, reverse=True)


# ------------------------------------------------------------------ check_labels: URLs

def _fake(responses: dict):
    calls = []

    def fetch(url):
        calls.append(url)
        return responses[url]
    return fetch, calls


def test_url_classification_never_ok_when_blocked():
    lab = _label(evidence_lifecycle_id="LC-900", lane="fine")
    row = _row(source_url="https://a.example/blocked", eol_date="2030-01-31")
    urls = {"DEV-900": ["https://a.example/page", "https://a.example/pdf", "https://a.example/down"]}
    fetch, calls = _fake({
        "https://a.example/blocked": {"status": 403, "content_type": "text/html", "text": "denied", "error": None},
        "https://a.example/page": {"status": 200, "content_type": "text/html",
                                   "text": "<p>End of life: January 31, 2030</p>", "error": None},
        "https://a.example/pdf": {"status": 200, "content_type": "application/pdf", "text": None, "error": None},
        "https://a.example/down": {"status": None, "content_type": "", "text": None, "error": "ConnectionError: x"},
    })
    res = cl.run(_inputs([lab], _inv(), [row], [], urls), fetcher=fetch, delay=0, log=lambda *_: None)
    assert sorted(calls) == sorted(set(calls)) and len(calls) == 4  # each URL fetched once
    u = res["urls"]
    assert u["https://a.example/blocked"]["result"] == "needs_human"
    assert "needs human check in a browser" in u["https://a.example/blocked"]["note"]
    assert u["https://a.example/pdf"]["result"] == "needs_human"
    assert u["https://a.example/down"]["result"] == "needs_human"
    assert u["https://a.example/page"]["result"] == "text"
    d = res["devices"][0]
    needle = next(n for n in d["source"]["needles"] if n["kind"] == "eol_date")
    assert needle["status"] == "found"                      # "January 31, 2030" matched 2030-01-31
    assert d["source"]["result"] == "needs_human"           # blocked page => never ok


def test_url_ok_only_when_all_text_and_found():
    lab = _label(evidence_lifecycle_id="LC-900", lane="patch", evidence_cve="CVE-2099-0001", version="1.2.3")
    row = _row(source_url="https://a.example/adv", fixed_version="1.2.4")
    fetch, _ = _fake({"https://a.example/adv": {"status": 200, "content_type": "text/html",
                                                "text": "Fixed in <b>1.2.4</b>", "error": None}})
    res = cl.run(_inputs([lab], _inv(), [row], KEV1), fetcher=fetch, delay=0, log=lambda *_: None)
    assert res["devices"][0]["source"]["result"] == "ok"
    fetch, _ = _fake({"https://a.example/adv": {"status": 200, "content_type": "text/html",
                                                "text": "Fixed in 1.3", "error": None}})
    res = cl.run(_inputs([lab], _inv(), [row], KEV1), fetcher=fetch, delay=0, log=lambda *_: None)
    n = res["devices"][0]["source"]["needles"][0]
    assert n["status"] == "not_found" and res["devices"][0]["source"]["result"] == "needs_human"


def test_offline_without_cache_needs_human():
    lab = _label(evidence_lifecycle_id="LC-900")
    res = cl.run(_inputs([lab], _inv(), [_row()], []), fetcher=None, log=lambda *_: None)
    assert res["devices"][0]["source"]["result"] == "needs_human"


def test_quote_extraction_and_dates():
    lab = _label(source_row_note="Vendor: '9.1x reached End-of-Support on December 31, 2024' and Sophos' named XGS.")
    texts = [n["text"] for n in cl.needles_for(lab, None)]
    assert texts == ["9.1x reached End-of-Support on December 31, 2024"]
    v = cl.date_variants("2024-12-31")
    assert {"December 31, 2024", "31 Dec 2024", "2024-12-31", "12/31/2024"} <= set(v)


# ------------------------------------------------------------------ blind page

def _forbidden_strings() -> list[str]:
    """Every cell of ground_truth.csv and blind_key.csv that the blind page must not contain.
    Exempt: the lane enum (the labeller picks from it) and values that appear in the
    worksheet's own input columns (e.g. a version equal to the raw firmware, a vendor that is
    part of the raw name) because the page legitimately shows those."""
    allowed = " | ".join(f"{r['blind_id']} | {r['device_name_raw']} | {r['firmware_version_raw']}"
                         for r in _rows(BLIND)).casefold()
    out = set()
    for path in (GT, BLIND_KEY):
        for r in _rows(path):
            for v in r.values():
                v = (v or "").strip()
                if v and v not in build_blind_page.LANES and v.casefold() not in allowed:
                    out.add(v)
                    out.update(x for x in v.split(";") if x and x.casefold() not in allowed)
    return sorted(out)


@pytest.fixture(scope="module")
def blind_html(tmp_path_factory) -> str:
    out = build_blind_page.build(tmp_path_factory.mktemp("blind") / "blind.html")
    return out.read_text(encoding="utf-8")


def test_blind_page_contains_no_label_data(blind_html):
    low = blind_html.casefold()
    forbidden = _forbidden_strings()
    assert len(forbidden) > 100  # sanity: the check is not vacuous
    leaked = [s for s in forbidden if s.casefold() in low]
    assert not leaked, f"blind.html leaks ground-truth / key strings: {leaked[:10]}"
    for pat in (r"DEV-\d{3}", r"LC-\d{3}", r"CVE-\d{4}-\d+"):
        assert not re.search(pat, blind_html), pat


def test_committed_blind_page_contains_no_label_data():
    p = ROOT / "review" / "blind.html"
    if not p.exists():
        pytest.skip("review/blind.html not generated")
    low = p.read_text(encoding="utf-8").casefold()
    assert not [s for s in _forbidden_strings() if s.casefold() in low]


def test_blind_page_is_offline_and_exports_worksheet_format(blind_html):
    assert not re.search(r"<script[^>]+src=", blind_html) and "<link" not in blind_html
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>',
                                blind_html, re.S).group(1))
    with BLIND.open(encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
    assert data["export_header"] == header + ["source_url_used"]
    assert {k for r in data["rows"] for k in r} == {"blind_id", "device_name_raw", "firmware_version_raw"}
    assert [r["blind_id"] for r in data["rows"]] == [r["blind_id"] for r in _rows(BLIND)]


def _node_core(script: str, html: str) -> str | None:
    node = shutil.which("node")
    if not node:
        return None
    core = re.search(r'<script id="core">(.*?)</script>', html, re.S).group(1)
    r = subprocess.run([node, "-e", core + "\n" + script], capture_output=True, text=True,
                       encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_blind_export_is_read_by_agreement_py(blind_html, tmp_path):
    """The page's own CSV writer (run under Node) produces a file eval/blind/agreement.py scores."""
    header = json.loads(re.search(r'id="data">(.*?)</script>', blind_html, re.S).group(1))["export_header"]
    gt = {r["device_id"]: r for r in _rows(GT)}
    key = {r["blind_id"]: r["device_id"] for r in _rows(BLIND_KEY)}
    rows = []
    for w in _rows(BLIND):
        t = gt[key[w["blind_id"]]]
        rows.append({**w, "labeller": "T", "comment": 'has "quotes", commas\nand a newline',
                     "source_url_used": "https://example.org/a,b",
                     **{c: t[c] for c in ("vendor", "product", "version", "lane")}})
    out = _node_core(f"process.stdout.write(toCsv({json.dumps(header)}, {json.dumps(rows)}));", blind_html)
    if out is None:
        pytest.skip("node not installed")
    p = tmp_path / "filled.csv"
    p.write_text(out, encoding="utf-8", newline="")
    spec = importlib.util.spec_from_file_location("agreement", ROOT / "eval" / "blind" / "agreement.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    back = mod.read_csv(p)
    assert back[0]["comment"] == 'has "quotes", commas\nand a newline'
    s = mod.score(back, {b: gt[d] for b, d in key.items()})
    assert s["n"] == 15 and all(v == 1.0 for v in s["fields"].values())


def test_js_core_csv_roundtrip(blind_html):
    out = _node_core(r"""
var rows = csvObjects(toCsv(['a','b'], [{a:'x,"y"', b:'line1\nline2'}, {a:'', b:'z'}]));
process.stdout.write(JSON.stringify({rows: rows, ok: validReviewer('HK'), bad: validReviewer('H,K'),
  blank: validReviewer('  '), js: safeUrl('javascript:alert(1)'), https: safeUrl('https://x.org/')}));
""", blind_html)
    if out is None:
        pytest.skip("node not installed")
    r = json.loads(out)
    assert r["rows"] == [{"a": 'x,"y"', "b": "line1\nline2"}, {"a": "", "b": "z"}]
    assert r["ok"] and not r["bad"] and not r["blank"] and r["js"] is None and r["https"] == "https://x.org/"


# ------------------------------------------------------------------ review page

def test_review_page_never_prefills_a_decision(tmp_path):
    checks = tmp_path / "checks.json"
    checks.write_text(json.dumps(cl.run(cl.load_inputs(), fetcher=None, log=lambda *_: None)), encoding="utf-8")
    html = build_review_page.build(tmp_path / "review.html", ROOT, checks).read_text(encoding="utf-8")
    data = json.loads(re.search(r'id="data">(.*?)</script>', html, re.S).group(1))
    assert len(data["devices"]) == 60
    assert data["export_header"] == ["device_id", "reviewer", "decision", "notes"]
    assert not re.search(r"<input[^>]*\bchecked\b", html)
    assert all("decision" not in d for d in data["devices"])
    assert not re.search(r"<script[^>]+src=", html)
    assert "</script" not in review_common.embed_json({"x": "</script><b>"})


# ------------------------------------------------------------------ merge_reviews

def _write_review(path: Path, reviewer: str, decisions: dict[str, str], notes: dict[str, str] | None = None):
    ids = [r["device_id"] for r in _rows(GT)]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(["device_id", "reviewer", "decision", "notes"])
        for i in ids:
            w.writerow([i, reviewer, decisions.get(i, "verified"), (notes or {}).get(i, "")])
    return path


def test_merge_fills_only_verified(tmp_path):
    before = GT.read_bytes()
    a = _write_review(tmp_path / "a.csv", "AB", {"DEV-002": "disagree", "DEV-003": ""},
                      {"DEV-002": "KEV product, not Pulse"})
    b = _write_review(tmp_path / "b.csv", "CD", {"DEV-002": "verified", "DEV-004": "unsure"})
    out, dis = tmp_path / "gt.reviewed.csv", tmp_path / "dis.md"
    assert merge_reviews.main([str(a), str(b), "--out", str(out), "--disagreements", str(dis)]) == 0
    assert GT.read_bytes() == before  # original untouched
    orig = {r["device_id"]: r for r in _rows(GT)}
    got = {r["device_id"]: r for r in _rows(out)}
    assert list(got) == list(orig)
    for did, r in got.items():
        for col in r:
            if col not in ("verified_by_a", "verified_by_b"):
                assert r[col] == orig[did][col], (did, col)
    assert got["DEV-001"]["verified_by_a"] == "AB" and got["DEV-001"]["verified_by_b"] == "CD"
    assert got["DEV-002"]["verified_by_a"] == "" and got["DEV-002"]["verified_by_b"] == "CD"
    assert got["DEV-003"]["verified_by_a"] == "" and got["DEV-004"]["verified_by_b"] == ""
    md = dis.read_text(encoding="utf-8")
    assert "Verified by both: 57 of 60" in md
    assert "DEV-002" in md and "KEV product, not Pulse" in md and "DEV-004" in md and "DEV-003" in md
    assert "| DEV-001 |" not in md


def test_merge_rejects_bad_input(tmp_path):
    a = _write_review(tmp_path / "a.csv", "AB", {})
    same = _write_review(tmp_path / "same.csv", "ab", {})
    args = ["--out", str(tmp_path / "o.csv"), "--disagreements", str(tmp_path / "d.md")]
    assert merge_reviews.main([str(a), str(same)] + args) == 2          # same reviewer
    bad = tmp_path / "bad.csv"
    bad.write_text("device_id,reviewer,decision\nDEV-001,CD,verified\n", encoding="utf-8")
    assert merge_reviews.main([str(a), str(bad)] + args) == 2           # wrong header
    odd = _write_review(tmp_path / "odd.csv", "CD", {"DEV-001": "yes"})
    assert merge_reviews.main([str(a), str(odd)] + args) == 2           # unknown decision
    blank = _write_review(tmp_path / "blank.csv", "", {})
    assert merge_reviews.main([str(a), str(blank)] + args) == 2         # no reviewer
    b = _write_review(tmp_path / "b.csv", "CD", {})
    assert merge_reviews.main([str(a), str(b), "--out", str(GT)]) == 2  # never overwrite the original
    assert not (tmp_path / "o.csv").exists()


def test_merge_reads_the_review_page_export(tmp_path):
    """A CSV from the review page's own writer (Node) merges cleanly."""
    html = (ROOT / "review" / "review.html")
    if not html.exists():
        pytest.skip("review/review.html not generated")
    rows = [{"device_id": r["device_id"], "reviewer": "A B", "decision": "verified", "notes": 'ok, "fine"'}
            for r in _rows(GT)]
    out = _node_core(f"process.stdout.write(toCsv(['device_id','reviewer','decision','notes'], {json.dumps(rows)}));",
                     html.read_text(encoding="utf-8"))
    if out is None:
        pytest.skip("node not installed")
    a = tmp_path / "a.csv"
    a.write_text(out, encoding="utf-8", newline="")
    b = _write_review(tmp_path / "b.csv", "CD", {})
    o = tmp_path / "o.csv"
    assert merge_reviews.main([str(a), str(b), "--out", str(o), "--disagreements", str(tmp_path / "d.md")]) == 0
    assert all(r["verified_by_a"] == "A B" for r in _rows(o))
