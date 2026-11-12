# Results analysis: full evaluation run, prompts-v1

**Read this first.**
- The 60-device inventory is **synthetic**, and it was **built on purpose with hard cases**:
  messy names, name collisions, missing versions, an injection string, do-not-touch devices.
  These numbers describe this test set only. **No claim is made about real-world accuracy or
  time saved.**
- **All 60 ground-truth rows are unverified.** None has both `verified_by_a` and
  `verified_by_b`. The ground truth is still a draft, so every number below is an "unverified"
  number. The "verified" slice is empty (n=0).
- Prompts, schemas, guards and data were frozen at tag `prompts-v1` (`docs/prompts-freeze.md`)
  before this run. Nothing was changed to fix a failure. Candidate fixes are listed at the end
  and have **not** been applied.
- **Labels corrected on 2026-11-12 (after the run).** DEV-025 and DEV-052 are WatchGuard
  Firebox T35 units. WatchGuard's End of Life Policy (https://www.watchguard.com/node/111406)
  lists the T35 EOL date as 31 Dec 2025, which is before `as_of_date`. Their lanes changed
  patch → retire and fine → retire. The predictions were **not** re-run: the published Deming
  CSVs and `data/lifecycle.csv` are unchanged, and re-scoring made no API calls. The numbers
  below use the corrected labels. The scores on the old labels are kept in `eval/results/20261111T141730Z/`, and the
  re-scored ones are in `eval/results/20261112T152247Z/`. See "Ground-truth corrections" for the before/after table.

## Run

| Item | Value |
|---|---|
| Model | `gemini-3.5-flash-lite`, temperature 0, structured JSON output |
| `as_of_date` | 2026-11-12 (`data/ground_truth_meta.json`) |
| Settings | Settings tab defaults (`sim.loop.SETTINGS_DEFAULTS`) |
| Driver | `eval/full_run.py` (wraps `eval/live_fixture_run.py`), one call at a time, response cache on, 429/503 retries |
| Real API calls | about 500: 495 in the first attempt, plus about 5 in the resume before the quota stop. 132 retries on 429/503 in the first attempt. 0 schema-validation failures |
| Run time | 3,137 s of active run time (about 52 min) for the first attempt. The process then hung for about 5 h after a network drop; that time is not run time |
| Repeat 0 | 60/60 devices: `eval/runs/deming-20261111T075938Z/deming.csv` |
| Repeat 1 | 60/60 devices: `eval/runs/deming-20261111T081026Z/deming.csv` |
| Repeat 2 | **Incomplete, excluded from every score.** The network dropped at DEV-039 (`getaddrinfo failed`), and DEV-039 to DEV-060 were written as error rows. A resume from the response cache finished DEV-039 and DEV-040. It then hit a 429 naming the per-day quota on DEV-041 and stopped, as the run rules require. So 40/60 devices have a valid third repeat |
| Baseline | `eval/runs/baseline-20261111T075945Z/baseline.csv` (offline, run after the freeze) |
| Scoring | Corrected labels: `eval/results/20261112T152247Z/` (same files). Original labels: `eval/run_eval.py` → `eval/results/20261111T141730Z/report.md` and `failures.csv`. Per-repeat, per-group and post-hoc numbers come from `eval/offline_analysis.py` → `offline_analysis.md` / `.json` in the same folder. **No API calls** were made for scoring or analysis. The analysis replays responses from the cache with a client that raises on any call, and that replay matches the published repeat 0/1 CSVs exactly (0 mismatches) |

`report.md` computes its primary metrics on the first Deming run (repeat 0). This document
reports repeats 0 and 1 side by side.

## Headline (all 60, unverified)

Strict match: vendor/product/version are compared as exact strings (case-insensitive, trimmed)
against the ground-truth canonical names. **Strict product match is the headline
normalization number.**

| Metric | Baseline | Deming rep 0 | Deming rep 1 |
|---|---|---|---|
| **Product match (strict)** | **0.18** | **0.47** | **0.52** |
| Vendor match | 0.42 | 1.00 | 1.00 |
| Version match | 0.97 | 0.98 | 0.98 |
| Vendor+product+version all match | 0.18 | 0.47 | 0.52 |
| Lane accuracy | 0.30 (18/60; was 0.32) | 0.87 (52/60; was 0.88) | 0.87 (52/60; was 0.88) |
| Exposure precision (lane patch/retire) | 0.72 (was 0.70) | 1.00 | 1.00 (was 0.97) |
| Exposure recall | **0.95** (39/41) | 0.85 (35/41; was 0.88) | 0.88 (36/41) |
| Unknown rate | 0.00 | 0.17 (10/60) | 0.17 (10/60) |
| Unknown was right (precision) | n/a | 0.40 (4/10) | 0.40 (4/10) |
| Unknown recall (true unknowns caught) | 0.00 | 1.00 (4/4) | 1.00 (4/4) |

Lane confusion (truth → predicted), corrected labels. For the original labels, see
`eval/results/20261111T141730Z/offline_analysis.json`.

| Truth | Baseline | Deming rep 0 | Deming rep 1 |
|---|---|---|---|
| patch (19) | patch 17, fine 2 | patch 17, unknown 2 | patch 17, unknown 2 |
| retire (22) | patch 21, retire 1 | retire 17, unknown 3, patch 1, fine 1 | retire 17, unknown 3, patch 2 |
| fine (15) | patch 15 | fine 14, unknown 1 | fine 14, unknown 1 |
| unknown (4) | patch 4 | unknown 4 | unknown 4 |

### Unknown lane
- Deming sent 10/60 devices to `unknown` in each repeat. 4 of those 10 were right, and those 4
  are all the truly unknown devices (DEV-023, DEV-030, DEV-040, DEV-053).
- The other 6 were wrong but safe. No exposed device was called `fine` through an unknown, and
  every one of them lands in front of a human:
  - rep 0: DEV-012, DEV-016, DEV-027, DEV-028, DEV-045, DEV-052;
  - rep 1: DEV-012, DEV-016, DEV-027, DEV-028, DEV-036, DEV-045.
- The baseline never outputs `unknown`, by design.
- Deming made one unsafe miss: DEV-011 in rep 0 is a retire device it called `fine`. With
  the corrected labels it made no false alarm. DEV-052 in rep 1, counted as a false alarm
  before the correction, is now a retire device called `patch`: the lane is wrong, but the
  device is still flagged for action.

## Per group (unverified; verified n=0 in every group)

Every group is 100% unverified.

| Group (n) | Metric | Baseline | Rep 0 | Rep 1 |
|---|---|---|---|---|
| clear_patch (15) | product strict | 0.07 | 0.53 | 0.47 |
| | lane | 0.93 | 1.00 | 1.00 |
| | exposure recall | 0.93 | 1.00 | 1.00 |
| clear_retire (12) | product strict | 0.17 | 0.25 | 0.33 |
| | lane | 0.00 | 0.83 | 0.92 |
| | exposure recall | **1.00** | 0.83 | 0.92 |
| supported_fine (15) | product strict | 0.27 | 0.80 | 0.87 |
| | lane | 0.00 | 0.93 | 0.93 |
| | exposure recall (n=1, DEV-052) | 1.00 | 0.00 | 1.00 |
| messy_name (10) | product strict | 0.20 | 0.30 | 0.40 |
| | version | 0.80 | 0.90 | 0.90 |
| | lane | 0.20 (was 0.30) | 0.60 (was 0.70) | 0.50 (was 0.60) |
| | exposure recall | **0.88** | 0.62 | 0.50 |
| | unknown rate / unknown right | 0.00 / n/a | 0.50 / 0.40 | 0.60 / 0.33 |
| name_collision (4) | product strict | 0.00 | 0.25 | 0.50 |
| | lane | 0.00 | 0.75 | 0.75 |
| critical_dnt (4) | product strict | **0.50** | 0.25 | 0.25 |
| | lane | 0.50 | 1.00 | 1.00 |

Full per-group tables, with all metrics for both repeats, are in
`eval/results/20261112T152247Z/offline_analysis.md` (corrected labels) and `eval/results/20261111T141730Z/offline_analysis.md` (original
labels). The supported_fine group name was kept for DEV-052, so that group now holds one retire
device.

## Where the baseline ties or wins

Stated plainly:
- **Exposure recall, overall:** the baseline wins, 0.95 vs 0.85 / 0.88. It calls almost
  everything `patch`, so it rarely misses an exposed device. The cost is that it flags all 15
  fine devices and all 4 unknown ones, giving exposure precision 0.72 and lane accuracy 0.30.
- **Exposure recall, supported_fine:** the baseline wins against rep 0 (1.00 vs 0.00 on the
  single action device, DEV-052).
- **Exposure recall, clear_retire:** the baseline wins, 1.00 vs 0.83 / 0.92.
- **Exposure recall, messy_name:** the baseline wins, 0.88 vs 0.62 / 0.50. Deming sends hard
  messy devices to `unknown` instead.
- **Strict product, critical_dnt:** the baseline wins, 0.50 vs 0.25, and the same on all three
  fields together. Deming wrote "DIR-859" for "DIR-859 Router" and "Adaptive Security Appliance
  Software" for "Adaptive Security Appliance (ASA)".
- **Ties:**
  - version match in clear_patch, clear_retire, critical_dnt and name_collision (1.00 each);
  - exposure precision in clear_patch, clear_retire, critical_dnt and messy_name (1.00 each);
  - exposure recall in critical_dnt and name_collision (1.00 each).
- **Version match overall** is close to a tie (0.97 vs 0.98). Both mostly copy the firmware
  field.

## Stability

Structured fields only (`eval/metrics.stability`, exact match after case-folding; evidence ids
compared as a set). Free text (reasons, message bodies) is reworded between repeats even at
temperature 0. It is not counted here.

**Two complete repeats (0 and 1), n=60:**

| Field | Lane | Vendor | Product | Version | Evidence ids | All structured |
|---|---|---|---|---|---|---|
| Agreement | 0.95 (57/60) | 1.00 | 0.80 | 1.00 | 0.87 | 0.73 |

- **Lane changed** on DEV-011 (fine → retire), DEV-036 (retire → unknown) and DEV-052
  (unknown → patch).
- **Evidence-id changes** follow product-name changes. Evidence is filled by code from the
  retrieval candidates, and a different product string retrieves a different KEV set:
  DEV-011, DEV-014, DEV-019, DEV-034, DEV-036, DEV-041, DEV-052, DEV-057.

**Footnote: three repeats on DEV-001 to DEV-040 (n=40).** Repeat 2 exists only for these
devices. Its values come from the response cache, not from the error-row CSV.

| Field | Lane | Vendor | Product | Version | Evidence ids | All structured |
|---|---|---|---|---|---|---|
| Agreement (3 repeats) | 0.95 | 1.00 | 0.80 | 1.00 | 0.82 | 0.68 |

- Lane changes across 3 repeats: DEV-011 (fine/retire/fine) and DEV-036 (retire/unknown/retire).
- This subset covers only 40 devices, and they aren't a random sample (they are the first 40 ids).

## Every wrong case, categorised

Categories, as requested:
- **N**: normalization / product spelling.
- **R**: retrieval miss.
- **V**: unparseable version → unknown (a known miss, by design).
- **M**: wrong lane from the model.
- **G**: ground-truth doubt.

The lane cause for each case was read from the cached Normalizer/Checker outputs, the
retrieval candidates and the guard notes.

### Wrong lane (8 per repeat; 9 distinct devices; corrected labels)

Before the label correction this was 7 per repeat across 8 distinct devices. DEV-025 is new on
the list, and DEV-052 changed from fine to retire.

| Device | Group | Truth | Rep 0 | Rep 1 | Category | What happened |
|---|---|---|---|---|---|---|
| DEV-011 | clear_retire | retire | **fine** | retire | M | Rep 0: the Checker said LC-018's support end (2024-07-15) was "not yet passed" as of 2026-11-12, then reasoned from the CVE fix build. It misread a past date. This is the one unsafe miss (retire → fine) |
| DEV-012 | clear_retire | retire | unknown | unknown | M | LC-017 (PAN-OS 10.1) support ended 2026-03-31, which has passed. The Checker skipped the retire rule and went to `unknown` because the `fixed_version` was blank. The contract tie-break puts retire before patch |
| DEV-016 | messy_name | retire | unknown | unknown | M | LC-010 (Vigor300B) security support ended 2026-04-22. The Checker chose `patch`, citing "fixed in 1.5.1.5" from LC-010's notes. The version guard downgraded it to `unknown` because LC-010's `fixed_version` column is blank. The injection text in the name was detected and ignored in both repeats |
| DEV-027 | messy_name | patch | unknown | unknown | V | Firmware `ROS 7.24.1` doesn't parse. The Normalizer extracted `7.24.1`, but the version guard reads the raw firmware field, so the patch went to `unknown` |
| DEV-028 | name_collision | fine | unknown | unknown | G (+ data) | NVRmini 3. LC-015 (NVRmini2) has a **blank `model_pattern`**, so it is retrieved for NVRmini 3 too. The Checker then refused to decide. The truth says `fine` because NVRmini 3 is the named replacement and has no KEV entry. A careful human could also say `unknown` with no version given |
| DEV-036 | messy_name | retire | retire | **unknown** | N → R | Rep 1: "sonicwal sma410" was normalized to product "Secure Mobile Access", model "SMA400". LC-012 wasn't retrieved; unrelated Ivanti/Cisco candidates came back instead. Rep 0 got LC-012 and was right |
| DEV-045 | messy_name | patch | unknown | unknown | V (+ N) | Firmware `NS14.1 38.53`. The Normalizer kept it as-is instead of `14.1-38.53`. It doesn't parse and matches no LC-023 `14.1*` row, so there was no lifecycle candidate and the result was `unknown` |
| DEV-025 | messy_name | retire (was patch) | patch | patch | D | "wtchgrd firebox T35" on 12.5.9. The run was right on the old label: below the T35 KEV fixes. But the T35 hardware reached EOL on 31 Dec 2025 (WatchGuard EOL policy), so retire wins. `data/lifecycle.csv` has no T35 hardware row, so Deming had no way to see the EOL date |
| DEV-052 | supported_fine | retire (was fine) | unknown | patch | D (+ M) | WatchGuard T35 on 12.5.15. EOL 31 Dec 2025, as for DEV-025, and missing from the lifecycle data in the same way. Rep 0 called the T35 builds ambiguous (`unknown`). Rep 1 claimed 12.5.15 is below 12.5.13, which is wrong, but `patch` still flags the device. Before the correction, this rep 1 result was the one false alarm |

Lane-error causes, counted per device:
- M, wrong lane from the model: 3 (DEV-011, DEV-012, DEV-016).
- D, data gap: 2 (DEV-025, DEV-052). No T35 hardware EOL row in `data/lifecycle.csv`; the run
  used that file unchanged.
- V, unparseable version: 2 (DEV-027, DEV-045).
- N → R, normalization leading to a retrieval miss: 1 (DEV-036).
- G, ground-truth doubt: 1 (DEV-028).

All three M cases (DEV-011, DEV-012, DEV-016) are the same failure: **the past
support date not being applied first**.

### Identity wrong but lane right (strict product mismatch)

Strict product match fails on 32 of 60 devices in rep 0 and 29 in rep 1. Most are
spelling-only: the Normalizer never sees the KEV/lifecycle product names, so it writes the
marketing name.

| Category | Devices | Example (truth → predicted) |
|---|---|---|
| N, spelling-only alias of the right product | DEV-003, 004, 009, 011, 013, 016, 017, 018, 019, 020, 021, 024, 030, 031, 032, 034, 037, 039, 041, 042, 044, 045, 049, 050, 051, 054, 059 | "Firebox" → "Fireware"; "Connect Secure, Policy Secure, and ZTA Gateways" → "Connect Secure"; "Multiple NAS Devices" → "DNS-325 ShareCenter"; "Vigor Routers" → "Vigor300B" |
| N, wrong product line | DEV-002 (both repeats), DEV-036 (both) | DEV-002: "Pulse Connect Secure" (the 9.1R18 line) → "Connect Secure", though the lane was still right (retire). DEV-036: "SMA100 Appliances" → "SMA 400 Series" / "Secure Mobile Access" |
| N, generic product word | DEV-023 rep 0 ("Firewall" for XGS 2100), DEV-053 rep 0 ("Router", truth blank) | The lane was right (`unknown`) in both |
| N, renamed product | DEV-057 rep 0 | "XG Firewall" → "Sophos Firewall" (the later SFOS name). Not counted as an alias, to stay conservative |
| G, product label | DEV-040 | "ASA fw dc1": the truth leaves product blank, but the model wrote "Adaptive Security Appliance". The name does say ASA. The lane was right (`unknown`: no model, no version) |
| N, version | DEV-045 | `NS14.1 38.53` not rewritten to `14.1-38.53` (see above) |

There were no retrieval misses beyond DEV-036 rep 1. Wherever the product was a spelling-only
alias, the right lifecycle row was still retrieved.

The baseline's errors are listed row by row in `failures.csv` (57 rows: 33 lane+identity, 16
identity, 8 lane). The pattern is a fuzzy match to the wrong vendor (35 vendor mismatches, e.g.
MikroTik → "Looking Glass", Palo Alto → "Sophos"). It ignores version and never says retire for
most end-of-life devices.

## POST-HOC view: vendor/product after normalising aliases

**This view was defined after seeing the results above.** It is not the headline and must not
be quoted without this label.

The alias table is `ALIASES` in `eval/offline_analysis.py`. It is applied identically to both
systems. It accepts only names for the same product line:
- the OS name for the device ("Fireware" for Firebox);
- a model inside a KEV family ("USG60" for Zyxel "Multiple Firewalls");
- shortened forms of the KEV product name.

It rejects generic words ("Firewall", "Router", "Secure Mobile Access"), different product
lines ("Connect Secure" for the Pulse 9.1x line, "SMA 400 Series" for an SMA 410) and the XG →
"Sophos Firewall" rename.

| Slice | Baseline strict → alias | Rep 0 strict → alias | Rep 1 strict → alias |
|---|---|---|---|
| all (60) | 0.18 → 0.30 | 0.47 → 0.90 | 0.52 → 0.95 |
| clear_patch | 0.07 → 0.27 | 0.53 → 1.00 | 0.47 → 1.00 |
| clear_retire | 0.17 → 0.25 | 0.25 → 0.92 | 0.33 → 1.00 |
| supported_fine | 0.27 → 0.27 | 0.80 → 1.00 | 0.87 → 1.00 |
| messy_name | 0.20 → 0.40 | 0.30 → 0.70 | 0.40 → 0.80 |
| name_collision | 0.00 → 0.00 | 0.25 → 0.50 | 0.50 → 0.75 |
| critical_dnt | 0.50 → 0.75 | 0.25 → 1.00 | 0.25 → 1.00 |

These figures are vendor+product matches; vendor alone is 1.00 for Deming in every slice.
Remaining alias-view product misses:
- rep 0: DEV-002, DEV-023, DEV-036, DEV-040, DEV-053, DEV-057;
- rep 1: DEV-002, DEV-036, DEV-040.

The large gap between strict and alias matching is the evidence for candidate fix 1 below.

## Candidate prompts-v2 fixes (NOT applied)

None of these is applied. Any change becomes `prompts-v2`, and its results must be reported
with before/after numbers and labelled **"tuned after seeing the test results"**.

| # | Candidate fix | Type | Failing devices |
|---|---|---|---|
| 1 | Give the Normalizer the KEV `vendorProject`/`product` and lifecycle `product` names of the retrieval candidates, and ask it to pick the canonical spelling from that list (or blank). This needs a two-pass flow (retrieve on the first guess, then canonicalise). It also stabilises evidence ids, which follow the product string | prompt + pipeline | spelling-only: DEV-003, 004, 009, 011, 013, 016, 017, 018, 019, 020, 021, 024, 030, 031, 032, 034, 037, 039, 041, 042, 044, 045, 049, 050, 051, 054, 059. Wrong line: DEV-002, 036. Evidence instability: DEV-011, 014, 019, 034, 041, 057 |
| 2 | Checker: make step 1 explicit and mechanical. Compare `last_security_support_date` (else `eol_date`) with `as_of_date` *first*. If it is before `as_of_date`, the lane is `retire`, regardless of KEV, `fixed_version` or notes. Add a worked example with a past date. A deterministic code guard doing the same date comparison would be the stronger fix (guard change, also v2) | prompt (+ guard) | DEV-011 (rep 0), DEV-012, DEV-016 |
| 3 | Version guard: when the raw firmware doesn't parse but the Normalizer's `version` parses *and* appears verbatim inside the raw string, use the normalized version (e.g. `ROS 7.24.1` → `7.24.1`). Normalizer prompt: rewrite vendor formats such as `NS14.1 38.53` → `14.1-38.53` only when the mapping is unambiguous | guard + prompt | DEV-027, DEV-045 |
| 4 | Data: give LC-015 (NVRmini2) a `model_pattern` such as `NVRmini2*`, so it isn't retrieved for NVRmini 3. Also review the DEV-028 label (fine vs unknown) | data + ground truth | DEV-028 |
| 5 | Data: add a WatchGuard Firebox T35 / T35-W hardware row (EOL 2025-12-31, https://www.watchguard.com/node/111406), with T35-R / T35-DW kept separate (EOL 2027-03-01). LC-029 (Firebox 12.x) `fixed_version` should also carry the T15/T35 train (`12.5.15`) and the 12.11 fix for CVE-2025-14733 (`12.11.6`), instead of only `12.11.4` | data | DEV-025, DEV-052 |
| 6 | Normalizer: never return a generic word ("Firewall", "Router") as the product; leave it blank. Keep a model token such as "SMA410" exact (don't round it to "SMA400") | prompt | DEV-023 (rep 0), DEV-053 (rep 0), DEV-036 |

Fixes 4 and 5 change data, and fix 4 may change a label. Both fall under the ground-truth
correction rule below.

## Ground-truth corrections (rule)

Any ground-truth label corrected after this run must be logged with:
- the device id;
- the old and new values;
- the evidence (source URL or vendor notice) and who changed it.

The affected metrics must be reported **both before and after** the correction. A correction
must never be folded silently into a new headline. The open doubts from this run are DEV-028
(lane) and DEV-040 (product left blank). The DEV-052 doubt was settled by the correction below.

### Correction log

| Date | Device | Field | Old | New | Evidence | Changed by |
|---|---|---|---|---|---|---|
| 2026-11-12 | DEV-025 ("wtchgrd firebox T35", 12.5.9) | lane | patch | retire | WatchGuard End of Life Policy, https://www.watchguard.com/node/111406, checked 2026-11-12: Firebox T35 EOL 31 Dec 2025 | Claude Code (AI), at the user's request; still `ai_drafted_unverified` |
| 2026-11-12 | DEV-052 ("WatchGuard Firebox T35 (sports complex)", 12.5.15) | lane | fine | retire | same page, same date | same |

Both raw names say plain "T35". The same page gives T35-W the same EOL (31 Dec 2025), but
T35-R and T35-DW have EOL 1 Mar 2027 and would stay out of retire. Only the lane changed.
Vendor, product, version, evidence ids and group were kept, and `verified_by_a/b` stay blank.
The new note and the source URL are in `data/ground_truth.csv` and `docs/label-review.csv`.

**Data gap that remains:** `data/lifecycle.csv` still has no T35 hardware EOL row. The
published Deming run used that file, so these two labels are now outside what Deming could
have known. The retire labels rest on the vendor page, not on a lifecycle row
(`tests/test_inventory.py`, `VENDOR_EOL_OVERRIDES`).

### Lane accuracy before / after the correction (same predictions, no API calls)

| Slice (n) | Baseline before | Baseline after | Rep 0 before | Rep 0 after | Rep 1 before | Rep 1 after |
|---|---|---|---|---|---|---|
| all (60) | 0.32 (19) | 0.30 (18) | 0.88 (53) | 0.87 (52) | 0.88 (53) | 0.87 (52) |
| clear_patch (15) | 0.93 | 0.93 | 1.00 | 1.00 | 1.00 | 1.00 |
| clear_retire (12) | 0.00 | 0.00 | 0.83 | 0.83 | 0.92 | 0.92 |
| supported_fine (15) | 0.00 | 0.00 | 0.93 | 0.93 | 0.93 | 0.93 |
| messy_name (10) | 0.30 | 0.20 | 0.70 | 0.60 | 0.60 | 0.50 |
| name_collision (4) | 0.00 | 0.00 | 0.75 | 0.75 | 0.75 | 0.75 |
| critical_dnt (4) | 0.50 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |

Other metrics that moved (all 60): exposure precision went from 0.70 to 0.72 for the baseline,
and from 0.97 to 1.00 for rep 1. Exposure recall went from 0.875 to 0.85 for rep 0, and from
0.875 to 0.88 for rep 1. The baseline's exposure recall stayed at 0.95. supported_fine got an
exposure-recall value for the first time (n=1). Normalization metrics and stability did not
change. The supported_fine lane score didn't change because DEV-052 was wrong before
(unknown/patch vs fine) and is still wrong (unknown/patch vs retire).

Before: `eval/results/20261111T141730Z/offline_analysis.md` (reproduced byte-for-byte on 2026-11-12 from the old
labels). After: `eval/results/20261112T152247Z/report.md`, `failures.csv`, `offline_analysis.md`, `.json`. Commands:

```powershell
python eval/run_eval.py --inventory data/inventory.csv --pred `
  eval/runs/baseline-20261111T075945Z/baseline.csv `
  eval/runs/deming-20261111T075938Z/deming.csv eval/runs/deming-20261111T081026Z/deming.csv
python eval/offline_analysis.py --results eval/results/20261112T152247Z `
  --baseline eval/runs/baseline-20261111T075945Z/baseline.csv `
  --deming eval/runs/deming-20261111T075938Z/deming.csv eval/runs/deming-20261111T081026Z/deming.csv
# before: add  --ground-truth <old ground_truth.csv>  (git show f1791ae:data/ground_truth.csv)
```

## Published files

- **Predictions:**
  - `eval/runs/deming-20261111T075938Z/deming.csv` (rep 0)
  - `eval/runs/deming-20261111T081026Z/deming.csv` (rep 1)
  - `eval/runs/baseline-20261111T075945Z/baseline.csv`
- **Run logs:**
  - `eval/runs/full-run-20261111T075937Z.log` (first attempt; it includes the network-drop errors)
  - `eval/runs/full-run-20261111T141434Z.log` (cache resume and quota stop)
  - `eval/runs/live-summary-deming-20261111T082318Z.json` / `.md`: the runner's own summary.
    It **includes the incomplete repeat 2**, so its "lanes per repeat [53, 53, 33]" and its
    38-device stability lines are not the headline numbers.
- **Scores, corrected labels (2026-11-12):** `eval/results/20261112T152247Z/` (`report.md`, `failures.csv`,
  `offline_analysis.md`, `offline_analysis.json`)
- **Scores, original labels:** `eval/results/20261111T141730Z/` (same files; kept unchanged)
- **Not published:**
  - the repeat-2 CSV (`deming-20261111T082318Z`), which holds error rows;
  - two CSVs the resume rewrote from cache (`deming-20261111T141435Z`, `deming-20261111T141440Z`),
    which are identical in content to repeats 0 and 1.
