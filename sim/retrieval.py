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


def lifecycle_candidates(device: dict, rows: list[dict], k: int = TOP_K_LIFECYCLE,
                         min_score: float = MIN_SCORE) -> list[dict]:
    query = _query(device)
    if not query.strip():
        return []
    product = device.get("product") or ""
    model = device.get("model") or ""
    scored = []
    for r in rows:
        score = fuzz.WRatio(query, f"{r.get('vendor', '')} {r.get('product', '')}",
                            processor=utils.default_process)
        pat = (r.get("model_pattern") or "").strip().lower()
        if pat and any(fnmatch.fnmatchcase(x.lower(), pat) for x in (product, model) if x):
            score = 100.0
        if score >= min_score:
            scored.append((score, r))
    scored.sort(key=lambda t: (-t[0], t[1].get("lifecycle_id", "")))
    return [{**r, "match_score": round(s, 1)} for s, r in scored[:k]]


def kev_products_rows(index: KevIndex) -> list[dict]:
    """One row per KEV product: the kev_products.csv Knowledge file for Agent Designer."""
    rows = []
    for (vendor, product), entries in sorted(index.by_product.items()):
        rows.append({
            "vendorProject": vendor,
            "product": product,
            "cveIDs": ";".join(e["cveID"] for e in entries),
            "earliest_dueDate": min((e.get("dueDate", "") for e in entries), default=""),
            "requiredActions": ";".join(sorted({re.sub(r"\s+", " ", e.get("requiredAction", ""))
                                                for e in entries})),
        })
    return rows
