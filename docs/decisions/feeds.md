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
