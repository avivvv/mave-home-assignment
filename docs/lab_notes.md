# Lab notes

Two parts. Part 1 is the decision log: every design decision, why it was taken, what it costs and what backs it. Part 2 is a dated diary of what was tried and what was learned. Both feed the report.

## Part 1: Decision log

Each entry has the same six lines. "Backed by" names the number or experiment that will support the decision once the work is done; until then the decision rests on the reasoning alone, and you should say so if asked. When a decision is made or changed during the work, add or amend an entry here in the same format, with the date.

Entries D1 to D12 record how the plan of 2026-10-06 differs from Aviv's original five-step plan.

### D1. The agent investigates incidents, not log lines

- **Your plan:** code marks each log as needing an agent or not.
- **Decision:** the agent gets one incident, never a single line. An incident is the logs of one log shape while that shape's incident is active (D19). Amended 2026-10-10; it was: alert logs of one component with less than G minutes between them.
- **Why:** one failure writes many lines, and an analyst investigates an event, not a line. On this data a rough keyword filter gives about 139,000 error-like events, about 6,700 incidents and about 300 distinct incident signatures (`notebooks/01_initial_EDA.ipynb`).
- **What it costs:** an incident never spans two log shapes, so a cascade across shapes becomes several incidents, and one incident can hold unrelated nodes that share a shape. The agent has a tool that lists the other active incidents on the same node or component, and it can say that the nodes of its incident are unrelated.
- **Backed by:** the incident counts from task 1.4, agent calls per day of logs in experiment E7, and the cost projection in Step 4.
- **In the interview:** "LLM cost should scale with the number of distinct problems, not with log volume, so I grouped before I called a model."

### D2. Triage is a log shape catalogue; keywords are the baseline

- **Your plan:** keyword search plus a hazard score per template, perhaps frequency rules.
- **Decision:** one catalogue row per log shape gives its route: `ignore`, `handle`, `investigate`, or `rule`, which names a rule in `config/triage.yaml` that decides from counts or values (D17). You label a few dozen log shapes (D21); the others have no row (D3). A new log shape can be classified once by a small model and stored as unreviewed. The keyword rule stays, as the baseline to beat. Amended 2026-10-10; the label was alert or not.
- **Why:** for most log shapes the answer never changes, so it is decided once and cached: at most 141 decisions instead of 433k. The few that depend on frequency or values get a named rule, so the exception is data too. A new log shape or a new rule needs no code change. Keywords get judgment cases wrong in both directions: `Link ok` is filed under state `error`, and `PSU status ( on off )` contains no error word.
- **What it costs:** rules are written by hand, and only with the conditions the router knows; a new kind of condition needs code.
- **Backed by:** experiment E1. If keywords turn out as good as the model, keep keywords and report that.
- **In the interview:** "The decision is per log shape, so I pay for it once per log shape, and where frequency matters I write a rule, not code. I measured the LLM against a keyword baseline on my own labels before trusting it."

### D3. Unknown log shapes go to the agent

- **Your plan:** not specified, though you wanted criteria "general enough so that we don't miss critical errors".
- **Decision:** a log shape with no catalogue row is routed to `investigate`. Keyword hits on its template never make it `ignore`; they only set its priority when incidents wait for the agent (D20). Amended 2026-10-10; it was: treated as an alert until classified.
- **Why:** in operations and in security, a missed problem costs more than a wasted investigation. A keyword list cannot anticipate how a new message will be worded, so letting it skip the agent would miss problems such as `PSU status ( on off )`.
- **What it costs:** a format change that creates many new log shapes at once opens many incidents at once. One incident per log shape (D19), the cap on agent calls (D20) and the quarantine counter limit the damage.
- **Backed by:** the log shape novelty plot (`docs/figures/log_shape_novelty.png`; after the first year, 1 to 9 new log shapes every quarter, `notebooks/04_log_shape_novelty.ipynb`) and E7.
- **In the interview:** "I chose to fail open: unknown means look at it, not ignore it."

### D4. The knowledge base is mandatory, and deliberately simple

- **Your plan:** leave the knowledge base out of round one, evaluate, then add it and evaluate again.
- **Decision:** your two-round experiment stays. The knowledge base is a fixed item on day 2: a folder of markdown runbooks, searched by keyword ranking (BM25). No embeddings, no vector database.
- **Why:** citations are a stated requirement, so a system without a knowledge source is incomplete. Ten documents do not need semantic search. A folder of files means adding a recommendation is adding a file.
- **What it costs:** the runbooks are written by us from public manuals, so they are partly synthetic. The evaluation therefore measures whether the agent uses and cites them faithfully, not whether the advice is what a real operator of that cluster would do. Keyword search also misses paraphrases, which is acceptable at this size.
- **Backed by:** experiment E2.
- **In the interview:** "I ran the agent without knowledge first to get a baseline, so I can show exactly what the knowledge base adds."
- **Amended 2026-10-11:** the knowledge base is `kb/cluster_facts.md` alone, the fact sheet read from the logs and the public sources; no runbook was written. It is split at its headings into passages and searched by BM25 through a `search_knowledge` tool that exists only when `knowledge` is on in `config/models.yaml`. The agent cites a passage by its id, in a remediation step's `citation` or by quoting it as an evidence line. Code records a citation that names no passage the agent retrieved, as it records an evidence line that names no shown id, and rejects neither. The system prompt is unchanged: the tool's description tells the agent that the knowledge exists and how to cite it. Backed by the knowledge arm of `scripts/evaluate_trajectories.py`: the ten golden cases run with the tool on, beside the same cases run without it ([06_knowledge_base.md](plan/06_knowledge_base.md)).

### D5. Two datasets, and the first is written before the agent exists

- **Your plan:** one golden dataset of trajectories produced by the system, labelled by you.
- **Decision:** (a) golden incidents: inputs with expected answers, written at the end of Step 1. (b) a judge calibration set: agent outputs that you graded.
- **Why:** they answer different questions. (a) tells you if the agent is right. (b) tells you if the judge is right. Expected answers written before seeing any agent output are not anchored by it. Incident labels stay valid when the agent changes, so they work as a regression suite; trajectory labels expire with every new agent version.
- **What it costs:** writing an expected root cause needs real understanding, so only confident cases qualify, and 25 is a small sample.
- **Backed by:** `labeling/golden_incidents.yaml` with a dev and holdout mark on every entry. Since 2026-10-11 the first golden set is `labeling/golden_cases.yaml`: 10 single logs (D23) whose expected answers are the verdicts of the hand investigations, written before any agent ran.
- **In the interview:** "I separated evaluating the agent from evaluating the evaluator."

### D6. You label with hindsight; the agent cannot see the future

- **Your plan:** you wanted cases you could grade with high confidence, without saying how to get that confidence.
- **Decision:** when labelling, you look at what happened after the incident: a recovery message means it cleared by itself, an operator command means a human acted. The agent's tools never return a log later than `max_visible_timestamp`: the log time at which its run started plus the time the agent has spent since (D20). Amended 2026-10-10; the limit was the incident's end.
- **Why:** hindsight is the only source of trustworthy labels without a domain expert. Blocking the agent from the future keeps the evaluation honest, because in real use that information does not exist yet. Letting the visible time grow with the agent's own time also shows what a slow agent misses.
- **What it costs:** an operator action after an incident is correlation, not proof of cause. Incidents with no clear aftermath are excluded, so the golden set leans toward clear-cut cases and likely overstates accuracy on ambiguous ones. The agent starts on the first lines of an incident, so an expected answer has to be reachable from what was visible then.
- **Backed by:** the `hindsight` field on each golden entry, citing log ids.
- **In the interview:** "I used operator behaviour recorded in the logs as weak supervision, and I made sure the agent could not see it."

### D7. Code measures what it can; the judge has three pass/fail criteria

- **Your plan:** a judge grades tool-call efficiency, hallucination, reasoning logic, safety of actions and precision of the solution; code scores cost and speed.
- **Decision:** your criteria are redistributed.

  | Your criterion | Where it went |
  |---|---|
  | Tool-call efficiency | Code: number of calls, repeated calls, hit the step limit |
  | Token cost, speed | Code, as you planned |
  | Hallucination | Split. Invented log ids and citations: code (the validator). Unsupported claims: judge, `grounded` |
  | Precision of the solution | Judge: `root_cause_match` against your expected answer, and `citation_supports_step` |
  | Reasoning logic | Dropped as its own criterion. Hard to label consistently, and its effect shows up in the outcome criteria |
  | Safety of actions | A `risk` field on every remediation step, plus an optional judge criterion if time allows |

- **Why:** code is exact, free and repeatable. A judge is noisy and every criterion it owns needs its own human labels before it can be trusted. Pass or fail is faster to label than a 1 to 5 scale, forces a decision, and gives agreement numbers that are easy to read.
- **What it costs:** no direct measurement of reasoning quality, and safety is only lightly covered.
- **Backed by:** the judge calibration table and the validation failure rate.
- **In the interview:** "I applied 'right tool for the job' to the evaluation too: an LLM judge only where a deterministic check is impossible."
- **Amended 2026-10-11:** the first judge, `prompts/judge_v1.md`, reads one complete trajectory and nothing else. It is given no expected answer and compares the agent with no human: it judges whether the work holds up on what the trajectory shows. Comparing the agent's verdicts with Aviv's is done separately, by hand. It grades six pass/fail criteria in a single call, each with its reasoning written first: `grounded`, `sufficient_investigation`, `tool_use`, `efficiency` (independent calls asked together in one round, nothing repeated, no wasted rounds), `verdict_supported`, `remediation_quality`, and adds two texts, what the agent did well and what was missing. `root_cause_match` is dropped because it needs an expected answer; `citation_supports_step` waits for the knowledge base. One call for all six is cheaper and simpler than one call per criterion; the cost is that the grades can lean on each other. The verdict gained a `scope` field: one source, several, or cluster-wide.

### D8. The judge is tuned on one half of the reference labels and reported on the other

- **Your plan:** compare the judge to your labels, study its mistakes, improve it.
- **Decision:** the same, with a split: adjust the judge prompts on one half, report agreement on the untouched half. A rule fixed in advance: a criterion whose judge catches fewer than 70% of the reference fails is not used for conclusions.
- **Why:** tuning a prompt on the labels you report on inflates the agreement, for the same reason you do not report training accuracy.
- **What it costs:** it halves a sample that is already small, so the uncertainty is about plus or minus 20 points.
- **Backed by:** the agreement table, with counts.
- **Amended 2026-10-11:** due to time constraints the reference labels were produced by Gemini 2.5 Pro on its web UI, not by Aviv grading each trajectory by hand. Gemini Pro received the exact prompt and tool descriptions the judge receives, together with each trajectory's text, and its JSON response was recorded. This is LLM-vs-LLM agreement, not human-vs-LLM. Gemini Pro is a frontier model from a different family than both the investigator (Nemotron) and the judge (GPT-OSS-20B), so its grades are independent. The report states this caveat wherever the agreement numbers appear.
- **In the interview:** "The judge is a classifier, so I evaluated it like one: held-out data and a threshold set beforehand. The reference labels came from a frontier model rather than from me, due to time — I state that openly, and I explain why it is still informative."

### D9. Bad outputs come from a weak model and from injected defects

- **Your plan:** perhaps tell the main agent to do a bad job on purpose, and use several models of different sizes.
- **Decision:** keep the different models. Replace "do a bad job" with injected defects: take a good output and break it in one known way (wrong citation, invented fact, wrong root cause).
- **Why:** an agent told to fail produces exaggerated failures unlike real ones. A weak model fails the way agents really fail. An injected defect has a known label and tells you which type of error the judge misses.
- **What it costs:** injected defects are easier to spot than natural ones, so they are reported separately and never mixed into the main agreement number.
- **Backed by:** detection rate per defect type.
- **In the interview:** "It is mutation testing for the judge."

### D10. A hand-written agent loop instead of a framework

- **Your plan:** LangChain, LangGraph or ReAct, preferring ready-made.
- **Decision:** about 80 lines on the OpenAI client pointed at NVIDIA.
- **Why:** the list of messages is the trajectory, so tracing needs no extra tooling. You can explain every line. Free hosted models sometimes return malformed tool calls, and handling that is simpler in your own loop than inside a framework.
- **What it costs:** no ready trace viewer, no checkpointing, no built-in human approval step. You write retry and parsing yourself.
- **Backed by:** the trace format and the validator.
- **In the interview:** "I wrote the loop to understand it and to own the trace format. For production I would adopt a framework once I needed checkpointing and approval steps."

### D11. The final answer is a schema with three verdicts, checked by a validator

- **Your plan:** the agent must be able to say "there is no problem here".
- **Decision:** the answer is a structured object with a verdict of `actionable`, `benign` or `insufficient_evidence`. A code validator rejects any answer citing a log or passage the agent never retrieved, and allows one retry.
- **Why:** `benign` is your "no problem". `insufficient_evidence` lets the agent escalate instead of guessing. A citation can only be trusted if a program can confirm the agent really read the source.
- **What it costs:** the validator proves the source was retrieved, not that it supports the claim. That second half is the judge's `citation_supports_step`.
- **Backed by:** validation failure rate per model.
- **In the interview:** "Citations are checked mechanically for existence and by a judge for support."
- **Amended 2026-10-11:** evidence is free text with a cheap code check. The agent quotes each line it relies on, a log or a row of a timeline or summary, and says why it matters. Every tool result carries an id on each row, a log id or a log shape id, and returns the ids it showed. `unanchored_evidence` then reports the evidence lines that name none of the ids the agent was shown. It is a signal and not a proof: a line that names a shown id can still misquote it, so whether the quote is faithful is left to the judge's `grounded` criterion and to a person. `count_logs` is the one tool whose rows have no id. Code also checks the format: the verdict must have a reasoning and at least one evidence line, and every tool call must carry a `reasoning` of one to three sentences, so each step of a trajectory says why it was taken.

### D12. A different model for each role

- **Your plan:** choose a model.
- **Decision:** a small model classifies log shapes, a main model investigates, and the strongest available model from a different family judges.
- **Why:** log shape classification is a narrow task where a small model may be enough. A judge from the same family as the agent tends to favour its own style.
- **What it costs:** three models to keep working on a free tier with a shared rate limit.
- **Backed by:** the model smoke test, E1 and E3.
- **In the interview:** "I matched model size to task difficulty and measured the trade."
- **Amended 2026-10-11:** the investigator's hidden thinking is capped at a budget of 200 tokens. Both chosen models think before they answer, in text that is never returned, and that thinking was most of the latency. On the first round of one investigation, five times each, the median was 34.7 seconds with full thinking, 11.5 with a budget of 500 tokens, 7.1 with a budget of 200 and 2.5 with none (`notebooks/06_model_selection.ipynb`, re-run on 2026-10-11 after the round limit changed; the first run gave 18.0, 8.2, 5.8 and 3.2, in the same order). The investigator already writes a `reasoning` in every tool call and in its verdict, so the reasoning that matters is the part that is logged. What the cap costs: in that comparison full thinking asked for several tools in one round, a median of 5 against 1 for the other settings, so less thinking means more rounds. `config/models.yaml` holds the setting per role under `options`, so comparing the settings on the golden cases is one changed line.

### D13. From the `labeling-helper` branch, only the log store changes are kept (2026-10-06)

- **Earlier work:** an unmerged branch holds a labelling form with an eight-field label per log shape, LLM draft labels and a human-against-LLM agreement check, plus changes to the log store.
- **Decision:** take the log store changes: a log shape is identified by component, state and masked text (it was called a template until D16); shared parsing; named masks; `requirements.txt`. Leave the labelling package on the branch. A log shape label is two columns: alert or not, and a category. Since 2026-10-10 the first is a route (D2).
- **Why:** the pipeline consumes one decision per log shape, so eight fields multiply the labelling time without changing what the system does in two days. A yes or no label also gives a plain precision and recall for experiment E1.
- **What it costs:** the richer fields (event role, whether a number matters, what context is needed) are not collected. The branch's ready agreement check is not reused, so E1 needs its own small scoring function.
- **Backed by:** the time Step 1 labelling actually takes, and E1.
- **In the interview:** "I had started a richer labelling tool and cut it back once I saw the pipeline needed one decision per log shape."

### D14. A judge inside the loop is an optional experiment, not part of the default pipeline (2026-10-06)

- **Your idea:** see what happens when the judge reviews the agent's answer before it is returned.
- **Decision:** experiment E6, optional. A configuration `main_kb_judge`: after the validator accepts an answer, the judge checks `grounded` and `citation_supports_step`. On a fail the critique goes back and the agent revises once. The default pipeline stays without it unless E6 shows a gain.
- **Why:** it is the cheapest form of one agent verifying another's work, so it turns the multi-agent point from an argument into a measurement. It stays out of the default because it adds LLM calls to every incident, and a reviewer with false alarms can make correct answers worse.
- **What it costs:** a measurement trap. The judge that steered an answer cannot score its own influence, so E6 is decided on measures the in-loop judge never saw: root-cause match against the expected answer, the code metrics, and your own reading of each revised answer before and after. `root_cause_match` cannot run in the loop at all, because it needs an expected answer. About 1.5 hours outside the budget.
- **Backed by:** E6's revision rate, false alarm rate, fix rate, harm rate and added cost.
- **In the interview:** "I tested a reviewer in the loop as a controlled experiment, and I did not let the reviewer grade its own influence."

### D15. One row per event: a repeated line updates its row (2026-10-07)

- **Earlier plan:** drop identical copies at ingest and keep the first.
- **Decision:** the `logs` table holds one row per event, identified by node, component, state, time and message. A line that repeats a stored event does not add a row: the row takes that line's flag, record counter and raw text, and `n_copies` goes up by one.
- **Why:** copies are one event reported several times, so storing each as its own log would inflate every count the agent sees. Dropping them lost information instead: among copies the flag only moves from 0 to 1 in file order, never back, so keeping the first copy kept the stale flag in 3,287 events. The rule lives in the table and not in the loading code, so it holds across loads, which is what a stream needs.
- **What it costs:** time is in whole seconds, so two real events from the same source with the same message in the same second become one row, and `n_copies` is the only trace. The unique index holds the message text, which makes the database larger and the build slower. What the flag means is still unknown.
- **Backed by:** `notebooks/03_flag_column_analysis.ipynb` for the order of the flags among copies, and the rebuild, which stores 411,483 rows and merges the other 22,007 lines of the file into them.
- **In the interview:** "Duplicates are normal in a stream that delivers at least once, so I made the store idempotent: the same event arriving again updates its row instead of adding one."

### D16. The labelled unit is a log shape; the template is its masked text (2026-10-10)

- **Earlier plan:** the table `templates` held rows of component, state and masked text, and the masked text was also called the template, so one word named both the row and one of its columns.
- **Decision:** a row is a **log shape**, stored in `log_shapes`, and `logs.log_shape_id` points at it. `template` keeps its meaning: the masked message text, one of the three columns that identify a log shape. The planned names follow: `log_shape_catalog`, `labeling/log_shapes.csv`.
- **Why:** the same masked text under another component or state is another log shape and can take another label (`not responding` from a node and from a domain), so the unit that is labelled must not carry the name of only one of its parts.
- **What it costs:** in the log parsing literature (Loghub, Drain) "template" means the masked text alone, so every comparison with it has to say which of the two is meant. The database had to be rebuilt.
- **Backed by:** naming only. The rebuild prints the same 411,483 logs, 22,007 merged copies and 141 log shapes as before.
- **In the interview:** "A label belongs to a message in its context, component and state included, so I named that unit separately from the masked text."

### D17. Every new event is routed by code before any LLM sees it (2026-10-10)

- **Earlier plan:** a catalogue said alert or not per log shape, and every alert log went to incident grouping.
- **Decision:** for each new event, code builds a `LogContext`: the log, its log shape, its catalogue row, keyword hits when the shape has no row, and any number of extra named fields. A router returns a `Decision`: a route (`ignore`, `handle` or `investigate`), the id of the rule that decided, and a reason. The route comes from the catalogue row. A row whose route is `rule` names a rule in `config/triage.yaml` that reads one feature, such as the log count of this shape on this node in the last hour, compares it with fixed operators, and must end with an `else`. A shape with no row goes to `investigate` (D3). `handle` runs the deterministic handler the row names, once for each affected node, and its answer has the verdict's format.
- **Why:** most decisions are fixed per log shape and a few depend on frequency or values. Both are kept as data, and code only knows the kinds of condition. The rule id on each decision is the audit trail and lets every rule be scored on its own. A handler costs nothing and answers at once when the fix is known.
- **What it costs:** rules are written by hand and can only say what the operators allow. A count rule ignores the first logs of a burst until the threshold is crossed, so an incident pulls those logs in when it opens. Extra fields are unchecked names, so a missing one raises an error instead of reading as zero.
- **Backed by:** the share of logs and incidents decided by each rule in the replay, and E1 for the catalogue.
- **In the interview:** "Code decides what code can decide, and every decision says which rule made it."

### D18. Stats look only at the past, and production keeps them in a per-chunk cache (2026-10-10)

- **Earlier plan:** log shape stats were computed over the whole database.
- **Decision:** a stat is a count, of logs or of distinct nodes, for one log shape, over the whole cluster or one node, in a window that ends at the log: by default the last hour, day, week and month. A stat is decided by time alone: it counts the logs whose time is inside the window, the log's own second included, and never a log with a later time. Amended 2026-10-10; it was the logs before the log in processing order, time and then id. They are computed lazily, when a rule, the incident card or the agent asks for them. In this repository they are SQL range queries over the log store. In production they are a cache updated in batches as chunks are ingested: before a chunk is routed it holds everything before the chunk, and each log is added as it is routed, so the cache is always current for exactly the next log. A catalogue row can name stats to fetch for every incident of its shape, and the agent has a tool for any other.
- **Why:** stats over the whole database include the future, which a deployed system cannot see, so decisions made with them would look better in a replay than they would be in production. Lazy computing means telemetry, most of the volume and ignored by its catalogue row, costs no query. A cache turns a range scan into a lookup, which is what makes per-log stats affordable on a live stream.
- **What it costs:** in SQL each stat scans a range, which is slow for frequent shapes over a month. A cache must return exactly the numbers SQL returns. Ingesting chunks in parallel would need an order across the workers, and is not attempted.
- **Backed by:** if the cache is built, a test that cache and SQL agree on every stat of a replay.
- **In the interview:** "Every number a decision uses is one the system could have known at that moment, and in production it costs a lookup."

### D19. An incident is one log shape while it is active (2026-10-10)

- **Earlier plan:** alert logs of one component with less than G minutes between them formed one incident.
- **Decision:** a log routed to `handle` or `investigate` opens an incident when none of its log shape is active. A later log of the shape joins the active incident, whatever its own route. Routes rank `ignore`, `handle`, `investigate`, and a joining log can only raise the incident's route: a `handle` incident that receives an `investigate` log is escalated, and the agent gets the handler's output. An incident stays active for a TTL that every new log restarts, 15 minutes by default and set per severity in config, up to a maximum duration; after that the next log opens a new incident. Time is log time, the latest timestamp ingested so far, so a fast replay behaves as the stream would. An incident that the agent or a handler has answered is marked resolved: it stays active so that new logs join it, and nothing more is done for it. Incidents are never merged.
- **Why:** an analyst investigates a problem, not each of its lines, and the active incident is what keeps a burst of a thousand lines to one agent call. Log time makes the behaviour independent of replay speed. With one shape per incident nothing needs merging: a problem spreading over nodes is already one incident, and a cascade across shapes is for the agent to find.
- **What it costs:** unrelated nodes that share a shape share an incident, and a cascade across shapes is several incidents. The agent's `related_incidents` tool shows the others, and its verdict can mark them resolved. A chronic shape is investigated again after each maximum duration.
- **Backed by:** E7, agent calls per day of logs with and without active incidents.
- **In the interview:** "Active incidents are a dedup cache with a TTL, and the TTL runs on log time so that a replay is faithful."

### D20. The agent starts at once, sees time pass, and is capped (2026-10-10)

- **Earlier plan:** the agent ran on a finished incident and saw logs up to its end.
- **Decision:** an incident routed to `investigate` gets the agent as soon as it opens. Ingestion never waits for the agent. The agent sees logs up to `max_visible_timestamp`: the log time at which its run started plus the real time it has spent since. The latencies of its calls are recorded, so a run replayed from the LLM cache sees the same logs. Agent runs are capped per hour of log time. Incidents over the cap wait in a queue ordered by severity and, for unknown shapes, by keyword hits. When the cap is reached the program says so loudly and prints the waiting incidents. A waiting incident is investigated even if it expires while it waits.
- **Why:** an operator needs the answer while the problem is happening. Visible time that grows with the agent's own time shows the real cost of a slow agent: it reasons on less, and answers later. The cap bounds the cost when a format change opens many incidents at once.
- **What it costs:** the agent starts on the first lines of a burst, which say the least. Its tools let it look further as time passes, and an optional task sends it the new logs of its incident during the run. An incident that waits under the cap is answered later, which E7 measures.
- **Backed by:** E7: tokens and dollars per incident and per day, against the lag from opening to verdict.
- **In the interview:** "The agent sees the world as it was while it worked, not as it was when the replay finished."

### D21. Only a few dozen log shapes are labelled (2026-10-10)

- **Earlier plan:** you label every log shape.
- **Decision:** you label a few dozen log shapes with a route, a severity and a category: the most frequent ones first, and every log shape of a golden incident. The others have no catalogue row, go to the agent (D3), and are seen in the evaluation.
- **Why:** the most frequent shapes decide most of the volume, and so most of the agent's load. The long tail is what the agent is for, and labelling it would hide how the system copes with shapes nobody labelled.
- **What it costs:** E1 is scored on a few dozen rows, so its numbers are rough. The unlabelled shapes open many incidents, which the cap and E7 deal with.
- **Backed by:** the share of logs covered by the labelled shapes, E1 and E7.
- **In the interview:** "I labelled the head of the distribution, let the agent take the tail, and measured what the tail costs."

### D22. Every read of the log store is bounded in time, and the store serves the agent only (2026-10-10)

- **Earlier plan:** the log store had general read helpers: any filter, any time span, oldest first.
- **Decision:** every read of `LogRepository` takes a start and an end, both required, and refuses a range longer than 31 days. `search` returns the logs of the range newest first. The repository holds only the queries the agent's tools and the router need: `search`, `count_by`, `stats` and `node_timeline`. Anything that only a notebook or a script needs, such as drawing a random log or counting a log shape over the whole history, is written in that notebook or script.
- **Why:** an investigation starts from a log and asks what happened around its time, so a query with no time range has no use, and one that an agent can call must not be able to pull the whole table. Newest first means that when a limit cuts the result, it keeps the logs nearest the moment being looked at. A small store with one way to ask each question is easier to defend and to keep correct.
- **What it costs:** a question about a longer period takes several calls. Whole-history counts, which the labelling table needs, are SQL outside the repository. The 9 logs with no usable timestamp are not returned by any read.
- **Backed by:** unit tests that every read refuses a range over 31 days, a range that ends before it starts and a missing bound.
- **In the interview:** "A tool an agent can call is bounded by construction: it cannot ask for everything, only for a window of time."
- **Amended 2026-10-11:** one read has no start, `LogRepository.shape_history(end)`: the counts, first seen and last seen of every log shape up to a moment. It returns one row per log shape and never a log, so the reason for the bound does not apply to it. The agent's `find_log_shapes` tool needs it to say which messages exist so far.

### D23. The agent investigates one log, from a fixed starting context (2026-10-11)

- **Earlier plan:** routing and active incidents are built first (Step 2A), and the agent receives an incident card.
- **Decision:** the agent is built first and investigates a single log. It always starts from the same three things: the log, the timeline of its node for the hour before, and the logs of the same log shape over the whole cluster for the hour before. It may submit a verdict at once or call tools first. Its tools are the helpers Aviv used in the hand investigations, moved from the notebooks to `agent/tools.py`: the notebooks call them with no limit and the agent with a limit at its visible time. Routing, incidents and the replay are postponed.
- **Why:** time. The 10 logs Aviv investigated by hand and is sure about already have a verdict, so an agent that takes a log can be run and graded against them now. An investigation by hand and one by the agent use the same code, so a difference between them is a difference of judgment and not of data.
- **What it costs:** one agent run per log, so the cost follows log volume until incidents exist (D1): about 6,000 input tokens on every call before any tool result, and up to 4 rounds. This cannot run on every log, and the report says so. The visible time stays at the log's own time during a run; a production system would let it move as the agent works (D20). The contracts of the overview that speak of incidents (the card, `related_incidents`, `resolves_incident_ids`) are not built.
- **The tools, amended 2026-10-11:** the agent has six general tools: `search_logs`, `node_timeline`, `log_shapes_between`, `count_logs`, `find_log_shapes` and `what_followed`, the last one for hindsight on a log shape. Tools that only make sense for one kind of device, such as the notebooks' `gige_levels` and `minutes_at_level`, are not built in. In a real deployment some tools are ours and some come from the user or the user's software, and a config per deployment lists the tools that are available.
- **Backed by:** `labeling/golden_cases.yaml`, and the tests that no tool returns a log after the visible time.
- **In the interview:** "I gave the agent the same tools I had used by hand, and the cases I had already solved became its first test."

### D24. The evaluation reads the judge as if it were calibrated (2026-10-11)

- **Earlier plan:** a criterion whose judge misses more than 30% of the reference fails is not used to draw conclusions (D8).
- **Decision:** `scripts/evaluate_trajectories.py` reports every judge criterion on equal footing, with no trust mark and no expected verdicts from Aviv. The caveat is stated in capitals at the top of the script and printed on every run: the judge was measured against Gemini Pro on seven tune items, not against a human, and missed most of the reference fails on `grounded` and `verdict_supported`.
- **Why:** time. Labelling expected verdicts and re-tuning the judge would cost more than the remaining budget, and a figure that greys out most of its bars says less than one that shows them with a stated caveat.
- **What it costs:** the judge's pass rates on `grounded` and `verdict_supported` are likely too high. The code checks of `evals/score.py`, which are stricter on exactly those two, are shown beside them so a reader can see the gap.
- **Backed by:** `labeling/judge_results/` and the agreement table of `notebooks/09_judge_calibration.ipynb`.
- **In the interview:** "The judge's numbers are shown as measured, with the calibration caveat next to them, and code checks beside them for the criteria a rule can read."

### Deliberately left out

| Left out | Reason |
|---|---|
| Several cooperating agents | One agent has to work and be measured first. More agents add cost, latency and new ways to fail. The one exception is the optional reviewer of E6 (D14) |
| Fine-tuning | Two days. The catalogue labels are the training set a later fine-tune would use |
| Vector database | Ten documents |
| Merging incidents | One incident per log shape needs no merge. A cascade across shapes is linked by the agent, which marks the related incidents resolved (D19) |
| Reusing a verdict across incidents of the same log shape | An active incident already keeps one verdict for all the logs it collects. A new incident of the same shape can need a different answer in a different context. Its numbers are used in the cost section only |
| Parallel ingestion | The replay ingests one 5-minute chunk at a time. Parallel workers would need the stats ordered across them (D18) |

## Part 2: Notes by date

One short entry per work session: what was done, what was found, what was learned.

### 2026-10-04: the flag column

Every number here is reproduced in `notebooks/03_flag_column_analysis.ipynb`.

The logs come with no error label. The one undocumented column that might have been one, `flag`, is not. It takes the values 1 (418,546 rows), 0 (11,779) and -1 (3,165).

**Flags 0 and -1 mark repeats.** Rows with those flags are almost always identical copies of another row: only 8.7% of the flag 0 rows and 0.7% of the flag -1 rows have no copy, against 94.5% of the flag 1 rows. When copies mix flag 0 and flag 1, which happens for 3,287 events, exactly one copy has flag 1. Flag -1 never appears together with flag 1.

**The flag says nothing about severity.** Flags 0 and -1 appear on 15 of 403 message patterns, mostly routine state reports such as `running` and `configured out`, and 14 of those 15 also appear with flag 1.

**Two decisions followed.** The flag is not used as a label, and identical copies are dropped before any analysis. That leaves 411,483 distinct events out of 433,490 rows.

### 2026-10-06: planning

The numbers in the next two paragraphs come from a first pass over the data, before any labelling, and `notebooks/01_initial_EDA.ipynb` reproduces each of them. Step 1 replaces the keyword filter used here with real labels.

**The data.** 433,490 lines over 33 months (2003-07-31 to 2006-04-30), about 411,000 distinct events once identical copies are dropped. A typical day with logs has 236 events and the busiest has 12,942. Masking the variable parts of the messages and keeping the component and state gives 249 log shapes. Half of them are four messages that differ only in the length of a list, so the real variety is closer to 140. New log shapes never stop arriving: after the first year, every quarter still brings between 1 and 12 that were never seen before. That is the practical reason the system has to adapt without code changes.

**Lines are not the unit of work.** A simple keyword filter marks about 139,000 of the events (34%) as error-like. Grouped by component and time they form about 6,700 incidents, and those have only about 300 distinct signatures, a signature being the component and the set of log shapes in the incident. The 20 most common signatures cover 89% of the incidents. So the agent investigates incidents, and its cost follows the number of distinct problems, not the volume of logs.

**What the cluster probably is.** No documentation comes with the data. The vocabulary of the logs (SRM, RIS boot, LMF, NIFF, the interface names `ee0` and `alt0`, file domains, partitions) points at a Compaq/HP AlphaServer SC running Tru64 UNIX with a Quadrics interconnect. Step 1 checks this against vendor manuals; at least one is online.

**No labels exist.** [Loghub](https://github.com/logpai/loghub), the public source of the dataset, lists none for HPC. This matches the earlier finding that the `flag` column is not an error label. Every label in this project has to be made here. One naming trap: the column the code calls `event_id` is Loghub's `LogId`, and it does not identify an event: 325,352 values over 411,483 distinct events, and 78,572 of those values sit on more than one event (`notebooks/01_initial_EDA.ipynb`). Copies are therefore dropped by comparing node, component, state, time and message.

**The template masks hold up.** Checked against Loghub's hand-annotated templates on its 2,000-line sample, in `notebooks/02_loghub_template_check.ipynb`: the masks never merge two different messages into one template. That is the templating error that matters, because a wrong merge could hide an alert under a non-alert label. On masked text the grouping agrees with the annotators on 97.2% of lines; Loghub's benchmark lists the Drain parser at 88.7% on the same sample. The masks were written looking at this data, so this shows they are sound here, not that they would generalise to a new format.

**The plan.** Five steps, one brief per step in `docs/plan/`, with the design decisions in Part 1. Two additions the same day. An optional experiment puts the judge inside the agent's loop (D14). The incident card lists log shapes in order of first appearance, because the earliest abnormal event is usually closer to the cause than the cascade that follows it.

**A practical constraint.** NVIDIA's free tier is reported to allow about 40 requests a minute across all models on one key. Every experiment therefore has to be cached and resumable.

**Learned.**

- Send an LLM the distinct problems, not the log volume.
- An LLM judge is a measuring instrument. Its numbers mean nothing until it is checked against human labels, and it cannot grade an answer it helped shape.
- There is no single correct set of templates. The right grouping depends on what it is used for, so agreement with someone else's annotation is a sanity check and not a score.

### 2026-10-07: what the columns really hold

Every number here is reproduced in `notebooks/01_initial_EDA.ipynb`.

**The first column is a record counter, not an event id.** It was restarted several times: it reaches 2.6 million in early 2004, starts again from 0, and restarts again later. Two events that share a value are unrelated and at least 18 days apart, with a median of 532 days. It is unique only between restarts, which is why copies are dropped by comparing the other fields.

**The node column is not always a node.** It names whatever the line is about. Only 158,466 of the 411,483 events come from the 256 compute nodes. The rest come from 16 interconnect switch modules, 8 ethernet switches, 8 domains, 8 terminal servers, a management server, a partition called `full`, and 2,078 command numbers, one for each operator command. 38 events have no source at all. So a count of "nodes" in an incident is a count of sources, and for operator commands the nodes affected are named inside the message.

**One format appears only at the very end.** 50 events in 40 minutes on 2006-04-20 are the only ones with two words in the node column: `resourcemgmtdaeomon node-25` and `node-31`, all saying `failed to configure resourcemgmt subsystem err = 10`. It is a small real case of a new format arriving late.

**The product names were probably replaced before release.** The message `An ServerFileSystem domain panic has occurred` has "An" in front of a consonant, so the original word began with a vowel. That fits the generic names all over the logs (`ClusterFileSystem`, `ServerFileSystem`, `resourcemgmt`), and the misspelt `daeomon` looks like a slip made during that replacement.

### 2026-10-07: the database in its final shape

The counts of logs, copies and log shapes are printed by `python -m scripts.build_db --rebuild`. The Loghub numbers are in `notebooks/02_loghub_template_check.ipynb`.

**The log store changes of the `labeling-helper` branch are on `main`** (D13), and the project runs on Python 3.14.

**One row per event.** A line that repeats the node, component, state, time and message of a stored row is the same event reported again. It does not add a row: the row takes the latest line, and `n_copies` counts the lines (D15). The rebuild stores 411,483 logs and merges the other 22,007 lines into them, which is exactly the number of distinct events the flag notebook counted. 9 of the stored logs have an unusable timestamp.

**The latest line wins because of how the flag behaves.** In the 3,287 events whose copies mix flag 0 and flag 1, the flag 0 lines always come first in the file and the flag 1 line last. The flag therefore looks like a state of the record that changes once, and the stored flag is the final one: 408,538 events end on 1, 2,390 on 0 and 555 on -1 (`notebooks/03_flag_column_analysis.ipynb`).

**A list no longer makes a new template.** A list of node names, a list of numbers and a set of nodes in brackets are each masked as a single item, so `Command Failed on: node-3` and the same message naming a long list of nodes share one template. Asterisks printed where a number could not be shown are masked as a number, so `Fan speeds ( 3552 3534 3375 **** 3515 3479 )` shares a template with the same report showing six numbers. Together this takes the log shapes from the 249 counted during planning to 141. Every label from here on is attached to one of these 141.

**The masks merge two Loghub templates in one place, on purpose.** Loghub annotates the fan report with asterisks and the one with six numbers as two templates; here they are one, because the message is the same and only a value differs. That is the single group that merges two annotated templates, 90 lines of the sample, and it brings agreement on masked text to 93.1% of lines, from 97.2%. Two annotated templates remain split, covering 48 lines; both name a filesystem domain, which the masks keep as text.

**Learned.** A check that backs a claim has to be re-run when the code under it changes. The Loghub notebook was the cheapest way to see exactly which messages a new mask brought together. And cleaning that throws a field away should wait until the field is understood: merging copies keeps what dropping them lost.

### 2026-10-07: what the cluster is

Every source is listed in `kb/sources.md`, with how much of it could be read.

**The logs are LANL's "System 20 usage event info".** Loghub names System 20 at Los Alamos as the origin, and LANL's own failure data page still lists the release: 433,490 records in a file called `MX20_NODES_0_TO_255_EVENTS`, next to a "usage with domain info" file. The record count is exactly the number of lines in `data/original_dataset/HPC.log`. That confirms the 256 nodes and that the system has domains. Loghub's paper is reported to describe System 20 as 49 nodes, which does not fit the logs; the paper itself was not opened.

**It is almost certainly an AlphaServer SC, and its management software has a public manual.** An AlphaServer SC is a supercomputer built from Alpha servers joined by a Quadrics interconnect and run by RMS, the Resource Management System: daemons, command line tools and an SQL database. No source says that System 20 is one. The identification rests on the vocabulary of the logs and on the contents page of the RMS Reference Manual, which matches it: a chapter on event handling with a list of events generated, a partitions table, link states and link errors, a figure with a terminal concentrator, and a list of status values.

**Only the first 20 pages of that manual could be read.** The site that hosts it shows the title, contents and introduction as text, and its link to the full file is broken. So the manual confirms what the system is and which concepts exist, but not what each status or event means. The companion System Administration Guide was not found at all.

**What the sources settle about the vocabulary.** A source can confirm what a term means. That a message in the logs uses the term in that sense is still a reading of the name.

| In the logs | Status | Source |
|---|---|---|
| 256 nodes in domains | Confirmed. What a domain is, and how the nodes are divided among the 8 of them, is in no source that could be read | LANL failure data page |
| `SRM` | Term confirmed: the console mode of an Alpha system, from which it is booted | Digital UNIX Installation Guide |
| `risBoot`, `bootGenvmunix` | Terms confirmed: RIS is a network boot from an installation server, `genvmunix` is the generic kernel | Digital UNIX Installation Guide |
| `LMF` | Term confirmed: the License Management Facility, a database of software licences | `lmf(8)` |
| `NIFF` | Term confirmed and sharpened: the Network Interface Failure Finder. It does not only watch an interface; it sends traffic through one that went quiet, to find out whether it is dead | `niffd(8)` |
| `partition` status | Confirmed in outline: RMS has a partitions table and gives access to the application nodes | RMS manual, contents and overview |
| `switch_module`, `Link error` | Confirmed in outline: the interconnect is Quadrics', and the manual has an appendix on link states and link errors | RMS manual, contents; Wikipedia |
| `tserver` | Weak: the manual's system figure shows a terminal concentrator | RMS manual, overview |
| `ServerFileSystem` panic and full | Likely AdvFS, the default Tru64 file system, which has domains. What a domain panic is comes from a search result only | `advfs(4)` for the file system |
| `ClusterFileSystem`, `clusterAddMember`, `gige`, `psu`, `fan`, the `boot_cmd` family | Still guesses | None |

**The flag is still unexplained.** Chapter 10 of the manual lists the tables of the RMS database, and it could not be read.

**Learned.** The knowledge base cannot be a copy of the vendor's guidance. It will rest on what the system is, on general practice for these components, and on what the operators in the logs actually did, and the report has to say so.

### 2026-10-10: log shapes, and triage as routing

The counts of logs, copies and log shapes are printed by `python -m scripts.build_db --rebuild`.

**The stored unit is now called a log shape** (D16). A log shape is a component, a state and a template, and the template is only the masked text. The rename went through the code, the tests, the notebooks and the plan, and the rebuilt database holds the same 411,483 logs and 141 log shapes.

**Triage became routing.** Every new event is routed by code to `ignore`, `handle` or `investigate`, from the catalogue row of its log shape or from a named rule that reads counts (D17). The counts look only at the past, and in production they come from a cache updated with each ingested chunk (D18). An incident is one log shape while it is active, with a TTL counted in log time (D19). The agent starts when an incident opens, sees time pass as it works, and is capped per hour of log time (D20). Only a few dozen log shapes are labelled; the rest reach the agent with no label (D21).

**The log file is not in time order.** Its first line is from April 2006 (`notebooks/01_initial_EDA.ipynb`). A replay therefore sorts by timestamp before it ingests, and "earlier" means earlier in time and then in id.

**Learned.**

- A name that covers two things hides a decision. Calling both the row and its text "template" hid that the label belongs to the message in its component and state.
- A decision made on stats is only as honest as the stats' clock. Counts over a full database quietly include the future.
- A replay needs one clock, the logs' own. Anything timed by the wall clock changes with the speed of the replay.

### 2026-10-10: the queries an investigation is made of

The share of the logs is printed by `notebooks/incidents/00_log_shapes_and_tools.ipynb`.

**The log store now answers every question the agent's log tools will ask.** `LogRepository` has four read-only queries: `search` returns the logs of a time range, newest first, filtered by node, component, text and log shape; `count_by` counts them per node, component, log shape or hour; `stats` gives their log count, node count, first seen and last seen; `node_timeline` gives one node's history with repeats collapsed. The first three share one set of filters. Step 2B wraps these as the agent's tools, so an investigation by hand and an investigation by the agent read the same data in the same way.

**Every read is bounded in time** (D22). A start and an end are required and may be at most 31 days apart, so no call can pull the whole table. `stats` over a window that ends at a log is the past-only stat of the router (D18): it is decided by time alone, includes the second it is asked about, and counts nothing later.

**The store holds only what the agent's tools need.** The general read helpers it had before were removed, and the store has no two functions that answer the same question. What only the notebooks need is written next to them, in `notebooks/incidents/common.py`: the table of all log shapes over the whole history, and the lookup of a pinned log.

**The notebooks are set up for investigating by hand.** The first lists the most common log shapes and shows each query on one filesystem panic. Then one log is fixed for each of the 17 most common log shapes, with one notebook per log. Those 17 shapes hold 90.6% of the logs.

**Learned.** Writing the queries before the agent means the tools are tried by a person first. Whatever is awkward to ask by hand will be awkward for the model too. And a new query is finished only when the older ones it replaces are deleted.

### 2026-10-10: seventeen logs investigated by hand

Every number here is printed by a notebook in `notebooks/incidents/`: `00` for the share of the logs, `01` to `17` for the investigations, one per log.

**What the 90.6% means, and what it does not.** The 17 shapes looked at hold 90.6% of the logs. That is coverage of shapes, not of cases: one log was investigated per shape, and logs of the same shape can differ. What the number does give is the size of the prize. Wherever a shape admits a deterministic rule, every log of that shape is routed by code and costs no agent call.

**One fixed log per shape, and a run that repeats exactly.** The 17 logs are pinned by their line in `HPC.log`, so a rebuilt database gives the same logs. A notebook is re-run with `python -m nbconvert --config jupyter_nbconvert_config.py --to notebook --execute --inplace`, and an unchanged notebook then writes the same file byte for byte: the config stops nbconvert from stamping run times into the cells and joins the chunks in which a cell's prints arrive.

**An investigation looks back first.** The verdict on a log is reached from the log and what came before it, which is all the agent will have. What happened afterwards is hindsight: it is used only after the verdict, to check it, and the notebook says so where it does.

**Log shapes can be searched.** `LogShapeRepository.search` finds log shapes by text in the template, by component and by state, and takes several texts at once, so one call asks for every shape that mentions `temperature` or `ambient`. The notebooks use it in place of a table of all shapes.

**Some shapes can only be judged by a value or by time spent.** The fan report is one shape whether it holds six speeds or a missing one, and fan 4 of one switch has no reading in 5,689 reports of the 30 days looked at. A gige temperature line is written only when the level changes, so a device can sit in `warning` for 89% of a day while its lines look like brief alerts.

**Some lines are the system's reaction to another line.** 85% of the `configured out` lines of the 30 days looked at follow a `not responding` on the same node within 5 minutes.

**A text can be replaced overnight.** `Linkerror event interval expired` was last seen on 2005-05-18 and `link errors remain current` first appeared the next day, in the same component and state. A label does not carry from one to the other by itself.

**Learned.**

- A default that truncates quietly misleads. Two of the first investigations read the 20 busiest hours and the newest 1,000 logs as if they were everything, so a tool has to say what it left out.
- Looking ahead is the easy mistake in an investigation by hand. Every table that reaches past the log's own time answers a question the agent cannot ask.

### 2026-10-11: new log shapes never stop, and what the logs say about the cluster

The novelty numbers are printed by `notebooks/04_log_shape_novelty.ipynb`, which also saves `docs/figures/log_shape_novelty.png`. The cluster numbers are printed by `notebooks/05_cluster_facts.ipynb`.

**New log shapes keep arriving.** Of the 141 log shapes, most appear when the logging gets going: December 2003, January 2004 and February 2004 bring 41, 36 and 18. But 21 of the 34 months bring at least one new shape, 28 shapes are first seen more than a year after the first log, and every quarter after that first year brings between 1 and 9. The last three arrive in the final month of the data. This is the measured reason for sending an unknown log shape to the agent (D3) and for keeping everything that changes in data.

**The cluster has a regular layout that can be read from the logs.** It is written up in `kb/cluster_facts.md`, where every statement is marked as read from the data, stated by a source, or a guess.

- A domain is 32 consecutive nodes: `node-D<k>` holds nodes `32k` to `32k+31`. All 652 operator commands that name one domain and one node agree.
- Filesystem messages are reported by a domain, never by a node, and the serving node they name is inside that domain in all 7,982 such logs.
- The 256 storage file domains are served by 64 nodes only, the nodes of the first and the last domain, four each, and the name of a storage file domain gives its serving node in 668 of 670 logs.
- A file domain shared by a whole domain is served by the domain's first node.
- There are 16 interconnect switch modules of two kinds. Broadcast errors come almost only from two of them, and the fan report from one.

**The agent comes first, and it takes one log** (D23). `labeling/golden_cases.yaml` holds the 10 hand-investigated logs Aviv is sure about, with each verdict and every note copied word for word from its notebook. The helpers of those notebooks moved to `agent/tools.py` and became the agent's nine tools: the notebooks call them with no limit, the agent with a limit at its visible time, and a tool result always says how many rows it left out. After the move, every notebook in `notebooks/incidents/` was re-run and prints what it printed before, except two whose saved outputs were older than their code.

**The fan case got its verdict from the past alone.** `notebooks/incidents/05_fan_speeds.ipynb` now checks for overheating with tools that see nothing later than the log: the one heat message a switch writes was logged on a single morning 163 days earlier, by eight other switches, and the first fan report with no reading came 86 days after that. So the missing fan reading is a low-severity hardware ticket.

**The loop runs, and every step of it is logged.** `agent/loop.py` investigates one log in at most 6 rounds. Each round the model answers with tool calls, which are run and sent back with the number of the next round, or with a verdict, which ends it. A reply with no tool call gets a reminder, an invalid verdict gets its errors back once, and tool calls on the last round end the investigation as failed: the model is told it is the last round and is not forced. Every event is one row of `runs/agent.db` under one request id: the request with its prompt file and starting context, each reply of the model with tokens and latency, each tool result with the ids it showed, the verdict, and each failure with its reason. `Trajectory(request_id)` reads them back as the text a person or the judge reads, with the totals. The judge's grades are not in that file: judging is offline evaluation. `python -m scripts.investigate --case c12` runs a golden case.

**The first real run was wrong in an instructive way.** On the cluster-wide outage of case c12 the agent found the whole chain, link errors, the blocked partition, 203 nodes not responding, no operator command, and then called it benign because the nodes are configured out automatically. The judge passed it on four criteria and failed it on `verdict_supported`: the severity does not fit the evidence. So the two instruments disagree with each other in the right place.

**Learned.** A fact sheet is worth more to an agent than a manual when it turns a name into a place: `storage612` is a string until it is known to mean `node-20`. And marking each statement as data, source or guess keeps the knowledge base honest about a system whose manuals could not be read.

### 2026-10-11: judge calibration with Gemini Pro as a stand-in for human labels

**The judge was calibrated against Gemini 2.5 Pro on the Gemini web UI, not against hand labels.** Due to time constraints, human grading of all 20 trajectories (10 golden cases × 2 agent configurations) was not feasible. Instead, each trajectory's text was pasted into Gemini Pro's web interface together with the exact prompt the judge receives (`prompts/judge_v1.md` and the tool descriptions), and Gemini's JSON response was recorded as the reference label in `labeling/human_grades.csv`.

**Why this is defensible, and why it is limited.** Agreement between two LLMs is weaker evidence than agreement between an LLM and a domain expert, but it is not zero: Gemini 2.5 Pro is a frontier model from a different family than both the investigator (Nemotron) and the judge (GPT-OSS-20B), so its grades are at least independent. It sees the same trajectory and the same rubric, so a disagreement points at a place where the rubric is ambiguous or the judge is wrong. In practice, Gemini Pro likely grades more consistently than a hurried human would — the risk is shared blind spots rather than noise. The report states this plainly: the agreement numbers measure judge-vs-frontier-LLM, not judge-vs-human, and conclusions drawn from them carry that caveat.

**Two agent configurations were run.** `nemotron-3-super-120b-a12b` with thinking budget 200 and 4 rounds, and `nemotron-3.5-lightning-30b-a3b` with thinking budget 200 and 8 rounds. The trajectories are committed as text files under `labeling/trajectories/`, named `{case_id}_{config}__{request_id}.txt`. The config tag is derived from the model URL, thinking settings and max_rounds, so changing `config/models.yaml` and re-running notebook 07 produces a new set alongside the old ones.

**The calibration workflow.** Notebook 08 (`08_trajectory_labeling.ipynb`) labels one trajectory at a time. Notebook 09 (`09_judge_calibration.ipynb`) loads the labels, splits them into tune and held-out sets by trajectory id (not by case, since one case can have trajectories from different configs), runs the judge, and shows per-criterion agreement and disagreements. The judge prompt is iterated on the tune set; the held-out set is touched only for the final number.

**Learned.** When time is the binding constraint, a frontier model from another family is a better reference than no reference. But the report must say what was done and not dress it up as human evaluation.

### 2026-10-11: re-runs, and what moved

The numbers are printed by `notebooks/06_model_selection.ipynb` and `notebooks/09_judge_calibration.ipynb`; the earlier values are the outputs of the same notebooks as committed in cabf853.

**Two notebooks were re-run because the code under them had changed.** The round limit went from 6 to 4 after notebook 06 was last run, so its thinking comparison no longer read from the cache. The new medians on the first round of one investigation are 34.7 seconds with full thinking, 11.5 with a budget of 500 tokens, 7.1 with a budget of 200 and 2.5 with none; the ordering, and the choice of a 200-token budget, stand. Notebook 09 was re-run after the mis-tagged nemotron judge configuration was renamed, which made its seven calls fresh.

**A judge is not deterministic at temperature 0.** The seven fresh nemotron judge calls graded the same seven trajectories with the same prompt and gave different grades: overall agreement with the reference moved from 67% to 71%, and on `tool_use` from 43% to 86%. One run of a judge is one sample; where a judge's number matters, it has to be repeated.

**The LLM cache and the agent's event log are in git** (`runs/llm_cache/`, `runs/agent.db`); only `runs/scratch/` is ignored. A run that was made once can be replayed without a key, and the tokens and latencies of every committed trajectory are kept.

**Learned.** A cache keyed on the whole request is a precise record of what was asked, and an equally precise reminder that a measurement is stale as soon as any part of the request changes.

### 2026-10-11: one command evaluates every saved trajectory

Every number here is printed by `python -m scripts.evaluate_trajectories`, which writes `runs/eval/summary.csv` and the four `eval_*.png` figures in `docs/figures/`.

**Code checks first, the judge second.** `evals/score.py` reads a trajectory's events from `runs/agent.db` and measures what code can measure: how the run ended and in which round, tool errors and whether a later call fixed them, repeated calls, cut and empty results, a `what_followed` range that reaches into the hour of the log, tokens and seconds, and on the verdict whether every evidence line was shown, whether the new log is among the evidence, and whether the remediation names a source and puts a check before a disruptive step. The judge is run only on trajectories that have a verdict, and its grades are read as if it were calibrated (D24).

**Most of the small model's runs never reach a verdict.** Of 10 cases, the 120b model ended with a verdict on 8, the 30b model on 3. Six of the 30b failures are invalid verdicts, and all six are the same mistake: `evidence` and `remediation` sent as strings where the schema wants lists. Every invalid verdict was submitted in the last round, so the one retry the loop allows never fired. A verdict obtained from the 30b model cost 236k tokens against 49k from the 120b model, because the failed runs are paid for too.

**Where the two instruments disagree, the code is stricter.** The judge passed `grounded` on all 11 verdicts; the code found an evidence line that names no shown id in 6 of them. The judge passed `remediation_quality` on all 11; the code found a step with no source name or a disruptive step with no check before it in 6 of the 8 verdicts of the 120b model. Both code checks are literal readings of the rubric, so this is a place to look at the judge, not a verdict on the agent.

**Learned.** A check that takes a minute to write in code catches the literal failures the judge waves through, and it costs nothing per run. The judge is for what cannot be written down as a rule.

### 2026-10-11: the knowledge base

The brief is `docs/plan/06_knowledge_base.md`; decision D4 is amended.

**The knowledge is the fact sheet, searched by BM25.** `agent/knowledge.py` splits every file of `kb/` that has a header at its headings into passages, several from `kb/cluster_facts.md`, and ranks them by the words they share with a query. The agent reaches it through one more tool, `search_knowledge`, which exists only when `knowledge` is on in `config/models.yaml`; the system prompt is unchanged, and the tool's description is what tells the agent that the knowledge exists and how to cite it. A citation is a passage id in a remediation step's `citation` or at the start of an evidence line. Code records a citation that names no retrieved passage, next to the evidence lines that name no shown id, and refuses neither. A configuration with knowledge on gets `_kb` at the end of its tag, so its trajectories sit beside the others and `scripts/evaluate_trajectories.py` treats it as one more configuration, with a fifth figure for the searches and the citations. `python -m scripts.kb_smoke_test` builds the knowledge, finds what must be there, gets nothing for what cannot be, and runs the tool with knowledge on and off.

**Hypothesis, written before the run.** With the knowledge tool available and the prompt unchanged, the 120b model at the current settings searches the knowledge in a minority of the ten cases, most likely those whose starting context holds a name the fact sheet explains: a storage file domain, an interconnect switch module, a network interface. Where it searches, at least one remediation step or evidence line cites a passage, and no citation names a passage that was not retrieved. The outcomes, the code checks and the judge's grades move by at most one case either way against the run without knowledge, and a run that searched costs a few thousand tokens more.

**What the run showed.** Every number here is printed by `python -m scripts.evaluate_trajectories` and saved in `runs/eval/summary.csv` and `runs/eval/trajectory_scores.csv`; the trajectories are the `_kb` files of `labeling/trajectories/`, made by `notebooks/07_create_golden_set_trajectories.ipynb`.

- The agent searched the knowledge in 2 of 10 runs, c07 for "configured out" and c17 for "alt0 component", and both runs ended at the round limit. No remediation step of the 4 verdicts cites a passage, 0 of 5, so the check on citations never had anything to check.
- The arm with the tool reached a verdict in 4 of 10 cases against 8 of 10 without it; the other 6 ended at the round limit and none with an invalid verdict. Of the 8 verdicts without the tool, 7 were submitted in the last round, so this configuration had no slack; with the tool, that last round went to one more tool call instead.
- On the 4 verdicts the judge passed `grounded` 4 of 4, `sufficient_investigation` 3 of 4, `verdict_supported` 3 of 4 and `efficiency` 0 of 4, and the code found every evidence line anchored in 2 of 4. Tokens per verdict obtained rose from 49k to 87k while the median run cost less, 35k against 39k, because a run that ends at the round limit never writes a verdict.

**What this says.** The hypothesis held on one point only: the tool was used in a minority of runs. It missed on citations, none, and on outcomes, which moved by four cases and not one. One sample per arm cannot tell the effect of a seventh tool from the model's own variance: the thinking comparison of notebook 06 showed the same settings answering one round with anything from one to six tool calls. The default stays `knowledge: false`.

**Learned.** A tool the prompt does not ask for is a tool the agent mostly leaves alone, and a tool it leaves alone still changes how it spends its rounds. Before the prompt is touched, the next experiment is a repeat of both arms and a round limit with slack.

**Aviv's reading of the two comparisons, a hypothesis to test.** The 30b model with 8 rounds, whose conversations grew longest, failed 6 of 10 cases on the shape of its verdict; the 120b model given a seventh tool, which lengthens every call, reached a verdict in 4 cases where it had reached 8. Both point the same way: as the context grows, the agent gets more confused. The experiment is to cut what the model reads without changing what it can do, one factor at a time: a shorter system prompt, shorter tool results, a starting context the agent asks for instead of receiving, hidden thinking off. It is recorded as item 16 of `docs/plan/future_work.md`.


### 2026-10-11: the README

**The repository has a README that takes a stranger from a clone to a verdict.** The root `README.md` says what was built and what was not, how the pieces fit, how to set up, and lists every script with its arguments, every module, every data and label file, the tests, the results of `runs/eval/summary.csv` and the limitations. `notebooks/README.md` describes the nine analysis notebooks, what each reads and writes and which call a model; `notebooks/incidents/README.md` gained one line per hand investigation, saying what it looked at, whether it reached a verdict and whether it is a golden case. Every command the README gives was run that day: the unit tests, the four smoke tests, `build_db` with and without `--rebuild` (a full build takes about 7 seconds), `investigate` with `--case`, `--line`, `--judge` and `--kb`, and `evaluate_trajectories`, which reproduced the committed tables and figures byte for byte from the cache.

### 2026-10-11: the report's structure

**The report is written from the repository.** Its structure is recorded in `docs/plan/05_report.md` and its skeleton is `report.md` at the repository root. The sources were ranked before anything was written: the assignment brief, then the code and the result files, then the plan and Aviv's own notes. Checking the plan and the notes against the repository settled what the report may claim: the golden set is the 10 hand-investigated logs; routing, rules, handlers, incidents and the replay are designed and not built; the knowledge base is one fact sheet; the judge's reference grades are Gemini's, 11 trajectories, 7 of them used for tuning and 4 kept untouched for a calibration against human grades.

**Two diagrams and one section exist.** The target system, with the ingestion flow the assignment asks for, the routing and incident layer, the agent and a learning loop in which repeated resolutions of one log shape become candidate rules under human review; and the evaluation design, code checks beside a judge calibrated on a split of reference grades. Built parts are drawn solid, designed parts dashed. Section 3, goal and metrics, sets the metrics of incident resolution and of agent evaluation as goals of the full system and says which ones this project measures.

**Learned.** A plan records intent and a repository records what happened; a report on a built system has to be written from the second and only explained by the first.

### 2026-10-12: the report

**Every section of `report.md` is written.** The executive summary, the data and the domain, goal and metrics, the design with its two diagrams and the rule miner, the solution module by module with case c12 walked through, the results one figure at a time, the process, fifteen lessons, the limitations in order of weight with the chosen-not-sampled cases and the unmasked logs first, the future work by priority, the repository map, and a table that names the script or notebook behind every number. The hand verdicts of the ten golden cases are set beside the agent's in one table, read from the incident notebooks and from `runs/eval/trajectory_scores.csv`.

**Learned.** Writing the numbers down with their sources is the fastest audit of a project: every number that could not be traced to a saved output was either a planning estimate, which the report now marks as rough, or was dropped.
