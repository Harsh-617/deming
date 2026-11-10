"""Normalizer -> Checker -> Planner for one device, and the Verifier for one ticket.

Each LLM step is followed by its guard (sim/guards.py). Nothing here sends anything: the Planner
output is a proposal that still needs recorded human approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import guards, retrieval
from .gemini_runner import GeminiRunner
from .models import CheckerOutput, NormalizerOutput, PlannerOutput, VerifierOutput

DEVICE_FIELDS = ("device_id", "device_name_raw", "location", "owner_email", "firmware_version_raw",
                 "internet_facing", "criticality", "do_not_touch", "last_updated")


@dataclass
class DeviceResult:
    device_id: str
    normalized: NormalizerOutput
    check: CheckerOutput
    plan: PlannerOutput
    kev_candidates: list[dict]
    lifecycle_candidates: list[dict]
    guard_notes: list[str] = field(default_factory=list)


def run_device(runner: GeminiRunner, device: dict, kev_index: retrieval.KevIndex,
               lifecycle_rows: list[dict], *, today: str, settings: dict,
               open_tickets: list[dict] | None = None, repeat_index: int = 0) -> DeviceResult:
    record = {k: device.get(k) for k in DEVICE_FIELDS}
    notes: list[str] = []

    norm = runner.run("normalizer", record, repeat_index).output
    norm, n = guards.guard_normalizer(norm)
    notes += n

    normalized_device = {**record, **norm.model_dump(include={"vendor", "product", "model",
                                                               "version", "confidence"})}
    kev_c = retrieval.kev_candidates(normalized_device, kev_index)
    lc_c = retrieval.lifecycle_candidates(normalized_device, lifecycle_rows)

    if norm.lane == "unknown":
        # Rule: below threshold the device is unknown. Don't ask the Checker to guess.
        check = CheckerOutput(device_id=record["device_id"], lane="unknown", evidence_cve=[],
                              evidence_lifecycle_id=None, due_date=None,
                              confidence=norm.confidence,
                              injection_detected=norm.injection_detected,
                              reason="The device could not be identified with enough confidence; "
                                     "a human needs to identify it.")
    else:
        check = runner.run("checker", {"today": today, "device": normalized_device,
                                       "kev_candidates": kev_c,
                                       "lifecycle_candidates": lc_c}, repeat_index).output
        check, n = guards.guard_checker(check, kev_c, lc_c, norm)
        notes += n

    planner_device = {**record, **norm.model_dump(include={"vendor", "product", "version"})}
    plan = runner.run("planner", {
        "today": today, "device": planner_device,
        "check": check.model_dump(mode="json", include={"lane", "evidence_cve",
                                                        "evidence_lifecycle_id", "due_date",
                                                        "reason"}),
        "open_tickets": open_tickets or [], "settings": settings}, repeat_index).output
    plan, n = guards.guard_planner(plan, record, check)
    notes += n
    return DeviceResult(record["device_id"], norm, check, plan, kev_c, lc_c, notes)


def verify_ticket(runner: GeminiRunner, *, today: str, ticket: dict, record_at_ticket: dict,
                  record_now: dict | None, recheck: dict | None, settings: dict,
                  repeat_index: int = 0) -> tuple[VerifierOutput, list[str]]:
    out = runner.run("verifier", {"today": today, "ticket": ticket,
                                  "record_at_ticket": record_at_ticket, "record_now": record_now,
                                  "recheck": recheck, "settings": settings}, repeat_index).output
    return guards.guard_verifier(out, ticket.get("lane", ""),
                                 (recheck or {}).get("lane"))
