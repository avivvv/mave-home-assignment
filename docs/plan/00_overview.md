# Plan overview: HPC log problem-resolution system

Written on 2026-10-06. This is the shared reference for every chat that works on the project.

## 1. How to use these documents

**Who reads this.** A chat that executes one step, with no memory of earlier chats, and Aviv, who reviews.

**Reading order.** `AGENTS.md` (loaded automatically), this file, the brief for the step you are executing, and Part 1 of [docs/lab_notes.md](../lab_notes.md), the decision log.

**One step per chat.** Step 2 has three parts and each part is its own chat. Steps depend on each other in order: do not start a step whose "Before you start" list is not satisfied.

| Brief | Covers |
|---|---|
| [01_data_and_golden_set.md](01_data_and_golden_set.md) | Bring the code base into shape, understand the data, label templates, write the golden incidents |
| [02_pipeline_and_agent.md](02_pipeline_and_agent.md) | Part A triage, Part B agent without knowledge, Part C knowledge base |
| [03_evaluation_and_judge.md](03_evaluation_and_judge.md) | Evaluation harness, code metrics, the judge and its calibration |
| [04_experiments.md](04_experiments.md) | Controlled experiments, cost and latency, the holdout run |
| [05_report.md](05_report.md) | Report, README, ingestion diagram |

**These documents describe design, not code.** Where a brief names a file, a function, a column or a field, the name is fixed, because other steps rely on it. How you implement it is yours to decide with Aviv.

**The plan is expected to change.** When something you find contradicts a brief, stop and tell Aviv. If a decision changes, amend the decision log and the affected brief or contract in the same session. Never deviate silently.

**At the end of every session:** update the status table below, add dated notes to `docs/lab_notes.md`, and suggest a commit.

## 2. Status

| Step | State | Notes |
|---|---|---|
| 1. Data and golden set | not started | |
| 2A. Triage | not started | |
| 2B. Agent without knowledge | not started | |
| 2C. Knowledge base | not started | |
| 3. Evaluation and judge | not started | |
| 4. Experiments | not started | |
| 5. Report | not started | Lab notes are running from day 1 |

**Repo state on 2026-10-06, before Step 1:**

- `main` has a tested SQLite log store in `logstore/`, a build script, two EDA notebooks (since moved to `notebooks/`). No triage, agent, knowledge base, evaluation or report.
- A local branch `labeling-helper` holds later work. Aviv decided to take **only its log store changes** (decision D13). Step 1 task 0 brings them over. Its `labeling/` package, notebook and their tests stay on the branch and must not be imported.
- `data/hpc.db` on disk was built from that branch, so it does not match the code on `main` until task 0 is done. It still contains identical copies of lines.
- There is an empty `labeling/` folder on `main` with a stale `__pycache__`. It becomes the home of the label files.
- No template labels exist yet.

## 3. The assignment, and what is graded

Build a system that processes HPC logs, identifies errors, and recommends specific remediation steps backed by citations and reasons. It must adapt to new log templates, formats and recommendations without code changes, and be realistic about cost and latency. Deliverables: a GitHub repository with a report and a README with exact run instructions. A diagram of data ingestion is required; implementing ingestion is not.

Three phrases in the assignment carry most of the weight, and the design answers each one:

1. **"Use the right tool for the job."** Deterministic code does the bulk work. An LLM is called only where judgment is needed. Every stage below is marked code or LLM.
2. **"Back them up with citations and reasons."** A citation counts only if the agent really retrieved that passage during the run, and a program checks this.
3. **"New logs and recommendations are introduced occasionally."** Everything that changes over time lives in data (a table, a markdown folder, a config file), not in Python.

The role is about evaluation as much as building: about a third of the time goes to measurement, and the agent is deliberately simple.

## 4. The system

```
HPC.log
  |  parse line (regex per format)            code   logstore/parsing.py
  |  drop identical copies                    code   logstore/ingest.py
  |  mask variables -> template               code   logstore/templating.py
  v
SQLite log store                                     logstore/
  |  template catalogue: alert or not, category      human labels for known templates;
  |                                                  LLM once per NEW template, cached; human can override
  |  group alert logs into incidents                 code   triage/
  v
incident, shown to the agent as a compact "card"
  |  investigator agent: loop of tool calls          LLM    agent/
  |     tools: search_logs, count_logs, node_timeline, search_knowledge
  |  validator: schema ok, every cited log id and passage really appeared in a tool result   code, one retry
  v
verdict (JSON) + full trace (JSON)                   runs/
  |
  v  offline
evaluation: code metrics, comparison to expected answers, calibrated LLM judge    evals/
```

| Stage | Tool | Reason |
|---|---|---|
| Parse, drop copies, template | Code | Deterministic, runs on every line, must cost nothing |
| Is this template an alert? | Human label, or LLM once per new template | Needs judgment, but the answer never changes for a given template, so it is decided once and stored |
| Group into incidents | Code | A time-gap rule, transparent and tunable from config |
| Investigate, explain, recommend | LLM agent with tools | The only stage that needs multi-step reasoning over evidence |
| Check that citations and evidence exist | Code | A fabricated log id is a fact about the trace, not an opinion |
| Is the diagnosis right, grounded, supported by its citation? | LLM judge | Semantic. The only place a judge is used |

| What changes over time | Where it lives | What happens with no code change |
|---|---|---|
| New log template | `template_catalog` table | Classified once by the small model and stored as unreviewed. Until then it counts as an alert |
| New recommendation | `kb/*.md` | Drop a markdown file in the folder. The search index is rebuilt on start |
| New log line format | `config/parsers.yaml` | Add a regex with named groups. Lines matching no format go to a quarantine table and are counted |
| New or better model | `config/models.yaml` | Change one string. The evaluation suite shows if quality moved |

## 5. Shared contracts

These are defined once here. Briefs refer to them by section number. If you need to change one, tell Aviv, change it here, and note it in the decision log.

### 5.1 Repository layout

```
logstore/    parse, template, store (exists)
triage/      catalogue, incident grouping, incident card
agent/       LLM client, tools, loop, verdict schema, validator, trace
kb/          markdown knowledge (data, not code)
prompts/     versioned prompt files
config/      parsers.yaml, triage.yaml, models.yaml
evals/       harness, metrics, judge, agreement
labeling/    templates.csv, golden_incidents.yaml, judge_labels.csv (data, not code)
notebooks/   exploration, labelling, results
runs/        traces, LLM cache, score tables
docs/        plan/, lab_notes.md, report.md, figures/
scripts/     entry points
tests/       unit tests
```

### 5.2 Database tables (`data/hpc.db`)

| Table | Columns | Notes |
|---|---|---|
| `templates` | `id`, `component`, `state`, `template` | Exists after Step 1 task 0. A template is identified by all three values, called the **template key** |
| `logs` | `id`, `event_id`, `node`, `component`, `state`, `time`, `flag`, `message`, `bad_time`, `ts`, `original_log`, `template_id` | Exists. `ts` is text `YYYY-MM-DD HH:MM:SS`, UTC, empty for the 9 lines with an unusable timestamp |
| `template_catalog` | `template_id` (primary key), `is_alert`, `category`, `rationale`, `source`, `model`, `reviewed` | New in 2A. `source` is `human`, `llm`, `keyword` or `default` |
| `incidents` | `id`, `component`, `start_ts`, `end_ts`, `n_logs`, `n_nodes`, `signature` | New in 2A. `signature` is the component plus its sorted distinct template ids |
| `incident_logs` | `incident_id`, `log_id` | New in 2A |
| `quarantine` | `id`, `raw_line`, `reason`, `ingested_at` | New in 2A, lower priority |

A template with no row in `template_catalog` counts as an alert (decision D3).

### 5.3 Label files (`labeling/`)

**`templates.csv`**, one row per template key. Columns: `component`, `state`, `template`, `n_logs`, `n_nodes`, `first_seen`, `last_seen`, `example_1`, `example_2`, `example_3`, `is_alert`, `category`, `note`. Aviv fills the last three. `is_alert` is `yes` or `no`.

`category` uses one fixed list, finalised in Step 1 and stored in `config/triage.yaml`. Alert rows take a problem category; non-alert rows take one of `telemetry`, `operations`, `recovery`, `info`. Starting proposal for problem categories, to be cut to six to eight: `hardware`, `temperature`, `interconnect`, `network`, `filesystem`, `node_state`, `boot`, `scheduler`, `other`.

**`golden_incidents.yaml`**, about 25 entries:

```yaml
- id: g07
  anchor: {component: clusterfilesystem, start: "2004-03-11 02:10:00", end: "2004-03-11 03:40:00", nodes: [node-33]}
  split: dev            # dev | holdout
  is_actionable: true
  category: filesystem
  expected_root_cause: "one sentence"
  must_mention: ["one to three key points a good remediation contains"]
  hindsight: "what happened afterwards, with log ids"
  confidence: high
```

The values above are made up. An incident is identified by its anchor (component, time window, optional nodes), never by a pipeline id, so labels survive changes to the grouping rule. 17 entries are `dev`, 8 are `holdout`.

**`judge_labels.csv`**, one row per human judgment. Columns: `run_file`, `criterion`, `item`, `human_pass`, `note`, `split`, `origin`, `defect_type`. `item` is empty for run-level criteria and the step number for `citation_supports_step`. `human_pass` is `pass` or `fail`. `split` is `tune` or `test`. `origin` is `natural` or `injected`.

### 5.4 Config files (`config/`)

| File | Holds |
|---|---|
| `triage.yaml` | `gap_minutes`, `max_hours`, the category list, the keyword baseline patterns |
| `models.yaml` | `base_url`, `requests_per_minute`, and a model id for each role: `small`, `main`, `judge` |
| `parsers.yaml` | Line formats as regexes with named groups, and the template masks. Lower priority |

The NVIDIA key is read from the environment variable `NVIDIA_API_KEY`, kept in `.env`, which git already ignores.

### 5.5 Incident and incident card

An **incident** has: `id` (empty when built from an anchor), `component`, `start_ts`, `end_ts`, `log_ids`, `n_logs`, `n_nodes`, `template_ids`, `signature`.

**Grouping rule.** Take logs whose template is an alert, with a usable timestamp, per component, in time order. A new incident starts when the gap to the previous log exceeds `gap_minutes`, or when the incident would exceed `max_hours`.

The **incident card** is the text the agent receives. It has a fixed size whatever the incident's size: component, time range, duration, log and node counts; the ten most frequent templates with counts; the templates in order of first appearance, each with the time and node of its first line; the ten busiest nodes with counts; the first five and last five raw lines with their log ids; one line saying what was left out.

### 5.6 Agent tools

All are read-only. Times are text in the format of `logs.ts`.

| Tool | Parameters | Returns |
|---|---|---|
| `search_logs` | `node`, `component`, `text`, `start`, `end`, `limit` (default 30, at most 50) | Lines `id, ts, node, component, state, message`, oldest first, then "N more not shown" |
| `count_logs` | `group_by` (`node`, `template`, `component` or `hour`), `node`, `component`, `text`, `start`, `end` | The 20 largest groups with counts |
| `node_timeline` | `node`, `hours_before` (default 24) | That node's history with runs of the same template collapsed to one line with a count |
| `search_knowledge` | `query`, `k` (default 3) | Passages: `passage_id`, `title`, `text`. Registered only when the configuration has knowledge on |
| `submit_verdict` | The fields of 5.7 | Ends the run |

**No look-ahead.** Every log tool caps `end` at the incident's `end_ts`, whatever the model asks for. When `start` is not given it defaults to 24 hours before the incident's start. A tool called with bad arguments returns an error message to the model; it does not raise.

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

### 5.8 Validator

An answer is valid when all of these hold:

1. It parses into the verdict schema.
2. Every `log_id` in `evidence` appeared in a tool result of this run or in the incident card.
3. Every non-empty `citation` is a `passage_id` returned by `search_knowledge` in this run.
4. An `actionable` verdict has a severity and at least one remediation step.

On failure the errors are sent back to the model for one retry. A second failure ends the run with status `validation_failed`.

### 5.9 Trace file

One JSON file per run:

| Field | Content |
|---|---|
| `run_id` | `<config>/<golden_id>__rep<k>` |
| `incident` | The incident fields and the card text |
| `config` | Configuration name, model id, prompt version, knowledge on or off, step limit, temperature, repeat number |
| `steps` | In order. Each has `role`, `content`, `tool_calls`, `tool_name`, `tool_args`, `tool_result`, `tokens_in`, `tokens_out`, `latency_ms`, `cached` |
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
| `runs/eval/e1_triage.csv` | Experiment E1: template classifiers against Aviv's labels | yes |
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
| E1 | Template triage: keyword rule against small model against main model, scored on Aviv's labels | Should | 2B, task B7, once the LLM client exists |
| E2 | `main_nokb` against `main_kb` | Must | 4 |
| E3 | `small_kb` against `main_kb` | Must | 4 |
| E4 | Group the failures of the best configuration, fix the most common type, re-run | Should | 4 |
| E5 | Three repeats per incident | Could | 4 |
| E6 | `main_kb` against `main_kb_judge`: the judge reviews the answer once before it is returned (decision D14) | Could | 4 |

## 7. Time budget and cut lines

About 18 focused hours over two days.

| Block | Hours | Day |
|---|---|---|
| Step 1 | 3.0 | 1 |
| Step 2A | 2.0 | 1 |
| Step 2B | 3.5 | 1 |
| Step 2C | 1.5 | 2 |
| Step 3 | 4.0 | 2 |
| Step 4 | 1.5 | 2 |
| Step 5 | 2.5 | 2 |

**Checkpoint, end of day 1:** one golden incident runs end to end and produces a verdict and a readable trace. If not, skip the LLM template classifier and E1, and use Aviv's labels alone as the catalogue.

**If behind, cut in this order:** E6, E5, injected defects, a second judge model, E4, the third judge criterion, the two-model comparison in E1.

**Never cut:** the knowledge base with citations, the golden incidents, at least one judge criterion calibrated against Aviv's labels, E2, the ingestion diagram, the README, the "what I learned" section.

## 8. Skills the project should show

| Skill from the job description | Evidence |
|---|---|
| Develop training and evaluation data | Template labels; golden incidents labelled with hindsight; judge calibration labels; injected defects |
| Select the right model | Model smoke test; E1 and E3; a judge from a different family |
| Own model and agent evaluation | Step 3: code metrics, reference checks, a judge calibrated on a held-out half |
| Run controlled experiments | E1 to E4: hypothesis first, one factor, a baseline, a holdout |
| Build agent infrastructure | Tool loop, structured output, validator with retry, backoff, cache, tracing, versioned prompts |
| Hallucinations, tool use, context limits | The validator and its failure rate; no look-ahead; incident cards and capped tool results; the step limit |
| Benchmarks across quality, latency, cost | The results table and the cost projection |
| Design multi-agent systems | Partial: three LLM roles with different models. If E6 is run, an investigator and a reviewer with the reviewer's effect measured; otherwise a verifier agent argued for as a next step |

## 9. Working rules for executing chats

- Follow `AGENTS.md`: one stage at a time, re-read a file immediately before editing it, targeted edits only, no findings or reasoning in notebook markdown or code comments, a summary of each module after writing it, a suggested commit after each working stage.
- **Explain as you go.** Aviv is new to LLM agents and to HPC cluster operations. When a concept in the brief's "Concepts to explain" list comes up, explain it in two or three sentences before using it.
- **Keep core logic short and explicit.** He must be able to defend the classification rule, the agent loop, the prompts and the evaluation line by line. Prefer forty obvious lines to fifteen clever ones.
- **"Run on a representative sample of 1000 logs"** means: for parsing and templating, the existing random `--sample 1000`. For grouping and the agent, a contiguous slice of time, because a random sample destroys the time structure that incidents depend on. The agent's tools always query the full database.
- **Test core logic** with unit tests: grouping, the incident card's size limit, the tools' time cap, the validator, the cache, the agent loop against a scripted fake model. No test may call the network.
- **Library documentation:** use Context7 for the OpenAI client, pydantic, PyYAML and rank_bm25. Check NVIDIA model ids against the live catalogue; never take them from memory or from these documents.
- **Dependencies:** when you add a package, pin it in `requirements.txt` in the same commit. Expected additions: pydantic, PyYAML, rank_bm25, python-dotenv for reading `.env`, and nbconvert for running a notebook from the command line (`python -m jupyter nbconvert --to notebook --execute --inplace <notebook>`).
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
| Two changed lines in `AGENTS.md` on the `labeling-helper` branch ("detailed summary", "run all tests after large changes") | Not taken. Ask Aviv in Step 1 task 0 |
| Agent framework | Hand-written loop (decision D10). Aviv may still switch to LangGraph before 2B starts |
