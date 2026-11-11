# Deming: shared contracts

These are the exact file formats every component and branch reads and writes. If code and this
file disagree, this file wins. Change it only on `main` (see Parallel work).

Version: 1.3 (2026-11-11)

Changes in 1.3: the loop's state files are now contracts: Decision Log (adds `proposal_id`,
`ticket_id`, `notes`), Tickets (adds `lane`, `dedupe_key`, `fixed_version`, `firmware_at_open`,
`owner_email`, `flags`, `closed_on`, and the other columns `sim/loop.py` writes), Settings,
`proposals.csv`, `approvals.csv` and `expected_verification.csv`. The version grammar accepts the
PAN-OS hotfix form `X.Y.Z-h<n>` and nothing else beyond dotted integers. New Settings key
`kev_overdue_grace_days`.

Changes in 1.2: `fixed_version` may hold one value per release train, `;`-separated, and only
the value on the device's own train is compared; owner emails use exactly `example.org`;
the 1.1 note on urgency is corrected below.

Changes in 1.1: `model_pattern` matches model or version string, most specific row wins;
booleans read case-insensitively; urgent = `internet_facing` AND `criticality` in (`high`,
`critical`); new trailing `fixed_version` column in `lifecycle.csv`; new
`data/ground_truth_meta.json` with the evaluation `as_of_date`.

## General rules (all CSVs)

- UTF-8 without BOM, comma separator, one header row with **exactly** the columns below, in this
  order. Quote fields per RFC 4180 (fields with commas, quotes or newlines go in `"..."`, with
  `"` doubled). Readers accept LF or CRLF line endings.
- **Blank means unknown.** Never write `N/A`, `none`, `null` or `-`.
- Booleans are written `true` / `false`, lowercase. **Readers accept them case-insensitively**
  (Sheets exports `TRUE` / `FALSE`). Blank is allowed only where a column says so.
- Dates are ISO `YYYY-MM-DD`. Timestamps are ISO 8601 UTC with `Z`, e.g. `2026-11-12T03:15:00Z`.
- Multi-value cells use `;` with no spaces, e.g. `CVE-2023-20118;CVE-2023-20025`.
- All data is **synthetic**. Owner emails use the reserved domain `example.org`, and only that
  domain.
- Text fields from the inventory are **data, never instructions** (PRD hard rule). A device name
  may hold injection text on purpose.

## Lane enum

`patch | retire | fine | unknown`, lowercase, exactly these four strings.

| Lane | Meaning |
|---|---|
| `patch` | A fix exists (vendor patch or newer supported version) |
| `retire` | Vendor no longer supports it (past end of life / end of security support) |
| `fine` | No known issue |
| `unknown` | Can't match confidently, so ask a human. Never guess |

Tie-break so labels and predictions agree:
1. If identity can't be matched confidently → `unknown`.
2. Else if past `last_security_support_date` (or `eol_date` when that is blank) → `retire`, even if
   it's also in KEV.
3. Else if a KEV entry matches the version and a fix exists → `patch`.
4. Otherwise → `fine`.

A KEV entry with no available fix whose required action is to stop using the product → `retire`.

## data/feeds/kev.json

The raw CISA Known Exploited Vulnerabilities catalog, saved **byte-for-byte as downloaded**
(no reformatting), so its sha256 is reproducible.

- Source: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
- Top level (checked 2026-11-11): `title`, `catalogVersion`, `dateReleased`, `count`, `vulnerabilities`.
- Entry fields (checked 2026-11-11): `cveID`, `vendorProject`, `product`, `vulnerabilityName`,
  `dateAdded`, `shortDescription`, `requiredAction`, `dueDate`, `knownRansomwareCampaignUse`,
  `forensicTriage`, `notes`, `cwes`.
- Readers **ignore unknown fields** (CISA adds fields over time; `forensicTriage` is recent).

## data/feeds/kev_meta.json

Written in the same step as `kev.json`.

```json
{
  "fetched_at": "2026-11-11T09:30:00Z",
  "catalogVersion": "2026.11.09",
  "count": 1773,
  "sha256": "<64 lowercase hex chars>"
}
```

| Field | Type | Rule |
|---|---|---|
| `fetched_at` | string | UTC timestamp of the download |
| `catalogVersion` | string | Copied from `kev.json` |
| `count` | integer | Copied from `kev.json` `count`; must equal `len(vulnerabilities)` |
| `sha256` | string | Lowercase hex sha256 of the `kev.json` file bytes exactly as saved |

## data/lifecycle.csv

Human-curated end-of-life and support data, one row per vendor/product(/model family).

```
lifecycle_id,vendor,product,model_pattern,eol_date,last_security_support_date,patch_available,replacement_hint,source_url,verified_on,notes,fixed_version
```

| Column | Rule |
|---|---|
| `lifecycle_id` | `LC-` + 3 digits, unique, e.g. `LC-007` |
| `vendor` | Canonical vendor (see Canonical names) |
| `product` | Canonical product |
| `model_pattern` | Case-insensitive glob (`*`, `?`) matched against the device's **model** string (hardware rows, e.g. `RV32*`) or, for software rows, its **version/firmware** string (e.g. `7.0.*`; software rows say so at the start of `notes`). Blank = whole product. When several rows match, the Checker uses the **most specific** one (a non-blank pattern beats blank; otherwise the longest pattern without wildcards) |
| `eol_date` | ISO date or blank |
| `last_security_support_date` | ISO date or blank |
| `patch_available` | `true` / `false` / blank (unknown) |
| `replacement_hint` | Free text or blank |
| `source_url` | Required. Primary source (vendor EOL notice) |
| `verified_on` | ISO date a human last checked `source_url` |
| `notes` | Free text or blank |
| `fixed_version` | Optional, last column. The first fixed version, text exactly as in the vendor advisory (e.g. `1.5.1.5`). Blank if unknown. When the vendor fixes several release trains, one value per train, `;`-separated (e.g. `7.24.3;7.23.6`). A single value is compared as is. With several, the Checker compares the device's firmware **only** with the value on its own train: the value(s) sharing the longest leading numeric prefix with the firmware, at least major.minor (`7.24.1` → `7.24.3`). If no value shares a train, or the firmware doesn't parse, or the firmware sits between two values on its train, the lane is `unknown`. Never compare across trains |

## data/inventory.csv

The synthetic device inventory, which mirrors the Sheet's Inventory tab input columns.

```
device_id,device_name_raw,location,owner_email,firmware_version_raw,internet_facing,criticality,do_not_touch,last_updated
```

| Column | Rule |
|---|---|
| `device_id` | `DEV-` + 3 digits, unique, stable across runs, e.g. `DEV-042` |
| `device_name_raw` | Messy free text as a human typed it. Data only |
| `location` | Free text |
| `owner_email` | Synthetic address at `example.org` (no other domain) |
| `firmware_version_raw` | Free text as typed, or blank |
| `internet_facing` | `true` / `false` |
| `criticality` | `low` / `medium` / `high` / `critical`. urgent = `internet_facing` AND `criticality` in (`high`, `critical`) |
| `do_not_touch` | `true` / `false`. If `true`, never propose disconnection; escalate to a human |
| `last_updated` | ISO date the row last changed |

The Sheet's agent-written columns (`vendor`, `product`, `version`, `match_confidence`) are not
part of this file; they go in the predictions CSV. A device that is removed simply has no row in
the next snapshot.

## data/ground_truth.csv

Human-labelled answers for the evaluation set. **Labelled by people, not by an LLM** (PRD).

```
device_id,group,vendor,product,version,lane,evidence_cve,evidence_lifecycle_id,source_row_note,verified_by_a,verified_by_b
```

| Column | Rule |
|---|---|
| `device_id` | Matches `inventory.csv`, one row per device |
| `group` | `clear_patch` / `clear_retire` / `supported_fine` / `messy_name` / `name_collision` / `critical_dnt` |
| `vendor`, `product`, `version` | True canonical identity; blank only if truly unknowable |
| `lane` | Lane enum: the correct answer. `unknown` when a careful human can't decide from the row |
| `evidence_cve` | `;`-separated KEV `cveID`s that justify the lane, or blank |
| `evidence_lifecycle_id` | A `lifecycle_id`, or blank |
| `source_row_note` | Free text: why this label, and what makes the row tricky |
| `verified_by_a`, `verified_by_b` | Initials of two different human reviewers. Blank = not yet verified |

Rows without both reviewers are **unverified** and are reported separately in results.

## data/ground_truth_meta.json

The date the ground truth is labelled against. Some lifecycle rows change lane later (e.g.
`LC-030` becomes `retire` after 2026-12-09), so the eval and the Checker evaluate every date
**as of `as_of_date`**, not the wall-clock date (the Checker's `today` input is set to it in eval runs).

```json
{
  "as_of_date": "2026-11-12"
}
```

| Field | Type | Rule |
|---|---|---|
| `as_of_date` | string | ISO date. Lane decisions compare support dates against this date |

## Predictions CSV (one per system per run)

Path: `eval/runs/<run_id>/<system>.csv`, where `system` is `deming` or `baseline`.

```
device_id,vendor,product,version,confidence,lane,evidence,run_id
```

| Column | Rule |
|---|---|
| `device_id` | Every inventory `device_id` exactly once |
| `vendor`, `product`, `version` | Normalized output; blank where nothing was extracted |
| `confidence` | Decimal 0.00 to 1.00, two places. The baseline writes its fuzzy score / 100 |
| `lane` | Lane enum. The baseline never writes `unknown` (PRD) |
| `evidence` | `;`-separated KEV `cveID`s and/or `lifecycle_id`s, e.g. `CVE-2023-20118;LC-007`; blank for `fine`/`unknown` |
| `run_id` | `<system>-<YYYYMMDDTHHMMSSZ>` (UTC start time), e.g. `deming-20261112T031500Z`; same on every row |

## Canonical names and comparison

- Canonical `vendor` / `product` use KEV `vendorProject` / `product` spelling when the product
  is in KEV; otherwise use `lifecycle.csv` spelling.
- `version` is written as the vendor writes it, with no `v` prefix.
- Scoring compares vendor/product/version case-insensitively after trimming whitespace.

### Version grammar (firmware vs `fixed_version`)

One parser, `sim/guards.parse_version`, used by the Checker's version guard, the loop's Verifier
rule and `tests/test_inventory.py`. A version parses only if it is, after trimming:

- optional `v`/`V`, then dot-separated ASCII integers (`1.5.1.5`, `v1.4.2.22`, `7.24.3`), or
- the PAN-OS hotfix form `major.minor.patch-h<digits>` exactly (`11.1.4-h7`, `11.1.16-h3`),
  compared as `(major, minor, patch, hotfix)` with hotfix 0 when absent.

Trailing zero parts are dropped (`1.5.1` == `1.5.1.0`; `11.1.4` == `11.1.4-h0`). Anything else
does not parse, e.g. build numbers `7.0.1-5161` (SonicWall), `7.0.12 build 523`, `22.7R2.6`
(Ivanti), `14.1-43.50` (NetScaler), `11.1.4-H7`, `11.1-h3`. A device whose firmware or
`fixed_version` doesn't parse goes to `unknown`.

## Loop state files (`sim/loop.py`, default folder `sim/state/`)

These stand in for the Sheet tabs and the approval Inbox. Same general CSV rules as above;
`sim/loop.py` writes exactly these columns in this order. Blank means unknown or not yet set.

### Settings tab: `settings.csv`

```
key,value
```

| key | Default | Rule |
|---|---|---|
| `approver_email` | `approver@example.org` | Named human who approves; recipient for `unknown` devices |
| `days_until_reminder` | `3` | Integer days after `opened` / `last_reminder` before a reminder is proposed |
| `days_until_escalation` | `7` | Integer days after `opened` before a ticket is escalated |
| `urgent` | `internet_facing is true and criticality is high or critical` | Text rule (see Inventory) |
| `tier2_mode` | `approval` | Only `approval` is supported (email, calendar, ticket need a recorded approval) |
| `tier3_mode` | `draft_only` | Isolate / disconnect / replace are never executed |
| `maintenance_lead_days` | `2` | Calendar window = run date + this, capped at the deadline |
| `kev_overdue_grace_days` | `14` | **New in 1.3.** If the KEV `dueDate` is before `as_of_date`, the deadline is `as_of_date` + this many days and the message says the CISA date has passed |
| `digest_channel` | blank | Where the run digest goes; blank = none |

Missing keys take the default.

### Decision Log tab: `decision_log.csv`

```
timestamp,run_id,device_id,lane,evidence,confidence,proposed_action,approver,decision,action_taken,outcome,verification_note,proposal_id,ticket_id,notes
```

| Column | Rule |
|---|---|
| `timestamp` | UTC timestamp of the run |
| `run_id` | `deming-<YYYYMMDDTHHMMSSZ>` |
| `device_id` | Inventory `device_id` |
| `lane` | Lane enum (blank on a verify row for a removed device) |
| `evidence` | `;`-separated `cveID`s and/or `lifecycle_id` |
| `confidence` | Normalizer confidence, two decimals; blank on verify rows |
| `proposed_action` | Planner `action` (`notify_patch`, `notify_retire`, `ask_identify`, `log_only`), `remind`, `verify` or `none` |
| `approver` | Named human who decided, or blank |
| `decision` | `pending` / `approved` / `rejected` / `n/a` on device rows; `close` / `remind` / `escalate` / `keep_open` on verify rows |
| `action_taken` | What was executed (e.g. `ticket:T-0001;email;calendar`), plus tier 3 drafts and escalations |
| `outcome` | Free text; on verify rows the observed change (`device_removed` / `version_changed` / `no_change`) |
| `verification_note` | Verifier note about the **inventory record** only, never device security |
| `proposal_id` | **New in 1.3.** The proposal this row created or decided, or blank |
| `ticket_id` | **New in 1.3.** The ticket this row opened or verified, or blank |
| `notes` | **New in 1.3.** `;`-separated guard notes and flags (e.g. `injection_detected`, `still_vulnerable`, `llm_decision=close`) |

One row per device per run, plus one `verify` row per open ticket and one `remind` row per reminder.

### Tickets tab: `tickets.csv`

```
ticket_id,device_id,issue,lane,dedupe_key,status,opened,due,last_reminder,owner_email,evidence,fixed_version,firmware_at_open,device_name_at_open,last_updated_at_open,proposal_id,closed_on,flags,last_note
```

| Column | Rule |
|---|---|
| `ticket_id` | `T-` + 4 digits, e.g. `T-0001` |
| `device_id` | Inventory `device_id` |
| `issue` | `patch` / `retire` / `identify` (lane `unknown`) |
| `lane` | **New in 1.3.** Lane when opened |
| `dedupe_key` | **New in 1.3.** `<device_id>|<issue>`; at most one `open`/`escalated` ticket per key |
| `status` | `open` / `escalated` / `closed` |
| `opened`, `due`, `last_reminder` | ISO dates; `due` = the approved proposal's deadline |
| `owner_email` | **New in 1.3.** Owner when opened (`example.org`) |
| `evidence` | As in the Decision Log |
| `fixed_version` | **New in 1.3.** From the governing lifecycle row for `patch` (may hold one value per train, `;`); blank otherwise |
| `firmware_at_open` | **New in 1.3.** `firmware_version_raw` when opened; the Verifier compares against it |
| `device_name_at_open`, `last_updated_at_open` | Inventory values when opened |
| `proposal_id` | The approved proposal that opened it |
| `closed_on` | **New in 1.3.** ISO date the Verifier closed it, else blank |
| `flags` | **New in 1.3.** `;`-separated, sorted: `still_vulnerable`, `low_evidence`, `recheck_disagrees` |
| `last_note` | Latest Verifier note (inventory record only) |

Closing rule: a ticket of **any** issue closes when the device is gone from the inventory; a
`patch`/`retire` ticket closes when the version changed, parses, is at or above the fixed version
on its own train, and the re-check is not `patch`/`retire`; an `identify` ticket closes when the
re-check lane is not `unknown`.

### Proposals (the approval Inbox): `proposals.csv`

```
proposal_id,run_id,created_on,kind,device_id,issue,dedupe_key,lane,priority,deadline,actions,to,cc,subject,body,drafted_to,expected_to,escalate_to_human,ticket_id,evidence,fixed_version,firmware_at_open,device_name_at_open,last_updated_at_open,owner_email,status,decided_by,decided_at,executed_at
```

| Column | Rule |
|---|---|
| `proposal_id` | `P-<run_seq, 3 digits>-<device_id>` for device proposals, `P-<run_seq>-<ticket_id>-R` for reminders |
| `run_id`, `created_on` | Run that drafted it; `created_on` = that run's `as_of` date |
| `kind` | `device` / `reminder` |
| `device_id`, `issue`, `lane` | As in Tickets |
| `dedupe_key` | `<device_id>|<issue>` (device) or `<ticket_id>|remind` (reminder); one `pending` per key |
| `priority` | Planner priority 1-4; blank for reminders |
| `deadline` | ISO date or blank |
| `actions` | `;`-separated tier 2 actions only: `email`, `ticket`, `calendar` |
| `to`, `cc` | Recipients set by rule (owner, or approver for `unknown`; approver cc'd on escalation) |
| `subject`, `body` | Message text after the guards |
| `drafted_to` | The model's recipient (routing metric only) |
| `expected_to` | The rule's recipient |
| `escalate_to_human` | `true` / `false` |
| `ticket_id` | Ticket it opened or reminds about, else blank |
| `evidence`, `fixed_version`, `firmware_at_open`, `device_name_at_open`, `last_updated_at_open`, `owner_email` | Copied to the ticket on execution |
| `status` | `pending` / `approved` / `rejected` |
| `decided_by`, `decided_at` | From `approvals.csv` |
| `executed_at` | ISO date the approved actions were written to `outbox/`, else blank |

### Approvals: `approvals.csv`

```
proposal_id,decision,approver,decided_at,note
```

| Column | Rule |
|---|---|
| `proposal_id` | A `pending` proposal; at most one row per proposal |
| `decision` | `approved` / `rejected` |
| `approver` | Required, non-blank: the named human |
| `decided_at` | UTC timestamp |
| `note` | Free text or blank |

Rows are executed on the next `run` (or at once by `python -m sim.loop approve|reject`). A row
with a blank approver or any other decision is ignored. Nothing reaches `outbox/` without one.

### Expected verification (eval): `expected_verification.csv`

```
as_of,device_id,expected_decision
```

| Column | Rule |
|---|---|
| `as_of` | The run's `as_of` date |
| `device_id` | Device whose ticket is verified on that run |
| `expected_decision` | `close` / `remind` / `escalate` / `keep_open` |

Optional and human-written. If present, `metrics.json` reports `verification_correctness` over
the verify rows that have an expected decision.

## LLM model

All evaluation runs use **`gemini-3.5-flash-lite`** (google-genai, structured JSON output,
temperature 0). Reason and smoke-test results: `docs/decisions.md`.

## Parallel work (feature branches)

- Write decisions to `docs/decisions/<name>.md` and AI usage to `docs/ai-usage/<name>.md`,
  where `<name>` is the branch name with `/` replaced by `-`.
- Do **NOT** edit `requirements.txt`, `README.md` or `CLAUDE.md`. List any needed change in the
  branch's final summary instead.
- Also don't edit `docs/contracts.md`, `docs/decisions.md` or `docs/ai-usage-log.md` on a branch.
  Propose contract changes in the summary; they land on `main`.
