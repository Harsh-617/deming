"""Live smoke test: Normalizer -> Checker -> Planner with the REAL Gemini runner on an inventory.

    python eval/live_fixture_run.py                     # 8-device fixture, repeat 0 only
    python eval/live_fixture_run.py --repeats 3         # repeat_index 0..2 (0 comes from cache)

Sequential calls (concurrency 1, docs/decisions.md "Live smoke test concurrency"). Uses the
response cache (.cache/gemini), so reruns are free. The API key is read by sim.gemini_runner from
.env and is never printed. Writes one contract predictions CSV per repeat under eval/runs/ and a
JSON summary (per-agent latency, call counts, errors, lanes vs truth, stability) next to them.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim import config, retrieval  # noqa: E402
from sim.gemini_runner import GeminiRunner  # noqa: E402
from sim.pipeline import run_device  # noqa: E402

FIX = ROOT / "eval" / "fixtures"
PRED_COLUMNS = ["device_id", "vendor", "product", "version", "confidence", "lane", "evidence", "run_id"]


class TimedRunner(GeminiRunner):
    """Records latency per agent for real (non-cached) calls."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.timings: dict[str, list[float]] = defaultdict(list)
        self.cached: dict[str, int] = defaultdict(int)

    def run(self, agent, payload, repeat_index=0):
        res = super().run(agent, payload, repeat_index)
        if res.cache_hit:
            self.cached[agent] += 1
        else:
            self.timings[agent].append(res.latency_s)
        return res


def _error(exc: BaseException) -> dict:
    cause = exc.__cause__
    return {"type": type(exc).__name__, "status": getattr(exc, "code", None),
            "message": str(exc)[:2000],
            "cause": str(cause)[:4000] if cause else None}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, default=FIX / "inventory.csv")
    p.add_argument("--truth", type=Path, default=FIX / "ground_truth.csv")
    p.add_argument("--kev", type=Path, default=FIX / "feeds" / "kev.json")
    p.add_argument("--lifecycle", type=Path, default=FIX / "lifecycle.csv")
    p.add_argument("--as-of", default=None)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--out-root", type=Path, default=ROOT / "eval" / "runs")
    args = p.parse_args(argv)

    as_of = config.load_as_of_date(args.as_of)
    devices = list(csv.DictReader(open(args.inventory, encoding="utf-8", newline="")))
    truth = {r["device_id"]: r for r in csv.DictReader(open(args.truth, encoding="utf-8", newline=""))}
    kev = retrieval.KevIndex.build(retrieval.load_kev(args.kev))
    lc = retrieval.load_lifecycle(args.lifecycle)
    runner = TimedRunner()
    lanes: dict[str, list[str]] = defaultdict(list)
    outputs: dict[str, list[str]] = defaultdict(list)
    errors, runs = [], []
    t_all = time.perf_counter()
    for rep in range(args.repeats):
        started = datetime.now(timezone.utc)
        run_id = "deming-" + started.strftime("%Y%m%dT%H%M%SZ")
        rows = []
        for d in devices:
            did = d["device_id"]
            try:
                r = run_device(runner, d, kev, lc, today=as_of, settings={}, as_of_date=as_of,
                               repeat_index=rep)
            except Exception as exc:  # noqa: BLE001 - report every failure, keep going
                errors.append({"repeat": rep, "device_id": did, **_error(exc),
                               "trace_tail": traceback.format_exc().splitlines()[-1]})
                lanes[did].append("ERROR")
                outputs[did].append("ERROR")
                rows.append({"device_id": did, "vendor": "", "product": "", "version": "",
                             "confidence": "0.00", "lane": "unknown", "evidence": "", "run_id": run_id})
                continue
            ev = r.check.evidence_cve + ([r.check.evidence_lifecycle_id] if r.check.evidence_lifecycle_id else [])
            lanes[did].append(r.check.lane)
            outputs[did].append(json.dumps([r.normalized.model_dump(mode="json"),
                                            r.check.model_dump(mode="json"),
                                            r.plan.model_dump(mode="json")], sort_keys=True))
            rows.append({"device_id": did, "vendor": r.normalized.vendor or "",
                         "product": r.normalized.product or "", "version": r.normalized.version or "",
                         "confidence": f"{r.normalized.confidence:.2f}", "lane": r.check.lane,
                         "evidence": ";".join(ev), "run_id": run_id})
            print(f"rep {rep} {did}: lane {r.check.lane:7s} truth {truth.get(did, {}).get('lane', '?'):7s}"
                  + (f"  guards: {'; '.join(r.guard_notes)}" if r.guard_notes else ""))
        out = args.out_root / run_id / "deming.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PRED_COLUMNS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        runs.append(str(out.relative_to(ROOT).as_posix()))
        time.sleep(1.1)  # distinct run_id per repeat (second resolution)

    lat = {a: {"calls": len(v), "mean_s": round(sum(v) / len(v), 2), "max_s": round(max(v), 2)}
           for a, v in runner.timings.items() if v}
    ids = [d["device_id"] for d in devices]
    lane_agree = sum(len(set(lanes[i])) == 1 for i in ids)
    full_agree = sum(len(set(outputs[i])) == 1 for i in ids)
    summary = {
        "model": runner.model, "as_of_date": as_of, "devices": len(devices), "repeats": args.repeats,
        "wall_time_s": round(time.perf_counter() - t_all, 1),
        "api_calls": runner.stats["calls"], "cache_hits": runner.stats["cache_hits"],
        "retries_429_503": runner.stats["retries"], "latency_per_agent": lat,
        "cached_per_agent": dict(runner.cached), "errors": errors,
        "lanes": {i: {"pred": lanes[i], "truth": truth.get(i, {}).get("lane")} for i in ids},
        "lane_correct_repeat0": sum(lanes[i][0] == truth.get(i, {}).get("lane") for i in ids),
        "stability": {"lane_agreement": f"{lane_agree}/{len(ids)}",
                      "full_output_agreement": f"{full_agree}/{len(ids)}"} if args.repeats > 1 else None,
        "prediction_files": runs,
    }
    path = args.out_root / f"live-summary-{runs[-1].split('/')[-2]}.json"
    path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "lanes"}, indent=1))
    print(f"summary: {path.relative_to(ROOT).as_posix()}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
