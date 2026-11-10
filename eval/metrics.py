"""Evaluation metrics. Pure functions over contract rows (dicts of strings).

Definitions (also printed in every report):
- Normalization accuracy: per field, predicted == truth after trim + casefold. A blank truth
  ("truly unknowable") is matched only by a blank prediction. `all_three` = all three fields right.
- Exposure: exposed = lane in {patch, retire}. Devices whose TRUE lane is `unknown` are left out
  (a human couldn't say whether they're exposed). A predicted `unknown` on an exposed device is a
  miss (false negative). Precision/recall are None when the denominator is 0.
- Lane accuracy + 4x4 confusion matrix (rows = truth, columns = predicted). A device with no
  prediction row is counted under the column "missing" and is always wrong.
- Unknown rate = predicted unknown / devices. Unknown precision = how often a predicted unknown
  was the right call (truth unknown). Unknown recall = share of truly-unknown devices the
  system abstained on.
- Stability (needs >= 2 runs of one system): share of devices where every run gave the same
  lane (and, separately, the same vendor/product/version).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from io_utils import EXPOSED_LANES, LANES, ContractError, norm

FIELDS = ("vendor", "product", "version")
MISSING = "missing"


def ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def index_predictions(pred_rows: list[dict], truth_ids: set[str] | None = None) -> dict[str, dict]:
    """device_id -> row. Rejects duplicate ids and bad lanes. Ids not in truth are ignored."""
    out: dict[str, dict] = {}
    for row in pred_rows:
        did = row.get("device_id", "").strip()
        if not did:
            raise ContractError("prediction row with blank device_id")
        if did in out:
            raise ContractError(f"duplicate prediction for {did}")
        lane = row.get("lane", "").strip()
        if lane not in LANES:
            raise ContractError(f"{did}: lane {lane!r} not in {LANES}")
        if truth_ids is None or did in truth_ids:
            out[did] = row
    return out


def is_verified(truth_row: dict) -> bool:
    a, b = truth_row.get("verified_by_a", "").strip(), truth_row.get("verified_by_b", "").strip()
    return bool(a and b and a.casefold() != b.casefold())


@dataclass
class Scores:
    n: int = 0
    field_correct: dict[str, int] = field(default_factory=lambda: {f: 0 for f in (*FIELDS, "all_three")})
    lane_correct: int = 0
    confusion: dict[str, Counter] = field(default_factory=lambda: {t: Counter() for t in LANES})
    tp: int = 0
    fp: int = 0
    fn: int = 0
    exposure_excluded: int = 0
    pred_unknown: int = 0
    pred_unknown_correct: int = 0
    truth_unknown: int = 0
    missing: int = 0

    # ---- derived -------------------------------------------------------
    def norm_acc(self, f: str) -> float | None:
        return ratio(self.field_correct[f], self.n)

    @property
    def lane_acc(self) -> float | None:
        return ratio(self.lane_correct, self.n)

    @property
    def exposure_precision(self) -> float | None:
        return ratio(self.tp, self.tp + self.fp)

    @property
    def exposure_recall(self) -> float | None:
        return ratio(self.tp, self.tp + self.fn)

    @property
    def unknown_rate(self) -> float | None:
        return ratio(self.pred_unknown, self.n)

    @property
    def unknown_precision(self) -> float | None:
        return ratio(self.pred_unknown_correct, self.pred_unknown)

    @property
    def unknown_recall(self) -> float | None:
        return ratio(self.pred_unknown_correct, self.truth_unknown)

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "norm_vendor": self.norm_acc("vendor"),
            "norm_product": self.norm_acc("product"),
            "norm_version": self.norm_acc("version"),
            "norm_all_three": self.norm_acc("all_three"),
            "exposure_precision": self.exposure_precision,
            "exposure_recall": self.exposure_recall,
            "lane_accuracy": self.lane_acc,
            "unknown_rate": self.unknown_rate,
            "unknown_precision": self.unknown_precision,
            "unknown_recall": self.unknown_recall,
            "missing_predictions": self.missing,
            "exposure_excluded": self.exposure_excluded,
        }


def field_matches(pred: dict | None, truth: dict) -> dict[str, bool]:
    if pred is None:
        return {f: False for f in FIELDS}
    return {f: norm(pred.get(f)) == norm(truth.get(f)) for f in FIELDS}


def score(truth_rows: list[dict], preds: dict[str, dict]) -> Scores:
    """Score one run on the given truth rows (any subset, e.g. one group)."""
    s = Scores()
    for t in truth_rows:
        s.n += 1
        did = t["device_id"]
        p = preds.get(did)
        t_lane = t["lane"].strip()
        if t_lane not in LANES:
            raise ContractError(f"ground truth {did}: lane {t_lane!r} not in {LANES}")
        p_lane = p["lane"].strip() if p is not None else MISSING
        if p is None:
            s.missing += 1

        fm = field_matches(p, t)
        for f in FIELDS:
            s.field_correct[f] += fm[f]
        s.field_correct["all_three"] += all(fm.values())

        s.confusion[t_lane][p_lane] += 1
        s.lane_correct += p_lane == t_lane

        if t_lane == "unknown":
            s.truth_unknown += 1
            s.exposure_excluded += 1
        else:
            t_exp, p_exp = t_lane in EXPOSED_LANES, p_lane in EXPOSED_LANES
            s.tp += t_exp and p_exp
            s.fp += (not t_exp) and p_exp
            s.fn += t_exp and not p_exp

        if p_lane == "unknown":
            s.pred_unknown += 1
            s.pred_unknown_correct += t_lane == "unknown"
    return s


def stability(truth_rows: list[dict], runs: list[dict[str, dict]]) -> dict:
    """Agreement across repeated runs of ONE system. None when fewer than 2 runs."""
    out = {"runs": len(runs), "lane_agreement": None, "identity_agreement": None, "unstable_devices": []}
    if len(runs) < 2 or not truth_rows:
        return out
    lane_ok = ident_ok = 0
    for t in truth_rows:
        did = t["device_id"]
        lanes = [r[did]["lane"] if did in r else MISSING for r in runs]
        idents = [tuple(norm(r[did].get(f)) for f in FIELDS) if did in r else (MISSING,) for r in runs]
        same_lane, same_ident = len(set(lanes)) == 1, len(set(idents)) == 1
        lane_ok += same_lane
        ident_ok += same_ident
        if not (same_lane and same_ident):
            out["unstable_devices"].append({"device_id": did, "lanes": lanes,
                                            "identities": ["/".join(i) for i in idents]})
    n = len(truth_rows)
    out["lane_agreement"] = lane_ok / n
    out["identity_agreement"] = ident_ok / n
    return out


def groups_of(truth_rows: list[dict]) -> list[str]:
    return sorted({t["group"] for t in truth_rows})


def slices(truth_rows: list[dict]) -> dict[str, list[dict]]:
    """Named subsets: all, verified, unverified, and one per group."""
    out = {
        "all": truth_rows,
        "verified": [t for t in truth_rows if is_verified(t)],
        "unverified": [t for t in truth_rows if not is_verified(t)],
    }
    for g in groups_of(truth_rows):
        out[f"group:{g}"] = [t for t in truth_rows if t["group"] == g]
    return out


def score_slices(truth_rows: list[dict], preds: dict[str, dict]) -> dict[str, Scores]:
    return {name: score(rows, preds) for name, rows in slices(truth_rows).items()}


def stability_slices(truth_rows: list[dict], runs: list[dict[str, dict]]) -> dict[str, dict]:
    return {name: stability(rows, runs) for name, rows in slices(truth_rows).items()}


# Metrics where higher is better; used for "baseline ties or beats" checks.
COMPARABLE = ("norm_vendor", "norm_product", "norm_version", "norm_all_three",
              "lane_accuracy", "exposure_precision", "exposure_recall", "unknown_recall")


def baseline_ties_or_beats(system: Scores, baseline: Scores) -> list[tuple[str, float, float]]:
    """Metrics where baseline >= system (both defined)."""
    sd, bd = system.as_dict(), baseline.as_dict()
    out = []
    for m in COMPARABLE:
        if sd[m] is not None and bd[m] is not None and bd[m] >= sd[m]:
            out.append((m, sd[m], bd[m]))
    return out
