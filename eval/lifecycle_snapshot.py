"""Deterministic snapshot of lifecycle retrieval + mock-pipeline predictions. No API calls.

Used by eval/test_lifecycle_extended.py to prove that, with the extended lifecycle file switched
off (the default), retrieval results and mock-pipeline predictions are byte-identical to the
ones main produced. The golden file eval/fixtures/lifecycle_flag_off_golden.json was written by
this module on main (4bd5cfb) before sim/retrieval.py gained the optional extended file:

    python eval/lifecycle_snapshot.py --write eval/fixtures/lifecycle_flag_off_golden.json

The mock model is sim/mock_llm.py (rule-based, no network); its runner is GeminiRunner with that
client and no response cache.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim import config, retrieval  # noqa: E402
from sim.gemini_runner import GeminiRunner  # noqa: E402
from sim.loop import typed_settings  # noqa: E402
from sim.mock_llm import rule_based_client  # noqa: E402
from sim.pipeline import run_device  # noqa: E402


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def snapshot(lifecycle_rows: list[dict] | None = None) -> str:
    """JSON text: per device, the lifecycle candidates for the ground-truth identity and the
    mock pipeline's prediction (with its lifecycle candidates). `lifecycle_rows` defaults to
    retrieval.load_lifecycle(data/lifecycle.csv) with no extra arguments, i.e. the default
    behaviour of whatever sim/retrieval.py is checked out."""
    inv = _read(ROOT / "data/inventory.csv")
    gt = {r["device_id"]: r for r in _read(ROOT / "data/ground_truth.csv")}
    if lifecycle_rows is None:
        lifecycle_rows = retrieval.load_lifecycle(ROOT / "data/lifecycle.csv")
    kev = retrieval.KevIndex.build(retrieval.load_kev(ROOT / "data/feeds/kev.json"))
    catalog = list(kev.keys) + [(r["vendor"], r["product"]) for r in lifecycle_rows]
    runner = GeminiRunner(rule_based_client(catalog), cache_dir=None)
    as_of = config.load_as_of_date()
    settings = typed_settings()
    out = {"lifecycle_ids": [r["lifecycle_id"] for r in lifecycle_rows], "devices": {}}
    for d in inv:
        t = gt[d["device_id"]]
        truth_dev = {"vendor": t["vendor"], "product": t["product"], "version": t["version"],
                     "firmware_version_raw": d["firmware_version_raw"]}
        r = run_device(runner, d, kev, lifecycle_rows, today=as_of, settings=settings,
                       as_of_date=as_of)
        out["devices"][d["device_id"]] = {
            "truth_lifecycle_candidates": retrieval.lifecycle_candidates(truth_dev, lifecycle_rows),
            "mock": {"vendor": r.normalized.vendor or "", "product": r.normalized.product or "",
                     "model": r.normalized.model or "", "version": r.normalized.version or "",
                     "confidence": f"{r.normalized.confidence:.2f}", "lane": r.check.lane,
                     "evidence_cve": r.check.evidence_cve,
                     "evidence_lifecycle_id": r.check.evidence_lifecycle_id or "",
                     "lifecycle_candidates": r.lifecycle_candidates,
                     "guard_notes": r.guard_notes},
        }
    return json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--write", type=Path, required=True)
    a = p.parse_args(argv)
    a.write.write_text(snapshot(), encoding="utf-8", newline="\n")
    print(f"wrote {a.write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
