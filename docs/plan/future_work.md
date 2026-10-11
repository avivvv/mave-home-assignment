# Future work: what was designed but not built

This file captures everything that was part of the original plan but cut on 2026-10-11 to fit the remaining time. Each section describes what would be built in production and why it matters. These feed directly into the report's "Design" and "Next steps" sections.

---

## 1. Routing by log shape catalogue

**What.** A `log_shape_catalog` table where each log shape has a reviewed route (`ignore`, `handle`, `investigate`, or `rule`), a severity, and a category. A human labels a few dozen of the most frequent log shapes; the rest reach the agent with no catalogue row.

**Why.** Most log volume is routine. In this dataset, about 140 log shapes produce 411k events. A handful of labels on the top shapes would let the system ignore telemetry, recovery messages, and operator commands — which together account for the majority of events — and send only genuine problems to the agent. Without routing, every investigated log costs one full agent run (~6,000 input tokens per call, up to 4 rounds).

**What it would take.** `labeling/log_shapes.csv` with route/severity/category columns filled for a few dozen rows; a loader that writes them to the catalogue table; a router that reads the catalogue row and returns a decision. The router, its rule engine, and the catalogue loader are fully designed in overview sections 5.3 and 5.5.

---

## 2. Named routing rules

**What.** Rules in `config/triage.yaml` that read a computed feature (e.g. `n_logs.node.1h`) and check threshold cases in order, so that a log shape can be routed differently depending on context — for example, one link error is ignored but a burst of them on one node triggers an investigation.

**Why.** Some log shapes are problems only in context. A rule lets an operator express "investigate when count > 3 on a node in one hour" without code changes. The rule engine is fully designed in overview section 5.5.

**What it would take.** A YAML schema for rules with operators (`lt`, `le`, `gt`, `ge`, `eq`) and an `else` clause; a loader that validates rules at startup; the router calling the rule when a catalogue row's route is `rule`.

---

## 3. Deterministic handlers

**What.** For log shapes with a known cause and a fixed remedy (e.g. "ServerFileSystem domain is full"), a handler function that returns a verdict immediately, per node, without calling any LLM.

**Why.** When the fix is known and always the same, an LLM adds only cost and latency. A handler's answer uses the same verdict schema as the agent's, so the evaluation and the operator read one format.

**What it would take.** One handler function per known fix, looked up by name from the catalogue row. The one candidate identified during exploration is `fdmn.full` (filesystem full).

---

## 4. Active incidents with TTL in log time

**What.** At most one incident per log shape is active at a time. A new log of that shape joins the existing incident instead of opening a new one. The incident closes after a TTL of no new logs (measured in log time, not wall time), or after a maximum duration.

**Why.** Without incidents, a burst of 500 logs of the same shape costs 500 agent runs. With incidents, it costs one. The TTL groups related logs into one investigation, and the maximum duration prevents a chronic shape from holding one incident open forever. Incidents are the mechanism that brings the number of agent runs from "number of logs" down to "number of distinct problems."

**What it would take.** An in-memory table of active incidents, written to `incidents` and `incident_logs` as they change. Join, raise (a log routed to `investigate` raises a `handle` incident), TTL close, and max-hours close. Fully designed in overview section 5.5.

---

## 5. The replay script

**What.** `scripts/replay.py` replays the log file in time order, in chunks of a few minutes of log time, routing each event and managing incidents. `--no-agent` counts agent runs without calling any model. `--agent <config>` runs the agent on each incident.

**Why.** The replay is the ingestion flow in miniature. It shows how the system would behave on the live stream: how many incidents open per day, how many agent runs that costs, how the cap limits peak load, and how long incidents wait.

**What it would take.** Sort lines by timestamp, ingest in chunks, route each event, manage incidents. The cap and queue for agent runs, with a loud warning when the cap is reached. Fully designed in overview section 5.5.

---

## 6. The agent inside the replay (visible time that moves)

**What.** When the agent investigates an incident during a replay, its visible time starts at the incident's opening and advances by the real latency of each LLM and tool call. Tools answer as of that moving time, so a slow agent sees more of the incident and a fast one sees less.

**Why.** In production, logs keep arriving while the agent works. The moving visible time simulates this faithfully, so the evaluation measures the agent as a real operator would experience it.

**What it would take.** The loop already tracks `max_visible_timestamp`. The replay would pass it to the agent and let it grow with each call's latency.

---

## 7. LLM log shape classifier (experiment E1)

**What.** A zero-shot LLM classifier that proposes a route (`ignore` or `investigate`) and a category for log shapes with no catalogue row. Scored against human labels: keyword baseline vs. small model vs. main model.

**Why.** New log shapes appear over time (the novelty plot shows this). A classifier that proposes labels for review means a human only confirms, not investigates from scratch. E1 would measure whether the LLM is better than keywords at this.

**What it would take.** A prompt with the category list and route definitions; scoring against `labeling/log_shapes.csv`; precision/recall per log shape and weighted by log count.

---

## 8. Settle time before the agent starts

**What.** A configurable delay (in log time) between an incident opening and the agent starting, so the agent begins with more context.

**Why.** The agent starts at the incident's first log, which is its least informative moment. A settle time lets a few more logs arrive before investigation, at the cost of a later verdict.

---

## 9. Updates to the agent during a run

**What.** Before each step of the loop, when new logs have joined the incident and fall within the visible time, inject a message with updated counts and the latest lines.

**Why.** The agent can already find new logs with its tools, but an update message saves a tool call and keeps the agent aware of changes without having to poll.

---

## 10. Judge inside the agent loop (experiment E6)

**What.** After the validator accepts an answer, the judge checks it on `grounded` and `citation_supports_step`. If any fails, the critiques go back to the agent for one revision round.

**Why.** This is the simplest form of one agent verifying another's work. The measurement challenge is that the in-loop judge cannot score its own influence — conclusions must rest on measures the judge never saw (root-cause match, recall, Aviv's reading of before/after pairs).

**What it would take.** An optional `reviewer` argument on the loop; the judge called on usable criteria; one revision round; the trace recording the review. Fully designed in overview section on E6.

---

## 11. Cost-vs-lag experiment (E7)

**What.** Replay the whole file with `--no-agent` under different settings of TTL and agent cap. Count agent runs, estimate tokens and dollars from the dev runs, and plot cost against lag to verdict.

**Why.** This is the trade-off the system is designed around: incidents and the cap reduce cost but increase lag. The experiment would show the shape of that trade — where the knee is, and what a tight cap costs on the busiest days.

**What it would take.** Multiple `--no-agent` replays with different settings; resampling token counts from dev runs; a cost-vs-lag scatter plot. Fully designed in overview section on E7.

---

## 12. Incident card

**What.** A fixed-size text summary of an incident, given to the agent at the start of its run: the log shape with its catalogue row, opening time, log/node counts, stats, the ten busiest nodes, first and last five lines, handler answers if any.

**Why.** The card gives the agent a structured starting point without dumping the full incident. Its fixed size keeps input tokens predictable regardless of incident size.

---

## 13. Stats cache updated per chunk

**What.** In production, stats (e.g. `n_logs.node.1h`) come from a cache updated in batches as chunks are ingested, not from SQL scans. Before a chunk is routed, the cache holds every earlier log. As each log is routed it is added, so the cache is current for exactly the next log.

**Why.** SQL range queries work for the prototype but do not scale. The cache is a design principle: stats are a lookup, not a scan.

**What it would take.** Time buckets per log shape and node, with counts and node sets. Longer windows sum over coarser buckets. A test that cache and SQL return the same values for every log in a sample week.

---

## 14. Audit trail and quarantine

**What.** `routing_decisions` table: one row per routed event with the route, rule id, and reason. `quarantine` table: lines that match no parser format. Parser config in `config/parsers.yaml`.

**Why.** Observability of the routing layer. The quarantine catches format drift — new log formats that the system does not understand.

---

## 15. Log shape labelling at scale (tasks 1.3–1.6)

**What.** Label a few dozen log shapes with route/severity/category. Try the incident rule at different TTLs. Mine hindsight (what follows each log shape on the same node). Write ~25 golden incidents with expected answers, split dev/holdout.

**Why.** The golden set would be larger and more representative. Hindsight mining shows which problems clear by themselves and which draw operator action. The incident rule prototype would inform the choice of TTL and maximum duration.

**What was done instead.** 10 hand-investigated logs in `labeling/golden_cases.yaml`, investigated directly on the database without incidents.

---

## 16. Less context per call

Added on 2026-10-11, from the evaluation of the knowledge base and of the two model sizes.

**What.** Measure how the agent's behaviour changes as the text it reads per call shrinks, one factor at a time: a shorter system prompt, shorter tool results, a starting context the agent asks for instead of receiving, a one-line description for the knowledge tool, hidden thinking off. Each factor is one configuration tag on the ten golden cases, scored by `scripts/evaluate_trajectories.py`, with a repeat of every arm because one sample per arm cannot separate the factor from the model's own variance.

**Why.** Two comparisons point the same way. The 30b model with 8 rounds, whose conversations grew longest, failed 6 of 10 cases on the shape of its verdict. The 120b model given a seventh tool, which lengthens every call, reached a verdict in 4 cases where it had reached 8 without it (`runs/eval/summary.csv`). The hypothesis is that the agent gets more confused as the context grows, and that removing unnecessary context improves cost and quality together.

**What it would take.** A prompt file per variant, a `max_rows` per tool result in the config, a switch that leaves the starting context out, and the thinking options that already exist in `config/models.yaml`.
