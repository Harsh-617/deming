# Decisions: feat/loop branch

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`.

---

### 2026-11-11 · Idempotent scheduled-run state: run key + per-action idempotency keys
- **Choice:** three keys.
  1. **Run key:** `run_id = deming-<scheduled UTC time>` (`--now`). A run_id already in
     `runs.csv` is a no-op, so a duplicate scheduler delivery does nothing.
  2. **Action key:** every outward record is keyed by `proposal_id` and written to
     `outbox/<proposal_id>.<kind>.json` with exclusive create (`open(..., "x")`). Re-applying an
     approval can't send twice.
  3. **Business dedupe key:** `device_id|issue` (issue = `patch` / `retire` / `identify`, set by
     code from the lane, never the model's free text). We check it at planning time (open ticket
     or pending proposal means no new proposal) and again at execution time (two approved
     proposals still open one ticket).
- **Why:** Google says Cloud Scheduler is at-least-once, so "a job may run more than once" and
  handlers should be idempotent. Stripe and the AWS Builders' Library both describe the same
  pattern: one stable key per logical action, sent on every retry, with the server keeping the
  first result. Gemini Enterprise schedules can start up to 5 min late and run hourly (PRD), so
  overlapping or repeated runs are possible.
- **Alternatives:** hash the inventory content to make the run key (rejected: AWS argues a
  caller-supplied key says what was meant, and an inferred hash can't). A lock file (doesn't
  survive a crash mid-run, and doesn't protect individual actions). Model-written `ticket.issue`
  as the dedupe key (rejected: free text varies between runs, so dedupe would silently fail).
- **Sources:** https://docs.cloud.google.com/scheduler/docs/overview ·
  https://docs.stripe.com/api/idempotent_requests ·
  https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- **Not verified:** the names of the Cloud Scheduler dedupe headers (not read). Whether
  Gemini Enterprise scheduled runs expose a stable scheduled time we could use as the run key.
  On the platform the Sheet/Drive file has no exclusive-create, so the action key would have to be
  a "proposal_id already in Tickets/Decision Log" check instead.

### 2026-11-11 · The closing rule is deterministic; the LLM Verifier is advisory
- **Choice:** `decide_verification()` in `sim/loop.py` decides. A ticket closes only when the
  device is gone from the inventory, OR the version changed AND the new version parses AND it is
  >= the ticket's `fixed_version` (reusing `sim/guards.compare_versions`). Stricter extras: if the
  re-check lane is still patch/retire the ticket stays open (`recheck_disagrees`); an `identify`
  ticket closes once the device can be matched (re-check lane not unknown). A changed version
  below the fix stays open, is flagged `still_vulnerable` and escalated. An unparseable version or
  a blank `fixed_version` stays open, flagged `low_evidence`. The LLM Verifier still runs (for
  patch/retire tickets) and its decision is logged, which gives the `verifier_llm_agreement`
  metric.
- **Why:** PRD acceptance: "a ticket closes only when the Sheet shows the fixed version or
  removal". This must not depend on a model.
- **Difference from `guards.guard_verifier`:** that guard allows `device_removed` to close only
  retire tickets. The task brief says close on removal for any lane, so the loop closes a removed
  patch device too. The guard is left unchanged (the loop's rule is the one that acts).
- **Source:** docs/PRD.md (acceptance criteria, tricky cases).

### 2026-11-11 · Approval model and tiers
- **Choice:** one proposal per device and issue, bundling tier 2 actions (email, ticket, and a
  calendar maintenance window for patch). Approve or reject per proposal via
  `python -m sim.loop approve|reject <id> --approver <name>`, by editing `approvals.csv` (applied
  on the next run), or with a `ScriptedApprover` in tests and the demo. Tier 3 (isolate, replace)
  only goes in the Decision Log as "drafted only". It is never a proposal, and `_write_outbox`
  refuses any non-tier-2 kind. do_not_touch devices get no tier 3 draft. Their email is cc'd to
  the approver and marked ESCALATE. Recipients are set by rule (owner, or the approver for unknown
  devices). The model's recipient is recorded only to measure routing accuracy. Reminders are
  their own proposals and need approval too. Escalation sets the ticket to `escalated` and is
  listed in the run digest for the approver.
- **Why:** PRD hard rules (no outward action without recorded approval; tier 3 is draft-only; do_not_touch is never
  proposed for disconnection) and `agents/main_agent.md` step 8 ("approve 1, 3").
- **Alternatives:** approval per action (finer-grained but slower in a 3-minute demo); auto mode
  for tier 2 (`tier2_mode` other than `approval` is ignored with a warning, since auto is only a PRD "Could").

### 2026-11-11 · Rule-based mock model for `--mock`
- **Choice:** `sim/mock_llm.py` applies the written rules from `agents/*.md` deterministically
  and plugs into the existing `GeminiRunner` as a fake client. So with `--mock` the full code path
  (runner, Pydantic validation, guards, loop) runs, just without the network.
- **Why:** this worktree has no API key. The eval mock (`eval/mock_gemini.py`) needs a
  per-test responder and can't produce realistic outputs for a whole inventory.
- **Limit:** the mock's name matching is simple. For example it sends the fixture's "fgt 60e
  fortigate" to unknown, where a real model might resolve it. Mock results say nothing about
  prompt quality.

### 2026-11-11 · Metrics definitions (`<state>/metrics.json`, `metrics.csv`)
- owner_routing_accuracy = model-drafted recipient == rule recipient, over drafted emails
  (routing_after_guard = what was actually addressed, always 1.0 by construction).
- duplicate_tickets = tickets opened while another ticket with the same `device_id|issue` was open.
- approval_compliance = outbox records with an approved decision by a named approver, decided on
  or before execution, tier 2 only. Violations are listed.
- verification_correctness = verify decisions matching `expected_verification.csv`
  (`as_of,device_id,expected_decision`) when the file exists. The demo writes one.
- run_time_s = mean wall time per run (`runs.csv` has each run).
