"""Lifecycle retrieval coverage, before vs after data/lifecycle_extended.csv. No network, no LLM.

    python eval/lifecycle_coverage.py            # writes docs/lifecycle-coverage.md

For each of the 60 devices, the device given to retrieval is the human-drafted identity from
data/ground_truth.csv (vendor, product, version) plus the inventory's firmware_version_raw.
Ground truth has no model column, so no model is given: hardware rows with a model pattern
(e.g. RV32*, *T35) can't be tested against it and come back on the vendor/product name alone.

"Before" = data/lifecycle.csv (30 rows, what the published results used).
"After"  = data/lifecycle.csv + data/lifecycle_extended.csv (retrieval.load_lifecycle with
           include_extended=True).

A returned row MATCHES the device if its vendor equals the truth vendor and either its product
equals the truth product or its model_pattern was tested against the device and fits
(case-insensitive). Three measures:
  any      a matching row is returned
  dated    a matching row with a support-end date (eol_date or last_security_support_date)
           whose pattern fits the device or is blank (whole product)
  name     a matching row with a support-end date whose pattern could NOT be tested (no model /
           no version in the truth identity); it may or may not apply to this device
This measures retrieval only. Lane accuracy with the extended rows needs a new Gemini run and
has NOT been measured.
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim import retrieval  # noqa: E402

OUT = ROOT / "docs" / "lifecycle-coverage.md"
GROUP_ORDER = ["clear_patch", "clear_retire", "supported_fine", "messy_name", "name_collision",
               "critical_dnt"]


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _n(s: str | None) -> str:
    return (s or "").strip().casefold()


def classify(device: dict, truth: dict, candidates: list[dict]) -> dict:
    match, dated, name_only = [], [], []
    for r in candidates:
        fits = retrieval.pattern_matches(r, device)
        if _n(r["vendor"]) != _n(truth["vendor"]) or not _n(truth["vendor"]):
            continue
        if not (_n(r["product"]) == _n(truth["product"]) and _n(truth["product"])) and fits is not True:
            continue
        match.append(r["lifecycle_id"])
        if not (r.get("eol_date") or r.get("last_security_support_date")):
            continue
        blank = not (r.get("model_pattern") or "").strip()
        (dated if fits is True or blank else name_only).append(r["lifecycle_id"])
    return {"returned": [r["lifecycle_id"] for r in candidates], "match": match,
            "dated": dated, "name": name_only}


def measure(lifecycle_path: Path = ROOT / "data/lifecycle.csv",
            extended_path: Path = retrieval.EXTENDED_LIFECYCLE_PATH) -> dict:
    inv = {r["device_id"]: r for r in _read(ROOT / "data/inventory.csv")}
    truth = _read(ROOT / "data/ground_truth.csv")
    before_rows = retrieval.load_lifecycle(lifecycle_path, include_extended=False)
    after_rows = retrieval.load_lifecycle(lifecycle_path, include_extended=True,
                                          extended_path=extended_path)
    out = OrderedDict()
    for t in truth:
        dev = {"vendor": t["vendor"], "product": t["product"], "version": t["version"],
               "firmware_version_raw": inv[t["device_id"]]["firmware_version_raw"]}
        out[t["device_id"]] = {
            "group": t["group"], "vendor": t["vendor"], "product": t["product"],
            "version": t["version"], "lane": t["lane"],
            "before": classify(dev, t, retrieval.lifecycle_candidates(dev, before_rows)),
            "after": classify(dev, t, retrieval.lifecycle_candidates(dev, after_rows)),
        }
    by_id = {r["lifecycle_id"]: r for r in after_rows}
    fits_raw = OrderedDict()
    for i, d in out.items():
        words = [w for w in re.split(r"[^a-z0-9.\-]+", _n(inv[i]["device_name_raw"])) if w]
        new = [x for x in d["after"]["name"] if x not in d["before"]["name"]]
        fits_raw[i] = [x for x in new
                       if any(fnmatch.fnmatchcase(w, _n(by_id[x]["model_pattern"])) for w in words)]
    return {"n_before": len(before_rows), "n_after": len(after_rows), "devices": out,
            "name_fits_raw": fits_raw}


def _count(devs: list[dict], when: str, key: str) -> int:
    return sum(bool(d[when][key]) for d in devs)


def render(m: dict) -> str:
    devs = m["devices"]
    groups = OrderedDict([("all", list(devs.values()))])
    for g in GROUP_ORDER + sorted({d["group"] for d in devs.values()} - set(GROUP_ORDER)):
        groups[g] = [d for d in devs.values() if d["group"] == g]

    L = ["# Lifecycle retrieval coverage: 30 rows vs 30 + extended", "",
         "Generated by `python eval/lifecycle_coverage.py` (offline: no network, no LLM or Gemini "
         "call). Synthetic inventory.", "",
         "**The published Deming results used only the original 30 rows of `data/lifecycle.csv`.** "
         "`data/lifecycle_extended.csv` is off by default. This page measures **retrieval coverage "
         "only**. The effect of the extended rows on lane accuracy has **NOT been measured**; that "
         "needs a new Gemini run.", "",
         f"- Before: `data/lifecycle.csv`, {m['n_before']} rows.",
         f"- After: `data/lifecycle.csv` + `data/lifecycle_extended.csv`, {m['n_after']} rows "
         "(`retrieval.load_lifecycle(..., include_extended=True)`, or `DEMING_LIFECYCLE_EXTENDED=1`).",
         "- Device identity given to retrieval: the human-drafted `vendor`, `product`, `version` "
         "from `data/ground_truth.csv`, plus the inventory `firmware_version_raw`. Ground truth has "
         "no model column, so no model is given.",
         f"- Retrieval: `sim/retrieval.lifecycle_candidates`, top {retrieval.TOP_K_LIFECYCLE}, unchanged.",
         "", "## Measures", "",
         "A returned row **matches** when its vendor equals the truth vendor and either its product "
         "equals the truth product or its `model_pattern` was tested against the device and fits.",
         "",
         "| Measure | Meaning |", "|---|---|",
         "| any | a matching row is returned (with or without dates) |",
         "| dated | a matching row with a support-end date (`eol_date` or "
         "`last_security_support_date`) whose pattern fits the device or is blank |",
         "| name-only | a matching dated row whose pattern could not be tested (no model, or no "
         "version, in the truth identity). It may not apply to this device, so it is NOT counted "
         "as dated |", "",
         "## Coverage by group", "",
         "| Group | n | any before | any after | dated before | dated after | name-only before | name-only after |",
         "|---|---|---|---|---|---|---|---|"]
    for g, ds in groups.items():
        n = len(ds)
        L.append(f"| {g} | {n} | " + " | ".join(
            f"{_count(ds, w, k)}/{n}" for k in ("match", "dated", "name") for w in ("before", "after")) + " |")

    def gained(key: str) -> list[str]:
        return [i for i, d in devs.items() if d["after"][key] and not d["before"][key]]

    def new_rows(i: str, key: str) -> str:
        return ", ".join(x for x in devs[i]["after"][key] if x not in devs[i]["before"][key])

    L += ["", "## Devices that gained coverage", ""]
    for key, title in (("match", "any"), ("dated", "dated"), ("name", "name-only")):
        ids = gained(key)
        L.append(f"**{title}** ({len(ids)}): " + (", ".join(f"{i} ({new_rows(i, key)})" for i in ids)
                                                 if ids else "none"))
        L.append("")
    L += ["Informational, not a measure (uses the raw device name, which the truth identity does "
          "not): new name-only rows whose model_pattern fits a word of `device_name_raw`: "
          + (", ".join(f"{i} ({', '.join(xs)})" for i, xs in m["name_fits_raw"].items() if xs) or "none")
          + ". For the other devices the raw name names no model these rows fit, so the rows are "
          "returned on the vendor/product name alone.", ""]
    added = [i for i, d in devs.items()
             if any(x not in d["before"]["dated"] + d["before"]["name"] for x in d["after"]["dated"] + d["after"]["name"])
             and i not in gained("dated") and i not in gained("name")]
    L.append(f"**Already covered, extra dated row returned** ({len(added)}): "
             + (", ".join(f"{i} ({', '.join(x for x in devs[i]['after']['dated'] + devs[i]['after']['name'] if x not in devs[i]['before']['dated'] + devs[i]['before']['name'])})"
                          for i in added) if added else "none"))
    L.append("")

    lost = [(i, [x for x in d["before"]["returned"] if x not in d["after"]["returned"]])
            for i, d in devs.items()]
    lost = [(i, xs) for i, xs in lost if xs]
    top = [(i, d["before"]["returned"][0], d["after"]["returned"][0]) for i, d in devs.items()
           if d["before"]["returned"] and d["after"]["returned"]
           and d["before"]["returned"][0] != d["after"]["returned"][0]]
    L += ["## Side effects on retrieval", "",
          f"**Rows pushed out of the top {retrieval.TOP_K_LIFECYCLE}** ({len(lost)}): "
          + ("; ".join(f"{i} lost {', '.join(xs)}" for i, xs in lost) if lost else "none"), "",
          f"**First-ranked row changed** ({len(top)}): "
          + ("; ".join(f"{i} {a} -> {b}" for i, a, b in top) if top else "none"), "",
          "A changed first row can change what the Checker reads first; whether that changes any "
          "lane is exactly what has not been measured.", "",
          "## Per device", "",
          "| Device | Group | Truth vendor / product / version | Truth lane | Returned before | Returned after | dated after | name-only after |",
          "|---|---|---|---|---|---|---|---|"]
    for i, d in devs.items():
        L.append(f"| {i} | {d['group']} | {d['vendor']} / {d['product']} / {d['version']} | {d['lane']} | "
                 f"{', '.join(d['before']['returned']) or '-'} | {', '.join(d['after']['returned']) or '-'} | "
                 f"{', '.join(d['after']['dated']) or '-'} | {', '.join(d['after']['name']) or '-'} |")
    L += ["", "## Limits", "",
          "- Retrieval coverage is not lane accuracy. No Gemini run used the extended rows.",
          "- No model is in the truth identity, so model-specific hardware rows (Cisco RV, D-Link NAS, "
          "WatchGuard T35) can only be name-only here. In a real run the Normalizer's `model` field "
          "decides whether they fit.",
          "- Rows are added only where a source states the date explicitly; the skipped products and "
          "why are printed by `python scripts/build_lifecycle_extended.py` and listed in "
          "`docs/decisions.md`.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    text = render(measure())
    a.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
