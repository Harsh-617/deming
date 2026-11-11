# Label check report (mechanical)

Generated 2026-11-11T14:32:52Z by `scripts/check_labels.py`, as of `2026-11-12` (data/ground_truth_meta.json). No LLM was used. This report checks the labels against the repo's own data and the public source pages; it does **not** replace the two human reviewers, and a `pass` here only means no mechanical rule disagreed.

## Summary

- Devices: 60. Mechanical **flag**: 10; pass: 50.
- Source check **needs human**: 19 devices; ok: 41.
- URLs: 34 unique; 6 could not be text-checked by script.

Flags by kind (a device can have several):

- recomputed lane differs from the label: 2 (DEV-023, DEV-052)
- evidence id missing or vendor/product mismatch: 1 (DEV-002)
- raw firmware changes the lane (version guard would differ): 2 (DEV-027, DEV-045)
- raw firmware doesn't parse (sim.guards grammar): 6 (DEV-002, DEV-027, DEV-042, DEV-045, DEV-058, DEV-059)
- cited lifecycle pattern doesn't fit the raw name: 2 (DEV-016, DEV-032)

URLs that need a human (open them in a browser):

- https://nuuo.com/wp-content/uploads/2023/03/NUUO-EOL-letter%EF%BC%BFNVRmini-2-and-NVRsolo-series.pdf: HTTP 200, PDF: not text-checked; open it and check by eye
- https://www.cisa.gov/known-exploited-vulnerabilities-catalog: HTTP 403: the site blocks scripts; needs human check in a browser
- https://www.cisco.com/c/en/us/products/collateral/routers/small-business-rv-series-routers/eos-eol-notice-c51-743069.html: HTTP 403: the site blocks scripts; needs human check in a browser
- https://www.cisco.com/c/en/us/products/collateral/routers/small-business-rv-series-routers/eos-eol-notice-c51-743070.html: HTTP 403: the site blocks scripts; needs human check in a browser
- https://www.cisco.com/c/en/us/products/collateral/routers/small-business-rv-series-routers/small-business-rv340-rv345-series-eol.html: HTTP 403: the site blocks scripts; needs human check in a browser
- https://www.cisco.com/c/en/us/products/collateral/security/asa-5500-series-next-generation-firewalls/eos-eol-notice-c51-744797.html: HTTP 403: the site blocks scripts; needs human check in a browser

Strings not found on any of the device's text pages: 8 distinct (the page may render with JavaScript, use other wording, or the value may come from another page).

## How to read this

- **Ordered by risk**: highest flag severity first (lane / evidence 3, firmware changes the lane 2, firmware doesn't parse / pattern / source 1), then device exposure (do_not_touch, then internet-facing high/critical, then criticality), then device_id.
- **Recomputed lane** uses the label's vendor/product/version, the cited lifecycle row (or the most specific matching row when none is cited) and KEV entries with the same vendorProject/product, with the contract tie-break: unknown, retire, patch, fine.
- **Firmware lane** repeats that with the inventory's raw `firmware_version_raw`, which is what the Checker's version guard compares. Versions use `sim/guards.py` only.
- **Source**: `ok` only when every URL returned a text page and every expected string (fixed_version on the device's train, support / EOL date in common formats, and phrases quoted in the notes) was found on at least one of them. Quotes found in the device's KEV entries count as found.

## Devices

| # | Device | Label lane | Recomputed | Mechanical | Source | Why |
|---|---|---|---|---|---|---|
| 1 | DEV-002 | retire | retire | **flag** | ok | evidence CVE-2025-22457 is KEV 'Ivanti / Connect Secure, Policy Secure, and ZTA Gateways', but the label says 'Ivanti / Pulse Connect Secure'; firmware '9.1R18' does not parse (sim.guards grammar); label version is '9.1R18' |
| 2 | DEV-023 | unknown | fine | **flag** | ok | label lane unknown, recomputed fine: no KEV entry for this vendor/product and not past support |
| 3 | DEV-052 | fine | patch | **flag** | ok | label lane fine, recomputed patch: 12.5.15 is below fixed 12.11.4 (LC-029) |
| 4 | DEV-045 | patch | patch | **flag** | ok | firmware 'NS14.1 38.53' does not parse (sim.guards grammar); label version is '14.1-38.53'; with the raw firmware 'NS14.1 38.53' the lane would be unknown (version 'NS14.1 38.53' does not parse (sim.guards grammar)), not patch: the Checker's version guard reads the raw firmware |
| 5 | DEV-027 | patch | patch | **flag** | ok | firmware 'ROS 7.24.1' does not parse (sim.guards grammar); label version is '7.24.1'; with the raw firmware 'ROS 7.24.1' the lane would be unknown (firmware 'ROS 7.24.1' does not parse, so its release train among fixed versions 7.24.3;7.23.6 can't be identified), not patch: the Checker's version guard reads the raw firmware |
| 6 | DEV-039 | retire | retire | **pass** | needs human | -<br>Source: last_security_support_date '2026-08-31' unchecked; eol_date '2021-08-02' unchecked; quote 'Last Date of Support: HW' unchecked; www.cisco.com needs human |
| 7 | DEV-059 | retire | retire | **flag** | ok | firmware '1.06B01' does not parse (sim.guards grammar); label version is '1.06B01' |
| 8 | DEV-030 | unknown | unknown | **pass** | needs human | -<br>Source: www.cisa.gov needs human |
| 9 | DEV-040 | unknown | unknown | **pass** | needs human | -<br>Source: www.cisco.com needs human |
| 10 | DEV-046 | fine | fine | **pass** | needs human | -<br>Source: www.cisa.gov needs human |
| 11 | DEV-005 | fine | fine | **pass** | needs human | -<br>Source: www.cisa.gov needs human |
| 12 | DEV-011 | retire | retire | **pass** | needs human | -<br>Source: last_security_support_date '2024-07-15' not found; eol_date '2023-07-15' not found |
| 13 | DEV-016 | retire | retire | **flag** | needs human | LC-010 model_pattern 'Vigor300B*' does not match the raw device name; the identity is a human reading of a messy name, check it<br>Source: last_security_support_date '2026-04-22' not found |
| 14 | DEV-019 | retire | retire | **pass** | needs human | -<br>Source: last_security_support_date '2025-01-31' unchecked; eol_date '2020-01-30' unchecked; quote 'Last Date of Support: HW' unchecked; quote 'has not released and will not release software updates' unchecked; www.cisco.com needs human |
| 15 | DEV-020 | retire | retire | **pass** | needs human | -<br>Source: last_security_support_date '2025-01-31' unchecked; eol_date '2020-01-30' unchecked; quote 'Last Date of Support: HW' unchecked; www.cisco.com needs human |
| 16 | DEV-028 | fine | fine | **pass** | needs human | -<br>Source: nuuo.com needs human; www.cisa.gov needs human |
| 17 | DEV-041 | retire | retire | **pass** | needs human | -<br>Source: last_security_support_date '2022-01-01' unchecked; eol_date '2020-03-15' unchecked; nuuo.com needs human |
| 18 | DEV-042 | retire | retire | **flag** | ok | firmware '1.05b03' does not parse (sim.guards grammar); label version is '1.05b03' |
| 19 | DEV-054 | retire | retire | **pass** | needs human | -<br>Source: last_security_support_date '2022-12-31' not found; eol_date '2024-05-16' not found |
| 20 | DEV-055 | fine | fine | **pass** | needs human | -<br>Source: www.cisa.gov needs human |
| 21 | DEV-057 | retire | retire | **pass** | needs human | -<br>Source: last_security_support_date '2025-03-31' not found; eol_date '2025-03-31' not found; quote 'Sophos will not provide patches or fixes' not found |
| 22 | DEV-026 | fine | fine | **pass** | needs human | -<br>Source: www.cisa.gov needs human |
| 23 | DEV-029 | fine | fine | **pass** | needs human | -<br>Source: www.cisa.gov needs human |
| 24 | DEV-032 | retire | retire | **flag** | ok | LC-006 model_pattern 'DNS-320L*' does not match the raw device name; the identity is a human reading of a messy name, check it |
| 25 | DEV-044 | retire | retire | **pass** | needs human | -<br>Source: last_security_support_date '2022-10-28' unchecked; eol_date '2021-10-28' unchecked; www.cisco.com needs human |
| 26 | DEV-053 | unknown | unknown | **pass** | needs human | -<br>Source: www.cisa.gov needs human |
| 27 | DEV-058 | retire | retire | **flag** | ok | firmware '1.05B03' does not parse (sim.guards grammar); label version is '1.05B03' |
| 28 | DEV-060 | fine | fine | **pass** | needs human | -<br>Source: www.cisa.gov needs human |
| 29 | DEV-004 | patch | patch | **pass** | ok | - |
| 30 | DEV-010 | retire | retire | **pass** | ok | - |
| 31 | DEV-008 | fine | fine | **pass** | ok | - |
| 32 | DEV-049 | patch | patch | **pass** | ok | - |
| 33 | DEV-001 | patch | patch | **pass** | ok | - |
| 34 | DEV-014 | patch | patch | **pass** | ok | - |
| 35 | DEV-021 | patch | patch | **pass** | ok | - |
| 36 | DEV-031 | retire | retire | **pass** | ok | - |
| 37 | DEV-033 | patch | patch | **pass** | ok | - |
| 38 | DEV-034 | patch | patch | **pass** | ok | - |
| 39 | DEV-037 | patch | patch | **pass** | ok | - |
| 40 | DEV-050 | patch | patch | **pass** | ok | - |
| 41 | DEV-047 | patch | patch | **pass** | ok | - |
| 42 | DEV-006 | fine | fine | **pass** | ok | - |
| 43 | DEV-022 | fine | fine | **pass** | ok | - |
| 44 | DEV-007 | patch | patch | **pass** | ok | - |
| 45 | DEV-009 | patch | patch | **pass** | ok | - |
| 46 | DEV-012 | retire | retire | **pass** | ok | - |
| 47 | DEV-015 | retire | retire | **pass** | ok | - |
| 48 | DEV-017 | fine | fine | **pass** | ok | - |
| 49 | DEV-018 | patch | patch | **pass** | ok | - |
| 50 | DEV-024 | patch | patch | **pass** | ok | - |
| 51 | DEV-035 | fine | fine | **pass** | ok | - |
| 52 | DEV-036 | retire | retire | **pass** | ok | - |
| 53 | DEV-038 | fine | fine | **pass** | ok | - |
| 54 | DEV-043 | patch | patch | **pass** | ok | - |
| 55 | DEV-051 | fine | fine | **pass** | ok | - |
| 56 | DEV-003 | retire | retire | **pass** | ok | - |
| 57 | DEV-013 | fine | fine | **pass** | ok | - |
| 58 | DEV-025 | patch | patch | **pass** | ok | - |
| 59 | DEV-048 | patch | patch | **pass** | ok | - |
| 60 | DEV-056 | patch | patch | **pass** | ok | - |

## URL results

| URL | HTTP | Result | Note |
|---|---|---|---|
| https://community.fortinet.com/fortigate-3/technical-tip-fortios-end-of-support-change-for-fortios-v7-4-and-v7-6-224876 | 200 | text | HTTP 200, text page |
| https://community.fortinet.com/t5/FortiGate/Technical-Tip-Extended-Support-for-FortiOS-7-0-FIPS-CC-Certified/ta-p/407617 | 200 | text | HTTP 200, text page |
| https://community.sophos.com/sophos-xg-firewall/b/blog/posts/xg-series-hardware-end-of-life-eol-frequently-asked-questions | 200 | text | HTTP 200, text page |
| https://fortiguard.fortinet.com/psirt/FG-IR-25-934 | 200 | text | HTTP 200, text page |
| https://mikrotik.com/supportsec/september-2026-vulnerability | 200 | text | HTTP 200, text page |
| https://nuuo.com/wp-content/uploads/2023/03/NUUO-EOL-letter%EF%BC%BFNVRmini-2-and-NVRsolo-series.pdf | 200 | needs_human | HTTP 200, PDF: not text-checked; open it and check by eye |
| https://psirt.watchguard.com/CVE-2025-14733 | 200 | text | HTTP 200, text page |
| https://psirt.watchguard.com/CVE-2025-9242 | 200 | text | HTTP 200, text page |
| https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-asaftd-tunnel-dos-s6mgkb75 | 200 | text | HTTP 200, text page |
| https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-asaftd-vpn-dos-dzv4mQFF | 200 | text | HTTP 200, text page |
| https://sec.cloudapps.cisco.com/security/center/resources/asa_ftd_continued_attacks | 200 | text | HTTP 200, text page |
| https://security.paloaltonetworks.com/CVE-2025-0108 | 200 | text | HTTP 200, text page |
| https://security.paloaltonetworks.com/CVE-2025-0111 | 200 | text | HTTP 200, text page |
| https://security.paloaltonetworks.com/CVE-2026-0257 | 200 | text | HTTP 200, text page |
| https://security.paloaltonetworks.com/CVE-2026-0300 | 200 | text | HTTP 200, text page |
| https://security.paloaltonetworks.com/CVE-2026-0322 | 200 | text | HTTP 200, text page |
| https://support.citrix.com/external/article/CTX694788/netscaler-adc-and-netscaler-gateway-secu.html | 200 | text | HTTP 200, text page |
| https://supportannouncement.us.dlink.com/announcement/publication.aspx?name=SAP10295 | 200 | text | HTTP 200, text page |
| https://supportannouncement.us.dlink.com/security/publication.aspx?name=SAP10371 | 200 | text | HTTP 200, text page |
| https://supportannouncement.us.dlink.com/security/publication.aspx?name=SAP10393 | 200 | text | HTTP 200, text page |
| https://supportannouncement.us.dlink.com/security/publication.aspx?name=sap10383 | 200 | text | HTTP 200, text page |
| https://www.cisa.gov/known-exploited-vulnerabilities-catalog | 403 | needs_human | HTTP 403: the site blocks scripts; needs human check in a browser |
| https://www.cisco.com/c/en/us/products/collateral/routers/small-business-rv-series-routers/eos-eol-notice-c51-743069.html | 403 | needs_human | HTTP 403: the site blocks scripts; needs human check in a browser |
| https://www.cisco.com/c/en/us/products/collateral/routers/small-business-rv-series-routers/eos-eol-notice-c51-743070.html | 403 | needs_human | HTTP 403: the site blocks scripts; needs human check in a browser |
| https://www.cisco.com/c/en/us/products/collateral/routers/small-business-rv-series-routers/small-business-rv340-rv345-series-eol.html | 403 | needs_human | HTTP 403: the site blocks scripts; needs human check in a browser |
| https://www.cisco.com/c/en/us/products/collateral/security/asa-5500-series-next-generation-firewalls/eos-eol-notice-c51-744797.html | 403 | needs_human | HTTP 403: the site blocks scripts; needs human check in a browser |
| https://www.citrix.com/support/product-lifecycle/legacy-product-matrix.html | 200 | text | HTTP 200, text page |
| https://www.draytek.com/support/product-lifecycle/ | 200 | text | HTTP 200, text page |
| https://www.edimax.com/edimax/post/post/data/edimax/global/press_releases/4801 | 200 | text | HTTP 200, text page |
| https://www.fortiguard.com/psirt/FG-IR-24-015 | 200 | text | HTTP 200, text page |
| https://www.ivanti.com/blog/security-update-pulse-connect-secure-ivanti-connect-secure-policy-secure-and-neurons-for-zta-gateways | 200 | text | HTTP 200, text page |
| https://www.paloaltonetworks.com/services/support/end-of-life-announcements/end-of-life-summary | 200 | text | HTTP 200, text page |
| https://www.sonicwall.com/support/product-lifecycle-tables/Secure-Mobile-Access-100-Series/Hardware | 200 | text | HTTP 200, text page |
| https://www.zyxel.com/global/en/support/end-of-life | 200 | text | HTTP 200, text page |

## What this cannot verify

- Whether a version string on the page applies to this exact model and train (a human reads the table).
- Pages rendered by JavaScript, PDFs and pages that block scripts: listed above for a browser check.
- KEV CVEs that a note says were not re-checked (they are named in the source notes).
- Synthetic firmware builds: they exist only in this inventory.
