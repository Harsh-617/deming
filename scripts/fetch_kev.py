"""Download the CISA Known Exploited Vulnerabilities (KEV) catalog.

Saves data/feeds/kev.json byte-for-byte as downloaded plus data/feeds/kev_meta.json
(see docs/contracts.md). Read-only: it only fetches a public feed, never touches devices.

Usage:
    python scripts/fetch_kev.py            # fetch and save
    python scripts/fetch_kev.py --diff     # also list entries added since the saved snapshot

Idempotent: if the downloaded bytes match the saved kev.json (same sha256), nothing is
rewritten, so kev_meta.json keeps the fetched_at of the download that produced those bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

PRIMARY_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
# Official CISA-maintained GitHub mirror of the same file.
MIRROR_URL = "https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json"

REPO_ROOT = Path(__file__).resolve().parent.parent
FEEDS_DIR = REPO_ROOT / "data" / "feeds"
KEV_PATH = FEEDS_DIR / "kev.json"
META_PATH = FEEDS_DIR / "kev_meta.json"

REQUIRED_ENTRY_FIELDS = ("cveID", "vendorProject", "product", "dateAdded")
TIMEOUT_S = 60


def download(url: str) -> bytes:
    resp = requests.get(url, timeout=TIMEOUT_S, headers={"User-Agent": "deming-feed-fetcher/1.0"})
    resp.raise_for_status()
    return resp.content


def parse_and_validate(raw: bytes) -> dict:
    """Parse KEV bytes and check the fields Deming relies on. Raises ValueError if bad."""
    data = json.loads(raw.decode("utf-8"))
    vulns = data.get("vulnerabilities")
    if not isinstance(vulns, list) or not vulns:
        raise ValueError("KEV JSON has no non-empty 'vulnerabilities' list")
    if data.get("count") != len(vulns):
        raise ValueError(f"KEV count {data.get('count')} != len(vulnerabilities) {len(vulns)}")
    for i, v in enumerate(vulns):
        missing = [f for f in REQUIRED_ENTRY_FIELDS if not v.get(f)]
        if missing:
            raise ValueError(f"KEV entry {i} missing {missing}")
    if not data.get("catalogVersion"):
        raise ValueError("KEV JSON has no catalogVersion")
    return data


def fetch() -> tuple[bytes, dict, str]:
    """Try the CISA URL, then the GitHub mirror. Returns (raw bytes, parsed, url used)."""
    errors = []
    for url in (PRIMARY_URL, MIRROR_URL):
        try:
            raw = download(url)
            return raw, parse_and_validate(raw), url
        except (requests.RequestException, ValueError, UnicodeDecodeError) as exc:
            errors.append(f"{url}: {exc}")
            print(f"warning: fetch failed from {url}: {exc}", file=sys.stderr)
    raise RuntimeError("all KEV sources failed:\n  " + "\n  ".join(errors))


def new_entries(old: dict | None, new: dict) -> list[dict]:
    """Entries in `new` whose dateAdded is later than the latest dateAdded in `old`.

    With no previous snapshot there is nothing to compare against, so returns [].
    ISO YYYY-MM-DD strings compare correctly as strings.
    """
    if not old or not old.get("vulnerabilities"):
        return []
    cutoff = max(v["dateAdded"] for v in old["vulnerabilities"])
    added = [v for v in new["vulnerabilities"] if v["dateAdded"] > cutoff]
    return sorted(added, key=lambda v: (v["dateAdded"], v["cveID"]))


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def save(raw: bytes, parsed: dict) -> dict:
    meta = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "catalogVersion": parsed["catalogVersion"],
        "count": parsed["count"],
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write(KEV_PATH, raw)
    _atomic_write(META_PATH, (json.dumps(meta, indent=2) + "\n").encode("utf-8"))
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diff", action="store_true",
                    help="list entries whose dateAdded is newer than the previously saved snapshot")
    args = ap.parse_args(argv)

    old_raw = KEV_PATH.read_bytes() if KEV_PATH.exists() else None
    old = None
    if old_raw is not None:
        try:
            old = json.loads(old_raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            print("warning: existing kev.json is unreadable; treating as no snapshot", file=sys.stderr)

    raw, parsed, url = fetch()
    sha = hashlib.sha256(raw).hexdigest()

    if old_raw is not None and hashlib.sha256(old_raw).hexdigest() == sha and META_PATH.exists():
        print(f"unchanged: catalogVersion {parsed['catalogVersion']}, {parsed['count']} entries (from {url})")
    else:
        meta = save(raw, parsed)
        print(f"saved: catalogVersion {meta['catalogVersion']}, {meta['count']} entries, "
              f"sha256 {meta['sha256'][:12]}... (from {url})")

    if args.diff:
        if old is None:
            print("diff: no previous snapshot to compare against")
        else:
            added = new_entries(old, parsed)
            print(f"diff: {len(added)} entr{'y' if len(added) == 1 else 'ies'} newer than previous snapshot")
            for v in added:
                print(f"  {v['dateAdded']}  {v['cveID']:<18} {v['vendorProject']} | {v['product']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
