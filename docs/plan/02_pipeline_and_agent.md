# Step 2: pipeline, agent, traces

Read first: `AGENTS.md`, [00_overview.md](00_overview.md), Part 1 of [docs/lab_notes.md](../lab_notes.md).

Three parts, one chat each. Budget: Part A 4 hours, Part B 3.5 hours, Part C 1.5 hours.

## Goal

A replay of the log file routes every event and opens incidents, with no LLM (Part A). One command takes an incident and returns a validated verdict plus a complete trace, first without the knowledge base (Part B), then with it (Part C).

## Concepts to explain when they come up

- **Tool calling.** You describe functions to the model as JSON schemas. The model replies either with text or with "call function X with these arguments". Your code runs the function and sends the result back.
- An **agent** is that exchange in a loop, until the model says it is done. **ReAct** (reason, act, observe) is the name of the loop pattern.
- A **trajectory** or **trace** is the full list of messages, tool calls and tool results of one run. It is what gets evaluated.
- **Structured output**: forcing the final answer into a schema so that code can check it.
- A **guardrail** is a code check on the model's output that can reject it.
- **Context limit**: a model reads a bounded amount of text per call, and long inputs cost money and attention. Tool results and the incident card are capped for this reason.
- **Temperature**: how much randomness the model uses. Zero is the most repeatable setting, though still not fully deterministic.

---

## Part A. Routing and incidents

Everything in Part A is code. No LLM is called. The contract is overview 5.5; read it before anything else. Decisions D17 to D20 give the reasons.

### Concepts to explain when they come up

- A **replay** feeds stored logs to the pipeline in the order and rhythm they were written, so that the pipeline behaves as it would on the live stream.
- **Log time** against wall-clock time. Log time is the latest timestamp ingested so far. A replay runs much faster than the clock, so every wait and every expiry is counted in log time.
- A **TTL**, time to live: how long an entry stays in a cache without being touched. Here it is how long an incident stays active with no new log.
- **Deduplication**: recognising that a new item is another report of something already being handled, and attaching it instead of starting again.
- **Back-pressure**: what a system does when work arrives faster than it can be done. Here it is the cap on agent runs and the queue behind it.

### Before you start

Step 1 is done: `data/hpc.db` is rebuilt, a few dozen rows of `labeling/log_shapes.csv` are labelled, the log shape for the handler and the log shape for the rule are chosen, and `ttl_minutes`, `max_hours`, the category list and the sample week are in lab notes. **If the handler or the rule has not been chosen, stop and ask Aviv before writing A1.**

### Tasks

- [ ] **A1. `config/triage.yaml`** (Must). The contents listed in overview 5.4. The rule Aviv chose in Step 1 replaces the placeholder `burst_on_node`. The keyword patterns (`fail`, `error`, `panic`, `full`, and so on) and the phrases that cancel them (`Link ok`, `completed successfully`). The loader checks every rule as overview 5.5 says and fails with a message that names the rule and the problem.
- [ ] **A2. Log shape catalogue** (Must). Add the `log_shape_catalog` table (overview 5.2). `scripts/load_catalog.py` loads the labelled rows of `labeling/log_shapes.csv` into it with `source = human` and `reviewed = 1`; a row with no route is skipped. Running it twice gives the same table. It reports how many log shapes have a row and how many have none, labels whose key is not in the database, and rows that name a rule or a handler that does not exist.
- [ ] **A3. `triage/context.py`** (Must). `LogContext` as in overview 5.5: the fixed fields, `**extra`, an error on a missing field, and `get(name)` for features computed on first use. Stats are features served by the query of Step 1 task 1.2, or by the cache of task 1.9 when it exists; the two are interchangeable behind one small interface. `triage/keywords.py` gives the keyword hits of a template; they are computed once per log shape with no catalogue row.
- [ ] **A4. `triage/router.py`** (Must). `route(ctx)` returns a `Decision` by the three steps of overview 5.5. Keep it short enough to read in one screen. Test each step, each operator, the `else`, and a rule whose feature is missing.
- [ ] **A5. `triage/handlers.py`** (Must). The one handler, for the log shape Aviv chose. It takes the incident and a node and returns an answer in the verdict format with `source = handler`. Its remediation steps name the runbook passage they come from once Part C has written it; until then the citation is empty. A handler is looked up by the name in the catalogue row.
- [ ] **A6. `triage/incidents.py`** (Must). The active incidents of overview 5.5: open, join, raise the route, take in earlier logs on opening, restart the TTL, close on TTL or on `max_hours`, mark resolved. Everything is counted in log time. They are written to `incidents` and `incident_logs` as they change.
  - `build_incident(conn, anchor)` returns the incident of a golden anchor as it was at its opening, without writing to the database. `scripts.investigate` and the evaluation harness use it.
  - Test with hand-made logs: a burst gives one incident; a gap longer than the TTL gives two; a chronic shape is cut at `max_hours`; a log routed to `ignore` joins an active incident and does not open one; an `investigate` log raises a `handle` incident and does not open a second; a log of another log shape never joins.
- [ ] **A7. `scripts/replay.py`** (Must). The ingestion flow of overview 5.5: empty database, lines sorted by time, chunks of `chunk_minutes`, each new event routed in processing order, incidents opened and closed, handlers run. `--start` and `--end` replay a slice; `--db` names the database, `data/replay.db` by default; `--rebuild` starts it empty.
  - In Part A it runs with `--no-agent` only. It applies the cap and the queue all the same, so that it can count how many agent runs would start and how long incidents would wait.
  - It prints: lines ingested, copies merged, lines left out for a bad timestamp; events per route and per rule id; incidents per route, per day, and by severity; agent runs that would start, per day; how often the cap was reached, with the loud warning and the table of waiting incidents of overview 5.5; the ten log shapes with the most incidents.
  - Replaying the same slice twice gives the same incidents. Test it.
- [ ] **A8. `evals/golden.py`** (Must). `load_golden(path)` reads `labeling/golden_incidents.yaml` and returns its entries, failing with a clear message when an entry lacks a field of overview 5.3 or has a `split` other than `dev` or `holdout`. `scripts.investigate` and the evaluation harness both use it.
- [ ] **A9. `triage/card.py`** (Must). `incident_card(conn, incident)` returns the card text of overview 5.5. Test that a 2-line incident and the largest incident in the database give cards of similar length.
- [ ] **A10. Audit trail, quarantine and parser config** (Should). The replay writes each decision to `routing_decisions`. Lines that match no format are stored in `quarantine` instead of only being returned. The line regex and the masks move to `config/parsers.yaml`.

### Sample run

Replay the sample week chosen in Step 1 first and read every incident it opens with Aviv: its log shape, its route and the rule that decided, when it opened and closed, its logs and nodes. Then replay the whole file.

### Done when

- Tests pass for: stats that count only earlier logs, each step of the router, the checks on rules, the incident cases listed in A6, the cap and its queue, a repeated replay giving the same incidents, and the card's size limit.
- `python -m scripts.replay --no-agent` prints the counts above for the whole file.
- The handler answers an incident of its log shape, once per node.
- Aviv has seen the card of three golden incidents and finds them readable.
- Aviv can say what happens to one log from the moment it is read to the moment it joins an incident.

### Lab notes should answer

- How many events went to each route, and which rule decided the most?
- How many incidents, and how many agent runs a day would they cost? How does that compare with one run per routed log?
- How many incidents come from log shapes with no catalogue row?
- How often was the cap reached, and how long did incidents wait?
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
  - **Cache.** The key is a hash of model id, messages, tools, tool choice, temperature and `cache_tag`. A hit makes no network call and returns the original token counts and latency. The recorded latency is also what moves the agent's visible time (overview 5.5), so a run replayed from the cache sees the same logs as the first run. `cache_tag` exists so that repeat runs can ask for a fresh answer. Files live in `runs/llm_cache/`.
  - **Retry** with growing waits on rate-limit and server errors, then a clear error.
  - **Pacing** below `requests_per_minute`. The free tier is reported to allow about 40 a minute, shared by all models on one key.
  - Tests use a fake transport. No test calls the network.

- [ ] **B3. `agent/tools.py`** (Must). `search_logs`, `count_logs`, `node_timeline`, `get_stats` and `related_incidents` as specified in overview 5.6, each with its JSON schema for the model and a function that runs it. `node_timeline` wraps `LogRepository.node_timeline` from Step 1, and `get_stats` wraps the same stats the router uses. Every function takes the visible time as an argument, so Aviv can call the same functions by hand from a notebook with no limit.
  - Test the no-look-ahead rule directly: a call asking for logs after `max_visible_timestamp` returns none; the same call later in the run, when the visible time has moved, returns them; `related_incidents` does not show an incident that opened after the visible time.

- [ ] **B4. `agent/schema.py` and `agent/validate.py`** (Must). The verdict of overview 5.7 as a pydantic model, and the validator of overview 5.8 with its five rules. `validate(verdict_args, trace)` returns a list of error messages, empty when valid. Each message is written for the model to read and act on, for example "log id 123 does not appear in any tool result of this run".

- [ ] **B5. `agent/trace.py`** (Must). Builds and saves the trace of overview 5.9, loads it back, and `render(trace)` prints it readably in a notebook: the card, then each step with its tool call and a shortened result, then the verdict. Aviv will read dozens of these when labelling in Step 3, so show him the rendering and adjust it to his taste.

- [ ] **B6. The loop** (Must). `prompts/investigator_v1.md`, `agent/loop.py`, `scripts/investigate.py`.
  - `investigate(incident, config, llm, conn)` returns a trace.
  - The conversation starts with the system prompt and the incident card. Each turn the model calls tools; the loop runs them and appends the results. The run ends when the model calls `submit_verdict` and the validator accepts it. That marks the incident resolved, together with the incidents the verdict names in `resolves_incident_ids`.
  - **Visible time.** The loop keeps `max_visible_timestamp` as overview 5.5 defines it: the log time at which the run started plus the latencies of the run's calls so far. It passes the current value to every tool and writes it on every step of the trace. The agent starts as soon as the incident opens; nothing waits for the incident to end.
  - **When things go wrong:** tool arguments that do not parse, or an unknown tool name, produce an error message as the tool result and the run continues. A reply with no tool call gets a short reminder to call a tool or submit. A verdict the validator rejects gets the errors back, once. At the step limit the model is told to submit now, with a forced tool choice if the model supports it. Each of these counts as a step and is visible in the trace.
  - **The prompt** says, in plain language: who the model is and who reads its answer; what `actionable`, `benign` and `insufficient_evidence` mean; look at the evidence before concluding; look for operator activity around the incident, since planned maintenance explains many errors; an incident holds one log shape and has just opened, so more of it may arrive while the model works, and its tools show a little more each time they are called; the nodes of an incident may be unrelated, and the answer should say so when they are; call `related_incidents` to see what else is active on the same nodes and component, treat the earliest abnormal event as the likelier cause and what follows it as possible cascade, and when this incident explains another one, name it in `resolves_incident_ids`; put in `evidence` only log ids it has seen; when a knowledge tool is available, search it and cite passages, otherwise leave citations empty; answer `insufficient_evidence` when unsure. Write it with Aviv and explain each paragraph's purpose. A prompt change is a new file (`investigator_v2.md`), never an edit.
  - `python -m scripts.investigate --golden <id>` builds the incident from its anchor on `data/replay.db`, as it was at its opening, runs the `main_nokb` configuration and writes a trace to `runs/scratch/`. `--config` picks another configuration.
  - Test the loop against a scripted fake model: a normal run, a malformed tool call, a rejected verdict followed by a valid one, a run that hits the step limit, and a run whose second tool call sees a log that the first could not.

- [ ] **B7. The agent inside the replay** (Should). `python -m scripts.replay --agent main_nokb --start ... --end ...` on the sample week.
  - An incident routed to `investigate` gets the agent as soon as it opens or is raised. **Ingestion never waits for the agent**: the replay goes on while a run is in progress, and the run's visible time keeps it from seeing what the replay has already ingested beyond it.
  - The verdict lands at log time `agent_started_ts` plus the run's elapsed time, as overview 5.5 says, and both are written on the incident with `verdict_ts`.
  - The cap and the queue of Part A now start real runs. When the cap is reached, the warning and the table of waiting incidents are printed as before.
  - Read the incidents of the week with Aviv: which were answered by the handler, which by the agent, which waited, and for how long.

- [ ] **B8. LLM log shape classifier and experiment E1** (Should). `triage/classify.py`.
  - `classify_log_shape(llm, role, log_shape_row)` asks for a route, `ignore` or `investigate`, a `category` and a one-line rationale, given the component, state, template, three examples and counts. It never proposes `handle` or `rule`. The prompt is zero-shot: it holds the meaning of the two routes and the category list, and no labelled examples, so nothing leaks from Aviv's labels.
  - `classify_new_log_shapes(conn, llm)` runs it for log shapes with no catalogue row and stores the result with `source = llm` and `reviewed = 0`. The router reads reviewed rows only (overview 5.5), so an LLM row is a proposal that changes nothing until a human reviews it, and unlabelled log shapes keep going to the agent (decision D21).
  - **E1.** Write the hypothesis in lab notes first. Then score three classifiers against the labelled rows of `labeling/log_shapes.csv`: the keyword baseline, the small model, the main model. The question scored is whether a log shape needs attention, which for Aviv's labels means any route other than `ignore`. Report precision and recall, both per log shape and weighted by log count, the confusion counts, and how many incidents each would open. Recall matters more: a missed error costs more than a wasted investigation. With a few dozen labelled rows the numbers are rough; say so next to them. Save the table to `runs/eval/e1_triage.csv`.

- [ ] **B9. A settle time before the agent starts** (Could). A `settle_minutes` per severity in `config/triage.yaml`, zero by default. An incident waits that long in log time before its run starts, so the agent begins with more of the burst. Zero keeps today's behaviour, so earlier traces stay comparable. If built, add the settle time as a third factor of experiment E7.

- [ ] **B10. Updates to the agent during a run** (Could). Before each step of the loop, when logs have joined the incident and are now inside the visible time, the loop adds one message with the new counts of logs and nodes and the latest lines, and asks the model to say whether this changes what it concluded so far. The updates are recorded in the trace. The agent can already find the same logs with its tools, so this is a convenience, not a need.

### Sample run and the day-1 checkpoint

Run `scripts.investigate` on three dev golden incidents: one clearly actionable, one clearly benign, one large. Read the three traces with Aviv.

**Checkpoint:** if no incident runs end to end by the end of day 1, skip B7 to B10 and move on.

### Done when

- `python -m scripts.investigate --golden <id>` prints a validated verdict and writes a trace.
- Tests pass for the cache, the tools' visible-time limit, the validator's five rules and the five loop scenarios.
- Aviv can walk through the loop and say what happens at each branch, and what the agent can and cannot see at each step.

### Lab notes should answer

- Which models were tried, and what did each get wrong in the smoke test?
- What was the first thing the agent did badly on a real incident, and what changed because of it?
- How much of its incident had the agent seen when it answered, and did starting at the opening hurt?
- Did the agent use `related_incidents`, and did it ever mark another incident resolved?
- How often did the validator fire on first answers, and on what?
- Tokens and seconds for the three sample runs.
- If B7 was run: how many runs in the week, how often was the cap reached, and how long did incidents wait?
- E1: was the hypothesis right? Where do keywords fail, and where does the model?

---

## Part C. Knowledge base

### Before you start

Part B is done. `kb/sources.md` from Step 1 lists the public sources that were found, or says none were.

### Tasks

- [ ] **C1. Runbooks** (Must, 1.5 hours at most for content). One markdown file per problem category in `kb/`, in the format of overview 5.11, plus `kb/cluster_facts.md` from Step 1. Write each from the sources in `kb/sources.md` and from the hindsight table of Step 1, which shows what operators actually did. Every remediation step either names its source or is marked "general practice, unsourced". Aviv reads and approves each file: this is the knowledge he will be asked about.

- [ ] **C2. `agent/knowledge.py`** (Must). Loads `kb/*.md`, splits each at its `##` headings into passages, and ranks passages against a query by keyword relevance (BM25, with the `rank_bm25` package). `search_knowledge(query, k=3)` returns `passage_id`, `title` and `text`. The index is built when the process starts, so a new file is picked up with no code change. Test: a query made of a runbook's own symptom words returns that runbook first.

- [ ] **C3. Wire it in** (Must). Register `search_knowledge` as a tool only when the configuration has knowledge on. Run `main_kb` on the same three incidents as in Part B and compare the traces with Aviv.

- [ ] **C3b. The handler cites its runbook** (Must). The handler of task A5 now names the passage its fix comes from, and a test checks that the passage exists in the knowledge base.

- [ ] **C4. Show the future-proof behaviour** (Should). Three small demonstrations, each recorded in lab notes with before and after, and none needing a code change: add a new runbook file and show a verdict that now cites it; ingest one line with a log shape never seen before and show the decision `unknown_log_shape`, the incident it opens and the agent's answer; add a rule to `config/triage.yaml`, point a catalogue row at it, and show a replay of the sample week routing that log shape differently.

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

One per task group: config and catalogue; log context and router; handler; active incidents; replay; incident card; LLM client; tools; schema and validator; trace; loop and first prompt; the agent inside the replay; classifier and E1; runbooks; knowledge search.

## Not in this step

No evaluation harness and no judge (Step 3). No merging of incidents, no parallel ingestion, and no reuse of a verdict across incidents of the same log shape: these are described in the report, and the last one's numbers are used in the cost section, but none is built (see "Deliberately left out" in the decision log).
