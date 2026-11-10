"""Deterministic enforcement of the hard rules, applied after every LLM call.

Prompts ask the model to follow these rules; the guards make sure the output does even if the
model was fooled (e.g. by injection text in a device name). Each guard returns a corrected copy
and a list of human-readable notes about what it changed.
"""
from __future__ import annotations

import re

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
                  threshold: float = CONFIDENCE_THRESHOLD):
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
    return out, notes


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
