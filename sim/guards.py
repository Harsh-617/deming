"""Deterministic enforcement of the hard rules, applied after every LLM call.

Prompts ask the model to follow these rules; the guards make sure the output does even if the
model was fooled (e.g. by injection text in a device name). Each guard returns a corrected copy
and a list of human-readable notes about what it changed.
"""
from __future__ import annotations

import datetime as dt
import re

from . import retrieval
from .config import CONFIDENCE_THRESHOLD
from .models import CheckerOutput, NormalizerOutput, PlannerOutput, VerifierOutput

_DISCONNECT = re.compile(r"\b(disconnect|isolat\w*|unplug|shut\s*down|power\s*off|decommission)\b",
                         re.IGNORECASE)
_SECURE_CLAIM = re.compile(r"\b(is|now|are)\s+(secure|safe|fixed|patched)\b", re.IGNORECASE)


def guard_normalizer(out: NormalizerOutput, threshold: float = CONFIDENCE_THRESHOLD):
    notes = []
    upd = {}
    if out.confidence < threshold and out.lane != "unknown":
        upd.update(lane="unknown", needs_human=True)
        notes.append(f"confidence {out.confidence:.2f} < {threshold:.2f}: forced lane unknown")
    if out.confidence >= threshold and out.lane == "unknown":
        upd.update(needs_human=True)
    return out.model_copy(update=upd), notes


def guard_checker(out: CheckerOutput, kev_candidates: list[dict], lifecycle_candidates: list[dict],
                  normalizer: NormalizerOutput | None = None,
                  threshold: float = CONFIDENCE_THRESHOLD, device: dict | None = None):
    notes = []
    allowed_cve = {c["cveID"] for c in kev_candidates}
    allowed_lc = {c["lifecycle_id"] for c in lifecycle_candidates}
    invented = [c for c in out.evidence_cve if c not in allowed_cve]
    if out.evidence_lifecycle_id and out.evidence_lifecycle_id not in allowed_lc:
        invented.append(out.evidence_lifecycle_id)
    reasons = []
    if invented:
        reasons.append(f"evidence not in candidates: {';'.join(invented)}")
    if out.confidence < threshold:
        reasons.append(f"checker confidence {out.confidence:.2f} < {threshold:.2f}")
    if normalizer is not None and normalizer.lane == "unknown":
        reasons.append("normalizer lane unknown")
    if out.lane in ("patch", "retire") and not (out.evidence_cve or out.evidence_lifecycle_id):
        reasons.append(f"lane {out.lane} without evidence")
    if reasons:
        notes.append("forced lane unknown: " + "; ".join(reasons))
        return out.model_copy(update=dict(lane="unknown", evidence_cve=[],
                                          evidence_lifecycle_id=None, due_date=None)), notes
    if out.lane == "fine" and (out.evidence_cve or out.evidence_lifecycle_id):
        notes.append("lane fine: evidence cleared")
        out = out.model_copy(update=dict(evidence_cve=[], evidence_lifecycle_id=None))
    if device is not None:
        out, n = guard_version(out, device, kev_candidates, lifecycle_candidates)
        notes += n
    return out, notes


# Strict version grammar: optional v/V, then dot-separated integers, nothing else.
# Anything messier ("7.0.12 build 523", "11.1.4-h13", "22.7R2.6") does not parse, and the
# device goes to unknown. packaging.version is deliberately not used: PEP 440 reads
# "7.0.1-5161" as a post-release and normalises other vendor strings in ways that look valid
# but mean something else (docs/decisions.md, 2026-11-11 version comparison).
_VERSION = re.compile(r"[vV]?([0-9]+(?:\.[0-9]+)*)")  # [0-9], not \d: \d matches non-ASCII digits


def parse_version(s: str | None) -> tuple[int, ...] | None:
    m = _VERSION.fullmatch((s or "").strip())
    if not m:
        return None
    parts = [int(x) for x in m.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:  # 1.5.1 == 1.5.1.0
        parts.pop()
    return tuple(parts)


def compare_versions(a: str | None, b: str | None) -> int | None:
    """-1 / 0 / 1 if both parse, else None."""
    pa, pb = parse_version(a), parse_version(b)
    if pa is None or pb is None:
        return None
    return (pa > pb) - (pa < pb)


def _same(a: str | None, b: str | None) -> bool:
    return bool(a) and (a or "").strip().casefold() == (b or "").strip().casefold()


def _governing_row(out: CheckerOutput, device: dict, lifecycle_candidates: list[dict]):
    if out.evidence_lifecycle_id:
        for r in lifecycle_candidates:
            if r.get("lifecycle_id") == out.evidence_lifecycle_id:
                return r
    # Candidates come most specific first (sim/retrieval.py); take the first whose pattern fits.
    for r in lifecycle_candidates:
        if retrieval.pattern_matches(r, device):
            return r
    return None


def guard_version(out: CheckerOutput, device: dict, kev_candidates: list[dict],
                  lifecycle_candidates: list[dict]):
    """Deterministic patch/fine check for a KEV-listed product with a lifecycle row.

    Applies only when the Checker said patch or fine (retire and unknown are left alone).
    The firmware is the inventory's firmware_version_raw (the Normalizer's version if blank).
    - fixed_version blank: unknown, "fixed version not documented".
    - either version doesn't parse: unknown.
    - both parse: firmware < fixed -> patch, else fine; a contradicting lane is overridden.
    """
    if out.lane not in ("patch", "fine"):
        return out, []
    row = _governing_row(out, device, lifecycle_candidates)
    if row is None:
        return out, []
    kev = [c for c in kev_candidates
           if (_same(c.get("vendorProject"), row.get("vendor")) and _same(c.get("product"), row.get("product")))
           or (_same(c.get("vendorProject"), device.get("vendor")) and _same(c.get("product"), device.get("product")))]
    if not kev and not (out.lane == "patch" and out.evidence_cve):
        return out, []  # not a KEV-listed product: nothing to compare

    lc_id = row.get("lifecycle_id")
    firmware = (device.get("firmware_version_raw") or "").strip() or (device.get("version") or "").strip()
    fixed = (row.get("fixed_version") or "").strip()

    def unknown(why: str):
        note = f"version guard: lane {out.lane} -> unknown ({why}; {lc_id})"
        return out.model_copy(update=dict(
            lane="unknown", evidence_cve=[], evidence_lifecycle_id=None, due_date=None,
            reason=f"[version guard] {why}. {out.reason}")), [note]

    if not fixed:
        return unknown("fixed version not documented")
    cmp = compare_versions(firmware, fixed)
    if cmp is None:
        bad = [f"{k} {v!r}" for k, v in (("firmware", firmware), ("fixed_version", fixed))
               if parse_version(v) is None]
        return unknown("version could not be compared: " + ", ".join(bad) + " does not parse")
    expected = "patch" if cmp < 0 else "fine"
    if out.lane == expected:
        return out, []
    why = (f"firmware {firmware} is {'below' if cmp < 0 else 'at or above'} fixed version "
           f"{fixed} ({lc_id}), so lane {expected}, not {out.lane}")
    if expected == "patch":
        cves = sorted({c["cveID"] for c in kev}) or list(out.evidence_cve)
        dues = sorted(c["dueDate"] for c in kev if c.get("dueDate"))
        upd = dict(lane="patch", evidence_cve=cves, evidence_lifecycle_id=lc_id,
                   due_date=dt.date.fromisoformat(dues[0]) if dues else None)
    else:
        upd = dict(lane="fine", evidence_cve=[], evidence_lifecycle_id=None, due_date=None)
    upd["reason"] = f"[version guard override] {why}. {out.reason}"
    return out.model_copy(update=upd), [f"version guard override: {why}"]


def guard_planner(out: PlannerOutput, device: dict, checker: CheckerOutput):
    notes = []
    upd = {}
    if not out.requires_approval:
        upd["requires_approval"] = True
        notes.append("requires_approval forced true")
    if out.lane != checker.lane:
        upd["lane"] = checker.lane
        notes.append(f"lane {out.lane} replaced by checker lane {checker.lane}")
    if _truthy(device.get("do_not_touch")):
        if not out.escalate_to_human:
            upd["escalate_to_human"] = True
            notes.append("do_not_touch: escalate_to_human forced true")
        if out.message and _DISCONNECT.search(out.message.body):
            body = ("This device is flagged do-not-touch. Deming makes no disconnection or "
                    "isolation proposal; a named person must decide the next step. "
                    f"Lane: {checker.lane}. Evidence: "
                    f"{';'.join(checker.evidence_cve + ([checker.evidence_lifecycle_id] if checker.evidence_lifecycle_id else [])) or 'none'}.")
            upd["message"] = out.message.model_copy(update={"body": body})
            notes.append("do_not_touch: disconnect/isolate wording removed from message")
    return out.model_copy(update=upd), notes


def guard_verifier(out: VerifierOutput, ticket_lane: str, recheck_lane: str | None):
    notes = []
    upd = {}
    if out.decision == "close":
        ok = ((out.observed_change == "device_removed" and ticket_lane == "retire")
              or (out.observed_change == "version_changed" and recheck_lane == "fine"))
        if not ok:
            upd["decision"] = "escalate"
            notes.append(f"close not allowed ({out.observed_change}, recheck {recheck_lane}): escalate")
    if _SECURE_CLAIM.search(out.note):
        upd["note"] = ("The inventory record was compared with the ticket; this only confirms what "
                       f"the record shows ({out.observed_change}), not that the device is secure.")
        notes.append("note rewritten: it claimed the device is secure/fixed")
    return out.model_copy(update=upd), notes


def _truthy(v) -> bool:
    return v is True or str(v).strip().lower() == "true"
