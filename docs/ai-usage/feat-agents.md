# AI usage: feat/agents

| Date | Tool | What for |
|---|---|---|
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Researched Agent Designer and Gemini structured-output docs; drafted the four subagent prompts (`agents/*.md`), the JSON schemas, the Pydantic models, candidate retrieval, the guards, the Gemini runner, the pipeline and the mock-client tests. No live Gemini calls were made. |
| 2026-11-11 | Claude Code (Claude Opus 5.5) | Researched the official Agent Designer / Workflow Builder docs (chat agents, schedules, workflows, connectors, known issues); wrote `docs/agent-designer-port.md`, `agents/main_agent.md`, `scripts/export_agent_assets.py` and its tests. Downloaded the public CISA KEV feed to a temp folder only, to measure the file sizes (not committed). |
