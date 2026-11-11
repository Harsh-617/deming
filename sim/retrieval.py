"""Deterministic top-k candidate retrieval for the Checker.

The Checker LLM never sees the whole KEV catalog. This module picks a handful of KEV products and
lifecycle rows that plausibly match one device, so the prompt stays small and every id the
Checker cites can be checked against the candidate list (see sim/guards.py).

In Agent Designer the same step is the "Candidate lookup" section of agents/checker.md:
search kev_products.csv and lifecycle.csv (Knowledge files) for matching vendor/product rows.
`kev_products_rows()` produces that kev_products.csv.
"""
from __future__ import annotations

import csv
import fnmatch
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz, process, utils

TOP_K_PRODUCTS = 5
TOP_K_LIFECYCLE = 5
MIN_SCORE = 60
MAX_CVES_PER_PRODUCT = 8
DESCRIPTION_CHARS = 400

KEV_FIELDS = ("cveID", "vendorProject", "product", "vulnerabilityName", "shortDescription",
              "requiredAction", "dueDate", "dateAdded", "notes")


def load_kev(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["vulnerabilities"]


def load_lifecycle(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@dataclass
class KevIndex:
    """KEV entries grouped by (vendorProject, product)."""
    by_product: dict[tuple[str, str], list[dict]] = field(default_factory=dict)

    @classmethod
    def build(cls, vulnerabilities: list[dict]) -> "KevIndex":
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for v in vulnerabilities:
            groups[(v.get("vendorProject", ""), v.get("product", ""))].append(v)
        return cls(dict(groups))

    @property
    def keys(self) -> list[tuple[str, str]]:
        return list(self.by_product)


def _query(device: dict) -> str:
    vendor, product, model = device.get("vendor"), device.get("product"), device.get("model")
    if vendor or product:
        return " ".join(x for x in (vendor, product, model) if x)
    return device.get("device_name_raw") or ""


def _tokens(device: dict) -> list[str]:
    toks = []
    for k in ("version", "model"):
        val = (device.get(k) or "").strip()
        if val:
            toks.append(val.lower())
    return toks


def _cve_rank(v: dict, toks: list[str]) -> tuple[int, str]:
    text = f"{v.get('vulnerabilityName', '')} {v.get('shortDescription', '')}".lower()
    hit = any(t in text for t in toks)
    return (0 if hit else 1, _neg_date(v.get("dateAdded", "")))


def _neg_date(d: str) -> str:
    # Sort newest first with an ascending sort: invert digits.
    return "".join(chr(ord("9") - ord(c) + ord("0")) if c.isdigit() else c for c in d)


def _slim(v: dict) -> dict:
    out = {k: v.get(k, "") for k in KEV_FIELDS}
    if len(out["shortDescription"]) > DESCRIPTION_CHARS:
        out["shortDescription"] = out["shortDescription"][:DESCRIPTION_CHARS] + "..."
    return out


def kev_candidates(device: dict, index: KevIndex, k: int = TOP_K_PRODUCTS,
                   min_score: float = MIN_SCORE,
                   max_cves: int = MAX_CVES_PER_PRODUCT) -> list[dict]:
    query = _query(device)
    if not query.strip() or not index.by_product:
        return []
    choices = [f"{v} {p}" for v, p in index.keys]
    hits = process.extract(query, choices, scorer=fuzz.WRatio, processor=utils.default_process,
                           limit=k, score_cutoff=min_score)
    toks = _tokens(device)
    out: list[dict] = []
    for _, score, i in hits:
        entries = sorted(index.by_product[index.keys[i]], key=lambda v: _cve_rank(v, toks))
        for v in entries[:max_cves]:
            out.append({**_slim(v), "match_score": round(score, 1)})
    return out


SOFTWARE_NOTE = "model_pattern is a version glob"


def is_software_row(row: dict) -> bool:
    """Software rows say so at the start of `notes` (contracts.md, lifecycle.csv)."""
    return (row.get("notes") or "").strip().lower().startswith(SOFTWARE_NOTE)


def _clean(s: str | None) -> str:
    s = (s or "").strip().lower()
    return s[1:] if s[:1] == "v" and s[1:2].isdigit() else s


def pattern_specificity(pattern: str) -> int:
    """Literal characters in a glob: `*`, `?` and `[...]` classes don't count."""
    return len(re.sub(r"\[[^\]]*\]|[*?]", "", (pattern or "").strip()))


def pattern_targets(row: dict, device: dict) -> list[str]:
    """The device strings a row's model_pattern is matched against (lowercased, no `v` prefix)."""
    keys = ("version", "firmware_version_raw") if is_software_row(row) else ("product", "model")
    return [x for x in (_clean(device.get(k)) for k in keys) if x]


def pattern_matches(row: dict, device: dict) -> bool | None:
    """True if the row's pattern fits the device, False if it was tested and doesn't, None if
    the pattern is blank or the device has no model (hardware) / version (software) to test."""
    pat = (row.get("model_pattern") or "").strip().lower()
    if not pat:
        return None
    # fnmatchcase on lowercased strings: fnmatch.fnmatch follows os.path.normcase, which is
    # case-insensitive on Windows only.
    if any(fnmatch.fnmatchcase(t, pat) for t in pattern_targets(row, device)):
        return True
    key = "version" if is_software_row(row) else "model"
    testable = _clean(device.get(key)) or (is_software_row(row)
                                           and _clean(device.get("firmware_version_raw")))
    return False if testable else None


def lifecycle_candidates(device: dict, rows: list[dict], k: int = TOP_K_LIFECYCLE,
                         min_score: float = MIN_SCORE) -> list[dict]:
    """Lifecycle rows for one device, most specific first.

    Order: rows whose model_pattern matches (most literal characters first), then rows with a
    blank pattern or nothing to test the pattern against, by name score. Rows whose pattern was
    tested and does not fit are dropped. A software row (version glob) also needs a vendor/
    product name match, so `7.*` from one vendor never matches another vendor's 7.x device.
    """
    query = _query(device)
    if not query.strip():
        return []
    scored = []
    for r in rows:
        name_score = fuzz.WRatio(query, f"{r.get('vendor', '')} {r.get('product', '')}",
                                 processor=utils.default_process)
        hit = pattern_matches(r, device)
        if hit is False:
            continue
        if hit and (not is_software_row(r) or name_score >= min_score):
            score, rank = 100.0, 0
        elif hit is None and name_score >= min_score:
            score, rank = name_score, 1
        else:
            continue
        spec = pattern_specificity(r.get("model_pattern", "")) if rank == 0 else 0
        scored.append((rank, -spec, -score, r.get("lifecycle_id", ""), score, r))
    scored.sort(key=lambda t: t[:4])
    return [{**r, "fixed_version": r.get("fixed_version") or "", "match_score": round(s, 1)}
            for *_, s, r in scored[:k]]


KEV_PRODUCTS_COLUMNS = ("vendorProject", "product", "cve_count", "cveIDs", "earliest_dueDate",
                        "latest_dateAdded", "known_ransomware_use", "requiredActions")
KEV_ENTRIES_COLUMNS = ("cveID", "vendorProject", "product", "vulnerabilityName",
                       "shortDescription", "requiredAction", "dueDate", "dateAdded",
                       "knownRansomwareCampaignUse")


def _one_line(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def kev_products_rows(index: KevIndex) -> list[dict]:
    """One row per KEV product: the kev_products.csv Knowledge file for Agent Designer."""
    rows = []
    for (vendor, product), entries in sorted(index.by_product.items()):
        entries = sorted(entries, key=lambda e: e["cveID"])
        rows.append({
            "vendorProject": vendor,
            "product": product,
            "cve_count": len(entries),
            "cveIDs": ";".join(e["cveID"] for e in entries),
            "earliest_dueDate": min((e.get("dueDate", "") for e in entries), default=""),
            "latest_dateAdded": max((e.get("dateAdded", "") for e in entries), default=""),
            "known_ransomware_use": str(any(e.get("knownRansomwareCampaignUse") == "Known"
                                            for e in entries)).lower(),
            "requiredActions": " | ".join(sorted({_one_line(e.get("requiredAction", ""))
                                                  for e in entries})),
        })
    return rows


def kev_entries_rows(vulnerabilities: list[dict],
                     description_chars: int = DESCRIPTION_CHARS) -> list[dict]:
    """One slim row per CVE: the kev_entries.csv Knowledge file (details behind kev_products)."""
    rows = []
    for v in sorted(vulnerabilities, key=lambda e: e["cveID"]):
        row = {k: _one_line(str(v.get(k, ""))) for k in KEV_ENTRIES_COLUMNS}
        if len(row["shortDescription"]) > description_chars:
            row["shortDescription"] = row["shortDescription"][:description_chars] + "..."
        rows.append(row)
    return rows
