"""End-to-end checks: baseline output contract, report contents, failures.csv completeness."""
import re
from pathlib import Path

import baseline
import run_eval
from io_utils import PREDICTION_COLUMNS, read_csv
from report import FAILURE_COLUMNS, SYNTHETIC_STATEMENT

FIX = Path(__file__).parent / "fixtures"


def run_baseline(tmp_path, run_id="baseline-20261111T000000Z"):
    return baseline.main(["--inventory", str(FIX / "inventory.csv"), "--kev", str(FIX / "feeds/kev.json"),
                          "--lifecycle", str(FIX / "lifecycle.csv"), "--out-root", str(tmp_path),
                          "--run-id", run_id])


def test_baseline_matches_committed_fixture_run(tmp_path):
    out = run_baseline(tmp_path)
    assert out.read_bytes() == (FIX / "runs/baseline-20261111T000000Z/baseline.csv").read_bytes().replace(b"\r\n", b"\n")


def test_baseline_contract(tmp_path):
    out = run_baseline(tmp_path)
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(PREDICTION_COLUMNS)
    rows = read_csv(out, PREDICTION_COLUMNS)
    inv = read_csv(FIX / "inventory.csv")
    assert [r["device_id"] for r in rows] == [d["device_id"] for d in inv]
    for r in rows:
        assert r["lane"] in {"patch", "retire", "fine"}
        assert re.fullmatch(r"(0|1)\.\d\d", r["confidence"])
        assert r["run_id"] == "baseline-20261111T000000Z"
        if r["lane"] == "fine":
            assert r["evidence"] == ""
        else:
            assert r["evidence"]


def test_baseline_default_run_id_format(tmp_path):
    out = baseline.main(["--inventory", str(FIX / "inventory.csv"), "--kev", str(FIX / "feeds/kev.json"),
                         "--lifecycle", str(FIX / "lifecycle.csv"), "--out-root", str(tmp_path)])
    assert re.fullmatch(r"baseline-\d{8}T\d{6}Z", out.parent.name)


def test_baseline_retire_needs_lifecycle_patch_false(tmp_path):
    rows = {r["device_id"]: r for r in read_csv(run_baseline(tmp_path))}
    assert rows["DEV-001"]["lane"] == "patch"
    assert rows["DEV-003"]["lane"] == "retire" and rows["DEV-003"]["evidence"].endswith("LC-001")


def test_baseline_without_lifecycle_never_retires(tmp_path):
    out = baseline.main(["--inventory", str(FIX / "inventory.csv"), "--kev", str(FIX / "feeds/kev.json"),
                         "--lifecycle", str(tmp_path / "nope.csv"), "--out-root", str(tmp_path),
                         "--run-id", "baseline-x"])
    assert all(r["lane"] != "retire" for r in read_csv(out))


def test_report_on_fixture(tmp_path):
    out_dir = run_eval.main(["--fixture", "--out-root", str(tmp_path)])
    md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert SYNTHETIC_STATEMENT in md
    assert "No claim is made about real-world accuracy or time saved" in md
    assert "Baseline BEATS the system on" in md
    assert "Plainly: the naive baseline beats the system" in md
    assert "group:messy_name" in md and "group:name_collision" in md

    fails = read_csv(out_dir / "failures.csv", FAILURE_COLUMNS)
    # Every wrong case is listed. Fixture truth has DEV-001/002/007 unknown (no fixed_version):
    # run1 4 (DEV-001/002 lane, DEV-006/007 identity), run2 4 (DEV-001/002/007 lane, DEV-006
    # identity), baseline 6 (DEV-001/002/005/006/007/008), plus 1 unstable device (DEV-007).
    keyed = {(f["run_id"], f["device_id"]) for f in fails}
    assert ("deming-20261111T010000Z", "DEV-007") in keyed
    assert ("deming-20261111T010000Z", "DEV-006") in keyed
    assert ("baseline-20261111T000000Z", "DEV-008") in keyed
    assert ("(all runs)", "DEV-007") in keyed
    assert len(fails) == 4 + 4 + 6 + 1
    assert all(f["explanation"] for f in fails)
    for f in fails:
        assert f["device_id"] in md  # also listed in report.md


def test_run_eval_as_of_default_and_override(tmp_path):
    import json
    import run_eval
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"as_of_date": "2026-11-12"}), encoding="utf-8")
    assert run_eval.load_as_of_date(path=meta) == "2026-11-12"
    assert run_eval.load_as_of_date("2026-12-10", path=meta) == "2026-12-10"
    out = run_eval.main(["--fixture", "--out-root", str(tmp_path), "--as-of", "2026-12-10"])
    assert "as_of_date: `2026-12-10 (--as-of override)`" in (out / "report.md").read_text(encoding="utf-8")
