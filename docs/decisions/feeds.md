# Decisions: feeds (branch feat/feeds)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.

---

### 2026-11-11 · KEV download
- **Choice:** `requests` GET of the official CISA JSON feed, saved byte-for-byte (contract requires a
  reproducible sha256). Fallback: the `cisagov/kev-data` GitHub repo raw file (CISA-owned org).
  Both validated before saving (non-empty `vulnerabilities`, `count == len`, required entry fields).
  Atomic write (temp file + `os.replace`). If the sha256 matches the saved file, nothing is rewritten.
- **`--diff`:** lists entries whose `dateAdded` is later than the newest `dateAdded` in the snapshot
  that was on disk before this run (as the task specifies). Entries added on the same day as the
  previous newest entry would be missed; acceptable because CISA publishes the catalog in daily batches.
- **Alternatives:** the KEV CSV feed (same data, but JSON keeps `cwes`/`notes` structured);
  NVD API `hasKev` filter (rate-limited, needs extra calls, and is a copy of CISA's data, not the source).
- **Source:** https://www.cisa.gov/known-exploited-vulnerabilities-catalog (links the JSON/CSV feeds);
  https://github.com/cisagov/kev-data. Both URLs returned HTTP 200 on 2026-11-11.
- **Not verified:** how quickly the GitHub mirror trails the cisa.gov file.

### 2026-11-11 · endoflife.date for edge devices: not used
- **Finding:** queried `https://endoflife.date/api/v1/products` (489 products). Categories: server-app 176,
  framework 74, os 68, app 62, lang 34, database 27, service 25, device 21. The network-relevant entries
  are software release lines only: `fortios`, `panos`, `cisco-ios-xe`, `routeros`, `big-ip`, `netapp-ontap`,
  `openwrt`, `truenas`, Stormshield `sns-*`. The `device` category is phones, tablets, watches, Raspberry Pi,
  Kindle and similar consumer hardware.
  No D-Link, TP-Link, Zyxel, Netgear, ASUS, DrayTek, SonicWall, Ivanti, Citrix/NetScaler, Cisco ASA or RV,
  QNAP, Synology, Hikvision, Dahua, Reolink or other camera/NAS/consumer-router hardware.
- **Choice:** don't depend on it. `data/lifecycle.csv` is hand-curated from vendor pages instead.
  endoflife.date could be an optional cross-check for FortiOS/PAN-OS branch dates later.
- **Source:** https://endoflife.date/api/v1/products (fetched 2026-11-11); https://endoflife.date/docs/api/v1/
- **Not verified:** how endoflife.date sources its network-OS dates; we cite the vendor pages directly.

### 2026-11-11 · lifecycle.csv sourcing
- **Choice:** hand-curated from vendor-owned EOL notices and security advisories. Each row cites the
  page that states the date or fix. Research subagents gathered verbatim quotes; the main session
  re-checked the riskiest rows directly (Cisco bulletins, D-Link NAS table, DrayTek and Zyxel lifecycle
  tables, Cisco ASA fixed releases) and confirmed every cited CVE is in the KEV snapshot. Pages that block
  scripts were read with WebFetch or a headless browser.
- **Alternatives:** endoflife.date (doesn't cover these devices; see above); NVD CPE "deprecated" flags
  (not an EOL signal); third-party EOL aggregators (not primary sources; rejected).
- **Source:** per-row `source_url`; summary in `docs/feeds.md`.
- **Not verified:**
  - Support end dates for Ivanti Connect Secure 22.x, NetScaler 14.1, SonicOS 7, RouterOS 7 and WatchGuard Fireware 12.
  - Check Point R81.20 has a month only ("May 2027"), so it is left blank.
  - Fortinet dates come from Fortinet staff technical tips, because the official portal needs a login.
  - TP-Link was omitted: its pages give no exact date.

### 2026-11-11 · model_pattern interpretation
- **Choice:** `model_pattern` globs the device's normalized model (hardware rows) or version
  (software-train rows, flagged in `notes`), not the canonical product string as contracts v1 says.
- **Why:** canonical KEV product names are family names ("Small Business RV Series Routers"), so the
  contract's own example (`RV32*`) can never match them. Proposed contract change is in the branch summary.
- **Alternatives:** add a separate `version_pattern` column (cleaner, but needs a contract change on main).
