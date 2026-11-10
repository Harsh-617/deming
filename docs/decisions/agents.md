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
