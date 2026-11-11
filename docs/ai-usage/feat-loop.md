# AI usage: feat/loop

| Date | Tool | What for |
|---|---|---|
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Researched idempotency for scheduled jobs (Cloud Scheduler, Stripe, AWS docs); wrote the closed-loop simulator (`sim/loop.py`), the rule-based mock model (`sim/mock_llm.py`), the demo scenario (`sim/demo_scenario.py`) and the loop tests (`eval/test_loop.py`). No live Gemini calls were made; everything ran on the mock. |
