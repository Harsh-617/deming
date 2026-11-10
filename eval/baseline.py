"""Naive KEV-matching baseline (the thing Deming has to beat).

What public "cross-reference your inventory with KEV" guides describe:
  1. lowercase the inventory name;
  2. if a KEV `product` appears as a substring of the name -> match (score 100);
  3. otherwise fuzzy-match the name against "vendorProject product" with rapidfuzz WRatio;
  4. best score >= threshold -> matched.

Lane rule (deliberately naive, ignores version):
  matched in KEV                                   -> patch
  matched AND a lifecycle row says patch_available=false -> retire
  no match                                          -> fine
It NEVER outputs `unknown` (PRD). It reads only local files; no network.

Usage:
  python eval/baseline.py                         # real data/ files
  python eval/baseline.py --inventory eval/fixtures/inventory.csv \
      --kev eval/fixtures/feeds/kev.json --lifecycle eval/fixtures/lifecycle.csv --out-root eval/fixtures/runs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path

from rapidfuzz import fuzz, utils

from io_utils import INVENTORY_COLUMNS, PREDICTION_COLUMNS, norm, read_csv, utc_stamp, write_csv

REPO = Path(__file__).resolve().parent.parent
DEFAULT_THRESHOLD = 85.0  # rapidfuzz 0-100 scale; see docs/decisions/eval.md


def load_kev(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("vulnerabilities", [])


def kev_products(vulns: list[dict]) -> dict[tuple[str, str], list[str]]:
    """(vendorProject, product) -> sorted list of cveIDs."""
    out: dict[tuple[str, str], list[str]] = {}
    for v in vulns:
        key = (v.get("vendorProject", "").strip(), v.get("product", "").strip())
        if key[0] or key[1]:
            out.setdefault(key, []).append(v.get("cveID", ""))
    return {k: sorted(c for c in v if c) for k, v in out.items()}


def score_pair(name: str, vendor: str, product: str) -> float:
    name_l = name.lower()
    product_l = product.lower().strip()
    if product_l and product_l in name_l:
        return 100.0
    return float(fuzz.WRatio(name, f"{vendor} {product}", processor=utils.default_process))


def best_match(name: str, products: dict[tuple[str, str], list[str]]) -> tuple[tuple[str, str] | None, float]:
    """Highest-scoring KEV (vendor, product). Ties broken alphabetically for determinism."""
    best_key, best = None, -1.0
    for key in sorted(products):
        s = score_pair(name, *key)
        if s > best:
            best_key, best = key, s
    return best_key, max(best, 0.0)


def find_lifecycle(vendor: str, product: str, lifecycle: list[dict]) -> dict | None:
    for row in lifecycle:
        if norm(row.get("vendor")) != norm(vendor) or norm(row.get("product")) != norm(product):
            continue
        pattern = norm(row.get("model_pattern")) or "*"
        if fnmatchcase(norm(product), pattern):
            return row
    return None


def clean_version(raw: str) -> str:
    """Naive: trim and drop a leading v/V."""
    return re.sub(r"^[vV](?=\d)", "", (raw or "").strip())


def predict(inventory: list[dict], vulns: list[dict], lifecycle: list[dict],
            run_id: str, threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    products = kev_products(vulns)
    rows = []
    for dev in inventory:
        name = dev.get("device_name_raw", "")
        key, score = best_match(name, products) if products else (None, 0.0)
        row = {
            "device_id": dev["device_id"],
            "vendor": "", "product": "",
            "version": clean_version(dev.get("firmware_version_raw", "")),
            "confidence": f"{score / 100:.2f}",
            "lane": "fine", "evidence": "", "run_id": run_id,
        }
        if key is not None and score >= threshold:
            vendor, product = key
            evidence = list(products[key])
            lane = "patch"
            lc = find_lifecycle(vendor, product, lifecycle)
            if lc is not None and norm(lc.get("patch_available")) == "false":
                lane = "retire"
                evidence.append(lc["lifecycle_id"])
            row.update(vendor=vendor, product=product, lane=lane, evidence=";".join(evidence))
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> Path:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--inventory", default=REPO / "data/inventory.csv")
    p.add_argument("--kev", default=REPO / "data/feeds/kev.json")
    p.add_argument("--lifecycle", default=REPO / "data/lifecycle.csv")
    p.add_argument("--out-root", default=REPO / "eval/runs", help="writes <out-root>/<run_id>/baseline.csv")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p.add_argument("--run-id", default=None, help="override (tests); default baseline-<UTC stamp>")
    args = p.parse_args(argv)

    inventory = read_csv(args.inventory, INVENTORY_COLUMNS)
    vulns = load_kev(args.kev)
    lifecycle = read_csv(args.lifecycle) if Path(args.lifecycle).exists() else []
    if not lifecycle:
        print(f"warning: no lifecycle rows at {args.lifecycle}; baseline can't output retire", file=sys.stderr)
    run_id = args.run_id or f"baseline-{utc_stamp()}"
    rows = predict(inventory, vulns, lifecycle, run_id, args.threshold)
    out = Path(args.out_root) / run_id / "baseline.csv"
    write_csv(out, PREDICTION_COLUMNS, rows)
    print(f"wrote {out} ({len(rows)} devices)")
    return out


if __name__ == "__main__":
    main()
