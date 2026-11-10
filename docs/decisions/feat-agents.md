# Decisions: feat/agents branch

One short entry per decision: choice, alternatives, source, and what couldn't be verified.
These entries will be merged into `docs/decisions.md` on `main`.

---

### 2026-11-11 · Subagent prompt format for Agent Designer
- **Choice:** one Markdown file per subagent (`agents/<name>.md`) with the sections Role, Inputs,
  Rules, Output and Examples. The whole file is the "Instructions" text and is pasted unchanged.
  Prompts are plain text with no templating, no code and no tool syntax. Thresholds are written as
  literal numbers (0.80) because Agent Designer can't read our config; a test checks the literal
  matches `sim/config.py`.
- **Why:** Agent Designer's main agent and subagents are configured in the Flow tab with a free-text
  Instructions field. The docs say to be "specific and concise".
- **Alternatives:** a Jinja-templated prompt filled in by code (not pasteable); one big prompt for all
  four steps (harder to evaluate, and Agent Designer is built around subagents).
- **Source:** https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer ·
  https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/create-agent
- **Not verified:** the docs I found give **no** limit on instruction length, the number of
  subagents, or nesting depth, and they don't say whether a subagent can enforce a JSON response
  schema. The only number I found is the 800,000-token combined limit for files uploaded as Knowledge
  to the main agent. If Agent Designer can't enforce a schema, each prompt's Output section still
  describes the JSON, and the schema file is the reference to check it against.

### 2026-11-11 · Structured output: `response_json_schema` with the schema files
- **Choice:** the runner passes the dict loaded from `schemas/<agent>.json` as
  `GenerateContentConfig(response_mime_type="application/json", response_json_schema=..., temperature=0)`.
  Every response is then validated with the Pydantic models in `sim/models.py`. The schema files
  are the single source and are portable (plain JSON Schema). The Pydantic models enforce the
  rules Gemini ignores.
- **Schema style:** only keywords Google lists as supported: `type`, `properties`, `required`,
  `additionalProperties`, `enum`, `items`, `minimum`/`maximum`, `description`. Nullable fields use
  type arrays (`["string","null"]`). There's no `$ref`, `const`, `minLength` or `pattern`, and every
  field is `required` (Google's advice for keeping the compiled grammar small).
- **Alternatives:** `response_schema=<Pydantic class>` (what `docs/decisions.md` chose for the smoke
  test, but it ties the schema to Python); the Interactions API with `response_format` (newer, and
  what the structured-output guide shows now, but more of a change than we need this week).
- **Source:** https://aistudio.google.com/docs/structured-output (supported and ignored keywords,
  `400 INVALID_ARGUMENT` for oversized schemas) · https://googleapis.github.io/python-genai/
- **Not verified:** that `gemini-3.5-flash-lite` accepts these exact schema files. No live call was
  made on this branch (no key). The first real run should confirm there's no 400.

### 2026-11-11 · Checker: deterministic top-k candidate retrieval before the LLM
- **Choice:** `sim/retrieval.py` scores the device's (normalized, else raw) vendor+product against
  the unique KEV `vendorProject`+`product` pairs and against every `lifecycle.csv` row with
  `rapidfuzz.fuzz.WRatio` (after `utils.default_process`). It keeps the top 5 KEV products
  (score >= 60) and the top 5 lifecycle rows. A lifecycle row whose `model_pattern` glob matches
  the product always gets 100. Each KEV product contributes at most 8 CVEs, ranked first by whether
  the version or a model token appears in `shortDescription`/`vulnerabilityName`, then newest
  `dateAdded`. Only those candidates go to the Checker, so its prompt stays a few KB instead of
  the whole 1,773-entry catalog.
- **Guard:** the Checker may cite only candidate ids. Any other CVE or lifecycle id in its output is
  treated as invented, and the device goes to `unknown` (`sim/guards.py`).
- **Agent Designer equivalent:** the same step is a Drive-file lookup. Upload two files as
  Knowledge (or keep them in Drive): `kev_products.csv` (one row per vendorProject/product with its
  cveIDs, dueDate, requiredAction) and `lifecycle.csv`. The Checker prompt's "Candidate lookup"
  section tells the agent to search those files for rows whose vendor and product match the device
  and use only those rows. In Python the runner does that search for it and passes the result as
  `kev_candidates` / `lifecycle_candidates`, so the prompt text is identical in both places.
- **Alternatives:** send the whole KEV catalog (about 1.5 MB, slow and costly, and Agent Designer
  Knowledge counts it against the 800k-token limit every turn); embeddings or vector search (an extra
  dependency, and less explainable than a fuzzy score you can print); exact join (misses typos,
  which is the whole point of the messy-name group).
- **Source:** https://rapidfuzz.github.io/RapidFuzz/Usage/process.html ·
  https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/create-agent (Knowledge limit)
- **Not verified:** that k=5, the 60 cutoff and 8 CVEs per product give full recall on the 60-device
  set (there's no inventory or KEV copy on this branch yet). Tune these after the data lands, and report
  retrieval recall separately so a retrieval miss isn't blamed on the LLM. I also haven't checked
  whether Agent Designer's Knowledge search is keyword- or embedding-based, so in-platform recall may differ.

### 2026-11-11 · Runner: own retry loop, SDK retry off
- **Choice:** `sim/gemini_runner.py` retries only on HTTP 429 and 503 with exponential backoff plus
  jitter (1, 2, 4, 8, 16 s, capped at 30 s; 5 retries), and sets the SDK's own
  `HttpRetryOptions(attempts=1)` so the two retry loops don't stack. That fits the decisions.md note
  that 3.8 calls looked like they were retried silently. The sleep function is injected, so tests
  run instantly.
- **Alternatives:** the SDK's built-in `HttpOptions(retry_options=HttpRetryOptions(...))` (less code,
  but harder to test and log); `tenacity` (a new dependency).
- **Source:** google-genai 3.0.0 `types.HttpRetryOptions` fields (`attempts`, `initial_delay`,
  `max_delay`, `exp_base`, `jitter`, `http_status_codes`), inspected locally ·
  https://googleapis.github.io/python-genai/
- **Not verified:** that `attempts=1` means "one try, no retry" (I read it from the field name and
  haven't checked the docs).

### 2026-11-11 · Response cache and repeated runs
- **Choice:** an on-disk JSON cache in `.cache/gemini/` (gitignored) keyed by the sha256 of
  model, agent name, prompt text, schema, temperature, canonical input JSON and `repeat_index`. Only
  responses that pass validation are cached. `run_repeated(agent, payload, n)` makes calls
  `repeat_index = 0..n-1`, so the 3-run stability metric measures real model calls rather than
  cache hits, and a rerun of the same evaluation is free.
- **Alternatives:** key without `repeat_index` (then stability is always 100%, which is meaningless);
  no cache (every eval rerun costs quota and time).
- **Source:** none needed (design choice).

### 2026-11-11 · Deterministic guards around every LLM output
- **Choice:** `sim/guards.py` enforces the hard rules in code, whatever the model says. Confidence
  below 0.80 means lane `unknown`. Evidence must come from the candidate list. A `do_not_touch` device
  gets no disconnect or isolate proposal and is escalated to a human. Every outward action has
  `requires_approval=true`. The Verifier may `close` only when the record changed and the re-check
  is not still vulnerable (a change isn't a fix).
- **Why:** prompt rules alone can be bypassed by injection text in a device name. The guards make
  the PRD rules testable without a live model.
- **Alternatives:** rely on the prompt alone (not provable); fail the run on a violation (loses the
  other devices' results).

### 2026-11-11 · Agent Designer port: build a chat agent first, workflow as the upgrade
- **Choice:** the port guide (`docs/agent-designer-port.md`) builds a **chat agent** (main agent
  + four subagents in the Flow tab, Schedule tab) as path A, and a **workflow** (Schedule trigger →
  four Gemini Agent steps → Request info → Condition → connector actions) as path B.
- **Why A first:** it matches the PRD's "main agent + four subagents" design and the prompts paste
  unchanged, one per subagent. **Why B exists:** only workflow agent steps document structured
  JSON output with a manual schema, and connector writes there get human review. Chat-agent
  schedules are documented as "not supported for actions involving other people", so on path A a
  scheduled run can only draft; sending happens in the approver's follow-up chat.
- **Alternatives:** workflow only (enforces schemas, but needs a batch-wrapper line above each
  prompt, because no loop step is documented); a single agent with the four prompts as sections
  (fallback F9 if subagent hand-off doesn't work).
- **Verified (official docs, 2026-11-11):**
  - Agent Designer pages now sit under "Workflow Builder", with two kinds: chat agents and workflows.
  - Creating an agent: **+ Create agent > Chat agent > Proceed to builder**, then **Add subagent**
    in the Flow tab. Main-agent fields: Name, Description, Instructions, Model (Flash/Pro),
    Data and tools, Knowledge (800k-token combined limit, loaded every turn), and Personalization.
    An agent left without clicking **Create** stays a Draft.
  - Chat-agent schedules: Hourly/Daily/Weekly/Monthly/Annually; credentials expire every 14 days
    and need a manual refresh (Agent Gallery or the Schedule tab's **Refresh schedules**); up to
    5 min of delay; multi-region only; no actions involving other people; a paused run has an
    **Approve** button; runs show in the Chats history; **Run in preview** button.
  - Workflows: Manual, Schedule (minutes to months or cron) and Event triggers; Gemini Agent step
    with plain text or structured JSON output and a manual schema; Condition; Request info (yes/no
    etc.); connectors include Gmail, Google Calendar, Google Chat, Jira and Jira Data Center, each
    with "Search For Data" and "Add Or Update Data" groups; "Adding or updating data through
    connectors requires human review"; Drive knowledge via "Add from Drive" when a Drive data
    store exists.
  - Known issues: disabled actions fail the run; "3.1 Pro" is recommended; HITL steps may show raw
    Markdown; RESOURCE_EXHAUSTED isn't retried for event triggers; the Gmail subject can't take
    non-English characters.
- **Not verified:**
  - The subagent fields (whether a subagent has its own Knowledge or tools), how the main agent
    passes data to a subagent, and instruction length or subagent count limits.
  - Whether chat agents can enforce a response schema.
  - The Inbox and "Needs your input": seen only in a third-party blog and Google's launch blog
    post, not in the docs.
  - Google Sheets read and write: Sheets isn't in the listed connectors. A release note saying
    Drive handles CSV/XLSX, and one about exporting tables to Sheets, came only through search
    summaries; I didn't open them.
  - Jira action names for chat agents (the docs show them for workflows), and edition
    differences (a support page on actions is for the Business edition).
  - Whether **Add from Drive** Knowledge follows file updates, the data-store re-index delay,
    which model names the dropdown offers, and whether temperature is exposed.
- **Sources:** https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer ·
  https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/create-chat-agent ·
  https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/schedule-agent ·
  https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/workflows ·
  https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/create-workflows ·
  https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/known-issues ·
  https://docs.cloud.google.com/gemini/enterprise/docs/connectors/gdrive/set-up-data-store

### 2026-11-11 · Drive assets: kev_products.csv + kev_entries.csv + lifecycle.csv
- **Choice:** `scripts/export_agent_assets.py` writes `dist/agent-designer/` (gitignored):
  - `kev_products.csv`: one row per KEV product, about 200 KB / ~50k tokens on catalog
    2026.11.09 (747 products);
  - `kev_entries.csv`: one row per CVE, description trimmed to 400 chars, 806 KB / ~200k tokens;
  - `lifecycle.csv`: a byte-for-byte copy, header checked against contracts.md;
  - the prompts as .txt, and a manifest with sha256 values.

  The small files go in Knowledge; `kev_entries.csv` stays in the Drive data store, because
  Knowledge is loaded into context on every turn.
- **Why a second KEV file:** the Checker needs each CVE's description and required action to
  judge the version. `kev_products.csv` alone only lists the ids. I added a line to `checker.md`'s
  Candidate lookup to point at it.
- **Guide drift guard:** the guide's pasted prompts are generated blocks. `--sync-guide` rewrites
  them, and a test fails if they differ from `agents/*.md`.
- **Alternatives:** upload raw `kev.json` (1.8 MB, JSON is harder for file search); kev_products
  only (no version detail).
- **Not verified:** token counts are chars / 4, not a tokenizer. How well Agent Designer's file
  search finds rows in a CSV this size isn't documented.

### 2026-11-11 · Normalizer example uses the real KEV product name
- **Choice:** the example now reads "Small Business RV320 and RV325 Routers", the actual KEV
  `product` for CVE-2019-1653 in catalog 2026.11.09. Before, it said "Small Business RV Series
  Routers", which isn't a KEV product name. Found while building the export.
