"""Metric tests on the 8-device fixture plus edge cases. Expected numbers were worked out by hand
from eval/fixtures/ground_truth.csv and eval/fixtures/runs/ (see runs/README.md)."""
from pathlib import Path

import pytest

from io_utils import GROUND_TRUTH_COLUMNS, PREDICTION_COLUMNS, ContractError, read_csv
from metrics import (MISSING, baseline_ties_or_beats, index_predictions, is_verified, score,
                     score_slices, stability)

FIX = Path(__file__).parent / "fixtures"
R1 = FIX / "runs/deming-20261111T010000Z/deming.csv"
R2 = FIX / "runs/deming-20261111T020000Z/deming.csv"
RB = FIX / "runs/baseline-20261111T000000Z/baseline.csv"


@pytest.fixture(scope="module")
def truth():
    return read_csv(FIX / "ground_truth.csv", GROUND_TRUTH_COLUMNS)


def preds(path, truth):
    return index_predictions(read_csv(path, PREDICTION_COLUMNS), {t["device_id"] for t in truth})


def approx(x):
    return pytest.approx(x, abs=1e-9)


# ---------------------------------------------------------------- fixture numbers

def test_system_run1_overall(truth):
    s = score(truth, preds(R1, truth)).as_dict()
    assert s["n"] == 8
    assert s["norm_vendor"] == approx(8 / 8)
    assert s["norm_product"] == approx(7 / 8)   # DEV-007 product blank
    assert s["norm_version"] == approx(7 / 8)   # DEV-006 'v6.5.62'
    assert s["norm_all_three"] == approx(6 / 8)
    assert s["lane_accuracy"] == approx(7 / 8)
    assert s["exposure_precision"] == approx(1.0)  # TP 4, FP 0
    assert s["exposure_recall"] == approx(4 / 5)   # DEV-007 abstained -> miss
    assert s["exposure_excluded"] == 1             # DEV-008 truth unknown
    assert s["unknown_rate"] == approx(2 / 8)
    assert s["unknown_precision"] == approx(1 / 2)
    assert s["unknown_recall"] == approx(1.0)


def test_baseline_overall(truth):
    s = score(truth, preds(RB, truth)).as_dict()
    assert s["norm_vendor"] == approx(4 / 8)
    assert s["norm_product"] == approx(3 / 8)
    assert s["norm_version"] == approx(8 / 8)
    assert s["norm_all_three"] == approx(3 / 8)
    assert s["lane_accuracy"] == approx(5 / 8)
    assert s["exposure_precision"] == approx(1.0)
    assert s["exposure_recall"] == approx(3 / 5)
    assert s["unknown_rate"] == 0
    assert s["unknown_precision"] is None   # never predicted unknown: undefined, not 0
    assert s["unknown_recall"] == 0


def test_baseline_never_unknown(truth):
    assert all(p["lane"] != "unknown" for p in preds(RB, truth).values())


def test_confusion_matrix(truth):
    s = score(truth, preds(RB, truth))
    assert s.confusion["patch"]["fine"] == 2
    assert s.confusion["unknown"]["retire"] == 1
    assert s.confusion["retire"]["retire"] == 2
    assert sum(sum(c.values()) for c in s.confusion.values()) == 8


def test_group_slices(truth):
    sl = score_slices(truth, preds(R1, truth))
    assert {"all", "verified", "unverified"} <= sl.keys()
    assert sl["verified"].n == 7 and sl["unverified"].n == 1
    assert sum(v.n for k, v in sl.items() if k.startswith("group:")) == 8
    assert sl["group:messy_name"].lane_acc == 0
    assert sl["group:name_collision"].exposure_precision is None
    assert sl["group:name_collision"].exposure_recall is None


def test_stability_two_runs(truth):
    st = stability(truth, [preds(R1, truth), preds(R2, truth)])
    assert st["lane_agreement"] == approx(7 / 8)
    assert st["identity_agreement"] == approx(7 / 8)
    assert [u["device_id"] for u in st["unstable_devices"]] == ["DEV-007"]


def test_stability_identical_runs(truth):
    p = preds(R1, truth)
    st = stability(truth, [p, p, p])
    assert st["lane_agreement"] == 1.0 and st["unstable_devices"] == []


def test_stability_one_run_is_undefined(truth):
    st = stability(truth, [preds(R1, truth)])
    assert st["lane_agreement"] is None and st["identity_agreement"] is None


def test_baseline_ties_or_beats(truth):
    hits = {m for m, *_ in baseline_ties_or_beats(score(truth, preds(R1, truth)), score(truth, preds(RB, truth)))}
    assert "norm_version" in hits          # baseline 1.00 vs 0.88: beats
    assert "exposure_precision" in hits    # 1.00 vs 1.00: tie
    assert "lane_accuracy" not in hits


# ---------------------------------------------------------------- edge cases

def T(did, lane, vendor="V", product="P", version="1", group="g", a="AA", b="BB"):
    return {"device_id": did, "group": group, "vendor": vendor, "product": product, "version": version,
            "lane": lane, "verified_by_a": a, "verified_by_b": b}


def P(did, lane, vendor="V", product="P", version="1"):
    return {"device_id": did, "vendor": vendor, "product": product, "version": version,
            "confidence": "0.50", "lane": lane, "evidence": "", "run_id": "x-1"}


def test_case_and_whitespace_insensitive():
    s = score([T("D1", "fine", "Cisco", "IOS XE", "17.3")],
              {"D1": P("D1", "fine", "  cisco ", "ios xe", "17.3 ")})
    assert s.norm_acc("all_three") == 1


def test_v_prefix_is_wrong_per_contract():
    s = score([T("D1", "fine", version="6.5.62")], {"D1": P("D1", "fine", version="v6.5.62")})
    assert s.norm_acc("version") == 0


def test_blank_truth_field_only_matches_blank():
    t = [T("D1", "unknown", "Cisco", "", "")]
    assert score(t, {"D1": P("D1", "unknown", "Cisco", "", "")}).norm_acc("all_three") == 1
    assert score(t, {"D1": P("D1", "unknown", "Cisco", "RV320", "")}).norm_acc("product") == 0


def test_missing_prediction_counts_wrong():
    s = score([T("D1", "patch"), T("D2", "fine")], {"D2": P("D2", "fine")})
    assert s.missing == 1
    assert s.lane_acc == 0.5
    assert s.confusion["patch"][MISSING] == 1
    assert s.exposure_recall == 0          # exposed device with no prediction = miss
    assert s.norm_acc("vendor") == 0.5


def test_no_predictions_at_all():
    s = score([T("D1", "patch")], {})
    assert s.lane_acc == 0 and s.exposure_precision is None and s.exposure_recall == 0


def test_empty_truth_gives_none_not_crash():
    d = score([], {}).as_dict()
    assert d["n"] == 0 and d["lane_accuracy"] is None and d["unknown_rate"] is None


def test_all_unknown_predictions():
    t = [T("D1", "patch"), T("D2", "fine"), T("D3", "unknown")]
    s = score(t, {d: P(d, "unknown") for d in ("D1", "D2", "D3")})
    assert s.unknown_rate == 1
    assert s.unknown_precision == pytest.approx(1 / 3)
    assert s.unknown_recall == 1
    assert s.exposure_precision is None      # nothing predicted exposed
    assert s.exposure_recall == 0


def test_no_exposed_devices_recall_undefined():
    s = score([T("D1", "fine")], {"D1": P("D1", "fine")})
    assert s.exposure_recall is None and s.exposure_precision is None


def test_patch_vs_retire_is_exposed_but_wrong_lane():
    s = score([T("D1", "retire")], {"D1": P("D1", "patch")})
    assert s.exposure_precision == 1 and s.exposure_recall == 1 and s.lane_acc == 0


def test_extra_prediction_ids_ignored():
    p = index_predictions([P("D1", "fine"), P("D99", "patch")], {"D1"})
    assert set(p) == {"D1"}


def test_duplicate_prediction_rejected():
    with pytest.raises(ContractError):
        index_predictions([P("D1", "fine"), P("D1", "patch")])


def test_bad_lane_rejected():
    with pytest.raises(ContractError):
        index_predictions([P("D1", "Patch ")])  # wrong case
    with pytest.raises(ContractError):
        index_predictions([P("D1", "N/A")])


def test_bad_truth_lane_rejected():
    with pytest.raises(ContractError):
        score([T("D1", "maybe")], {"D1": P("D1", "fine")})


def test_verified_needs_two_different_reviewers():
    assert is_verified(T("D1", "fine", a="HK", b="QA"))
    assert not is_verified(T("D1", "fine", a="HK", b=""))
    assert not is_verified(T("D1", "fine", a="HK", b="hk"))


def test_crlf_and_bom_files_read(tmp_path):
    f = tmp_path / "p.csv"
    f.write_bytes(b"\xef\xbb\xbf" + "\r\n".join([",".join(PREDICTION_COLUMNS),
                                                 'D1,"Cisco, Inc",P,1,0.50,fine,,x-1']).encode() + b"\r\n")
    rows = read_csv(f, PREDICTION_COLUMNS)
    assert rows[0]["vendor"] == "Cisco, Inc" and rows[0]["run_id"] == "x-1"


def test_missing_column_rejected(tmp_path):
    f = tmp_path / "p.csv"
    f.write_text("device_id,lane\nD1,fine\n", encoding="utf-8")
    with pytest.raises(ContractError):
        read_csv(f, PREDICTION_COLUMNS)
