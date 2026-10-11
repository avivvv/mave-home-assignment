# HPC log problem-resolution system

A small end-to-end system that reads the logs of a high-performance computing (HPC) cluster, investigates with an LLM agent, and returns a verdict with evidence and remediation steps. Everything the agent does is logged and can be replayed, and a second part of the repository evaluates how well it works.

This is a take-home assignment for a Data Scientist role at Mave Security, built in about 4 work days. It is a prototype, not a product. The sections [What was built](#what-was-built-and-what-was-not) and [Limitations](#limitations) say plainly where it stops.

# TL;DR -

### (A) Report sits in `report.md`

### (B) Minimal demonstration to run:

1. `pip install -r requirements.txt`
2. fill in the `NVIDIA_API_KEY` entry in a `.env` file (or don't, most llm calls will still work because they are cached and I saved the cache to git)
3. `python -m scripts.build_db --rebuild`
4. `python -m scripts.investigate --case c12 --judge`

Other options appear below, under [Quick start: from a clone to a verdict](#quick-start-from-a-clone-to-a-verdict)
And you can also run the many Jupyter notebooks - see [`notebooks/`](notebooks/README.md) and [`notebooks/incidents/`](notebooks/incidents/README.md).


# The longer readme -

## Contents

- [The assignment](#the-assignment)
- [What was built, and what was not](#what-was-built-and-what-was-not)
- [How it works](#how-it-works)
- [Setup](#setup)
- [Quick start: from a clone to a verdict](#quick-start-from-a-clone-to-a-verdict)
- [Scripts](#scripts)
- [Code modules](#code-modules)
- [Notebooks](#notebooks)
- [Data, labels, knowledge, prompts, configuration, runs](#data-labels-knowledge-prompts-configuration-runs)
- [Tests](#tests)
- [Results so far](#results-so-far)
- [Limitations](#limitations)
- [Documentation](#documentation)
- [Repository layout](#repository-layout)

## The assignment

> **DS Home Assignment: Building a Problem Resolution System for HPC Logs**
>
> High performance computing (HPC) combines computing resources to achieve performance beyond a single computer, using either custom supercomputers or clusters of individual machines.
> Your task is to build an intelligent system that not only analyzes HPC logs but creates an end-to-end workflow for automated problem resolution. The goal is to reduce downtime by providing precise and actionable recommendations. The solution should be designed to handle evolving log formats and recommendations, making it "future-proof." While latency is not the primary concern, take into consideration that you want this to function in a real-world environment where cost and latency are important.

The data is the public HPC dataset from [Loghub](https://github.com/logpai/loghub): 433,490 log records from "System 20" at Los Alamos National Laboratory, written between July 2003 and April 2006. It comes with no labels and no documentation of its columns. The file is committed at `data/original_dataset/HPC.log`.

## What was built, and what was not

**Built and working:**

- A **log store**: the log file parsed into SQLite, one row per event, with every message reduced to a *log shape* (component, state, and the message with its variable parts masked). Repeated lines are merged into one row. New messages become new log shapes automatically, with no code change.
- An **investigator agent**: a hand-written tool-calling loop over the OpenAI client pointed at NVIDIA's hosted models. The agent starts from one log and a fixed starting context, calls read-only tools over the log store, and ends with a structured verdict (actionable, benign, or insufficient evidence) with severity, evidence lines, and remediation steps. It never sees a log written after the one it investigates.
- A **knowledge base** of one file, a fact sheet about the cluster, split into passages and searched by BM25 through an optional tool. Citations name passage ids, and code records whether each cited passage was really retrieved.
- An **event log** of every investigation (`runs/agent.db`) and an **LLM cache** (`runs/llm_cache/`), both committed, so a run that was made once replays without an API key.
- An **evaluation**: deterministic code checks on every trajectory, an LLM judge with six pass/fail criteria on every trajectory that has a verdict, and five figures. Ten hand-investigated "golden" cases were run under three agent configurations.
- Hand investigations of one log for each of the 17 most common log shapes, in notebooks, which produced the golden cases and the agent's tools.

**Designed but not built** (the designs are in `docs/plan/00_overview.md` and `docs/plan/future_work.md`):

- Routing of each new log by a human-labelled catalogue of log shapes, with named rules and deterministic handlers for known fixes.
- Grouping logs into incidents with a time-to-live, so that a burst of a thousand lines costs one agent run instead of a thousand.
- Calibration of the llm-as-judge against verified human labels, with a human that knows what they are doing.
- Runbooks in the knowledge base. The knowledge is one fact sheet, and no remediation step in any saved run cites it.
- More system components, architectural improvements, more experiments to be carried out, more options for llm configurations implemented and tested, etc. - all explained in the `report.md`.

Today, **one agent run costs one log**, about 6,000 input tokens before any tool result and up to four rounds. This cannot run on every log of a real stream, and the plan documents say how the cost would be brought down to the number of distinct problems.

## How it works

```
data/original_dataset/HPC.log
  |  parse each line                                   logstore/parsing.py
  |  mask variables in the message -> template         logstore/templating.py
  |  log shape = (component, state, template)          logstore/repositories.py
  |  one row per event; a repeated line is merged      logstore/repositories.py
  v
data/hpc.db   (SQLite: tables logs, log_shapes)        scripts/build_db.py
  |
  |  one log to investigate (a golden case, or any raw line)
  v
starting context: the log, its source's last hour,     agent/context.py
  the same log shape across the cluster in that hour
  |
  v
investigator loop, at most 4 rounds                    agent/loop.py
  |  model answers with tool calls -> run, send back   agent/tools.py  (6 log tools, +1 knowledge tool)
  |  or with submit_verdict -> validated by schema     agent/schema.py
  |  every event written under one request id         agent/trajectory.py -> runs/agent.db
  v
verdict JSON + full trajectory text
  |
  v  offline
evals/score.py   code checks on every trajectory
agent/judge.py   LLM judge on every trajectory with a verdict
evals/figures.py five figures -> docs/figures/
```

**The tools the agent has.** All read-only, all bounded to a time range of at most 31 days, and all capped at the time of the log under investigation so the agent cannot look into the future. Each result row carries an id (a log id or a log shape id), and the tool returns the ids it showed, which is how evidence lines are checked.

| Tool | What it returns |
|---|---|
| `search_logs` | The logs of a time range that pass filters (source, component, state, text, log shape), newest first, at most 50 |
| `node_timeline` | Everything one source logged in a range, with runs of the same log shape collapsed into one line |
| `log_shapes_between` | Every log shape seen in a range, in order of first appearance, with counts |
| `count_logs` | Log counts per source, component, or hour |
| `find_log_shapes` | The log shapes seen so far that match a text, component, or state, with their history |
| `what_followed` | Hindsight on past occurrences of a log shape: what the same source logged shortly after each |
| `search_knowledge` | Passages of the knowledge base that match a query. Present only when `knowledge: true` in `config/models.yaml` or `--kb` is passed |

**The verdict** is a pydantic schema (`agent/schema.py`): `verdict`, `severity`, `category`, `scope`, `summary`, `root_cause`, a list of `evidence` lines each with a `why`, a list of `remediation` steps each with a `reason`, a `risk` (safe or disruptive), and an optional `citation`, and `confidence`. An actionable verdict must have a severity and at least one step. Code then records, without rejecting, evidence lines that name no id the agent was shown and citations that name no passage it retrieved.

**The judge** (`agent/judge.py`, prompt `prompts/judge_v1.md`) reads one complete trajectory and nothing else, no expected answer, and grades six criteria pass or fail: grounded, sufficient investigation, tool use, efficiency, verdict supported, remediation quality. It uses a model from a different family than the investigator.

**Models.** All LLM calls go through `agent/llm.py`, which reads `config/models.yaml`: the NVIDIA endpoint, one model per role (`main` for the investigator, `judge`), request spacing for the free tier's rate limit, retries, a timeout, and per-role options such as the investigator's hidden-thinking budget. Every reply is cached on disk under a hash of the whole request.

## Setup

Requirements: Python 3.14 (the version the project was developed and tested on), and an NVIDIA API key for anything that calls a model.

```
pip install -r requirements.txt
```

**The `.env` file is gitignored, so a clone does not have one. If you want to run any LLM call that has not already been stored in `runs/llm_cache/`, you need an `NVIDIA_API_KEY`.** Replaying a cached run needs no key. Put the key in a file named `.env` at the repository root:

```
NVIDIA_API_KEY=...
```

Every command below is run from the repository root with `python -m ...`, so that the packages import.

## Quick start: from a clone to a verdict

1. **Build the database.** Loads `HPC.log` into `data/hpc.db` (gitignored). Takes well under a minute.

   ```
   python -m scripts.build_db --rebuild
   ```

   It prints the counts: 411,483 logs, 22,007 merged copies, 141 log shapes, 9 logs with an unusable timestamp. Without `--rebuild` it refuses to load into a database that already holds logs.

2. **Run the unit tests.** No network is used.

   ```
   python -m pytest
   ```

3. **Investigate one golden case** and print its trajectory and verdict. This calls the models unless the exact same request is in the cache.

   ```
   python -m scripts.investigate --case c12
   ```

   Case c12 is a `not responding` log from node-221 that turns out to be the first minute of a cluster-wide outage. Add `--judge` to also print the judge's grades.

4. **Evaluate every saved trajectory.** Reads the 30 committed trajectories, runs the code checks, calls the judge (from the cache, so no key is needed), and writes `runs/eval/*.csv` and the figures in `docs/figures/`. Re-running it on an unchanged repository reproduces the committed files byte for byte.

   ```
   python -m scripts.evaluate_trajectories
   ```

## Scripts

All in `scripts/`, all run from the repository root. "Models" says whether the script calls the NVIDIA API.

| Command | What it does | Models | Writes |
|---|---|---|---|
| `python -m scripts.build_db --rebuild` | Loads `data/original_dataset/HPC.log` into `data/hpc.db`: parses lines, masks messages, registers log shapes, merges repeated lines, builds indexes, prints the counts. Options: `--log PATH`, `--db PATH`, `--sample N` (N random lines, fixed seed), `--rebuild` (delete the database first). Refuses to load into a non-empty database without `--rebuild` | No | `data/hpc.db` |
| `python -m scripts.investigate --case c12` | Investigates one log with the agent and prints the trajectory, the verdict, and the totals (rounds, calls, tokens, seconds). `--case ID` takes a golden case from `labeling/golden_cases.yaml`; `--line "<raw line>"` takes any line of `HPC.log`, which must be in the database, character for character. `--judge` also grades the trajectory. `--fresh` ignores the cache. `--kb` gives the agent the knowledge tool for this run | Yes, unless cached | A new request in `runs/agent.db`; new replies in `runs/llm_cache/` |
| `python -m scripts.evaluate_trajectories` | Scores every trajectory file in `labeling/trajectories/` (events are read from `runs/agent.db`), calls the judge on those with a verdict, summarises per configuration, and draws five figures. `--only c01_ c12_` restricts to files whose name starts with one of the prefixes; note that this overwrites the output files with the subset. Prints a warning on every run that the judge is not calibrated | Judge only, from cache for the committed trajectories | `runs/eval/trajectory_scores.csv`, `runs/eval/judgements.csv`, `runs/eval/summary.csv`, `docs/figures/eval_*.png` |
| `python -m scripts.db_smoke_test` | Builds a 1,000-line sample into `data/smoke_test.db`, ingests three more lines through the API (a known shape, a new shape, garbage), reads them back and checks every read | No | `data/smoke_test.db` (gitignored) |
| `python -m scripts.agent_smoke_test` | Three single calls to the real models on four made-up logs: the investigator's first round (it must choose tools), its last round (it must submit a valid verdict), and the judge on a plainly bad trajectory (it must fail it). No retry, no cache | Yes, 3 calls | `runs/scratch/` (gitignored) |
| `python -m scripts.eval_smoke_test` | Runs the whole of `evaluate_trajectories` on one committed trajectory and checks the shape of every output. The judge's reply is read from the cache | Judge only, from cache | `runs/scratch/eval_smoke/` (gitignored) |
| `python -m scripts.kb_smoke_test` | Builds the knowledge base from `kb/`, lists the passages, checks that a question the fact sheet answers finds the right passage first and a nonsense query finds nothing, and runs the tool with knowledge on and off | No | Nothing |

Every command in this table was run on 2026-10-11 and finished as described. The three smoke tests print `SMOKE TEST PASSED` or raise.

## Code modules

Each is a plain Python package with no entry point of its own.

**`logstore/`: the log store**

| File | Purpose |
|---|---|
| `parsing.py` | The regex that reads one line of `HPC.log` into its fields (record counter, source, component, state, epoch time, flag, message); reading the file; sampling lines with a fixed seed. A line that does not match is reported, not dropped silently |
| `templating.py` | The ordered masks that turn a message into a template: quoted names, hex values, node names and node sets, numbers, asterisks, lists collapsed to one item |
| `models.py` | Dataclasses: `Log`, `LogShape`, `LogStats`, `TimelineEntry` |
| `db.py` | The SQLite schema (`logs`, `log_shapes`), the indexes, `connect` |
| `repositories.py` | `LogShapeRepository` (add, list, search by text/component/state) and `LogRepository` (bulk insert that merges repeated events; `search`, `count_by`, `stats`, `node_timeline`, all over a required time range of at most 31 days; `find_by_line`; `shape_history`) |
| `ingest.py` | `ingest_lines`: parse, template, register shapes, store; returns what was inserted, merged, and unparsed |

**`agent/`: the investigator, the judge, and their record**

| File | Purpose |
|---|---|
| `llm.py` | The one entry point for every model call. Adds a disk cache keyed on the whole request, spacing between calls for the rate limit, and one error type. Reads `config/models.yaml` and the key from `.env` |
| `tools.py` | `LogTools`: the queries an investigation is made of, with a `visible` time that no read may pass. The tool definitions as the model sees them, the runner that executes a call and returns errors as text, and the ids each result showed |
| `context.py` | The starting context of an investigation (the log, its source's last hour, the same log shape across the cluster in that hour), the round notice, prompt loading, and the configuration tag that names a run |
| `schema.py` | The `Verdict` and `Judgement` pydantic models, the `submit_verdict` tool, and the two code checks: `unanchored_evidence` and `unknown_citations` |
| `loop.py` | `investigate(log, tools, llm, events)`: the round loop. A reply with no tool call gets a reminder; an invalid verdict gets its errors back once; tool calls on the last round end the run as a failure. Every event is written to the event log |
| `trajectory.py` | `EventLog` writes rows to `runs/agent.db`; `Trajectory(request_id)` reads them back as the text a person or the judge reads, the verdict, the failures, and the totals |
| `judge.py` | One call to the judge model on a trajectory text, parsed into a `Judgement`, with one retry on an invalid answer |
| `knowledge.py` | Splits each `kb/*.md` file that has a front-matter header at its `##` headings into passages and ranks them by BM25 (`rank_bm25`). A paraphrase that shares no word with a passage is not found |

**`evals/`: measurement**

| File | Purpose |
|---|---|
| `score.py` | `score(trajectory)`: the deterministic checks on one run (outcome, rounds, tool errors and whether a later call fixed them, repeated calls, cut results, a `what_followed` range that reaches into the present, tokens, seconds, and on the verdict: every evidence line anchored, the new log cited, steps naming a source, a check before a disruptive step, citations known). `summarise(rows)`: one row per configuration with every share written as "k of n" |
| `figures.py` | The five figures: how runs ended, verdict quality (judge criteria beside code checks), a per-case heatmap, cost in tokens, and use of the knowledge base |

## Notebooks

The notebooks are where the data was understood, the models were chosen, and the labels were made. They are committed with their outputs, and every number quoted in the documentation points at the notebook that prints it. Each folder has its own README with one entry per notebook.

**[`notebooks/`](notebooks/README.md)**: nine analysis notebooks, in the order the work happened. Notebooks 01 to 03 explore the raw file: the column distributions, the finding that the undocumented `flag` column is not an error label, how repeated lines behave, and a check of the template masks against Loghub's hand-annotated sample. Notebooks 04 and 05 read the database: when each log shape was first seen (new ones never stop arriving), and the cluster's layout as it can be read from the logs, which became the knowledge base. Notebook 06 compares three NVIDIA models on tool calling and as a judge, and measures what the investigator's hidden thinking costs in latency. Notebooks 07 to 09 produce and grade the saved trajectories: 07 runs the agent on the ten golden cases and saves the trajectories, 08 is the form for grading one trajectory by hand, and 09 compares the judge's grades with the reference grades and saves the agreement tables and figures.

**[`notebooks/incidents/`](notebooks/incidents/README.md)**: the hand investigations. One log was fixed for each of the 17 most common log shapes, which together hold 90.6% of the logs, and investigated with the same queries the agent now has as tools, looking only at the log and what came before it. Thirteen of the seventeen end with a verdict and four are unfinished. Ten of them, the ones Aviv was sure about, became the golden cases in `labeling/golden_cases.yaml`. Notebook 00 lists the common shapes and shows each query once; `common.py` holds the shared setup and the 17 pinned logs.

## Data, labels, knowledge, prompts, configuration, runs

| Path | What it holds | In git |
|---|---|---|
| `data/original_dataset/HPC.log` | The raw log file, 433,490 records, as distributed by Loghub, with Loghub's README beside it | Yes |
| `data/loghub/` | Loghub's 2,000-line annotated sample and its template list, used by notebook 02 to check the masks | Yes |
| `data/hpc.db` | The SQLite log store built by `scripts.build_db`. Rebuilt from the file in under a minute | No |
| `labeling/golden_cases.yaml` | The ten golden cases: each a raw log line and its log shape. A case is pinned by its line, so a rebuilt database gives the same log; its verdict is in its hand-investigation notebook under `notebooks/incidents/` | Yes |
| `labeling/trajectories/` | 30 trajectory text files, one per golden case per agent configuration, named `{case}_{config}__{request_id}.txt`. Written by notebook 07; the structured events behind them are in `runs/agent.db` | Yes |
| `labeling/human_grades.csv` | The reference grades for 11 trajectories, six criteria each. **These were produced by Gemini 2.5 Pro on its web UI given the judge's exact prompt, not by a human.** The file name predates that decision | Yes |
| `labeling/judge_results/` | For each of three judge configurations tried in notebook 09, the judge's grades on the seven tune trajectories beside the reference grades, with the judge's reasoning | Yes |
| `kb/cluster_facts.md` | The knowledge base: a fact sheet about the cluster, every statement marked `[data]` (read from the logs), `[source]` (a public document) or `[guess]`. Several passages: the text before the first heading and one per heading | Yes |
| `kb/sources.md` | Every public document consulted, with how much of it could actually be read. It has no header and is not indexed | Yes |
| `prompts/investigator_v1.md`, `prompts/judge_v1.md` | The two system prompts. Versioned by file name | Yes |
| `config/models.yaml` | The endpoint, rate limit, retries, timeout, the model per role, the round limit, the knowledge switch, per-role request options, and the candidate list of notebook 06 | Yes |
| `runs/agent.db` | The event log: every investigation ever run, one row per event under a request id | Yes |
| `runs/llm_cache/` | Every model reply, keyed by a hash of the full request. Lets committed runs replay without a key | Yes |
| `runs/eval/` | The three CSVs written by `scripts.evaluate_trajectories` | Yes |
| `runs/scratch/` | Output of the smoke tests | No |
| `docs/figures/` | Eight PNGs: the five evaluation figures, the two judge-calibration figures from notebook 09, and the log-shape novelty chart from notebook 04 | Yes |
| `jupyter_nbconvert_config.py` | Makes a notebook re-run write the same file byte for byte when nothing changed | Yes |
| `.vscode/launch.json` | Debug configurations for the tests, the smoke tests and `build_db` | Yes |

## Tests

```
python -m pytest
```

Unit tests in `tests/`, none of which touches the network: the parser and the masks; ingestion and the merge of repeated lines; every repository query, including that a range over 31 days or with a missing bound is refused; `build_db` on a temporary file; the LLM client's cache and call spacing against a fake client and clock; the tools' visible-time limit and the knowledge tool; the verdict schema, the evidence and citation checks, the starting context, the prompts and the judge parser; the loop against a scripted fake model; the scoring and the figures.

After a change, the project's rule is to run all unit tests and the smoke test that covers the changed part: `db_smoke_test` for the log store, `agent_smoke_test` for prompts, tools or the loop, `eval_smoke_test` for `evals/` or the judge, `kb_smoke_test` for the knowledge base.

## Results so far

Every number here is in `runs/eval/summary.csv`, written by `python -m scripts.evaluate_trajectories`, from the 30 committed trajectories: the ten golden cases under three agent configurations. The sample is one run per case per configuration, which is too small to separate a configuration's effect from the model's own run-to-run variance.

| Configuration | Ended with a verdict | Ended at the round limit | Invalid verdict | Tokens per verdict obtained | Searched the knowledge base |
|---|---|---|---|---|---|
| Nemotron 3 Super 120B, thinking budget 200, 4 rounds | 8 of 10 | 1 | 1 | about 49k | not available |
| The same, with the knowledge tool | 4 of 10 | 6 | 0 | about 87k | 2 of 10 runs; 0 of 5 remediation steps cite a passage |
| Nemotron 3.5 Lightning 30B, thinking budget 200, 8 rounds | 3 of 10 | 1 | 6 | about 236k | not available |

What the two instruments say about the verdicts obtained, from the same file: the judge passed `grounded` on all 15 verdicts, while the code check found an evidence line that names no shown id in 8 of them. The judge passed `remediation_quality` on all 15, while the code check found a step with no source name or a disruptive step with no check before it in 9 of them. The code checks are literal readings of the rubric, so this is a reason to doubt the judge on those two criteria, not a measurement of the agent.

The judge's calibration is weak and is stated on every run of the evaluation script. The configured judge (GPT-OSS-20B, low effort) agreed with the reference grades on 62% of criterion decisions over the seven tune trajectories, caught 0 of the 2 reference fails on `grounded` and 2 of the 4 on `verdict_supported` (`labeling/judge_results/gpt-oss-20b_effort-low_judge_v1.csv`, from notebook 09). The reference grades came from another LLM, not a person. A re-run of the same judge at temperature 0 gave different grades on the same inputs, so one judge run is one sample.

## Limitations

The project at its current state has many limitations. Section 8 of [`report.md`](report.md) states them in order of weight and says what each would take to remove.

## Documentation

- `docs/plan/00_overview.md`: the full design, including the parts not built, and the status of each step. The other briefs in `docs/plan/` are one per step; `06_knowledge_base.md` is the knowledge base as actually built; `future_work.md` lists what was designed and cut, and why it matters.
- `AGENTS.md`: the working rules for the project, read by the AI coding assistant that helped build it.

## Repository layout

```
agent/          LLM client, tools, starting context, loop, verdict schema, event log, judge, knowledge
logstore/       parsing, templating, schema, repositories, ingestion
evals/          code checks, summary, figures
scripts/        entry points (see Scripts)
tests/          unit tests, no network
notebooks/      analysis notebooks 01 to 09, with their own README
notebooks/incidents/  the 17 hand investigations, with their own README
kb/             the knowledge base (data, not code) and the list of sources
prompts/        versioned system prompts
config/         models.yaml
labeling/       golden cases, saved trajectories, reference grades, judge results
runs/           event log, LLM cache, evaluation tables
data/           the raw log, Loghub's sample, the SQLite store (gitignored)
docs/           plan, figures
```
