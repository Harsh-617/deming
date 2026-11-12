# Decisions: feat/owner-sim branch

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`. Synthetic data, simulated.

---

### 2026-11-12 · Owner simulator as scripted rules around the unchanged loop
- **Choice:** `sim/owner_sim.py` drives `sim.loop.run_loop` one daily tick at a time. Scripted
  owners read the loop's own outbox records and edit the inventory CSV between ticks; a scripted
  human approver (`PolicyApprover`) records decisions through the loop's existing approver hook.
  No existing file changed except `.gitignore` (adds `sim/owner_sim_state/`), so no default-OFF
  wiring was needed.
- **Why:** the task says reuse the loop, not reimplement it. Driving the real `run_loop` means
  the approval gate, dedupe and Verifier closing rule under test are the shipped ones.
- **Alternatives:** a discrete-event framework such as SimPy (https://simpy.readthedocs.io/) or an
  agent-based one such as Mesa (https://mesa.readthedocs.io/). Rejected: the loop is already a
  fixed daily schedule, so a plain `for` loop over dates is the whole event model; a framework
  adds a dependency (we may not edit `requirements.txt` on a branch) and nothing we measure.
- **Not verified:** SimPy/Mesa pages were not re-opened this session; the rejection rests on
  the dependency rule, not on their docs.

### 2026-11-12 · Seeded determinism with `random.Random(seed)` instances
- **Choice:** one `random.Random(seed)` for the owner->behaviour draw and one
  `random.Random(f"{seed}|{ticket_id}")` per maintenance-window draw; no global random state, no
  wall-clock values in the results doc.
- **Source:** https://docs.python.org/3/library/random.html: "By reusing a seed value, the same
  sequence should be reproducible from run to run"; str seeds (version 2) use all bits of the
  string. The same page says most algorithms and seeding functions "are subject to change
  across Python versions", so reproducibility is claimed **only on Python 3.11** (the repo venv,
  3.11.7), checked by `eval/test_owner_sim.py::test_runs_are_deterministic`.

### 2026-11-12 · Audit independent of the loop's bookkeeping
- **Choice:** `owner_sim.audit` recomputes every metric from the state files plus the simulator's
  own `owner_events.csv`. A close counts as right only if it passes the contract rule against
  that run's inventory snapshot AND the simulator recorded a real fix/replacement/identification/
  removal. A test plants a wrong close and an unapproved outbox record to prove the audit
  catches them.
- **Why:** a metric computed by the code under test can share its bug.

### 2026-11-12 · Reroute is a human Sheet edit, not a loop feature
- **Choice:** on a "wrong person" reply a scripted steward edits both the Inventory and the
  Tickets tab `owner_email`. Deming does not parse replies.
- **Why:** reminders use the Tickets tab `owner_email` captured at open (`sim/loop.py
  _propose_reminder`), so an Inventory-only edit would keep reminding the wrong person. Reported
  as a finding in `docs/owner-sim-results.md`; proposing a loop change is left to `main`.
