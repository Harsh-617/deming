# Decisions: inventory (branch feat/inventory)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.

---

### 2026-11-11 · Realistic messy names (research rule, ~5 min)
- **Choice:** mix three naming styles seen in practice: (1) role/site hostnames such as `kl-hq-fw01`
  (site-role-sequence conventions), (2) free-text descriptions with the location in the name
  ("MikroTik router - hostel block C"), (3) human typos and run-together models ("sonicwal sma410",
  "Dlink DNS320L", "Mikrotk", "wtchgrd"). Firmware typed with prefixes (`v7.4.1`, `ROS 7.24.1`,
  `NS14.1 38.53`) or left blank. One row holds injection text (PRD tricky case).
- **Sources:** site-role-sequence convention with role codes like FW:
  https://kb.dtctoday.com/books/dtcs-pillars-of-technology/page/device-naming-convention ;
  function-site-number names: https://oneuptime.com/blog/post/2026-03-20-document-ipv4-assignments-naming-conventions/markdown ;
  location kept in CMDB vs hostname debate: https://industrialmonitordirect.com/blogs/knowledgebase/enterprise-laptop-naming-convention-best-practices ;
  ServiceNow naming/uniqueness: https://www.servicenow.com/community/cmdb-forum/why-not-use-unique-name-values-in-cmdb-ref-to-csa-lab-4-4-1/td-p/3518122
- **Not verified:** no published dataset of real vendor typos was found in the time box; the typo
  style is a judgement, not a measured distribution.
- **Rule kept:** model names appear only when a source names them (lifecycle row, KEV entry, or the
  advisory). Two model names typed from memory (MikroTik hEX/RB) were removed.

### 2026-11-11 · KEV has no version ranges, so fixed_version was filled from the cited pages
- **Finding:** kev.json entry fields are `cveID, vendorProject, product, vulnerabilityName, dateAdded,
  shortDescription, requiredAction, dueDate, knownRansomwareCampaignUse, forensicTriage, notes, cwes`.
  No affected-version field.
- **Choice:** filled `fixed_version` in `data/lifecycle.csv` only where the row's own `source_url` page
  states the fix (re-opened 2026-11-11). Multi-train fixes use `;` (one value per train, contract's
  multi-value rule):

  | Row | fixed_version | Quote from source_url |
  |---|---|---|
  | LC-020 FortiOS 7.4 | 7.4.3 | "7.4.0 through 7.4.2" / "Upgrade to 7.4.3 or above" |
  | LC-021 PAN-OS 11.1 | 11.1.2-h18;11.1.4-h13;11.1.6-h1 | "< 11.1.2-h18", "< 11.1.4-h13", "< 11.1.6-h1" |
  | LC-022 Ivanti 22.x | 22.7R2.6 | "fully patched in Ivanti Connect Secure 22.7R2.6" |
  | LC-023 NetScaler 14.1 | 14.1-47.46 | "14.1 BEFORE 14.1-47.46" |
  | LC-025 RouterOS 7 | 7.24.3;7.23.6 | complete fix "7.24.3 (stable) and 7.23.6 (long-term)" (KEV CVEs alone fixed in 7.24.2/7.23.4; the complete fix is used so no device sits between them) |
  | LC-026 ASA 9.2x | 9.20.4.10;9.22.2.14;9.23.1.19 | "All Vulnerabilities" column |
  | LC-029 Fireware 12.x | 12.11.4 | default models; T15/T35 12.5.13 and FIPS exceptions stay in replacement_hint |

- **Left blank** (fix not on the source_url page, or not a single value): LC-024 SonicOS (page doesn't
  name CVE-2024-40766), LC-028 Check Point (several Jumbo Hotfix takes: 26/41/53/54/65), LC-027 and
  LC-030 (fix only on the second URL in notes), LC-003, LC-010, LC-018 (EOL pages, fix only in notes),
  all no-fix retire rows.

### 2026-11-11 · supported_fine uses KEV products at/above every checked fix
- **Problem:** all 30 lifecycle rows are KEV products, and every supported one has KEV CVEs added
  after the one its fixed_version covers. "At/above fixed_version" alone would mislabel fine.
- **Choice:** opened the newer advisories and chose versions above all of them:
  PAN-OS 11.1.16-h3 (CVE-2025-0111, CVE-2026-0257/0300/0322), Fireware 12.11.6 (CVE-2025-14733),
  RouterOS 7.24.3/7.23.6 (complete fix for all 2026 MikroTik KEV CVEs). FortiOS, ASA, Ivanti and
  NetScaler were NOT used for fine: each has 2026 KEV entries (FortiOS also "Multiple Products"
  entries) that weren't checked.
- **Sources:** https://security.paloaltonetworks.com/CVE-2026-0322 (and -0257, -0300, CVE-2025-0111);
  https://psirt.watchguard.com/CVE-2025-14733 ; https://fortiguard.fortinet.com/psirt/FG-IR-25-934 ;
  https://fortiguard.fortinet.com/psirt/FG-IR-24-535 ; Cisco cisco-sa-asaftd-tunnel-dos-s6mgkb75 and
  cisco-sa-asaftd-vpn-dos-dzv4mQFF (used for the patch rows' evidence).
- **Not verified:** older KEV advisories (PAN-OS 2024, WatchGuard 2022, MikroTik CVE-2018-7445).
  Every fine row is flagged `needs_extra_review` in docs/label-review.csv.

### 2026-11-11 · name_collision rows
- Ivanti "Connect Secure" name with firmware 9.1R18 → Pulse Connect Secure 9.1x, retire (LC-011;
  Ivanti blog: "9.1x reached End-of-Support on December 31, 2024").
- SonicWall SMA 1000 → not SMA100 (KEV lists "SMA1000 Appliances" as its own product). No fix data,
  no firmware → unknown. Must not be retire.
- Sophos XGS 2100 → not XG hardware (LC-013: "Pattern 'XG *' does not match XGS"; XGS 2100 is the
  named replacement for XG 210). No firmware → unknown.
- NUUO NVRmini 3 → the replacement named in LC-015's EOL letter; no KEV entry or lifecycle row → fine.
- **Alternatives rejected:** Zyxel USG20-VPN / USG FLEX (same KEV product "Multiple Firewalls", so not a
  different product); Cisco Firepower 1000 (runs ASA/FTD software that is in KEV).

### 2026-11-11 · Owner email domain
- **Choice:** `@example.org` (contracts.md: "Synthetic address at example.org"; existing tests and
  fixtures use it). The task brief said example.com; both are reserved (RFC 2606). Flagged in the summary.

### 2026-11-11 · Build and review files
- `scripts/build_inventory.py` holds every hand-written row and lays them out deterministically
  (seed 20261111): device ids are shuffled so ids don't reveal the group; the blind sample of 15 uses
  the same RNG. Re-running gives identical files.
- `eval/blind/blind_key.csv` maps blind ids to device ids, kept separate so the worksheet shows only
  name + firmware. Labellers must not open it (honour system; it's in the repo).
- `eval/blind/agreement.py`: per-field percent agreement vs ground truth and Cohen's kappa on lane,
  plus pairwise labeller kappa.
