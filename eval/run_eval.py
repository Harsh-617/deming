"""Score predictions CSVs against ground truth and write a report.

  python eval/run_eval.py                              # every eval/runs/*/*.csv vs data/ground_truth.csv
  python eval/run_eval.py --pred a.csv b.csv           # explicit files
  python eval/run_eval.py --fixture                    # the 8-device fixture (harness self-check)
  python eval/run_eval.py --as-of 2026-12-10           # override data/ground_truth_meta.json

Output: eval/results/<UTC timestamp>/report.md and failures.csv.
System name = the part of run_id before the first '-' (deming, baseline), else the file stem.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from io_utils import GROUND_TRUTH_COLUMNS, INVENTORY_COLUMNS, PREDICTION_COLUMNS, ContractError, read_csv, utc_stamp
from metrics import index_predictions, is_verified
from report import DEFAULT_LABEL_STATUS, build_report

REPO = Path(__file__).resolve().parent.parent
GT_META = REPO / "data/ground_truth_meta.json"


def load_as_of_date(override: str | None = None, path: Path = GT_META) -> str:
    """as_of_date the ground truth is labelled against (contracts.md); `override` wins."""
    import datetime as dt
    import json
    value = override or json.loads(path.read_text(encoding="utf-8"))["as_of_date"]
    return dt.date.fromisoformat(value).isoformat()


def load_label_status(path: Path = GT_META) -> str:
    """How the labels were made (`label_status` in ground_truth_meta.json). A missing field is
    read as the conservative `ai_drafted_unverified`, never as human-verified."""
    import json
    return json.loads(path.read_text(encoding="utf-8")).get("label_status", DEFAULT_LABEL_STATUS)


FIXTURE = REPO / "eval/fixtures"


def _show(path: Path) -> str:
    path = path.resolve()
    return (path.relative_to(REPO) if path.is_relative_to(REPO) else path).as_posix()


def load_runs(paths: list[Path], truth_ids: set[str]) -> dict[str, list[tuple[str, dict]]]:
    systems: dict[str, list[tuple[str, dict]]] = {}
    for path in paths:
        rows = read_csv(path, PREDICTION_COLUMNS)
        run_ids = {r["run_id"] for r in rows}
        if len(run_ids) > 1:
            raise ContractError(f"{path}: more than one run_id {sorted(run_ids)}")
        run_id = run_ids.pop() if run_ids else path.parent.name
        system = run_id.split("-", 1)[0] if "-" in run_id else path.stem
        preds = index_predictions(rows, truth_ids)
        missing = truth_ids - preds.keys()
        if missing:
            print(f"warning: {path} has no prediction for {len(missing)} device(s): {sorted(missing)[:5]}",
                  file=sys.stderr)
        systems.setdefault(system, []).append((run_id, preds))
    for runs in systems.values():
        runs.sort(key=lambda r: r[0])
    # Put the system under test first, baseline last, for readable tables.
    return dict(sorted(systems.items(), key=lambda kv: (kv[0] == "baseline", kv[0])))


def main(argv: list[str] | None = None) -> Path:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", action="store_true", help="use eval/fixtures/ (truth, inventory, runs)")
    p.add_argument("--ground-truth", type=Path, default=None)
    p.add_argument("--inventory", type=Path, default=None, help="optional; adds device names to failures")
    p.add_argument("--pred", type=Path, nargs="*", default=None, help="predictions CSVs")
    p.add_argument("--runs-dir", type=Path, default=None, help="scan <dir>/*/*.csv when --pred is not given")
    p.add_argument("--out-root", type=Path, default=REPO / "eval/results")
    p.add_argument("--as-of", default=None,
                   help="YYYY-MM-DD the truth is labelled against; default: data/ground_truth_meta.json")
    args = p.parse_args(argv)
    as_of = load_as_of_date(args.as_of)
    label_status = load_label_status()

    base = FIXTURE if args.fixture else REPO / "data"
    gt_path = args.ground_truth or base / "ground_truth.csv"
    inv_path = args.inventory or base / "inventory.csv"
    runs_dir = args.runs_dir or (FIXTURE / "runs" if args.fixture else REPO / "eval/runs")
    pred_paths = args.pred if args.pred else sorted(runs_dir.glob("*/*.csv"))

    if not gt_path.exists():
        sys.exit(f"ground truth not found: {gt_path} (try --fixture)")
    if not pred_paths:
        sys.exit(f"no predictions CSVs found (looked in {runs_dir})")

    truth = read_csv(gt_path, GROUND_TRUTH_COLUMNS)
    if not truth:
        sys.exit(f"ground truth is empty: {gt_path}")
    ids = [t["device_id"] for t in truth]
    if len(ids) != len(set(ids)):
        raise ContractError(f"{gt_path}: duplicate device_id")
    if label_status == "human_verified" and not all(is_verified(t) for t in truth):
        raise ContractError(f"{_show(GT_META)} says human_verified but {gt_path} has rows without two "
                            "different reviewers")
    inventory = {r["device_id"]: r for r in read_csv(inv_path, INVENTORY_COLUMNS)} if inv_path.exists() else {}

    systems = load_runs(pred_paths, set(ids))
    out_dir = args.out_root / utc_stamp()
    res = build_report(truth_rows=truth, systems=systems, inventory=inventory, out_dir=out_dir,
                       label_status=label_status, sources={"ground truth": _show(gt_path), "inventory": _show(inv_path),
                                "as_of_date": as_of + (" (--as-of override)" if args.as_of else
                                                       f" ({_show(GT_META)})")})
    for name in systems:
        s = res["primary"][name]["all"]
        print(f"{name:9s} lane_acc={s.lane_acc:.2f} norm_all3={s.norm_acc('all_three'):.2f} "
              f"unknown_rate={s.unknown_rate:.2f}")
    print(f"as_of_date {as_of}")
    print(f"wrote {out_dir / 'report.md'} and failures.csv ({len(res['failures'])} failure rows)")
    return out_dir


if __name__ == "__main__":
    main()
