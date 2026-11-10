# Deming: working rules for Claude

Deming is a scheduled agent for the APU Cloud Innovation Hackathon 2026. It reads a
synthetic device inventory (Google Sheet), normalizes messy device names to
vendor/product/version with a confidence score, checks them against CISA KEV and
end-of-life data, assigns a lane, drafts owner messages, waits for human approval,
and on the next run verifies that the inventory record changed.

Subagents: **Normalizer → Checker → Planner → Verifier**.

**At the start of every session, read docs/PRD.md. It is the condensed spec. Full report:
docs/reference/full-report.md (read only when needed).**

Deadlines: prototype due Fri 13 Nov 2026 12:00 MYT (target 10:00). Final pitch
17 Nov 2026 must run on Gemini Enterprise; the prototype does not need it.

## Lanes

| Lane | Meaning | Owner action |
|---|---|---|
| **Patch** | A fix exists (vendor patch / newer supported version) | Apply the fix |
| **Retire** | Vendor no longer supports it (end of life) | Replace or decommission |
| **Fine** | No known issue | None |
| **Unknown** | Can't match confidently | Ask a human to identify it |

## Hard rules

1. **Never scan or touch real devices.** The inventory is synthetic. No network
   probes, no SSH, no agents on hosts. Only read the inventory and public data feeds.
2. **Unknown lane when confidence is low. Never guess.** If the Normalizer's
   confidence is below threshold, the device goes to Unknown, not to the closest match.
3. **The Verifier only confirms the inventory record changed**, not that the device is
   secure. Word every Verifier output that way.
4. **Prompts and output formats must be portable to Gemini Enterprise Agent Designer.**
   Keep each subagent's instructions as plain-text prompts with JSON schemas
   (in `/schemas`), no framework-specific magic.
5. **LLM calls use the Gemini API via the `google-genai` package**, with structured JSON
   output (`response_mime_type="application/json"` + `response_schema`). Read the
   CURRENT model name from Google's official docs; never assume one. Gemini 2.5
   models are shut down / deprecated. Keep the model name in one config place.
6. **Never commit secrets.** The API key lives in `.env` (gitignored). `.env.example`
   holds `GEMINI_API_KEY=` only; the user fills `.env` themselves. A PreToolUse hook
   (`.claude/hooks/block_secrets.py`) blocks commits containing `.env` or Google key
   patterns; don't bypass it.
7. **Keep the AI-usage log** in `docs/ai-usage-log.md` (tool, what for, date).

## Research rule (standing)

Before each new task, spend **at most 5 minutes** checking official docs for the best
current tool or approach. Prefer primary sources. Record the choice, the alternatives
and a source URL in `docs/decisions.md`, one short entry each. If something couldn't
be verified, say so in the entry. Don't let research eat build time; the deadline is hard.

## Environment

- Windows, PowerShell. Use PowerShell-compatible commands.
- Plain venv in the repo: `python -m venv .venv`, activate with
  `.venv\Scripts\Activate.ps1`. Base Python is conda 3.11.7.
- **Do NOT run `conda deactivate`.** It switches the user to Python 3.14.

## Layout

- `data/`: synthetic inventory and cached public feeds
- `agents/`: the four subagents (prompts + code)
- `schemas/`: JSON schemas for structured output
- `eval/`: evaluation sets and tests
- `sim/`: simulation of runs / approvals
- `docs/`: decisions, AI-usage log
