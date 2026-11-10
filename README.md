# Deming

A scheduled agent that keeps a device inventory honest. Built for the APU Cloud
Innovation Hackathon 2026.

Each run it:

1. Reads a device inventory (Google Sheet, synthetic data only).
2. **Normalizer** maps messy names to vendor / product / version with a confidence score.
3. **Checker** looks them up in CISA KEV and end-of-life data.
4. **Planner** assigns a lane and drafts a message to the owner, then waits for human approval.
5. **Verifier** checks on the next run that the inventory record changed.

| Lane | Meaning |
|---|---|
| Patch | A fix exists |
| Retire | Vendor no longer supports it |
| Fine | No known issue |
| Unknown | Can't match confidently, so a human is asked |

Deming never scans or touches real devices. The Verifier confirms only that the
inventory record changed, not that a device is secure.

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then put your Gemini API key in .env yourself
```

## Layout

`data/` inventory and feeds · `agents/` subagents · `schemas/` JSON schemas ·
`eval/` tests and eval sets · `sim/` run simulation · `docs/` decisions and AI-usage log

Status: scaffold only.
