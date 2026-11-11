"""Tests for eval/blind/cross_check.py (adapter + metrics + source-check logic). No network."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval" / "blind"))

import agreement  # noqa: E402
import cross_check as cc  # noqa: E402

AI_HEADER = ["blind_id", "device_name_raw", "firmware_version_raw", "labeller", "vendor", "product",
             "version", "lane", "comment", "source_url_used", "notes"]


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


@pytest.fixture
def small(tmp_path):
    ai = write_csv(tmp_path / "ai.csv", AI_HEADER, [
        ["B01", "box one", "1.0", "claude", "Acme", "Router X", "1.0", "patch",
         "fixed in 1.2 (2025-01-31)", "https://a.example/x", ""],
        ["B02", "box two", "2.0", "claude", "Acme", "Cam", "v2.0", "retire", "EOL", "", ""],
        ["B03", "box three", "3.0", "claude", "Acme", "dir-600", "3.0", "unknown", "?", "https://b.example", ""],
    ])
    key = write_csv(tmp_path / "key.csv", ["blind_id", "device_id"],
                    [["B01", "DEV-001"], ["B02", "DEV-002"], ["B03", "DEV-003"]])
    gt_header = ["device_id", "group", "vendor", "product", "version", "lane", "evidence_cve",
                 "evidence_lifecycle_id", "source_row_note", "verified_by_a", "verified_by_b"]
    gt = write_csv(tmp_path / "gt.csv", gt_header, [
        ["DEV-001", "g", "Acme", "Router X", "1.0", "patch", "CVE-1", "LC-001", "n", "", ""],
        ["DEV-002", "g", "acme", "Cam", "2.0", "fine", "", "", "LC-002. fine", "", ""],
        ["DEV-003", "g", "Acme", "DIR-600 Router", "3.0", "patch", "", "LC-001", "n", "", ""],
    ])
    lc = write_csv(tmp_path / "lc.csv", ["lifecycle_id", "source_url"],
                   [["LC-001", "https://lc1.example"], ["LC-002", "https://lc2.example"]])
    return ai, key, gt, lc


def test_agreement_reads_ai_file_unchanged(small):
    ai, key, gt, _ = small
    by = agreement.load_labellers([ai])
    assert list(by) == ["claude"]
    truth = {k["blind_id"]: g for k in agreement.read_csv(key)
             for g in agreement.read_csv(gt) if g["device_id"] == k["device_id"]}
    s = agreement.score(by["claude"], truth)
    assert s["n"] == 3 and s["fields"]["lane"] == pytest.approx(1 / 3)


def test_read_ai_maps_columns(small):
    rows, used = cc.read_ai(small[0])
    assert used == {"reason": "comment", "source_url": "source_url_used", "notes": "notes"}
    assert rows[0]["reason"].startswith("fixed in") and rows[0]["source_url"] == "https://a.example/x"


def test_read_ai_rejects_missing_required(tmp_path):
    p = write_csv(tmp_path / "bad.csv", ["blind_id", "lane"], [["B01", "fine"]])
    with pytest.raises(ValueError, match="missing required"):
        cc.read_ai(p)


def test_compare_exact_alias_and_severity(small):
    ai, key, gt, lc = small
    rows, _ = cc.read_ai(ai)
    cmp = cc.compare(rows, *(agreement.read_csv(p) for p in (key, gt, lc)))
    b1, b2, b3 = cmp
    assert b1["exact"] == {"vendor": True, "product": True, "version": True, "lane": True}
    assert b1["severity"] == 4 and not b1["identity_disagree"]
    assert b2["exact"]["version"] and b2["exact"]["vendor"]  # leading v and case ignored
    assert b2["severity"] == 1  # retire vs fine
    assert b2["truth_lc"] == "LC-002" and b2["truth_lc_urls"] == ["https://lc2.example"]  # from note
    assert not b3["exact"]["product"] and b3["alias_product"]  # post-hoc alias dir-600
    assert b3["severity"] == 3


def test_severity_order():
    assert cc.severity("fine", "patch", False) == 1
    assert cc.severity("retire", "fine", False) == 1
    assert cc.severity("retire", "patch", False) == 2
    assert cc.severity("unknown", "patch", False) == 3
    assert cc.severity("patch", "patch", True) == 4


def test_lane_metrics_matches_hand_computation():
    ai = ["retire"] * 9 + ["fine"] * 3 + ["patch"] * 2 + ["unknown"]
    truth = (["retire"] * 7 + ["fine", "patch"] + ["fine"] * 3 + ["patch"] * 2 + ["patch"])
    m = cc.lane_metrics(ai, truth)
    assert m["agree"] == 12 and m["po"] == pytest.approx(0.8)
    assert m["pe"] == pytest.approx(83 / 225)
    assert m["kappa"] == pytest.approx((0.8 - 83 / 225) / (1 - 83 / 225))
    assert m["kappa"] == pytest.approx(agreement.cohen_kappa(ai, truth))
    lo, hi = m["ci"]
    assert lo < m["kappa"] < hi <= 1.0


def test_lane_metrics_perfect_and_undefined():
    m = cc.lane_metrics(["fine", "patch"], ["fine", "patch"])
    assert m["kappa"] == pytest.approx(1.0)
    assert cc.lane_metrics(["fine", "fine"], ["fine", "fine"])["kappa"] is None


def test_extract_claims_dates_versions_quotes():
    c = cc.extract_claims('EoL August 31, 2026; EOS 11/01/2017; fix 12.11.4 for CVE-2025-9242',
                          'vendor: "all of the above are fixed"', own_version="12.9.2")
    texts = [x["text"] for x in c]
    assert texts == ["August 31, 2026", "11/01/2017", "CVE-2025-9242", "12.11.4",
                     "all of the above are fixed"]
    aug = c[0]["variants"]
    assert "2026-08-31" in aug and "31 Aug 2026" in aug


def test_extract_claims_skips_own_version_unless_nothing_else():
    assert [x["text"] for x in cc.extract_claims("12.9.2 in range 12.0-12.11.3", "", "12.9.2")] \
        == ["12.0", "12.11.3"]
    assert [x["text"] for x in cc.extract_claims("7.23.6 fixes all", "", "7.23.6")] == ["7.23.6"]
    assert cc.extract_claims("no strings here", "", "") == []


def test_page_text_and_claim_found():
    t = cc.page_text("<html><script>var x='2025-01-31'</script><p>Last&nbsp;date: 31 Jan 2025</p></html>")
    assert "var x" not in t
    claim = cc.extract_claims("LDoS 2025-01-31")[0]
    assert cc.claim_found(t, claim)
    assert not cc.claim_found("nothing", claim)


def test_classify():
    long = "x" * 1000
    assert cc.classify(200, long, "") == "opened"
    assert cc.classify(403, "", "") == cc.NEEDS_HUMAN
    assert cc.classify(200, "short", "") == cc.NEEDS_HUMAN
    assert cc.classify(200, "Please enable JavaScript " + long, "") == cc.NEEDS_HUMAN
    assert cc.classify(None, "", "") == "error"
    assert cc.classify(404, "", "") == "http 404"


def test_run_fetch_fetches_each_url_once_and_summarises(tmp_path):
    rows = [
        {"blind_id": "B1", "reason": "LDoS 2025-01-31", "notes": "", "source_url": "https://u"},
        {"blind_id": "B2", "reason": "fix 1.2.3", "notes": "", "source_url": "https://u"},
        {"blind_id": "B3", "reason": "EOL", "notes": "", "source_url": ""},
        {"blind_id": "B4", "reason": "EOL 2020-01-01", "notes": "", "source_url": "https://blocked"},
        {"blind_id": "B5", "reason": "EOL", "notes": "", "source_url": "https://u"},
    ]
    calls = []

    def fake(url):
        calls.append(url)
        if url == "https://blocked":
            return 403, ""
        return 200, "<p>" + "filler " * 100 + "Last date 31 January 2025</p>"

    out = cc.run_fetch(rows, tmp_path / "checks.csv", delay=0, fetcher=fake)
    assert calls == ["https://u", "https://blocked"]
    assert (tmp_path / "checks.csv").exists()
    s = cc.source_summary(agreement.read_csv(tmp_path / "checks.csv"))
    assert s["B1"]["supported"] and s["B1"]["verdict"].startswith("opened; all 1")
    assert not s["B2"]["supported"] and "1.2.3" in s["B2"]["verdict"]
    assert not s["B3"]["supported"] and s["B3"]["verdict"] == "no source: unsupported"
    assert not s["B4"]["supported"] and cc.NEEDS_HUMAN in s["B4"]["verdict"]
    assert not s["B5"]["supported"] and "no date/version" in s["B5"]["verdict"]
    assert len(out) == 5


def test_render_has_required_statements(small):
    ai, key, gt, lc = small
    rows, used = cc.read_ai(ai)
    cmp = cc.compare(rows, *(agreement.read_csv(p) for p in (key, gt, lc)))
    lm = cc.lane_metrics([c["ai"]["lane"] for c in cmp], [c["truth"]["lane"] for c in cmp])
    md = cc.render(cmp, lm, {}, used, "ai.csv", "claude")
    assert "NOT human verification" in md and "same model family" in md
    assert "third-party" in md.lower() and "n = 3 is tiny" in md
    # most severe first
    assert md.index("### B02") < md.index("### B03")
    assert "verified by" not in md.lower().replace("verified_by", "")


def test_real_input_matches_published_numbers():
    ai = ROOT / "eval/blind/external/blind_ai_claude.csv"
    if not ai.exists():
        pytest.skip("external AI file not present")
    rows, _ = cc.read_ai(ai)
    cmp = cc.compare(rows, agreement.read_csv(ROOT / "eval/blind/blind_key.csv"),
                     agreement.read_csv(ROOT / "data/ground_truth.csv"),
                     agreement.read_csv(ROOT / "data/lifecycle.csv"))
    lm = cc.lane_metrics([c["ai"]["lane"] for c in cmp], [c["truth"]["lane"] for c in cmp])
    assert (lm["n"], lm["agree"]) == (15, 12)
    assert round(lm["kappa"], 2) == 0.68
