"""Live smoke test: Normalizer -> Checker -> Planner with the REAL Gemini runner on an inventory.

    python eval/live_fixture_run.py                     # 8-device fixture, repeat 0 only
    python eval/live_fixture_run.py --repeats 3         # repeat_index 0..2
    DEMING_CACHE_DIR=<empty dir> python eval/live_fixture_run.py --repeats 3   # force live calls

Sequential calls (concurrency 1, docs/decisions.md "Live smoke test concurrency"). Uses the
response cache (.cache/gemini unless DEMING_CACHE_DIR is set), so reruns are free. The API key is
read by sim.gemini_runner from .env and is never printed. Runs with the DEFAULT Settings tab
(sim.loop.SETTINGS_DEFAULTS), as a real run would. Writes one contract predictions CSV per repeat
under eval/runs/, plus a JSON summary and a markdown report next to them: schema failures, call
counts and latency, lanes vs truth, and stability split into structured fields and free text.
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
from sim.gemini_runner import GeminiRunner, SchemaValidationFailed  # noqa: E402
from sim.loop import typed_settings  # noqa: E402
from sim.pipeline import run_device  # noqa: E402

FIX = ROOT / "eval" / "fixtures"
PRED_COLUMNS = ["device_id", "vendor", "product", "version", "confidence", "lane", "evidence", "run_id"]
# Stability fields. Structured: the contract fields (as eval/metrics.STRUCTURED_FIELDS) plus the
# Planner's structured choices. Free text: everything a model writes in prose.
STRUCTURED = ("lane", "vendor", "product", "version", "evidence")
PLANNER_STRUCTURED = ("action", "priority", "deadline", "escalate_to_human", "ticket_issue",
                      "ticket_create", "recipient")
FREE_TEXT = ("normalizer_reason", "checker_reason", "planner_subject", "planner_body", "planner_reason")


class TimedRunner(GeminiRunner):
    """Records latency per agent for real (non-cached) calls, and schema failures."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.timings: dict[str, list[float]] = defaultdict(list)
        self.cached: dict[str, int] = defaultdict(int)
        self.schema_failures: list[dict] = []

    def run(self, agent, payload, repeat_index=0):
        try:
            res = super().run(agent, payload, repeat_index)
        except SchemaValidationFailed as exc:
            self.schema_failures.append({"agent": agent, "repeat": repeat_index, "error": str(exc)[:500]})
            raise
        if res.cache_hit:
            self.cached[agent] += 1
        else:
            self.timings[agent].append(res.latency_s)
        return res


def _show(p: Path) -> str:
    """Repo-relative path when inside the repo, else absolute (posix)."""
    p = p.resolve()
    return (p.relative_to(ROOT) if p.is_relative_to(ROOT) else p).as_posix()


def _error(exc: BaseException) -> dict:
    cause = exc.__cause__
    return {"type": type(exc).__name__, "status": getattr(exc, "code", None),
            "message": str(exc)[:2000],
            "cause": str(cause)[:4000] if cause else None}


def _fields(r) -> dict:
    """One device result as flat structured and free-text fields."""
    n, c, p = r.normalized, r.check, r.plan
    ev = sorted(c.evidence_cve + ([c.evidence_lifecycle_id] if c.evidence_lifecycle_id else []))
    return {
        "lane": c.lane, "vendor": (n.vendor or "").strip().casefold(),
        "product": (n.product or "").strip().casefold(), "version": (n.version or "").strip().casefold(),
        "evidence": ";".join(ev),
        "action": p.action, "priority": p.priority, "deadline": str(p.deadline or ""),
        "escalate_to_human": p.escalate_to_human,
        "ticket_issue": p.ticket.issue if p.ticket else "", "ticket_create": p.ticket.create if p.ticket else "",
        "recipient": r.recipient,
        "normalizer_reason": n.reason, "checker_reason": c.reason,
        "planner_subject": p.message.subject if p.message else "",
        "planner_body": p.message.body if p.message else "", "planner_reason": p.reason,
    }


def _agreement(per_device: dict[str, list[dict]], fields: tuple[str, ...]) -> dict:
    """Per field: devices whose every repeat agrees; plus all fields together."""
    ids = [i for i, runs in per_device.items() if runs and all(runs)]  # devices with no ERROR repeat
    out = {f: sum(len({str(x[f]) for x in per_device[i]}) == 1 for i in ids) for f in fields}
    out["all"] = sum(all(len({str(x[f]) for x in per_device[i]}) == 1 for f in fields) for i in ids)
    return {"devices": len(ids), **{k: f"{v}/{len(ids)}" for k, v in out.items()}}


def _report_md(s: dict) -> str:
    L = [f"# Live fixture run ({s['model']}, as of {s['as_of_date']})", "",
         "Synthetic devices. No claim about real-world accuracy.", "",
         f"- Devices: {s['devices']}, repeats: {s['repeats']}, settings: {s['settings_source']}",
         f"- API calls: {s['api_calls']} (cache hits {s['cache_hits']}, 429/503 retries "
         f"{s['retries_429_503']}), wall time {s['wall_time_s']} s",
         f"- Schema validation failures: {len(s['schema_failures'])}; other errors: "
         f"{len(s['errors']) - len(s['schema_failures'])}",
         f"- Lanes vs fixture truth: {s['lane_correct_per_repeat']} correct per repeat", ""]
    L += ["## Lanes", "", "| Device | Truth | Predicted per repeat |", "|---|---|---|"]
    L += [f"| {i} | {v['truth']} | {' / '.join(v['pred'])} |" for i, v in s["lanes"].items()]
    if s["stability"]:
        st = s["stability"]
        L += ["", "## Stability across repeats", "",
              "Structured fields are compared exactly (vendor/product/version case-insensitive, "
              "evidence ids as a set); free text is compared exactly too, so any rewording counts.", ""]
        for name in ("structured", "planner_structured", "free_text"):
            L.append(f"- **{name}**: " + ", ".join(f"{k} {v}" for k, v in st[name].items() if k != "devices"))
    L += ["", "## Latency per agent (live calls only)", ""]
    L += [f"- {a}: {v['calls']} calls, mean {v['mean_s']} s, max {v['max_s']} s"
          for a, v in s["latency_per_agent"].items()]
    return "\n".join(L) + "\n"


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
    settings = typed_settings()  # the Settings tab defaults, not an empty dict
    devices = list(csv.DictReader(open(args.inventory, encoding="utf-8", newline="")))
    truth = {r["device_id"]: r for r in csv.DictReader(open(args.truth, encoding="utf-8", newline=""))}
    kev = retrieval.KevIndex.build(retrieval.load_kev(args.kev))
    lc = retrieval.load_lifecycle(args.lifecycle)
    runner = TimedRunner()
    lanes: dict[str, list[str]] = defaultdict(list)
    fields: dict[str, list[dict | None]] = defaultdict(list)
    errors, runs = [], []
    t_all = time.perf_counter()
    for rep in range(args.repeats):
        started = datetime.now(timezone.utc)
        run_id = "deming-" + started.strftime("%Y%m%dT%H%M%SZ")
        rows = []
        for d in devices:
            did = d["device_id"]
            try:
                r = run_device(runner, d, kev, lc, today=as_of, settings=settings, as_of_date=as_of,
                               repeat_index=rep)
            except Exception as exc:  # noqa: BLE001 - report every failure, keep going
                errors.append({"repeat": rep, "device_id": did, **_error(exc),
                               "trace_tail": traceback.format_exc().splitlines()[-1]})
                lanes[did].append("ERROR")
                fields[did].append(None)
                rows.append({"device_id": did, "vendor": "", "product": "", "version": "",
                             "confidence": "0.00", "lane": "unknown", "evidence": "", "run_id": run_id})
                continue
            ev = r.check.evidence_cve + ([r.check.evidence_lifecycle_id] if r.check.evidence_lifecycle_id else [])
            lanes[did].append(r.check.lane)
            fields[did].append(_fields(r))
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
        runs.append(_show(out))
        time.sleep(1.1)  # distinct run_id per repeat (second resolution)

    lat = {a: {"calls": len(v), "mean_s": round(sum(v) / len(v), 2), "max_s": round(max(v), 2)}
           for a, v in runner.timings.items() if v}
    ids = [d["device_id"] for d in devices]
    summary = {
        "model": runner.model, "as_of_date": as_of, "devices": len(devices), "repeats": args.repeats,
        "settings_source": "sim.loop.SETTINGS_DEFAULTS", "settings": settings,
        "wall_time_s": round(time.perf_counter() - t_all, 1),
        "api_calls": runner.stats["calls"], "cache_hits": runner.stats["cache_hits"],
        "retries_429_503": runner.stats["retries"], "latency_per_agent": lat,
        "cached_per_agent": dict(runner.cached), "schema_failures": runner.schema_failures,
        "errors": errors,
        "lanes": {i: {"pred": lanes[i], "truth": truth.get(i, {}).get("lane")} for i in ids},
        "lane_correct_per_repeat": [sum(lanes[i][k] == truth.get(i, {}).get("lane") for i in ids)
                                    for k in range(args.repeats)],
        "stability": {
            "structured": _agreement(fields, STRUCTURED),
            "planner_structured": _agreement(fields, PLANNER_STRUCTURED),
            "free_text": _agreement(fields, FREE_TEXT),
        } if args.repeats > 1 else None,
        "prediction_files": runs,
    }
    stem = f"live-summary-{Path(runs[-1]).parent.name}"
    path = args.out_root / f"{stem}.json"
    path.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    (args.out_root / f"{stem}.md").write_text(_report_md(summary), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("lanes", "settings")}, indent=1, default=str))
    print(f"summary: {_show(path)} (+ .md)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
