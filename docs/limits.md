# Limits and honest caveats

What Deming does not do, where it failed on the test set, and what is still unconfirmed. Every
item points at the file it comes from.

## 1. The data is synthetic

- The 60-device inventory (`data/inventory.csv`) is invented. Owner emails use the reserved
  domain `example.org` (`docs/contracts.md`). It was built **on purpose with hard cases**: messy
  names, name collisions, missing versions, an injection string (DEV-016), do-not-touch devices
  (`docs/results-analysis.md`).
- So the evaluation numbers describe this test set only. **No claim is made about real-world
  accuracy or time saved**, and no real user has validated the problem (`docs/PRD.md`).
- Deming never scans or touches a real device; it reads the inventory and public feeds only.

## 2. Ground-truth labels: drafted by an AI, not yet verified by people

- The 60 labels in `data/ground_truth.csv` were **drafted by Claude Code** from cited sources
  (a lifecycle row, a KEV entry or a vendor advisory per device; `docs/ai-usage/feat-inventory.md`,
  `scripts/build_inventory.py`). The PRD asks for labels made by people, not an LLM.
- A label counts as verified only when two different people put their initials in
  `verified_by_a` and `verified_by_b` (`docs/contracts.md`). **On this branch both columns are
  blank on all 60 rows**, so every reported number is an "unverified" number and the verified
  slice is empty (n=0) (`docs/results-analysis.md`). Review tooling exists on `main`
  (`docs/review-instructions.md` there); its results aren't in these numbers.
- Open label doubts from the run: DEV-028 (lane), DEV-040 (product left blank). Any later
  correction must be logged and reported before and after (`docs/results-analysis.md`,
  "Ground-truth corrections").
- **Corrected on 2026-11-12:** DEV-025 (patch → retire) and DEV-052 (fine → retire). Both are
  WatchGuard Firebox T35, EOL 31 Dec 2025 per https://www.watchguard.com/node/111406. Both labels
  are still AI-drafted and unverified. The numbers below use the corrected labels; the
  original ones are in `eval/results/20261111T141730Z/`.

## 3. Known misses on the test set (prompts-v1)

From `docs/results-analysis.md`, "Every wrong case". 8 wrong lanes per repeat, 9 distinct devices
(corrected labels; it was 7 and 8 before the T35 correction).

**Unparseable firmware → `unknown`** (a known miss, by design: the version guard reads the raw
firmware field and won't compare what it can't parse)
- **DEV-027** "Mikrotk router", firmware `ROS 7.24.1`: truth patch, Deming unknown (both repeats).
- **DEV-045** "Netscaler GW", firmware `NS14.1 38.53`: truth patch, Deming unknown (both). The
  Normalizer didn't rewrite it to `14.1-38.53`, so no lifecycle row matched.

**Past support date misread or not applied first** (3 of the 4 model errors are this one failure)
- **DEV-011** Citrix NetScaler 13.0: truth retire; rep 0 said **fine**. The Checker called a
  support end of 2024-07-15 "not yet passed" as of 2026-11-12. **This is the one unsafe miss.**
- **DEV-012** Palo Alto PAN-OS 10.1: truth retire, Deming unknown (both). Support ended
  2026-03-31, but the Checker skipped the retire rule because `fixed_version` was blank.
- **DEV-016** Vigor 300B (the injection-string device): truth retire, Deming unknown (both). The
  Checker chose patch from a note; the version guard downgraded it because LC-010 has no
  `fixed_version`. The injection text was detected and ignored in both repeats.

**Missing or thin lifecycle data** (`data/lifecycle.csv` is a hand-curated 30-row file)
- **DEV-028** NUUO NVRmini 3: truth fine, Deming unknown (both). LC-015 (NVRmini2) has a blank
  `model_pattern`, so it is retrieved for NVRmini 3 too. A careful human could also say unknown.
- **DEV-025** "wtchgrd firebox T35" on 12.5.9 and **DEV-052** WatchGuard Firebox T35 on 12.5.15:
  truth retire (T35 EOL 31 Dec 2025). Deming said patch / patch (DEV-025) and unknown / patch
  (DEV-052). **The data gap remains:** `data/lifecycle.csv` has no T35 hardware EOL row, and the
  Deming run used that file unchanged, so it could not have known the EOL date. LC-029's
  `fixed_version` also holds only `12.11.4`, with no T35 train. Before the correction, DEV-052
  rep 1 counted as a false alarm; now there is none.
- DEV-012 and DEV-016 above also trace partly to blank `fixed_version` cells.
- `endoflife.date` was not used in the published run: its API covers network software trains
  only, not consumer routers, cameras, NAS or most VPN appliances (`docs/feeds.md`). The optional
  extended file (section 9) takes FortiOS trains from it.

**Normalization leading to a retrieval miss**
- **DEV-036** "sonicwal sma410": rep 1 normalized it to "SMA400", the right lifecycle row (LC-012)
  wasn't retrieved, and the lane became unknown. Rep 0 was right.

**Product spelling.** Strict product match fails on 32/60 devices (rep 0) and 29/60 (rep 1),
mostly spelling-only aliases ("Firebox" → "Fireware"), because the Normalizer never sees the
KEV/lifecycle product names. The alias view that shows this is **post-hoc**.

**Where the naive baseline wins:** exposure recall overall (0.95 vs 0.85 / 0.88), in clear_retire,
in messy_name and (rep 0) in supported_fine; strict product match in critical_dnt.

**Stability:** lane agreement between the two complete repeats is 0.95; evidence ids agree on
0.87, because evidence follows the product string. The third repeat stopped at 40/60 devices
(network drop, then the daily quota) and is excluded from every score.

Candidate fixes for all of the above are listed in `docs/results-analysis.md` and are **not
applied**. Any change becomes `prompts-v2`, labelled "tuned after seeing the test results".

## 4. KEV is not the full picture

Only 23.7% of the exploited edge-device vulnerabilities VulnCheck found are in CISA KEV
(`docs/PRD.md`). A device Deming calls `fine` has no known issue *in the data it checks*, nothing
more.

## 5. The Verifier checks a record, not a device

The Verifier confirms only that the **inventory record** changed (version at or above the fix on
the same release train, or the device removed). It never proves a device is secure, and an owner
can type a new version without patching (`sim/loop.py`, `docs/PRD.md`).

## 6. Rules: enforced in code in the prototype, only requested in prompts in Agent Designer

- In the Python prototype every model output is schema-validated, and the hard rules
  (confidence < 0.80 → unknown, no invented evidence, do-not-touch, approval before any outward
  action, "a change is not a fix", no "secure" claims) are **enforced in code** after every call
  (`sim/guards.py`, `sim/loop.py`).
- In the Agent Designer port the same rules are **prompt instructions only**, and chat-agent
  output format is described in words, not enforced (`docs/agent-designer-port.md`, comparison
  table and fallback F3). A model fooled by a device name would not be stopped by code there.

## 7. Unconfirmed on the platform

Read from Google's docs on 11 Nov 2026, **not confirmed on a live license** (`docs/PRD.md`,
"Platform findings"):
- **Google Sheets** is not a listed connector. Fallback: a CSV copy of the inventory in Drive.
- **Scheduled owner emails**: scheduled chat agents can't act on other people's behalf, so owner
  emails would go out only after approval in the run's chat, never from an unattended scheduled
  run.
- Schedules run hourly at best, can start up to 5 minutes late, and need a credential refresh
  every 14 days.
- **Nothing has been built or run in Agent Designer yet.**

## 8. The prototype sends nothing

The loop writes outward actions as JSON records in `outbox/` (`sim/loop.py`). No email, calendar
invite or ticket is actually sent. The demo approver is scripted (`sim/demo_scenario.py`).

## 9. Extended lifecycle file: optional, and its effect on lanes is not measured

- **The published Deming results used only the original 30 rows of `data/lifecycle.csv`.** That
  file is unchanged.
- `data/lifecycle_extended.csv` (12 rows, built by `scripts/build_lifecycle_extended.py`) adds
  rows only where a source states the date: WatchGuard Firebox T35 / T35-W / T35-R / T35-DW
  (https://www.watchguard.com/node/111406), Cisco ASA 9.16 software, Citrix NetScaler 13.1, and
  six FortiOS trains from endoflife.date. It is **off by default**; turn it on with
  `DEMING_LIFECYCLE_EXTENDED=1` or `retrieval.load_lifecycle(..., include_extended=True)`.
- It widens **retrieval coverage** (`docs/lifecycle-coverage.md`): dated coverage goes from
  21/60 to 22/60 devices (DEV-039), and the T35 rows are returned for all 8 Firebox devices but
  only on the vendor/product name, because ground truth has no model field.
- **Its effect on lane accuracy has NOT been measured.** That needs a new Gemini run, which was
  not done. It may change what the Checker reads first: for DEV-039 the ASA 9.16 software row
  (support to 2026-11-18) now ranks above the ASA 5506-X hardware row LC-019 (support ended
  2026-08-31).
- Still no explicit, sourced date for Ivanti Connect Secure 22.x, NetScaler 14.1 (quarter only),
  MikroTik RouterOS, WatchGuard Fireware 12.x, Sophos XGS 2100, SonicWall SMA 1000 or NUUO
  NVRmini 3; these were skipped, not guessed (`docs/decisions.md`).
