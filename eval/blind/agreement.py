"""Agreement between blind human labellers and data/ground_truth.csv.

Each labeller fills a copy of eval/blind/blind_worksheet.csv (vendor, product, version, lane,
and their initials in `labeller`) without looking at the ground truth or blind_key.csv.

Run:
  python eval/blind/agreement.py eval/blind/filled_HK.csv eval/blind/filled_QA.csv

For each labeller: percent agreement with the ground truth per field (vendor, product, version,
lane) and Cohen's kappa on lane. With two or more labellers, also lane agreement and kappa
between each pair. Blank answers count as disagreement and are reported separately.
Comparison follows docs/contracts.md: trim, case-insensitive; versions also drop a leading 'v'.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ("vendor", "product", "version", "lane")
LANES = ("patch", "retire", "fine", "unknown")


def read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]


def norm(field: str, value: str) -> str:
    v = (value or "").strip().lower()
    if field == "version" and v.startswith("v") and v[1:2].isdigit():
        v = v[1:]
    return v


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Cohen's kappa for two equal-length label lists. None if undefined (expected agreement 1)."""
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)


def score(labels: list[dict], truth_by_blind: dict[str, dict]) -> dict:
    out: dict = {"n": 0, "blank_lane": 0, "fields": {}, "lane_kappa": None, "disagreements": []}
    rows = [r for r in labels if r.get("blind_id") in truth_by_blind]
    out["n"] = len(rows)
    for f in FIELDS:
        agree = sum(norm(f, r.get(f, "")) == norm(f, truth_by_blind[r["blind_id"]][f]) for r in rows)
        out["fields"][f] = agree / len(rows) if rows else None
    out["blank_lane"] = sum(not r.get("lane") for r in rows)
    out["lane_kappa"] = cohen_kappa([norm("lane", r.get("lane", "")) for r in rows],
                                    [truth_by_blind[r["blind_id"]]["lane"] for r in rows])
    for r in rows:
        t = truth_by_blind[r["blind_id"]]
        if norm("lane", r.get("lane", "")) != t["lane"]:
            out["disagreements"].append((r["blind_id"], t["device_id"], r.get("lane", ""), t["lane"]))
    return out


def load_labellers(paths: list[Path]) -> dict[str, list[dict]]:
    """Group filled rows by the `labeller` column (falls back to the file name)."""
    by: dict[str, list[dict]] = {}
    for p in paths:
        for r in read_csv(p):
            by.setdefault(r.get("labeller") or Path(p).stem, []).append(r)
    return by


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("filled", nargs="+", type=Path, help="filled blind worksheet CSV(s)")
    ap.add_argument("--key", type=Path, default=ROOT / "eval/blind/blind_key.csv")
    ap.add_argument("--ground-truth", type=Path, default=ROOT / "data/ground_truth.csv")
    a = ap.parse_args(argv)

    gt = {r["device_id"]: r for r in read_csv(a.ground_truth)}
    truth_by_blind = {k["blind_id"]: gt[k["device_id"]] for k in read_csv(a.key)}
    labellers = load_labellers(a.filled)

    for name, rows in labellers.items():
        s = score(rows, truth_by_blind)
        pct = ", ".join(f"{f} {v:.0%}" if v is not None else f"{f} n/a" for f, v in s["fields"].items())
        k = "n/a" if s["lane_kappa"] is None else f"{s['lane_kappa']:.2f}"
        print(f"[{name}] vs ground truth, n={s['n']}: {pct}; lane kappa {k}; blank lanes {s['blank_lane']}")
        for bid, did, got, want in s["disagreements"]:
            print(f"    {bid} ({did}): labeller {got or '(blank)'} vs truth {want}")

    for x, y in combinations(sorted(labellers), 2):
        lx = {r["blind_id"]: norm("lane", r.get("lane", "")) for r in labellers[x]}
        ly = {r["blind_id"]: norm("lane", r.get("lane", "")) for r in labellers[y]}
        common = sorted(set(lx) & set(ly) & set(truth_by_blind))
        a_, b_ = [lx[c] for c in common], [ly[c] for c in common]
        agree = sum(p == q for p, q in zip(a_, b_)) / len(common) if common else 0
        k = cohen_kappa(a_, b_)
        print(f"[{x} vs {y}] lane agreement {agree:.0%} on {len(common)}; kappa {'n/a' if k is None else f'{k:.2f}'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
