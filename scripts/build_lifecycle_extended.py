"""Build data/lifecycle_extended.csv: extra end-of-life rows, each from a source that states the
date explicitly. Same columns and rules as data/lifecycle.csv (docs/contracts.md).

    python scripts/build_lifecycle_extended.py            # offline: uses the cached feed
    python scripts/build_lifecycle_extended.py --fetch    # re-download the endoflife.date feed first

data/lifecycle.csv is read only to skip trains it already has, and is NEVER changed. The published Deming results used
only its 30 rows; this file is optional input, off by default (sim/retrieval.py,
DEMING_LIFECYCLE_EXTENDED). Its effect on lane accuracy has not been measured (needs a new
Gemini run). Research and source choices: docs/decisions.md (2026-11-12, lifecycle_extended).

Two kinds of rows:
1. VENDOR_ROWS: written by hand from a vendor lifecycle page, opened and read on `verified_on`.
2. endoflife.date rows: generated from the cached API response data/feeds/endoflife/<slug>.json
   (API v1, https://endoflife.date/docs/api/v1/). A cycle becomes a row only if the response
   gives BOTH support dates as explicit ISO dates, and only if lifecycle.csv has no row for it.

A row is skipped when its source gives no explicit date (month or quarter only, "TBD", no table,
login wall). SKIPPED lists every product looked at and not added, with the reason.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "lifecycle_extended.csv"
FEEDS = ROOT / "data" / "feeds" / "endoflife"
BASE_LIFECYCLE = ROOT / "data" / "lifecycle.csv"

HEADER = ["lifecycle_id", "vendor", "product", "model_pattern", "eol_date",
          "last_security_support_date", "patch_available", "replacement_hint", "source_url",
          "verified_on", "notes", "fixed_version"]
FIRST_ID = 101  # LC-101.. so ids never collide with lifecycle.csv (LC-001..LC-030)
RETRIEVED = "2026-11-12"
SOFTWARE = "model_pattern is a version glob (software train)."

WATCHGUARD_EOL = "https://www.watchguard.com/node/111406"
WATCHGUARD_NOTE = ("Hardware row. WatchGuard End of Life Policy, Firebox table: End of Sale {eos}; "
                   "End of Life {eol}. EOL = 'Conclusion of development and support for defined "
                   "End-of-Sale products'. The page gives no separate security-support date, so "
                   "last_security_support_date is blank and eol_date governs (contracts.md "
                   "tie-break). Fireware software fixes for this model: LC-029.")


def _wg(model: str, eos: str, eol: str, migrate: str) -> dict:
    return {"vendor": "WatchGuard", "product": "Firebox", "model_pattern": f"*{model}",
            "eol_date": eol, "last_security_support_date": "", "patch_available": "",
            "replacement_hint": f"Firebox {migrate} (WatchGuard migration path)",
            "source_url": WATCHGUARD_EOL, "verified_on": RETRIEVED,
            "notes": f"Firebox {model}. " + WATCHGUARD_NOTE.format(eos=eos, eol=eol),
            "fixed_version": ""}


VENDOR_ROWS: list[dict] = [
    _wg("T35", "2021-07-17", "2025-12-31", "T125, T145"),
    _wg("T35-W", "2020-12-31", "2025-12-31", "T125-W, T145-W"),
    _wg("T35-R", "2023-07-01", "2027-03-01", "T125, T145"),
    _wg("T35-DW", "2023-07-01", "2027-03-01", "T125-W, T145-W"),
    {"vendor": "Cisco", "product": "Adaptive Security Appliance (ASA)", "model_pattern": "9.16.*",
     "eol_date": "2026-11-18", "last_security_support_date": "2026-11-18", "patch_available": "",
     "replacement_hint": "Move to a supported ASA release (the notice names none)",
     "source_url": "https://www.cisco.com/c/en/us/products/collateral/security/asa-firepower-services/asa-9-16-asav-asdm-release-7-16-eol.html",
     "verified_on": RETRIEVED,
     "notes": f"{SOFTWARE} ASA/ASAv 9.16(x) software. eol_date = 'End of SW Maintenance Releases "
              "Date: App SW'; last_security_support_date = 'End of Vulnerability/Security "
              "Support: App SW' (both 2026-11-18). Last Date of Support 2027-11-30.",
     "fixed_version": ""},
    {"vendor": "Citrix", "product": "NetScaler ADC and Gateway", "model_pattern": "13.1*",
     "eol_date": "2026-09-15", "last_security_support_date": "2027-09-15", "patch_available": "",
     "replacement_hint": "Upgrade to 14.1",
     "source_url": "https://support.citrix.com/external/article/CTX241500/netscaler-adc-firmware-release-cycle.html",
     "verified_on": RETRIEVED,
     "notes": f"{SOFTWARE} Same mapping as LC-018: eol_date = EOM, last_security_support_date = "
              "EOL. CTX241500: '13.1 will reach EOM on 15-Sep-26 and EOL on 15-Sep-27'. The same article moves "
              "NetScaler Console on-prem 13.1 (not ADC) to 15-Apr-26; that revision is not applied here.",
     "fixed_version": ""},
]

# endoflife.date slugs checked against https://endoflife.date/api/v1/products on 2026-11-12.
# field mapping per slug: (eol_date field, last_security_support_date field, label meaning).
EOLDATE_SOURCES = {
    "fortios": {"vendor": "Fortinet", "product": "FortiOS",
                "eol_field": "eoasFrom", "sec_field": "eolFrom",
                "meaning": "eol_date = End of Engineering Support; last_security_support_date = "
                           "End of Support (endoflife.date labels, same mapping as LC-016)",
                "hint": "Upgrade to a supported FortiOS train"},
}

SKIPPED = [
    ("Ivanti Connect Secure 22.x", "Vendor EOL matrix (hub.ivanti.com Pulse-Secure-Product-End-of-Life-EOL-Policy) "
     "shows no release table without login; no endoflife.date slug. Third-party trackers only."),
    ("Citrix NetScaler ADC 14.1", "CTX241500 gives 'EOM during Q3/29', 'EOL during Q3/30': quarter only, no date."),
    ("MikroTik RouterOS 7.x", "No MikroTik end-of-support statement. endoflife.date 'routeros' dates are "
     "derived (a stable cycle ends when the next one ships), not stated by the vendor."),
    ("Palo Alto Networks PAN-OS (other trains)", "endoflife.date 'panos' gives one 'End-of-life Date' "
     "(standard support) but not Extended Support+, so last_security_support_date would be wrong. "
     "Inventory only runs 10.1/11.1, already in lifecycle.csv."),
    ("WatchGuard Fireware 12.x (software)", "No Fireware OS end-of-support date found on the vendor site."),
    ("WatchGuard Firebox other models (T15, T20, T40, ...)", "Dates exist on the same page, but no inventory "
     "device uses them and extra name-only rows would crowd the top-5 Firebox candidates."),
    ("Sophos XGS 2100", "docs.sophos.com lifecycle page has no date for it (policy: at least 5 years after "
     "an EoS date that is not announced)."),
    ("SonicWall SMA 1000 Series", "Software lifecycle table flattens to text with an ambiguous column "
     "order (Support Discontinued vs Limited Support); hardware table not read. Not added."),
    ("NUUO NVRmini 3", "No vendor EOL notice found."),
    ("Ivanti Pulse Connect Secure 9.1x, Cisco RV, D-Link, Zyxel USG, DrayTek, Edimax, NUUO NVRmini2, "
     "SonicWall SMA100, Sophos XG, Fortinet FortiOS 7.0/7.4, PAN-OS 10.1/11.1, ASA 5506-X, Citrix 13.0",
     "Already in data/lifecycle.csv; not duplicated."),
]


def _iso(v) -> str | None:
    if not isinstance(v, str):
        return None
    try:
        return dt.date.fromisoformat(v).isoformat()
    except ValueError:
        return None


def fetch(slug: str) -> Path:
    url = f"https://endoflife.date/api/v1/products/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "deming-lifecycle-builder"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed https URL
        body = r.read()
    FEEDS.mkdir(parents=True, exist_ok=True)
    path = FEEDS / f"{slug}.json"
    path.write_bytes(body)  # byte-for-byte as downloaded
    meta = {"source_url": url, "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": hashlib.sha256(body).hexdigest()}
    (FEEDS / f"{slug}_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return path


def base_trains(vendor: str, product: str) -> set[str]:
    """Version globs lifecycle.csv already has for this vendor/product."""
    with open(BASE_LIFECYCLE, encoding="utf-8", newline="") as f:
        return {r["model_pattern"].strip() for r in csv.DictReader(f)
                if r["vendor"] == vendor and r["product"] == product}


def endoflife_rows(slug: str, spec: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    meta = json.loads((FEEDS / f"{slug}_meta.json").read_text(encoding="utf-8"))
    data = json.loads((FEEDS / f"{slug}.json").read_text(encoding="utf-8"))["result"]
    have = base_trains(spec["vendor"], spec["product"])
    rows, skipped = [], []
    for rel in data["releases"]:
        name = rel["name"]
        pattern = f"{name}.*"
        label = f"{spec['vendor']} {spec['product']} {name}"
        if pattern in have:
            skipped.append((label, "already in data/lifecycle.csv"))
            continue
        eol, sec = _iso(rel.get(spec["eol_field"])), _iso(rel.get(spec["sec_field"]))
        if not (eol and sec):
            skipped.append((label, f"endoflife.date gives no explicit {spec['eol_field']}/{spec['sec_field']} date"))
            continue
        rows.append({
            "vendor": spec["vendor"], "product": spec["product"], "model_pattern": pattern,
            "eol_date": eol, "last_security_support_date": sec, "patch_available": "",
            "replacement_hint": spec["hint"],
            "source_url": f"https://endoflife.date/{slug}",
            "verified_on": meta["fetched_at"][:10],
            "notes": f"{SOFTWARE} {spec['product']} {name}. {spec['meaning']}. From endoflife.date API "
                     f"v1 {meta['source_url']} (cached data/feeds/endoflife/{slug}.json, sha256 "
                     f"{meta['sha256'][:12]}).",
            "fixed_version": ""})
    return rows, skipped


def build() -> tuple[list[dict], list[tuple[str, str]]]:
    rows = list(VENDOR_ROWS)
    skipped = list(SKIPPED)
    for slug, spec in EOLDATE_SOURCES.items():
        r, s = endoflife_rows(slug, spec)
        rows += r
        skipped += s
    out = []
    for i, r in enumerate(rows):
        assert r["source_url"].startswith("https://") and _iso(r["verified_on"]), r
        assert r["eol_date"] or r["last_security_support_date"], f"row without a date: {r}"
        out.append({"lifecycle_id": f"LC-{FIRST_ID + i:03d}", **{k: r[k] for k in HEADER[1:]}})
    return out, skipped


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fetch", action="store_true", help="re-download the endoflife.date feed(s)")
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    if a.fetch:
        for slug in EOLDATE_SOURCES:
            print(f"fetched {fetch(slug)}")
    rows, skipped = build()
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {a.out}")
    print("skipped (not sourced explicitly, or already present):")
    for what, why in skipped:
        print(f"  - {what}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
