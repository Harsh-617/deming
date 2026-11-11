"""Write eval/results/<timestamp>/report.md and failures.csv."""
from __future__ import annotations

from pathlib import Path

from io_utils import EXPOSED_LANES, LANES, norm, write_csv
from metrics import (COMPARABLE, FIELDS, MISSING, Scores, baseline_ties_or_beats, field_matches,
                     groups_of, is_verified, score_slices, stability_slices)

# How the ground-truth labels were made, keyed by `label_status` in data/ground_truth_meta.json.
# The report's caveat sentence is built from this, so it can't claim more than the data says
# (eval/test_report_wording.py checks it). Keep the wording in line with docs/limits.md section 2.
LABEL_STATUS_TEXT = {
    "ai_drafted_unverified": (
        "The ground-truth labels were drafted by an AI (Claude Code) from cited sources; some were "
        "cross-checked blind by a separate AI session. **No person has verified them yet.**"
    ),
    "human_verified": "The ground-truth labels were verified by two different people per row.",
}
DEFAULT_LABEL_STATUS = "ai_drafted_unverified"


def synthetic_statement(label_status: str = DEFAULT_LABEL_STATUS) -> str:
    if label_status not in LABEL_STATUS_TEXT:
        raise ValueError(f"unknown label_status {label_status!r}; expected one of {sorted(LABEL_STATUS_TEXT)}")
    return (
        "**The inventory is synthetic.** Every device, owner and version in this evaluation was made up "
        f"for the hackathon. {LABEL_STATUS_TEXT[label_status]} These numbers describe performance on "
        "this test set only. **No claim is made about real-world accuracy or time saved.**"
    )


SYNTHETIC_STATEMENT = synthetic_statement()

FAILURE_COLUMNS = [
    "system", "run_id", "device_id", "group", "verified", "device_name_raw", "error_type",
    "truth_lane", "pred_lane", "truth_identity", "pred_identity", "confidence", "pred_evidence",
    "truth_evidence", "explanation", "truth_note",
]

METRIC_LABELS = {
    "norm_vendor": "Norm. vendor", "norm_product": "Norm. product", "norm_version": "Norm. version",
    "norm_all_three": "Norm. all three", "exposure_precision": "Exposure precision",
    "exposure_recall": "Exposure recall", "lane_accuracy": "Lane accuracy",
    "unknown_rate": "Unknown rate", "unknown_precision": "Unknown was right",
    "unknown_recall": "Unknown recall",
}


def fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def ident(row: dict | None) -> str:
    if row is None:
        return "(no prediction)"
    return " / ".join(row.get(f, "") or "?" for f in FIELDS)


def explain_lane(t_lane: str, p_lane: str) -> str:
    if p_lane == MISSING:
        return "No prediction row for this device."
    if t_lane == "unknown":
        return (f"Guessed '{p_lane}' on a device the label marks as not identifiable; the right "
                f"call was unknown (ask a human).")
    if p_lane == "unknown":
        return f"Abstained (unknown) on a device labelled '{t_lane}'; a missed {t_lane}."
    if t_lane in EXPOSED_LANES and p_lane == "fine":
        return f"Missed exposure: truth is '{t_lane}' but predicted 'fine'."
    if t_lane == "fine" and p_lane in EXPOSED_LANES:
        return f"False alarm: device is fine but predicted '{p_lane}'."
    return f"Exposure found but wrong action: predicted '{p_lane}', should be '{t_lane}'."


def explain_fields(pred: dict | None, truth: dict) -> str:
    if pred is None:
        return ""
    bad = []
    for f, ok in field_matches(pred, truth).items():
        if not ok:
            bad.append(f"{f}: got '{pred.get(f, '')}', expected '{truth.get(f, '')}'"
                       + (" (truth blank = unknowable)" if not truth.get(f) else ""))
    return "; ".join(bad)


def failure_rows(system: str, run_id: str, truth_rows: list[dict], preds: dict[str, dict],
                 inventory: dict[str, dict]) -> list[dict]:
    """One row per device that is wrong on lane OR any identity field."""
    out = []
    for t in truth_rows:
        did = t["device_id"]
        p = preds.get(did)
        p_lane = p["lane"] if p is not None else MISSING
        lane_wrong = p_lane != t["lane"]
        field_msg = explain_fields(p, t)
        if not lane_wrong and not field_msg and p is not None:
            continue
        parts = []
        if lane_wrong:
            parts.append(explain_lane(t["lane"], p_lane))
        if field_msg:
            parts.append(("Lane right but identity wrong: " if not lane_wrong else "Identity: ") + field_msg + ".")
        error_type = ("lane+identity" if lane_wrong and field_msg else
                      "missing" if p is None else "lane" if lane_wrong else "identity")
        out.append({
            "system": system, "run_id": run_id, "device_id": did, "group": t["group"],
            "verified": "true" if is_verified(t) else "false",
            "device_name_raw": inventory.get(did, {}).get("device_name_raw", ""),
            "error_type": error_type, "truth_lane": t["lane"], "pred_lane": p_lane,
            "truth_identity": ident(t), "pred_identity": ident(p),
            "confidence": p.get("confidence", "") if p else "",
            "pred_evidence": p.get("evidence", "") if p else "",
            "truth_evidence": ";".join(x for x in (t.get("evidence_cve", ""), t.get("evidence_lifecycle_id", "")) if x),
            "explanation": " ".join(parts), "truth_note": t.get("source_row_note", ""),
        })
    return out


def instability_rows(system: str, stab: dict, truth_by_id: dict[str, dict], inventory: dict[str, dict]) -> list[dict]:
    out = []
    for u in stab["unstable_devices"]:
        t = truth_by_id[u["device_id"]]
        out.append({
            "system": system, "run_id": "(all runs)", "device_id": u["device_id"], "group": t["group"],
            "verified": "true" if is_verified(t) else "false",
            "device_name_raw": inventory.get(u["device_id"], {}).get("device_name_raw", ""),
            "error_type": "unstable", "truth_lane": t["lane"], "pred_lane": " | ".join(u["lanes"]),
            "truth_identity": ident(t), "pred_identity": " | ".join(u["identities"]),
            "confidence": "", "pred_evidence": "", "truth_evidence": "",
            "explanation": (f"Repeated runs disagree on the same input ({', '.join(u['fields'])}): "
                            f"lanes {u['lanes']}, evidence {u['evidence']}."),
            "truth_note": t.get("source_row_note", ""),
        })
    return out


# --------------------------------------------------------------------------- markdown

def _md_table(header: list[str], rows: list[list[str]]) -> list[str]:
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(esc(h) for h in header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return lines


def _confusion_md(s: Scores) -> list[str]:
    cols = list(LANES) + ([MISSING] if s.missing else [])
    rows = [[f"**{t}**"] + [str(s.confusion[t][c]) for c in cols] for t in LANES]
    return _md_table(["truth \\ predicted"] + cols, rows)


def build_report(*, truth_rows: list[dict], systems: dict[str, list[tuple[str, dict[str, dict]]]],
                 inventory: dict[str, dict], out_dir: Path, sources: dict[str, str],
                 label_status: str = DEFAULT_LABEL_STATUS) -> dict:
    """systems: name -> [(run_id, preds_by_device_id), ...] sorted by run_id.

    Primary metrics use each system's FIRST run; stability uses all runs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    truth_by_id = {t["device_id"]: t for t in truth_rows}
    primary = {name: score_slices(truth_rows, runs[0][1]) for name, runs in systems.items()}
    per_run = {name: [(rid, score_slices(truth_rows, p)["all"]) for rid, p in runs] for name, runs in systems.items()}
    stab = {name: stability_slices(truth_rows, [p for _, p in runs]) for name, runs in systems.items()}

    failures: list[dict] = []
    for name, runs in systems.items():
        for rid, p in runs:
            failures += failure_rows(name, rid, truth_rows, p, inventory)
        failures += instability_rows(name, stab[name]["all"], truth_by_id, inventory)
    write_csv(out_dir / "failures.csv", FAILURE_COLUMNS, failures)

    names = list(systems)
    slice_names = list(primary[names[0]]) if names else []
    n_verified = sum(is_verified(t) for t in truth_rows)

    statement = synthetic_statement(label_status)
    L: list[str] = ["# Deming evaluation report", "", statement, ""]
    L += ["## Inputs", ""]
    for k, v in sources.items():
        L.append(f"- {k}: `{v}`")
    L.append(f"- Devices in ground truth: {len(truth_rows)} ({n_verified} verified by two reviewers, "
             f"{len(truth_rows) - n_verified} unverified; unverified rows are also reported separately)")
    for name, runs in systems.items():
        L.append(f"- **{name}**: {len(runs)} run(s): " + ", ".join(f"`{r}`" for r, _ in runs)
                 + f". Primary metrics use `{runs[0][0]}`.")
    if "baseline" in systems:
        L.append("- Baseline: naive lowercase-substring + rapidfuzz match of the device name to KEV "
                 "vendor/product. It never outputs `unknown`.")
    L.append("")

    # ---- headline
    L += ["## Headline (all devices)", ""]
    keys = list(METRIC_LABELS)
    L += _md_table(["Metric"] + names,
                   [[METRIC_LABELS[k]] + [fmt(primary[n]["all"].as_dict()[k]) for n in names] for k in keys]
                   + [["Missing predictions"] + [str(primary[n]["all"].missing) for n in names]])
    L.append("")

    # ---- baseline vs system, plainly
    if "baseline" in systems and len(names) > 1:
        L += ["## Where the baseline ties or beats the system", "",
              "Compared on: " + ", ".join(METRIC_LABELS[m].lower() for m in COMPARABLE)
              + ". A slice with n/a on both sides is skipped for that metric.", ""]
        rows = []
        for n in names:
            if n == "baseline":
                continue
            for sl in slice_names:
                if primary[n][sl].n == 0:
                    continue
                hits = baseline_ties_or_beats(primary[n][sl], primary["baseline"][sl])
                beats = [f"{METRIC_LABELS[m].lower()} ({fmt(bv)} vs {fmt(sv)})" for m, sv, bv in hits if bv > sv]
                ties = [f"{METRIC_LABELS[m].lower()} ({fmt(bv)})" for m, sv, bv in hits if bv == sv]
                if beats or ties:
                    rows.append([n, sl, str(primary[n][sl].n), "; ".join(beats) or "-", "; ".join(ties) or "-"])
        if rows:
            L += _md_table(["System", "Slice", "n", "Baseline BEATS the system on", "Baseline TIES on"], rows)
            beat_slices = sorted({r[1] for r in rows if r[3] != "-"})
            if beat_slices:
                L += ["", f"**Plainly: the naive baseline beats the system on at least one metric in "
                          f"{', '.join(beat_slices)}.**"]
        else:
            L.append("None: the system is strictly ahead on every compared metric in every slice.")
        L.append("")

    # ---- per slice
    L += ["## By slice (verified / unverified / group)", ""]
    for sl in slice_names:
        n_sl = primary[names[0]][sl].n
        L += [f"### {sl} (n={n_sl})", ""]
        if n_sl == 0:
            L += ["No devices.", ""]
            continue
        L += _md_table(["Metric"] + names,
                       [[METRIC_LABELS[k]] + [fmt(primary[n][sl].as_dict()[k]) for n in names] for k in keys]
                       + [["Lane agreement across runs"] + [fmt(stab[n][sl]["lane_agreement"]) for n in names]])
        L.append("")

    # ---- confusion matrices
    L += ["## Lane confusion matrices (all devices, primary run)", ""]
    for n in names:
        L += [f"### {n}", ""] + _confusion_md(primary[n]["all"]) + [""]

    # ---- per run + stability
    L += ["## Stability across repeated runs", ""]
    for n in names:
        st = stab[n]["all"]
        if st["runs"] < 2:
            L.append(f"- **{n}**: only {st['runs']} run, so stability is not measured.")
        else:
            fa = st["field_agreement"]
            unstable = ", ".join(f"{u['device_id']} ({', '.join(u['fields'])})"
                                 for u in st["unstable_devices"]) or "none"
            L.append(f"- **{n}**: {st['runs']} runs. Structured fields, share of devices where every "
                     f"run agrees: lane {fmt(st['lane_agreement'])}, vendor {fmt(fa['vendor'])}, "
                     f"product {fmt(fa['product'])}, version {fmt(fa['version'])}, evidence ids "
                     f"{fmt(fa['evidence'])}; all structured fields together "
                     f"{fmt(st['structured_agreement'])}. Free text: not measured here (the "
                     f"predictions CSV holds none; see the live run report). Unstable devices: {unstable}.")
    L.append("")
    if any(len(r) > 1 for r in per_run.values()):
        L += _md_table(["System", "Run", "Lane accuracy", "Norm. all three", "Unknown rate"],
                       [[n, rid, fmt(s.lane_acc), fmt(s.norm_acc("all_three")), fmt(s.unknown_rate)]
                        for n, rs in per_run.items() for rid, s in rs])
        L.append("")

    # ---- every failure
    L += ["## Every wrong case", "",
          f"{len(failures)} rows, also in `failures.csv`. Lane or identity errors are listed per run; "
          "`unstable` rows are devices whose runs disagree.", ""]
    if failures:
        L += _md_table(["System", "Run", "Device", "Group", "Name", "Truth", "Predicted", "Explanation"],
                       [[f["system"], f["run_id"], f["device_id"], f["group"], f["device_name_raw"],
                         f"{f['truth_lane']} ({f['truth_identity']})", f"{f['pred_lane']} ({f['pred_identity']})",
                         f["explanation"]] for f in failures])
    else:
        L.append("No wrong cases.")
    L.append("")

    L += ["## Metric definitions", "",
          "- Normalization: vendor/product/version compared after trimming, case-insensitive. A blank truth "
          "field matches only a blank prediction.",
          "- Exposed = `patch` or `retire`. Devices whose true lane is `unknown` are left out of exposure "
          "precision/recall; a predicted `unknown` on an exposed device counts as a miss.",
          "- Unknown was right = of the devices predicted `unknown`, the share whose true lane is `unknown`. "
          "Unknown recall = of the truly-unknown devices, the share predicted `unknown`.",
          "- Stability = share of devices where all runs agree, per structured field (lane, vendor, "
          "product, version, evidence ids as a set) and for all of them together. Free text (reasons, "
          "message bodies) is reported separately by `eval/live_fixture_run.py`. `n/a` = undefined "
          "(zero denominator or one run).",
          "- Owner routing, duplicate tickets, approval compliance and verification correctness are **not** "
          "measured here (they need the Planner/Verifier run logs).", "",
          statement, ""]

    (out_dir / "report.md").write_text("\n".join(L), encoding="utf-8")
    return {"primary": primary, "stability": stab, "failures": failures}
