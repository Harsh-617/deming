"""Offline analysis of the prompts-v1 full run. Makes NO API calls.

    python eval/offline_analysis.py --results eval/results/<stamp> \
        --baseline eval/runs/<baseline-run>/baseline.csv \
        --deming eval/runs/<rep0>/deming.csv eval/runs/<rep1>/deming.csv

Writes <results>/offline_analysis.json and offline_analysis.md:
1. Per-slice scores (all / verified / unverified / each group) for EVERY complete Deming repeat
   and the baseline, with strict string matching (eval/metrics.py).
2. Stability across the complete repeats (eval/metrics.stability).
3. Footnote: stability across 3 repeats for the devices whose third repeat finished
   (--three-repeat-ids, default DEV-001..DEV-040). Repeat 2's CSV holds error rows from a
   network drop, so it is NOT read. Instead those devices are replayed from the on-disk
   response cache with a client that raises on any call: a cache miss is an error, never a call.
4. POST-HOC alias view (defined after seeing the results): vendor/product compared after mapping
   product-name aliases that name the same product line (ALIASES below). Applied to both systems.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))

import metrics  # noqa: E402

# POST-HOC. Truth product (casefold) -> predicted names (casefold) accepted as the same product
# line. Written after reading the strict-match failures. Generic names that don't pin the line
# ("Secure Mobile Access", "Firewall", "Router") and different lines ("Connect Secure" for the
# Pulse 9.1x line, "SMA 400 Series" for an SMA 410, "Sophos Firewall" for XG hardware) are
# deliberately NOT aliases.
ALIASES = {
    "connect secure, policy secure, and zta gateways": {"connect secure", "ivanti connect secure"},
    "dir-600 router": {"dir-600"},
    "dir-859 router": {"dir-859"},
    "firebox": {"fireware", "fireware os"},  # Fireware is the OS of Firebox (same lifecycle row)
    "multiple firewalls": {"usg60"},
    "multiple nas devices": {"dns-320l", "dns-325 sharecenter", "dns-325"},
    "nvrmini2 devices": {"nvrmini 2", "nvrmini2"},
    "netscaler adc and gateway": {"application delivery controller and gateway",
                                  "netscaler adc and netscaler gateway", "netscaler adc",
                                  "netscaler gateway", "netscaler"},
    "sma100 appliances": {"sma 210", "secure mobile access (sma) 100 series", "sma100"},
    "sma1000 appliances": {"sma 1000 series"},
    "secure firewall adaptive security appliance and secure firewall threat defense":
        {"adaptive security appliance software"},
    "adaptive security appliance (asa)": {"adaptive security appliance software"},
    "small business rv series routers": {"rv042 and rv042g dual wan vpn routers",
                                         "small business rv320 and rv325 routers"},
    "small business rv160, rv260, rv340, and rv345 series routers":
        {"small business rv340, rv340w, rv345, and rv345p routers",
         "rv345 and rv345p dual wan gigabit vpn routers"},
    "vigor routers": {"vigor300b"},
}


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def alias_match(truth: dict, pred: dict | None) -> dict[str, bool]:
    if pred is None:
        return {"vendor": False, "product": False, "vendor_product": False}
    n = metrics.norm
    v = n(pred.get("vendor")) == n(truth.get("vendor"))
    tp, pp = n(truth.get("product")), n(pred.get("product"))
    p = tp == pp or (bool(tp) and pp in ALIASES.get(tp, set()))
    return {"vendor": v, "product": p, "vendor_product": v and p}


def alias_view(truth_rows: list[dict], preds: dict[str, dict]) -> dict:
    out = {}
    for name, rows in metrics.slices(truth_rows).items():
        if not rows:
            out[name] = None
            continue
        m = [alias_match(t, preds.get(t["device_id"])) for t in rows]
        strict = [metrics.field_matches(preds.get(t["device_id"]), t) for t in rows]
        out[name] = {"n": len(rows),
                     "strict_product": sum(s["product"] for s in strict) / len(rows),
                     "alias_vendor": sum(x["vendor"] for x in m) / len(rows),
                     "alias_product": sum(x["product"] for x in m) / len(rows),
                     "alias_vendor_product": sum(x["vendor_product"] for x in m) / len(rows)}
    return out


def replay_from_cache(ids: list[str], repeats: int) -> list[dict[str, dict]]:
    """Predictions rebuilt from the response cache only. Raises on any cache miss."""
    from sim import config, retrieval
    from sim.gemini_runner import GeminiRunner
    from sim.loop import typed_settings
    from sim.pipeline import run_device

    class _NoNetwork:
        class models:  # noqa: N801 - mimics client.models
            @staticmethod
            def generate_content(**_):
                raise RuntimeError("cache miss: offline analysis never calls the API")

    inv = {r["device_id"]: r for r in read(ROOT / "data/inventory.csv")}
    kev = retrieval.KevIndex.build(retrieval.load_kev(ROOT / "data/feeds/kev.json"))
    lc = retrieval.load_lifecycle(ROOT / "data/lifecycle.csv")
    as_of = config.load_as_of_date()
    settings = typed_settings()
    runner = GeminiRunner(client=_NoNetwork())
    runs = []
    for rep in range(repeats):
        preds = {}
        for did in ids:
            r = run_device(runner, inv[did], kev, lc, today=as_of, settings=settings,
                           as_of_date=as_of, repeat_index=rep)
            ev = r.check.evidence_cve + ([r.check.evidence_lifecycle_id] if r.check.evidence_lifecycle_id else [])
            preds[did] = {"device_id": did, "vendor": r.normalized.vendor or "",
                          "product": r.normalized.product or "", "version": r.normalized.version or "",
                          "confidence": f"{r.normalized.confidence:.2f}", "lane": r.check.lane,
                          "evidence": ";".join(ev)}
        runs.append(preds)
    if runner.stats["calls"]:
        raise RuntimeError("an API call was attempted")
    return runs


def fmt(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--deming", type=Path, nargs="+", required=True)
    p.add_argument("--three-repeat-ids", default="DEV-001:DEV-040")
    a = p.parse_args(argv)

    truth = read(ROOT / "data/ground_truth.csv")
    ids = {t["device_id"] for t in truth}
    base = metrics.index_predictions(read(a.baseline), ids)
    dem = [metrics.index_predictions(read(f), ids) for f in a.deming]

    scores = {"baseline": {k: v.as_dict() for k, v in metrics.score_slices(truth, base).items()}}
    for i, d in enumerate(dem):
        scores[f"deming_rep{i}"] = {k: v.as_dict() for k, v in metrics.score_slices(truth, d).items()}
    confusion = {f"deming_rep{i}": {t: dict(c) for t, c in metrics.score(truth, d).confusion.items()}
                 for i, d in enumerate(dem)}
    confusion["baseline"] = {t: dict(c) for t, c in metrics.score(truth, base).confusion.items()}
    stab2 = metrics.stability(truth, dem)

    lo, hi = a.three_repeat_ids.split(":")
    sub_ids = sorted(i for i in ids if lo <= i <= hi)
    sub_truth = [t for t in truth if t["device_id"] in sub_ids]
    replay = replay_from_cache(sub_ids, 3)
    # Sanity: the replayed repeats 0 and 1 must equal the published CSVs on these devices.
    mismatch = [(k, did) for k in range(min(2, len(dem))) for did in sub_ids
                if any(metrics.norm(replay[k][did][f]) != metrics.norm(dem[k][did][f])
                       for f in ("vendor", "product", "version", "lane"))
                or metrics.evidence_ids(replay[k][did]["evidence"]) != metrics.evidence_ids(dem[k][did]["evidence"])]
    stab3 = metrics.stability(sub_truth, replay)
    stab2_sub = metrics.stability(sub_truth, dem)
    lanes3 = {did: [r[did]["lane"] for r in replay] for did in sub_ids}

    alias = {"baseline": alias_view(truth, base),
             **{f"deming_rep{i}": alias_view(truth, d) for i, d in enumerate(dem)}}

    out = {"scores": scores, "confusion_all": confusion, "stability_complete_repeats": stab2,
           "footnote_three_repeats": {"device_ids": f"{lo}..{hi}", "n": len(sub_ids),
                                      "stability_3_repeats": stab3,
                                      "stability_2_repeats_same_devices": stab2_sub,
                                      "replay_vs_published_mismatches": mismatch,
                                      "lanes": lanes3},
           "posthoc_alias_view": alias, "aliases": {k: sorted(v) for k, v in ALIASES.items()}}
    (a.results / "offline_analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    systems = ["baseline"] + [f"deming_rep{i}" for i in range(len(dem))]
    keys = ["norm_vendor", "norm_product", "norm_version", "norm_all_three", "lane_accuracy",
            "exposure_precision", "exposure_recall", "unknown_rate", "unknown_precision", "unknown_recall"]
    L = ["# Offline analysis (no API calls)", "",
         "Synthetic inventory; no real-world accuracy or time-saved claim. All 60 ground-truth rows "
         "are unverified. Repeat 2 is excluded from every score.", ""]
    for sl in scores["baseline"]:
        n = scores["baseline"][sl]["n"]
        L += [f"## {sl} (n={n})", "", "| Metric | " + " | ".join(systems) + " |",
              "|---|" + "---|" * len(systems)]
        if n == 0:
            L += ["| (no rows) |" + " |" * len(systems), ""]
            continue
        L += [f"| {k} | " + " | ".join(fmt(scores[s][sl][k]) for s in systems) + " |" for k in keys]
        L.append("")
    fa = stab2["field_agreement"]
    L += ["## Stability, complete repeats (0 and 1, n=60)", "",
          f"lane {fmt(fa['lane'])}, vendor {fmt(fa['vendor'])}, product {fmt(fa['product'])}, "
          f"version {fmt(fa['version'])}, evidence {fmt(fa['evidence'])}, "
          f"all structured {fmt(stab2['structured_agreement'])}", "",
          "Unstable devices: " + ", ".join(f"{u['device_id']} ({'/'.join(u['fields'])})"
                                            for u in stab2["unstable_devices"]), ""]
    f3 = stab3["field_agreement"]
    L += [f"## Footnote: 3 repeats on {lo}..{hi} (n={len(sub_ids)}, replayed from cache)", "",
          f"lane {fmt(f3['lane'])}, vendor {fmt(f3['vendor'])}, product {fmt(f3['product'])}, "
          f"version {fmt(f3['version'])}, evidence {fmt(f3['evidence'])}, "
          f"all structured {fmt(stab3['structured_agreement'])}", "",
          f"Replay vs published CSVs (repeats 0-1): {len(mismatch)} mismatches.", ""]
    L += ["## POST-HOC alias view (defined after seeing the results)", "",
          "| Slice | System | strict product | alias vendor | alias product | alias vendor+product |",
          "|---|---|---|---|---|---|"]
    for sl in alias["baseline"]:
        for s in systems:
            v = alias[s][sl]
            if v:
                L.append(f"| {sl} | {s} | {fmt(v['strict_product'])} | {fmt(v['alias_vendor'])} | "
                         f"{fmt(v['alias_product'])} | {fmt(v['alias_vendor_product'])} |")
    (a.results / "offline_analysis.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {a.results / 'offline_analysis.json'} and .md; replay mismatches: {len(mismatch)}; "
          f"api calls: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
