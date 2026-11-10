# Data feeds: provenance

Formats are defined in `docs/contracts.md`. This file records where each file came from and
which rows are weaker than others.

## data/feeds/kev.json and kev_meta.json

- **What:** CISA Known Exploited Vulnerabilities catalog, saved byte-for-byte as downloaded.
- **From:** https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
  (fallback: https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json).
- **How:** `python scripts/fetch_kev.py [--diff]`. The script validates the feed before saving and
  writes atomically. If the bytes are unchanged, nothing is rewritten.
  `--diff` prints entries whose `dateAdded` is later than the newest one in the previous snapshot.
- **Current snapshot:** catalogVersion `2026.11.09`, 1773 entries, fetched 2026-11-10T16:56:56Z
  from cisa.gov (sha256 in `kev_meta.json`).
- **Line endings:** `.gitattributes` marks `data/feeds/*.json` as `-text`, so git never converts
  line endings and the sha256 stays valid after checkout.

## data/lifecycle.csv

- **What:** 30 hand-curated rows for edge devices: routers, firewalls, VPN gateways, NAS, an IP
  camera and an NVR. Most have a CVE in the KEV snapshot. Mix: 19 end-of-life or no-patch rows and 11 supported rows with a
  published fix. The Vigor2960 row is in the second group until 2026-12-09.
- **From:** vendor-owned pages only (Cisco, D-Link, Zyxel, DrayTek, Ivanti, SonicWall, Sophos,
  Edimax, NUUO, Fortinet, Palo Alto Networks, Citrix/NetScaler, MikroTik, Check Point, WatchGuard).
  `source_url` is the page that states the date or fix. When a second page was needed, its URL is
  in `notes`. Every row was checked on 2026-11-11 (`verified_on`).
- **How it was checked:** research subagents opened each vendor page and returned verbatim quotes.
  These rows were then re-checked directly by the main session:
  - Cisco RV320/RV325, RV340/RV345 and ASA 5506-X bulletins
  - D-Link NAS table (SAP10383)
  - DrayTek lifecycle table and Vigor2960 1.5.1.5 release note
  - Zyxel end-of-life table
  - Cisco ASA fixed-release table
  - KEV membership of every cited CVE

  Pages that block scripts (Cisco and DrayTek return 403 to curl) were read with WebFetch or a
  headless browser. They open normally in a browser.
- **Dates:** copied as the vendor states them, never estimated. Where a vendor gives only a month
  ("May 2027") or no date ("discontinued over 10 years ago"), the cell is blank.

### Interpretation choices (affect the Checker)

1. **`model_pattern`**: the contract says it is matched against the canonical product. In practice
   the canonical KEV product is often a family name ("Small Business RV Series Routers"), so the
   pattern only makes sense against the device's model (hardware rows, e.g. `RV32*`) or version
   (software-train rows, e.g. FortiOS `7.0.*`). Software-train rows say so at the start of `notes`.
   See the proposed contract change in the branch summary.
2. **Which column holds which date:** each vendor uses different milestone names.
   - `eol_date`: end of sale / end of maintenance / standard-support end.
   - `last_security_support_date`: end of vulnerability/security support where the vendor has it.
     Otherwise "Last Date of Support" or "End of Support".
   - Each row's `notes` names the vendor milestone used.
3. **`patch_available`** refers to the KEV CVE(s) named in `notes`. It is blank when the vendor
   page doesn't say whether a fix exists for this product line.

### Rows to treat with care

| Row | Concern |
|---|---|
| LC-001, LC-002, LC-019 (Cisco RV32x, RV042, ASA 5506-X) | The bulletins have no "End of Vulnerability/Security Support" row, so "Last Date of Support" is used. Cisco's series page shows earlier dates for RV320/RV325 (31-Jul-2021) than the bulletin (2025-01-31); the bulletin is used. |
| LC-004 (D-Link DIR-859) | Page says "Resolved Status: Yes" but names no fixed firmware; `patch_available` left blank. Lane is retire on date anyway. |
| LC-010, LC-030 (DrayTek) | The lifecycle page returns 403 to scripts, so it was read in a browser. **LC-030 (Vigor2960) changes from patch to retire on 2026-12-09.** |
| LC-011, LC-022 (Ivanti) | Source is an Ivanti blog post, not the EOL matrix (the matrix couldn't be reached). Connect Secure 22.x end-of-support date not verified. |
| LC-013 (Sophos XG) | Source is a Sophos staff post on community.sophos.com (vendor domain, not a formal notice page). |
| LC-014 (Edimax IC-7100) | No date at all; retire rests on the vendor's "no security patch ... can be provided". |
| LC-015 (NUUO NVRmini2) | EOL letter predates the KEV CVE; patch status blank. |
| LC-016, LC-020 (FortiOS) | Fortinet's official life-cycle portal needs a login; dates come from Fortinet staff technical tips on community.fortinet.com. |
| LC-017, LC-021 (PAN-OS) | Two end-of-life columns (Standard / Extended Support+); the mapping to our columns is explained in `notes`. |
| LC-024 (SonicOS 7) | Per-model support dates not verified. Fix for the newest SonicWall KEV CVE (CVE-2026-19868) not verified; the advisory page is JavaScript-only. |
| LC-026 (Cisco ASA 9.2x) | Fixed versions read from Cisco's event-response page, whose table renders oddly; values cross-checked twice. |
| LC-028 (Check Point R81.20) | Support end is "May 2027" (month only), left blank. |
| LC-029 (WatchGuard) | Support end dates not verified; only the fix is. |

### Researched but left out

- **TP-Link TL-WR940N / TL-WR841N / Archer C5 (KEV CVE-2023-33538):** TP-Link says these are EOL,
  but its list gives only "Before 2018" and no page ties a date to the KEV CVE. Omitted.
- **Zyxel NAS326 / NAS542:** end of vulnerability support 2023-12-31 is verified, but the verified
  advisory covers CVE-2024-29973, which is not in KEV (KEV lists CVE-2023-27992 and CVE-2020-9054
  for Zyxel NAS). Omitted to stay within 30 rows; easy to add.
- **QNAP QTS 5.x:** no KEV CVE in the snapshot has a QTS 5.x-specific fix. Omitted.
- **Found by the research agents but cut to stay within 30 rows** (vendor-stated dates, not
  re-checked by the main session; re-open the page before adding a row):
  | Product | End of sale / EOL | Last (security) support | Source |
  |---|---|---|---|
  | Cisco RV082 | 2016-05-05 | 2021-05-31 | cisco.com eos-eol-notice-c51-736749 |
  | Cisco RV016 | | 2021-01-31 (series page) | cisco.com RV series page |
  | D-Link DNS-340L | | 2019-07-31 | D-Link SAP10383 (re-checked) |
  | D-Link DIR-605 / DIR-605L | | 2015-02-01 / 2019-09-24 | D-Link SAP10393 |
  | Cisco ASA 5508-X / 5516-X | 2021-08-02 | 2026-08-31 | cisco.com eos-eol-notice-c51-744798 |
  | FortiOS 6.4 | | 2024-09-30 | Fortinet staff tip ta-p/345103 |
  | PAN-OS 9.1 | 2024-06-30 | | Palo Alto end-of-life summary |
  | NetScaler 12.1 | 2022-05-30 | 2023-05-30 | Citrix legacy product matrix |
  | Zyxel VPN50/100/300/1000 | 2025-03-31 | 2023-09-30 | Zyxel end-of-life page |
  | Zyxel ZyWALL 110/310/1100 | 2024-05-16 | 2022-12-31 | Zyxel end-of-life page |

## endoflife.date

Not used. Its API covers network software trains only (FortiOS, PAN-OS, IOS XE, RouterOS, BIG-IP)
and no consumer routers, cameras, NAS or most VPN appliances. Details: `docs/decisions/feeds.md`.
