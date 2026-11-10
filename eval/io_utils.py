"""Shared CSV helpers that follow docs/contracts.md (v1)."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

LANES = ("patch", "retire", "fine", "unknown")
EXPOSED_LANES = frozenset({"patch", "retire"})

PREDICTION_COLUMNS = ["device_id", "vendor", "product", "version", "confidence", "lane", "evidence", "run_id"]
GROUND_TRUTH_COLUMNS = [
    "device_id", "group", "vendor", "product", "version", "lane",
    "evidence_cve", "evidence_lifecycle_id", "source_row_note", "verified_by_a", "verified_by_b",
]
INVENTORY_COLUMNS = [
    "device_id", "device_name_raw", "location", "owner_email", "firmware_version_raw",
    "internet_facing", "criticality", "do_not_touch", "last_updated",
]


class ContractError(ValueError):
    """A file does not match docs/contracts.md."""


def read_csv(path: str | Path, required: list[str] | None = None) -> list[dict[str, str]]:
    """Read a contract CSV. Accepts LF/CRLF; tolerates a BOM on read. Values are stripped."""
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if required is not None:
            missing = [c for c in required if c not in header]
            if missing:
                raise ContractError(f"{path}: missing columns {missing}")
        return [{k: (v or "").strip() for k, v in row.items() if k is not None} for row in reader]


def write_csv(path: str | Path, columns: list[str], rows: list[dict]) -> None:
    """Write UTF-8 (no BOM), RFC 4180 quoting, exact column order."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in columns})


def utc_stamp(now: datetime | None = None) -> str:
    """`YYYYMMDDTHHMMSSZ` in UTC."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def norm(value: str | None) -> str:
    """Contract comparison: trim whitespace, case-insensitive."""
    return (value or "").strip().casefold()
