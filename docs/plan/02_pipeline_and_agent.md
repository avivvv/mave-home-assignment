# Step 2: pipeline, agent, traces

Read first: `AGENTS.md`, [00_overview.md](00_overview.md), Part 1 of [docs/lab_notes.md](../lab_notes.md).

Three parts, one chat each. Budget: Part A 2 hours, Part B 3.5 hours, Part C 1.5 hours.

## Goal

One command takes an incident and returns a validated verdict plus a complete trace, first without the knowledge base (Part B), then with it (Part C).

## Concepts to explain when they come up

- **Tool calling.** You describe functions to the model as JSON schemas. The model replies either with text or with "call function X with these arguments". Your code runs the function and sends the result back.
- An **agent** is that exchange in a loop, until the model says it is done. **ReAct** (reason, act, observe) is the name of the loop pattern.
- A **trajectory** or **trace** is the full list of messages, tool calls and tool results of one run. It is what gets evaluated.
- **Structured output**: forcing the final answer into a schema so that code can check it.
- A **guardrail** is a code check on the model's output that can reject it.
- **Context limit**: a model reads a bounded amount of text per call, and long inputs cost money and attention. Tool results and the incident card are capped for this reason.
- **Temperature**: how much randomness the model uses. Zero is the most repeatable setting, though still not fully deterministic.

---

## Part A. Triage

Everything in Part A is code. No LLM is called.

### Before you start

Step 1 is done: the database is rebuilt, `labeling/templates.csv` is fully labelled, and `gap_minutes`, `max_hours`, the category list and the sample week are in lab notes.

### Tasks

- [ ] **A1. `config/triage.yaml`** (Must). `gap_minutes`, `max_hours`, the category list, and the keyword baseline: a list of patterns that mark a template as an alert (`fail`, `error`, `panic`, `full`, and so on) and a list of phrases that cancel it (`Link ok`, `completed successfully`).
- [ ] **A2. Template catalogue** (Must). Add the `template_catalog` table (overview 5.2). `scripts/load_catalog.py` loads `labeling/templates.csv` into it with `source = human` and `reviewed = 1`. Running it twice gives the same table. It reports template keys in the database that have no label, and labels whose key is not in the database.
- [ ] **A3. `triage/incidents.py`** (Must).
  - `group_incidents(conn, gap_minutes, max_hours)` applies the rule of overview 5.5 and fills `incidents` and `incident_logs`. A template with no catalogue row counts as an alert (decision D3).
  - `build_incident(conn, component, start, end, nodes=None)` returns the same kind of incident for a golden anchor, without writing to the database.
  - Both return the incident fields of overview 5.5.
- [ ] **A3b. `evals/golden.py`** (Must). `load_golden(path)` reads `labeling/golden_incidents.yaml` and returns its entries, failing with a clear message when an entry lacks a field of overview 5.3 or has a `split` other than `dev` or `holdout`. `scripts.investigate` and the evaluation harness both use it.
- [ ] **A4. `triage/card.py`** (Must). `incident_card(conn, incident)` returns the card text of overview 5.5. Test that a 2-line incident and the largest incident in the database give cards of similar length.
- [ ] **A5. `triage/keywords.py`** (Should). `keyword_is_alert(template_text, config)`, the baseline for experiment E1. It is used only for comparison, never by the pipeline.
- [ ] **A6. `scripts/run_triage.py`** (Must). Groups incidents and prints: templates in the catalogue by source, templates treated as alerts by default, incidents created, incidents per day, and the ten most common signatures.
- [ ] **A7. Quarantine and parser config** (Should). Lines that match no format are stored in `quarantine` instead of only being returned. The line regex and the masks move to `config/parsers.yaml`.

### Sample run

Run grouping on the sample week chosen in Step 1 first and read every incident it produces with Aviv, then on the full database.

### Done when

- Tests pass for: the gap rule, the length cap, the default-to-alert rule, anchors giving the same incident as grouping for the same window, and the card's size limit.
- `python -m scripts.run_triage` prints the counts above on the full database.
- Aviv has seen the card of three golden incidents and finds them readable.

### Lab notes should answer

- How many incidents, and how many distinct signatures? How does that compare with the rough planning numbers?
- What does the largest incident look like, and is one card enough to describe it?
- Did any golden anchor produce an incident that surprised you?

---

## Part B. The agent, without knowledge

### Before you start

Part A is done. `NVIDIA_API_KEY` is in `.env`. Confirm with Aviv that the hand-written loop (decision D10) still stands; if he prefers LangGraph, stop and revise this part with him first.

### Tasks

- [ ] **B1. Model smoke test** (Must, 30 minutes). `scripts/model_smoke_test.py`. NVIDIA's catalogue changes, so list the available models live. Pick four or five of different sizes from families documented to support tool calling (Llama 3.x, Nemotron, Qwen, gpt-oss, DeepSeek, Mistral at the time of planning). For each one check three things: it returns a well-formed tool call; it completes a two-step task (call a tool, read the result, call a second tool); how long a call takes. Also check whether it obeys a forced tool choice, which B6 needs. Then choose with Aviv and write `config/models.yaml`: a **small** model, a **main** model, and the strongest available as **judge**, from a different family than the main model (decision D12). Keep one fallback per role in a comment, because free endpoints disappear.

- [ ] **B2. `agent/llm.py`** (Must). The single entry point for every LLM call in the project: agent, classifier and judge. It wraps the OpenAI Python client with `base_url` from `config/models.yaml`.
  - `chat(role, messages, tools=None, tool_choice=None, temperature=0, cache_tag="")` returns the reply message, tokens in, tokens out, latency, whether it came from the cache, and the model id.
  - **Cache.** The key is a hash of model id, messages, tools, tool choice, temperature and `cache_tag`. A hit makes no network call and returns the original token counts and latency. `cache_tag` exists so that repeat runs can ask for a fresh answer. Files live in `runs/llm_cache/`.
  - **Retry** with growing waits on rate-limit and server errors, then a clear error.
  - **Pacing** below `requests_per_minute`. The free tier is reported to allow about 40 a minute, shared by all models on one key.
  - Tests use a fake transport. No test calls the network.

- [ ] **B3. `agent/tools.py`** (Must). `search_logs`, `count_logs`, `node_timeline` as specified in overview 5.6, each with its JSON schema for the model and a function that runs it. `node_timeline` wraps `logstore.queries.node_timeline` from Step 1. Test the no-look-ahead rule directly: a call asking for logs after the incident's end returns none.

- [ ] **B4. `agent/schema.py` and `agent/validate.py`** (Must). The verdict of overview 5.7 as a pydantic model, and the validator of overview 5.8. `validate(verdict_args, trace)` returns a list of error messages, empty when valid. Each message is written for the model to read and act on, for example "log id 123 does not appear in any tool result of this run".

- [ ] **B5. `agent/trace.py`** (Must). Builds and saves the trace of overview 5.9, loads it back, and `render(trace)` prints it readably in a notebook: the card, then each step with its tool call and a shortened result, then the verdict. Aviv will read dozens of these when labelling in Step 3, so show him the rendering and adjust it to his taste.

- [ ] **B6. The loop** (Must). `prompts/investigator_v1.md`, `agent/loop.py`, `scripts/investigate.py`.
  - `investigate(incident, config, llm, conn)` returns a trace.
  - The conversation starts with the system prompt and the incident card. Each turn the model calls tools; the loop runs them and appends the results. The run ends when the model calls `submit_verdict` and the validator accepts it.
  - **When things go wrong:** tool arguments that do not parse, or an unknown tool name, produce an error message as the tool result and the run continues. A reply with no tool call gets a short reminder to call a tool or submit. A verdict the validator rejects gets the errors back, once. At the step limit the model is told to submit now, with a forced tool choice if the model supports it. Each of these counts as a step and is visible in the trace.
  - **The prompt** says, in plain language: who the model is and who reads its answer; what `actionable`, `benign` and `insufficient_evidence` mean; look at the evidence before concluding; look for operator activity around the incident, since planned maintenance explains many errors; look at other components in the same time window; treat the earliest abnormal event as the likelier cause and what follows it as possible cascade; put in `evidence` only log ids it has seen; when a knowledge tool is available, search it and cite passages, otherwise leave citations empty; answer `insufficient_evidence` when unsure. Write it with Aviv and explain each paragraph's purpose. A prompt change is a new file (`investigator_v2.md`), never an edit.
  - `python -m scripts.investigate --golden <id>` builds the incident from its anchor, runs the `main_nokb` configuration and writes a trace to `runs/scratch/`. `--config` picks another configuration.
  - Test the loop against a scripted fake model: a normal run, a malformed tool call, a rejected verdict followed by a valid one, and a run that hits the step limit.

- [ ] **B7. LLM template classifier and experiment E1** (Should). `triage/classify.py`.
  - `classify_template(llm, role, template_row)` asks for `is_alert`, `category` and a one-line rationale, given the component, state, template, three examples and counts. The prompt is zero-shot: it holds the definition of an alert and the category list, and no labelled examples, so nothing leaks from Aviv's labels.
  - `classify_new_templates(conn, llm)` runs it for templates with no catalogue row and stores the result with `source = llm` and `reviewed = 0`. If the call fails, the template stays without a row and so counts as an alert.
  - **E1.** Write the hypothesis in lab notes first. Then score three classifiers against `labeling/templates.csv`: the keyword baseline, the small model, the main model. Report precision and recall for `is_alert`, both per template and weighted by log count, the confusion counts, and how many incidents each would open. Recall matters more: a missed error costs more than a wasted investigation. Save the table to `runs/eval/e1_triage.csv`.

### Sample run and the day-1 checkpoint

Run `scripts.investigate` on three dev golden incidents: one clearly actionable, one clearly benign, one large. Read the three traces with Aviv.

**Checkpoint:** if no incident runs end to end by the end of day 1, skip B7 and move on.

### Done when

- `python -m scripts.investigate --golden <id>` prints a validated verdict and writes a trace.
- Tests pass for the cache, the tools' time cap, the validator's four rules and the four loop scenarios.
- Aviv can walk through the loop and say what happens at each branch.

### Lab notes should answer

- Which models were tried, and what did each get wrong in the smoke test?
- What was the first thing the agent did badly on a real incident, and what changed because of it?
- How often did the validator fire on first answers, and on what?
- Tokens and seconds for the three sample runs.
- E1: was the hypothesis right? Where do keywords fail, and where does the model?

---

## Part C. Knowledge base

### Before you start

Part B is done. `kb/sources.md` from Step 1 lists the public sources that were found, or says none were.

### Tasks

- [ ] **C1. Runbooks** (Must, 1.5 hours at most for content). One markdown file per problem category in `kb/`, in the format of overview 5.11, plus `kb/cluster_facts.md` from Step 1. Write each from the sources in `kb/sources.md` and from the hindsight table of Step 1, which shows what operators actually did. Every remediation step either names its source or is marked "general practice, unsourced". Aviv reads and approves each file: this is the knowledge he will be asked about.

- [ ] **C2. `agent/knowledge.py`** (Must). Loads `kb/*.md`, splits each at its `##` headings into passages, and ranks passages against a query by keyword relevance (BM25, with the `rank_bm25` package). `search_knowledge(query, k=3)` returns `passage_id`, `title` and `text`. The index is built when the process starts, so a new file is picked up with no code change. Test: a query made of a runbook's own symptom words returns that runbook first.

- [ ] **C3. Wire it in** (Must). Register `search_knowledge` as a tool only when the configuration has knowledge on. Run `main_kb` on the same three incidents as in Part B and compare the traces with Aviv.

- [ ] **C4. Show the future-proof behaviour** (Should). Two small demonstrations, each recorded in lab notes with before and after: add a new runbook file and show a verdict that now cites it; ingest one line with a template never seen before and show it is treated as an alert and then classified.

- [ ] **C5. Real excerpts** (Could). Add one or two passages copied from a vendor manual as their own documents, so that some citations point at vendor text.

### What to be honest about

The runbooks are written by us from public manuals, so they are partly synthetic. The evaluation therefore measures whether the agent uses and cites them faithfully, not whether a 2004 operator of that cluster would agree with them. This sentence, or one like it, goes in the report.

### Done when

- `python -m scripts.investigate --golden <id> --config main_kb` returns a verdict whose remediation steps carry citations that the validator accepted.
- Every problem category has a runbook that Aviv has read.
- The same incident run with `main_nokb` and `main_kb` differs only in the availability of the knowledge tool.

### Lab notes should answer

- Which sources were used for which runbook, and how much is unsourced?
- Did the agent search before recommending, or recommend from memory and cite afterwards?
- Did keyword search miss a passage that was clearly relevant? With which query?

## Suggested commits

One per task group: triage tables and grouping; incident card; LLM client; tools; schema and validator; trace; loop and first prompt; classifier and E1; runbooks; knowledge search.

## Not in this step

No evaluation harness and no judge (Step 3). No reuse of verdicts across incidents with the same signature: it is described in the report and its numbers are used in the cost section, but it is not built (see "Deliberately left out" in the decision log).
