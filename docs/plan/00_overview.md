# Plan overview: HPC log problem-resolution system

Written on 2026-10-06. This is the shared reference for every chat that works on the project.

## 1. How to use these documents

**Who reads this.** A chat that executes one step, with no memory of earlier chats, and Aviv, who reviews.

**Reading order.** `AGENTS.md` (loaded automatically), this file, the brief for the step you are executing, and Part 1 of [docs/lab_notes.md](../lab_notes.md), the decision log.

**One step per chat.** Step 2 has three parts and each part is its own chat. Steps depend on each other in order: do not start a step whose "Before you start" list is not satisfied. Some substeps are optional (marked Should or Could) - when relevant, consult with Aviv whether they are to be implemented.

| Brief | Covers |
|---|---|
| [01_data_and_golden_set.md](01_data_and_golden_set.md) | Bring the code base into shape, understand the data, label a few dozen log shapes, write the golden incidents |
| [02_pipeline_and_agent.md](02_pipeline_and_agent.md) | Part A routing and incidents, Part B agent without knowledge, Part C knowledge base |
| [03_evaluation_and_judge.md](03_evaluation_and_judge.md) | Evaluation harness, code metrics, the judge and its calibration |
| [04_experiments.md](04_experiments.md) | Controlled experiments, cost and latency, the holdout run |
| [05_report.md](05_report.md) | Report, README, ingestion diagram |

**These documents describe design, not code.** Where a brief names a file, a function, a column or a field, the name is fixed, because other steps rely on it. How you implement it is yours to decide with Aviv.

**The plan is expected to change.** When something you find contradicts a brief, stop and tell Aviv. If a decision changes, amend the decision log and the affected brief or contract in the same session. Never deviate silently.

**At the end of every session:** update the status table below, add dated notes to `docs/lab_notes.md`, and suggest a commit.

## 2. Status

| Step | State | Notes |
|---|---|---|
| 1. Data and golden set | in progress | Tasks 0 and 1.0 done on 2026-10-07: log store changes taken, copies merged into one row per event, list variants collapsed, database rebuilt. Task 1.1 done: sources in `kb/sources.md`; the cluster is identified, the vendor manual's body could not be read. Task 1.2 started: query helpers and the exploration notebook. On 2026-10-10 the stored unit was renamed log shape (D16) and triage was redesigned as routing with active incidents (D17 to D21); this plan was rewritten to match. Task 1.2 done on 2026-10-10: the queries behind the agent's log tools and the past-only stats are on `LogRepository`, and the notebooks in `notebooks/incidents/` show them and investigate one fixed log for each of the 17 most common log shapes, one notebook per log; the investigations were completed on 2026-10-10 and are evidence for the labelling, not labels. Tasks 1.7 and 1.8 done on 2026-10-11, ahead of order: the novelty plot is `docs/figures/log_shape_novelty.png` (`notebooks/04_log_shape_novelty.ipynb`) and the fact sheet is `kb/cluster_facts.md` (`notebooks/05_cluster_facts.ipynb`). Tasks 1.3 to 1.6 are set aside: on 2026-10-11 the order changed and the agent is built first, on single logs (D23). `labeling/golden_cases.yaml` holds the 10 hand-investigated logs with their verdicts |
| 2A. Routing and incidents | not started | |
| 2B. Agent without knowledge | in progress | Started on 2026-10-11 ahead of 2A, on single logs and not incidents (D23); the briefs of 2A and 2B are not followed as written. Done: the tools, `agent/tools.py`; the LLM client, `agent/llm.py`, with `config/models.yaml`; `notebooks/06_model_selection.ipynb`, which compares three models on tool calling and as judge and backs the three roles in `config/models.yaml`; the tools cut to six, each returning ids; the verdict and judge schemas, `agent/schema.py`; the starting context, `agent/context.py`; the prompts `prompts/investigator_v1.md` and `prompts/judge_v1.md`; the judge, `agent/judge.py`; and `scripts/agent_smoke_test.py`, which runs the investigator and the judge against the real models on made-up logs and passes. Next: the real loop with its visible time, the check of cited log ids, the trace, and `scripts.investigate --case` on the 10 golden cases |
| 2C. Knowledge base | not started | |
| 3. Evaluation and judge | not started | |
| 4. Experiments | not started | |
| 5. Report | not started | Lab notes are running from day 1 |

**Repo state on 2026-10-06, before Step 1:**

- `main` has a tested SQLite log store in `logstore/`, a build script, two EDA notebooks (since moved to `notebooks/`).

## 3. The assignment, and what is graded

Build a system that processes HPC logs, identifies errors, and recommends specific remediation steps backed by citations and reasons. It must adapt to new log templates, formats and recommendations without code changes, and be realistic about cost and latency. Deliverables: a GitHub repository with a report and a README with exact run instructions. A diagram of data ingestion is required; implementing ingestion is not.

Three phrases in the assignment carry most of the weight, and the design answers each one:

1. **"Use the right tool for the job."** Deterministic code does the bulk work. An LLM is called only where judgment is needed. Every stage below is marked code or LLM.
2. **"Back them up with citations and reasons."** A citation counts only if the agent really retrieved that passage during the run, and a program checks this.
3. **"New logs and recommendations are introduced occasionally."** Everything that changes over time lives in data (a table, a markdown folder, a config file), not in Python.

The role is about evaluation as much as building: about a third of the time goes to measurement, and the agent is deliberately simple.

## 4. The system

```
HPC.log, replayed in time order in 5-minute chunks   scripts/replay.py
  |  parse line (regex per format)            code   logstore/parsing.py
  |  merge copies into one row per event      code   logstore/repositories.py
  |  mask variables -> template               code   logstore/templating.py
  |  log shape = (component, state, template) code   logstore/repositories.py
  v
SQLite log store                                     logstore/
  |  each new event, in time order:
  |  LogContext: log shape, catalogue row,    code   triage/context.py
  |     keyword hits if the shape is unknown,
  |     stats looking only at the past, on demand    (SQL here, a per-chunk cache in production)
  |  router: ignore | handle | investigate    code   triage/router.py
  |     from the log shape catalogue                 human labels for a few dozen log shapes
  |     or a named rule in config                    config/triage.yaml
  |  active incidents: one per log shape,     code   triage/incidents.py
  |     joined or opened, TTL in log time
  |--> handle: deterministic handler, per node    code   triage/handlers.py
  v  investigate: at once, under a cap per hour of log time
incident, shown to the agent as a compact "card"
  |  investigator agent: loop of tool calls          LLM    agent/
  |     tools: search_logs, count_logs, node_timeline, get_stats, related_incidents, search_knowledge
  |     sees logs only up to max_visible_timestamp = log time when its run started + its own elapsed time
  |  validator: schema ok, every cited log id, passage and incident really appeared in a tool result   code, one retry
  v
verdict (JSON) + full trace (JSON)                   runs/
  |
  v  offline
evaluation: code metrics, comparison to expected answers, calibrated LLM judge    evals/
```

| Stage | Tool | Reason |
|---|---|---|
| Parse, merge copies, template, log shape | Code | Deterministic, runs on every line, must cost nothing |
| Route each new event | Code: the catalogue row of its log shape, or a named rule over its stats or values | Most answers are fixed per log shape and some depend on frequency; both are decided once and stored as data |
| What does a log shape mean? | Human label for a few dozen log shapes; the agent for the rest; optionally an LLM once per new log shape | Needs judgment, but for a labelled log shape the answer never changes, so it is decided once and stored |
| Open or join an incident | Code | One incident per log shape while active, with a TTL in log time, so a burst costs one investigation |
| Apply a known fix | Code: a deterministic handler | When the fix is known, an LLM adds only cost and latency |
| Investigate, explain, recommend | LLM agent with tools | The only stage that needs multi-step reasoning over evidence |
| Check that citations and evidence exist | Code | A fabricated log id is a fact about the trace, not an opinion |
| Is the diagnosis right, grounded, supported by its citation? | LLM judge | Semantic. The only place a judge is used |

| What changes over time | Where it lives | What happens with no code change |
|---|---|---|
| New log shape | No row in the `log_shape_catalog` table | Routed to the agent at once (D3). Optionally classified once by the small model and stored as an unreviewed proposal; a human review turns it into a route |
| New routing rule | `config/triage.yaml` | Write a rule from the existing conditions and point a catalogue row at it |
| New recommendation | `kb/*.md` | Drop a markdown file in the folder. The search index is rebuilt on start |
| New log line format | `config/parsers.yaml` | Add a regex with named groups. Lines matching no format go to a quarantine table and are counted |
| New or better model | `config/models.yaml` | Change one string. The evaluation suite shows if quality moved |
| New tool for the agent | Not built: today the six tools are fixed in `agent/tools.py` | In production some tools are built in and some come from the user or the user's software, such as a tool that reads one kind of device. A config per deployment lists the tools that are available, and a tool's description tells the agent and the judge what it is for (D23) |

## 5. Shared contracts

These are defined once here. Briefs refer to them by section number. If you need to change one, tell Aviv, change it here, and note it in the decision log.

### 5.1 Repository layout

```
logstore/    parse, template, log shapes, store (exists)
triage/      catalogue, log context and stats, router and rules, handlers, active incidents, incident card
agent/       LLM client, tools, loop, verdict schema, validator, trace
kb/          markdown knowledge (data, not code)
prompts/     versioned prompt files
config/      parsers.yaml, triage.yaml, models.yaml
evals/       harness, metrics, judge, agreement
labeling/    log_shapes.csv, golden_incidents.yaml, judge_labels.csv (data, not code)
notebooks/   exploration, labelling, results
runs/        traces, LLM cache, score tables
docs/        plan/, lab_notes.md, report.md, figures/
scripts/     entry points
tests/       unit tests
```

### 5.2 Database tables

Two database files have the same tables. `data/hpc.db` is loaded whole by `scripts/build_db.py`; it is for tests, labelling, and investigating by hand with the agent's tools. `data/replay.db` starts empty and is written by `scripts/replay.py` (5.5); it is the only one that has incidents, and the evaluation runs on it.

| Table | Columns | Notes |
|---|---|---|
| `log_shapes` | `id`, `component`, `state`, `template` | Exists after Step 1 task 0. A **log shape** is identified by all three values together; `template` is the masked message text, so one template can belong to several log shapes (decision D16) |
| `logs` | `id`, `event_id`, `node`, `component`, `state`, `time`, `flag`, `message`, `bad_time`, `ts`, `original_log`, `log_shape_id`, `n_copies` | Exists. `ts` is text `YYYY-MM-DD HH:MM:SS`, UTC, empty for the 9 lines with an unusable timestamp. One row per event: node, component, state, time and message together are unique. A line that repeats them updates the row to that line and adds one to `n_copies` (decision D15) |
| `log_shape_catalog` | `log_shape_id` (primary key), `route`, `rule`, `handler`, `severity`, `category`, `stats`, `rationale`, `source`, `model`, `reviewed` | New in 2A. The columns from `route` to `stats` mean what they mean in `log_shapes.csv` (5.3). `source` is `human` or `llm` |
| `incidents` | `id`, `log_shape_id`, `route`, `severity`, `status`, `opened_ts`, `last_ts`, `closed_ts`, `n_logs`, `n_nodes`, `agent_started_ts`, `verdict_ts`, `resolved_by` | New in 2A. Written by the replay as the incident changes (5.5). `status` is `open`, `waiting`, `investigating` or `resolved`; `closed_ts` is empty while the incident is active. `resolved_by` is `agent`, `handler`, or the id of the incident whose verdict marked this one resolved. The times are log times |
| `incident_logs` | `incident_id`, `log_id` | New in 2A |
| `routing_decisions` | `log_id`, `route`, `rule_id`, `reason` | New in 2A, lower priority. The audit trail of the router: one row per routed event |
| `quarantine` | `id`, `raw_line`, `reason`, `ingested_at` | New in 2A, lower priority |

A log shape with no row in `log_shape_catalog` is routed to `investigate` (decision D3).

### 5.3 Label files (`labeling/`)

**`log_shapes.csv`**, one row per log shape. Columns: `component`, `state`, `template`, `n_logs`, `n_nodes`, `first_seen`, `last_seen`, `example_1`, `example_2`, `example_3`, `route`, `rule`, `handler`, `severity`, `category`, `stats`, `note`. Aviv fills the columns from `route` on, for a few dozen rows only (decision D21); a row he leaves empty has no catalogue row and goes to the agent.

| Column | Values |
|---|---|
| `route` | `ignore`, `handle`, `investigate`, or `rule` |
| `rule` | When `route` is `rule`: the name of a rule in `config/triage.yaml` (5.5) |
| `handler` | When the route is `handle`, or a case of the rule routes to `handle`: the name of a handler in `triage/handlers.py` |
| `severity` | `low`, `medium`, `high` or `critical`. Sets the incident's TTL and its place in the queue for the agent |
| `stats` | Optional. Names of stats (5.5) put on the card of every incident of this log shape, separated by `;` |

`category` uses one fixed list, finalised in Step 1 and stored in `config/triage.yaml`. Rows routed to `ignore` take one of `telemetry`, `operations`, `recovery`, `info`; the others take a problem category. Starting proposal for problem categories, to be cut to six to eight: `hardware`, `temperature`, `interconnect`, `network`, `filesystem`, `node_state`, `boot`, `scheduler`, `other`.

**`golden_incidents.yaml`**, about 25 entries:

```yaml
- id: g07
  anchor: {component: clusterfilesystem, state: fdmn.full, template: "ServerFileSystem: ...", start: "2004-03-11 02:10:00", end: "2004-03-11 03:40:00", nodes: [node-33]}
  split: dev            # dev | holdout
  is_actionable: true
  category: filesystem
  expected_root_cause: "one sentence"
  must_mention: ["one to three key points a good remediation contains"]
  hindsight: "what happened afterwards, with log ids"
  confidence: high
```

The values above are made up. An incident is identified by its anchor, never by a pipeline id, so labels survive changes to rules and TTLs: its log shape, `start`, the time the incident opens, `end`, the end of the window Aviv used for hindsight, and optionally the nodes. The agent's run starts at `start` and sees only what was visible from then on (5.6), so the expected answer must be one an investigator could reach from the logs up to the opening and the history before it. Hindsight decides how sure the label is; it is not part of what the agent must say. 17 entries are `dev`, 8 are `holdout`.

**`judge_labels.csv`**, one row per human judgment. Columns: `run_file`, `criterion`, `item`, `human_pass`, `note`, `split`, `origin`, `defect_type`. `item` is empty for run-level criteria and the step number for `citation_supports_step`. `human_pass` is `pass` or `fail`. `split` is `tune` or `test`. `origin` is `natural` or `injected`.

### 5.4 Config files (`config/`)

| File | Holds |
|---|---|
| `triage.yaml` | `chunk_minutes` (5), `windows` for stats (default `1h`, `1d`, `7d`, `30d`), `ttl_minutes` per severity (default 15), `max_hours`, `max_agent_runs_per_hour`, the rules (5.5), the category list, the keyword patterns and the phrases that cancel them |
| `models.yaml` | `base_url`, `requests_per_minute`, a model id for each role: `small`, `main`, `judge`, and for each role an assumed price per million tokens in and out, used only to turn tokens into dollars (E7 and the cost section) |
| `parsers.yaml` | Line formats as regexes with named groups, and the template masks. Lower priority |

The NVIDIA key is read from the environment variable `NVIDIA_API_KEY`, kept in `.env`, which git already ignores.

### 5.5 Routing, incidents and the incident card

Decisions D17 to D20. Everything in this section is code; no LLM is involved until an incident reaches the agent.

**Replay and log time.** `scripts/replay.py` is the ingestion flow. It starts from an empty database, sorts the lines of `HPC.log` by their timestamp (the file is not in time order), and ingests them in chunks of `chunk_minutes` of log time. The 9 lines with no usable timestamp cannot be placed; they are left out and counted. Inside a chunk, events are routed in **processing order**: time, then id. A line that merges into a stored event (decision D15) is not routed again. **Log time** is the latest timestamp ingested so far. Every TTL, every wait and every limit on what the agent sees is measured in log time, never by the clock on the wall, so a fast replay behaves as the live stream would.

**LogContext.** Built for each new event. It holds `log`, `log_shape`, `catalogue_row` (empty when the log shape has no row), `keyword_hits` (only for a log shape with no row; computed once per log shape and kept), and any number of extra named fields, passed as `**extra`. Reading a field that is not there raises an error; it never reads as zero or empty. `get(name)` computes a named feature the first time it is asked for and keeps it. Stats are features.

**Stats.** A stat has a count, a scope and a window, written `n_logs.node.1h`. The count is `n_logs` or `n_nodes` (distinct nodes). The scope is `cluster`, all logs of this log shape, or `node`, those on this log's node. The window is one of `windows` in `config/triage.yaml`. A stat counts the logs of the same log shape whose time falls inside the window. The window ends at this log's time and includes it, so the log itself and any other log of the same second are counted. It never counts a log with a later time. Stats are computed only when a rule, the incident card or the agent asks.

- In this repository a stat is one query, `LogRepository.stats`, filtered by log shape, node and time.
- In production stats come from a **cache that is updated in batches as chunks are ingested**. Before a chunk is routed, the cache holds every earlier log. As each log of the chunk is routed it is added, so the cache is current for exactly the next log. A stat is then a lookup, not a scan. This is a design principle of the system and the report states it. Step 1 has an optional task that builds this cache over the database; it must return the same numbers as SQL.

**Router.** `route(ctx)` returns a `Decision` with `route` (`ignore`, `handle` or `investigate`), `rule_id` and `reason`.

1. No reviewed catalogue row: `investigate`, with rule id `unknown_log_shape`. A row an LLM proposed counts only once a human has reviewed it.
2. A row whose route is `ignore`, `handle` or `investigate`: that route, with rule id `catalogue`.
3. A row whose route is `rule`: the result of the rule it names, with the rule's name as rule id.

A **rule** lives in `config/triage.yaml`. It reads one feature and checks its cases in order with the operators `lt`, `le`, `gt`, `ge`, `eq`. The first case that holds gives the route. `else` is required, so a rule always answers.

```yaml
rules:
  burst_on_node:            # a placeholder: Aviv picks the real example in task 1.3
    feature: n_logs.node.1h
    cases:
      - {gt: 3, route: investigate}
    else: ignore
```

Rules are checked when the config is loaded: an unknown feature, operator or route, or a missing `else`, is an error then, not during routing. A new rule from these parts needs no code change; a new kind of condition does.

**Handlers.** A handler is a function in `triage/handlers.py`, named by the catalogue row. It runs once for each node of the incident, including nodes that join later, and returns an answer in the verdict format of 5.7 with `source` set to `handler`. One log shape is routed to a handler in this project; Aviv picks it in task 1.3.

**Active incidents.** At most one incident per log shape is active.

- A log routed to `handle` or `investigate` **opens** an incident when its log shape has none active. The new incident takes in the earlier logs of its shape from the window of the rule that opened it, or from the last TTL when no rule did. This is how the first logs of a burst, which a count rule ignored, become part of the incident.
- Any later log of the shape **joins** the active incident, whatever its own route.
- Routes rank `ignore`, `handle`, `investigate`. A joining log can raise the incident's route and never lowers it. An incident raised from `handle` to `investigate` gets the agent, with the handler's answers on its card. A log routed to `investigate` therefore never opens a second incident beside a `handle` one.
- The **TTL** starts again with every log that joins: `ttl_minutes` for the incident's severity, 15 by default. An incident with no new log for one TTL closes. An incident also closes `max_hours` after it opened; the next log of the shape opens a new one.
- An incident answered by the agent or a handler is **resolved**. It stays active until it closes, so new logs join it, and nothing more is done for it.
- Incidents are never merged (decision D19).
- Active incidents are kept in memory and written to `incidents` and `incident_logs` as they change.

An **incident** has: `id`, `log_shape_id`, `route`, `severity`, `status`, `opened_ts`, `last_ts`, `closed_ts`, `log_ids`, `n_logs`, `n_nodes`.

**Agent runs.**

- An incident whose route is `investigate` gets the agent as soon as it opens or is raised. Ingestion never waits for the agent.
- The agent sees logs only up to **`max_visible_timestamp`**. It starts at the log time at which the run starts, `agent_started_ts`: the opening time, or later for an incident that waited under the cap. From there it grows by the real time the agent takes: the sum of the latencies of its LLM calls and tool calls. So a slow agent sees more of the incident and answers later, and a fast one sees less and answers sooner. The latencies are recorded, and a run replayed from the LLM cache uses the recorded ones, so it sees exactly what the first run saw.
- The verdict lands at log time `agent_started_ts` plus the elapsed time, and `verdict_ts` records it. If the replay is already past that time when the answer arrives, it is applied at once.
- **Cap.** At most `max_agent_runs_per_hour` runs start in any hour of log time. An incident over the cap gets status `waiting`. Waiting incidents are ordered by severity, then, for log shapes with no catalogue row, by keyword hits. When the cap is reached the replay prints a warning that cannot be missed, with a table of the waiting incidents: id, log shape, opened, logs, nodes, severity, waiting since. At the end it prints how many incidents waited and for how long. A waiting incident is investigated even when it closes while it waits. One that another verdict marked resolved is not.
- `python -m scripts.replay --no-agent` routes and opens incidents without calling any model. It is how incidents are counted, and what experiment E7 runs.
- Optional, in Step 2B: a settle time before the agent starts, and updates during a run with the incident's new visible logs.

The **incident card** is the text the agent receives, as of the moment its run starts. It has a fixed size whatever the incident's size: the log shape with its catalogue row, or the words "unknown log shape" with its keyword hits; opening time; log and node counts; `n_logs` and `n_nodes` over the cluster for each window, plus the stats the catalogue row names; the ten busiest nodes with counts; the first five and last five raw lines with their log ids; the handler's answers when the incident was raised from `handle`; one line saying what was left out.

### 5.6 Agent tools

All are read-only. Times are text in the format of `logs.ts`.

| Tool | Parameters | Returns |
|---|---|---|
| `search_logs` | `node`, `component`, `text`, `start`, `end`, `limit` (default 30, at most 50) | Lines `id, ts, node, component, state, message`, newest first, then "N more not shown" |
| `count_logs` | `group_by` (`node`, `log_shape`, `component` or `hour`), `node`, `component`, `text`, `start`, `end` | The 20 largest groups with counts |
| `node_timeline` | `node`, `hours_before` (default 24) | That node's history with runs of the same log shape collapsed to one line with a count |
| `get_stats` | `log_shape_id`, `stats` (names as in 5.5), `node` | The value of each stat as of the visible time. The same code the router uses |
| `related_incidents` | `node`, `component` | The other incidents active at the visible time that involve that node or component: id, log shape, route, status, opened, logs, nodes, and the summary of the verdict if there is one |
| `search_knowledge` | `query`, `k` (default 3) | Passages: `passage_id`, `title`, `text`. Registered only when the configuration has knowledge on |
| `submit_verdict` | The fields of 5.7 | Ends the run and marks the incident resolved, together with the incidents named in `resolves_incident_ids` |

**No look-ahead.** Every tool answers as of `max_visible_timestamp` (5.5), whatever the model asks for: log tools cap `end` at it, and `get_stats` and `related_incidents` describe that moment. When `start` is not given it defaults to 24 hours before the incident opened. A log tool never covers more than 31 days in one call (decision D22); a longer range is a bad argument. A tool called with bad arguments returns an error message to the model; it does not raise.

The tools are plain functions that take the visible time as an argument. Called by hand from a notebook on `data/hpc.db`, with no limit given, they show everything; this is how Aviv investigates when labelling. `related_incidents` reads the `incidents` table, so it needs `data/replay.db`.

### 5.7 Verdict

| Field | Values |
|---|---|
| `verdict` | `actionable`, `benign`, `insufficient_evidence` |
| `severity` | `low`, `medium`, `high`, `critical`. Required when actionable |
| `category` | One of the problem categories of 5.3 |
| `summary` | What happened, two or three sentences |
| `root_cause` | The hypothesis |
| `evidence` | List of `{log_id, why}` |
| `remediation` | List of `{step, reason, citation, risk}`. `citation` is a `passage_id` or empty. `risk` is `safe` or `disruptive` |
| `confidence` | `low`, `medium`, `high` |
| `resolves_incident_ids` | Ids of other active incidents that this verdict also answers, for example the later steps of a cascade. Usually empty. They are marked resolved with this incident; they are not merged into it |
| `source` | `agent` or `handler`. Set by code, not by the model |

A handler's answer (5.5) uses the same fields, so the evaluation and the operator read one format.

### 5.8 Validator

An answer is valid when all of these hold:

1. It parses into the verdict schema.
2. Every `log_id` in `evidence` appeared in a tool result of this run or in the incident card.
3. Every non-empty `citation` is a `passage_id` returned by `search_knowledge` in this run.
4. An `actionable` verdict has a severity and at least one remediation step.
5. Every id in `resolves_incident_ids` was returned by `related_incidents` in this run.

On failure the errors are sent back to the model for one retry. A second failure ends the run with status `validation_failed`.

### 5.9 Trace file

One JSON file per run:

| Field | Content |
|---|---|
| `run_id` | `<config>/<golden_id>__rep<k>` |
| `incident` | The incident fields and the card text, as of the start of the run |
| `config` | Configuration name, model id, prompt version, knowledge on or off, step limit, temperature, repeat number |
| `steps` | In order. Each has `role`, `content`, `tool_calls`, `tool_name`, `tool_args`, `tool_result`, `tokens_in`, `tokens_out`, `latency_ms`, `cached`, and `max_visible_timestamp`, the limit that applied at that step |
| `validation` | Number of attempts and the errors of each failed attempt |
| `review` | Empty unless a reviewer is on (experiment E6). Per criterion: pass or fail and the critique; whether a revision was requested; the reviewer's tokens and latency |
| `verdict` | The final answer, or empty |
| `totals` | `llm_calls`, `tool_calls`, `tokens_in`, `tokens_out`, `latency_ms` |
| `status` | `ok`, `max_steps`, `validation_failed`, `error` |

### 5.10 Agent configurations and run folders

| Configuration | Model role | Knowledge |
|---|---|---|
| `main_nokb` | `main` | off |
| `main_kb` | `main` | on |
| `small_kb` | `small` | on |
| `main_kb_judge` | `main` | on, and the `judge` model reviews the answer once before it is returned. Optional, experiment E6 only |

All use the same prompt version, a step limit of 8 and temperature 0. The prompt tells the model to cite passages when a knowledge tool is available and to leave citations empty otherwise, so that turning knowledge on changes exactly one thing.

| Path | Content | In git |
|---|---|---|
| `runs/eval/<config>/<golden_id>__rep<k>.json` | Traces of evaluation runs | yes |
| `runs/eval/scores.csv`, `summary.csv` | One row per run; one row per configuration | yes |
| `runs/eval/judgements.csv` | Judge output: `run_file`, `criterion`, `item`, `judge_model`, `judge_prompt`, `pass`, `critique` | yes |
| `runs/eval/judge_agreement.csv` | Judge against human labels | yes |
| `runs/eval/injected/` | Traces with one defect injected on purpose, for testing the judge | yes |
| `runs/eval/e1_triage.csv` | Experiment E1: log shape classifiers against Aviv's labels | yes |
| `runs/eval/e7_cost.csv` | Experiment E7: one row per setting of cap and TTL, with agent runs, tokens, dollars and lag | yes |
| `runs/llm_cache/` | Cached LLM responses | yes |
| `runs/scratch/` | Ad-hoc runs | no |

### 5.11 Knowledge base documents

A markdown file in `kb/` with a header holding `id`, `title`, `source_urls`, `categories`. Runbooks have these sections, each a `##` heading: Symptoms in the logs, Likely causes, Checks, Remediation, When to escalate, Sources. A **passage** is one section. Its `passage_id` is `<id>#<section-slug>`, and that is the citation format.

### 5.12 Metrics computed by code

| Metric | Definition |
|---|---|
| Actionable recall | Of incidents labelled actionable, the share the agent called actionable |
| Benign recall | Of incidents labelled benign, the share the agent called benign |
| Abstention rate | Share answered `insufficient_evidence` |
| Validation failure rate | Share of runs whose first answer failed the validator |
| Citation coverage | Share of remediation steps that carry a citation |
| Tool calls, repeated calls, step-limit rate | Per run: calls made, calls identical to an earlier call, whether the limit was hit |
| Tokens, latency | Tokens in and out per run; median and 90th percentile seconds |
| Agent runs per day of logs | From a replay: the number of agent runs started, divided by the days of log time replayed |
| Lag to verdict | Per incident, log time from `opened_ts` to `verdict_ts`: the wait under the cap plus the agent's elapsed time |
| Waiting incidents | How many incidents waited under the cap, and for how long |

### 5.13 Judge criteria

Each is pass or fail, with a short critique written before the verdict. One prompt and one call per criterion.

| Criterion | The judge sees | Question | Unit |
|---|---|---|---|
| `root_cause_match` | Expected root cause; agent's summary and root cause | Do they describe the same cause? | Run |
| `grounded` | The tool results of the trace; agent's summary and root cause | Is every factual claim supported by those results? | Run |
| `citation_supports_step` | One remediation step and the passage it cites | Does the passage support this step? | Step with a citation |

## 6. Experiments

| Id | Comparison | Priority | Run in |
|---|---|---|---|
| E1 | Log shape triage: keyword rule against small model against main model, scored on the few dozen log shapes Aviv labelled | Should | 2B, task B8, once the LLM client exists |
| E2 | `main_nokb` against `main_kb` | Must | 4 |
| E3 | `small_kb` against `main_kb` | Must | 4 |
| E4 | Group the failures of the best configuration, fix the most common type, re-run | Should | 4 |
| E5 | Three repeats per incident | Could | 4 |
| E6 | `main_kb` against `main_kb_judge`: the judge reviews the answer once before it is returned (decision D14) | Could | 4 |
| E7 | Cost against lag: replays with different agent caps and TTLs, and with no active incidents at all. Tokens and dollars per incident and per day against the lag to verdict (decisions D19, D20) | Should | 4 |

## 7. Time budget and cut lines

About 20 focused hours over two days. Step 2A grew from 2 to 4 hours on 2026-10-10, when triage became routing with active incidents.

| Block | Hours | Day |
|---|---|---|
| Step 1 | 3.0 | 1 |
| Step 2A | 4.0 | 1 |
| Step 2B | 3.5 | 1 |
| Step 2C | 1.5 | 2 |
| Step 3 | 4.0 | 2 |
| Step 4 | 1.5 | 2 |
| Step 5 | 2.5 | 2 |

**Checkpoint, end of day 1:** one golden incident runs end to end and produces a verdict and a readable trace. If not, skip the LLM log shape classifier and E1, and use Aviv's labels alone as the catalogue.

**If behind, cut in this order:** the optional tasks (the stats cache, the settle time, updates to the agent during a run), E6, E5, injected defects, a second judge model, E4, E7, the third judge criterion, the two-model comparison in E1.

**Never cut:** the knowledge base with citations, the golden incidents, at least one judge criterion calibrated against Aviv's labels, E2, the ingestion diagram, the README, the "what I learned" section.

## 8. Skills the project should show

| Skill from the job description | Evidence |
|---|---|
| Develop training and evaluation data | Log shape labels; golden incidents labelled with hindsight; judge calibration labels; injected defects |
| Select the right model | Model smoke test; E1 and E3; a judge from a different family |
| Own model and agent evaluation | Step 3: code metrics, reference checks, a judge calibrated on a held-out half |
| Run controlled experiments | E1 to E4: hypothesis first, one factor, a baseline, a holdout |
| Build agent infrastructure | Tool loop, structured output, validator with retry, backoff, cache, tracing, versioned prompts; the router, active incidents with a TTL in log time, and the cap on agent runs |
| Hallucinations, tool use, context limits | The validator and its failure rate; no look-ahead, with a visible time that moves as the agent works; incident cards and capped tool results; the step limit |
| Benchmarks across quality, latency, cost | The results table, the cost projection, and E7's cost against lag |
| Design multi-agent systems | Partial: three LLM roles with different models. If E6 is run, an investigator and a reviewer with the reviewer's effect measured; otherwise a verifier agent argued for as a next step |

## 9. Working rules for executing chats

- Follow `AGENTS.md`: one stage at a time, re-read a file immediately before editing it, targeted edits only, no findings or reasoning in notebook markdown or code comments, a summary of each module after writing it, a suggested commit after each working stage.
- **Explain as you go.** Aviv is new to LLM agents and to HPC cluster operations. When a concept in the brief's "Concepts to explain" list comes up, explain it in two or three sentences before using it.
- **Keep core logic short and explicit.** He must be able to defend the classification rule, the agent loop, the prompts and the evaluation line by line. Prefer forty obvious lines to fifteen clever ones.
- **"Run on a representative sample of 1000 logs"** means: for parsing and templating, the existing random `--sample 1000`. For routing, incidents and the agent, a replay of a contiguous slice of time (the sample week of Step 1), because a random sample destroys the time structure that incidents depend on.
- **Test core logic** with unit tests: stats that never count a later log, the router and the checks on rules, active incidents (join, raise, TTL and maximum duration in log time), the cap and its queue, the incident card's size limit, the tools' visible-time limit, the validator, the LLM cache, the agent loop against a scripted fake model. No test may call the network.
- **Library documentation:** use Context7 for the OpenAI client, pydantic, PyYAML and rank_bm25. Check NVIDIA model ids against the live catalogue; never take them from memory or from these documents.
- **Dependencies:** when you add a package, pin it in `requirements.txt` in the same commit. Expected additions: pydantic, PyYAML, rank_bm25, python-dotenv for reading `.env`, and nbconvert for running a notebook from the command line (already pinned; the command is in the Python rule below).
- **Python:** the project runs on Python 3.14 (agreed in Step 1). It is the default `python` on this machine, and the pinned requirements are installed there. A notebook is re-run from the repository root with `python -m nbconvert --config jupyter_nbconvert_config.py --to notebook --execute --inplace <notebook>`. The config makes the run repeatable: an unchanged notebook writes the same file byte for byte. Do not use `python -m jupyter nbconvert`: on this machine it runs the notebook on the Python 3.13 install.
- **Secrets:** the key stays in `.env`. Never print it, never commit it.
- **Lab notes:** one short dated entry per work session in Part 2 of `docs/lab_notes.md`: what was done, what was found, what was learned. It should read smoothly, as the story of the progress made. Write outcomes only: no rejected ideas, no back-and-forth, no open questions. A decision that shapes the system gets an entry in Part 1; smaller choices do not. Each brief ends with the questions its notes should answer.
- **Every number has code behind it.** A number written into the report, the lab notes or these documents comes from a notebook or script in the repo, saved with its output, and the text says where. A number from a throwaway script does not go into the repo until that code does.
- **Write the hypothesis before the run.** For every experiment, the expected result goes into lab notes before the numbers exist.
- **Numbers in these documents marked "rough" were measured during planning with a crude keyword filter.** Re-measure before quoting them.

## 10. Open items

| Item | Current assumption |
|---|---|
| Model access | NVIDIA only. If Aviv has a key for a stronger model, use it only as the judge |
| Hours available | 20. If closer to 10, drop the two-model comparison in E1, E4, injected defects and the third judge criterion from the start |
| Two changed lines in `AGENTS.md` on the `labeling-helper` branch ("detailed summary", "run all tests after large changes") | Settled in Step 1 task 0: the test rule was taken, "detailed summary" was not |
| Agent framework | Hand-written loop (decision D10). Aviv may still switch to LangGraph before 2B starts |
