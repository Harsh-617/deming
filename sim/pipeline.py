"""Normalizer -> Checker -> Planner for one device, and the Verifier for one ticket.

Each LLM step is followed by its guard (sim/guards.py). Nothing here sends anything: the Planner
output is a proposal that still needs recorded human approval.

CLI (writes a predictions CSV per docs/contracts.md; needs GEMINI_API_KEY in .env):
    python -m sim.pipeline --inventory data/inventory.csv            # as_of from ground_truth_meta.json
    python -m sim.pipeline --inventory data/inventory.csv --as-of 2026-12-10
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import config, guards, retrieval
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
    recipient: str = ""  # set by rule (guards.recipient), never by the model


def run_device(runner: GeminiRunner, device: dict, kev_index: retrieval.KevIndex,
               lifecycle_rows: list[dict], *, today: str, settings: dict,
               open_tickets: list[dict] | None = None, repeat_index: int = 0,
               as_of_date: str | None = None) -> DeviceResult:
    """`as_of_date` (default: data/ground_truth_meta.json) is the date the Checker compares
    support end dates against; `today` stays the run date."""
    as_of = config.load_as_of_date(as_of_date)
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
        check = runner.run("checker", {"today": today, "as_of_date": as_of,
                                       "device": normalized_device,
                                       "kev_candidates": kev_c,
                                       "lifecycle_candidates": lc_c}, repeat_index).output
        check, n = guards.guard_checker(check, kev_c, lc_c, norm, device=normalized_device)
        notes += n

    planner_device = {**record, **norm.model_dump(include={"vendor", "product", "version"})}
    plan = runner.run("planner", {
        "today": today, "as_of_date": as_of, "device": planner_device,
        "check": check.model_dump(mode="json", include={"lane", "evidence_cve",
                                                        "evidence_lifecycle_id", "due_date",
                                                        "reason"}),
        "open_tickets": open_tickets or [], "settings": settings}, repeat_index).output
    plan, n = guards.guard_planner(plan, record, check, as_of_date=as_of, settings=settings)
    notes += n
    to = guards.recipient(check.lane, record, settings) if plan.message else ""
    return DeviceResult(record["device_id"], norm, check, plan, kev_c, lc_c, notes, to)


def verify_ticket(runner: GeminiRunner, *, today: str, ticket: dict, record_at_ticket: dict,
                  record_now: dict | None, recheck: dict | None, settings: dict,
                  repeat_index: int = 0) -> tuple[VerifierOutput, list[str]]:
    out = runner.run("verifier", {"today": today, "ticket": ticket,
                                  "record_at_ticket": record_at_ticket, "record_now": record_now,
                                  "recheck": recheck, "settings": settings}, repeat_index).output
    return guards.guard_verifier(out, ticket.get("lane", ""),
                                 (recheck or {}).get("lane"),
                                 record_present=record_now is not None)


def main(argv: list[str] | None = None) -> Path:
    import argparse
    import csv
    from datetime import datetime, timezone

    p = argparse.ArgumentParser(description="Run Deming on an inventory CSV, write predictions.")
    p.add_argument("--inventory", type=Path, default=config.ROOT / "data/inventory.csv")
    p.add_argument("--kev", type=Path, default=config.ROOT / "data/feeds/kev.json")
    p.add_argument("--lifecycle", type=Path, default=config.ROOT / "data/lifecycle.csv")
    p.add_argument("--as-of", default=None,
                   help="YYYY-MM-DD; default: as_of_date in data/ground_truth_meta.json")
    p.add_argument("--out-root", type=Path, default=config.ROOT / "eval/runs")
    args = p.parse_args(argv)

    as_of = config.load_as_of_date(args.as_of)
    started = datetime.now(timezone.utc)
    run_id = "deming-" + started.strftime("%Y%m%dT%H%M%SZ")
    with open(args.inventory, encoding="utf-8", newline="") as f:
        devices = list(csv.DictReader(f))
    kev_index = retrieval.KevIndex.build(retrieval.load_kev(args.kev))
    lifecycle_rows = retrieval.load_lifecycle(args.lifecycle)
    from .loop import typed_settings  # late import: sim.loop imports this module
    settings = typed_settings()  # Settings tab defaults (docs/contracts.md)
    runner = GeminiRunner()
    rows = []
    for d in devices:
        r = run_device(runner, d, kev_index, lifecycle_rows, today=started.date().isoformat(),
                       settings=settings, as_of_date=as_of)
        evidence = r.check.evidence_cve + ([r.check.evidence_lifecycle_id]
                                           if r.check.evidence_lifecycle_id else [])
        rows.append({"device_id": r.device_id, "vendor": r.normalized.vendor or "",
                     "product": r.normalized.product or "", "version": r.normalized.version or "",
                     "confidence": f"{r.normalized.confidence:.2f}", "lane": r.check.lane,
                     "evidence": ";".join(evidence), "run_id": run_id})
        for note in r.guard_notes:
            print(f"{r.device_id}: {note}")
    out = args.out_root / run_id / "deming.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["device_id", "vendor", "product", "version", "confidence", "lane", "evidence", "run_id"]
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"as_of_date {as_of}; wrote {out}")
    return out


if __name__ == "__main__":
    main()
