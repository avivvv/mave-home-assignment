# Lab notes

Two parts. Part 1 is the decision log: every design decision, why it was taken, what it costs and what backs it. Part 2 is a dated diary of what was tried and what was learned. Both feed the report.

## Part 1: Decision log

Each entry has the same six lines. "Backed by" names the number or experiment that will support the decision once the work is done; until then the decision rests on the reasoning alone, and you should say so if asked. When a decision is made or changed during the work, add or amend an entry here in the same format, with the date.

Entries D1 to D12 record how the plan of 2026-10-06 differs from Aviv's original five-step plan.

### D1. The agent investigates incidents, not log lines

- **Your plan:** code marks each log as needing an agent or not.
- **Decision:** alert logs of the same component with less than G minutes between them form one incident. The agent gets one incident.
- **Why:** one failure writes many lines, and an analyst investigates an event, not a line. On this data a rough filter gives 134k error-like lines, about 6,700 incidents and about 300 distinct incident shapes.
- **What it costs:** a time-gap rule can merge two unrelated problems, and it splits a cascade that crosses components into several incidents. The agent is told to look at other components in the same window, which softens the second problem and does not solve it.
- **Backed by:** the incident counts from task 1.4 and the cost projection in Step 4.
- **In the interview:** "LLM cost should scale with the number of distinct problems, not with log volume, so I grouped before I called a model."

### D2. Triage is a template catalogue; keywords are the baseline

- **Your plan:** keyword search plus a hazard score per template, perhaps frequency rules.
- **Decision:** one table row per template saying alert or not, with a category. You label the existing templates. A new template is classified once by a small model and stored as unreviewed. The keyword rule stays, as the baseline to beat.
- **Why:** the answer for a template never changes, so it is computed once and cached: about 250 decisions instead of 433k. A new template needs no code change. Keywords get judgment cases wrong in both directions: `Link ok` is filed under state `error`, and `PSU status ( on off )` contains no error word.
- **What it costs:** a label per template ignores values and frequency, so one link error and a thousand look the same at this stage. The agent sees the counts later. Frequency rules are left out.
- **Backed by:** experiment E1. If keywords turn out as good as the model, keep keywords and report that.
- **In the interview:** "The decision is per template, so I pay for it once per template. I measured the LLM against a keyword baseline on my own labels before trusting it."

### D3. Unknown templates default to alert

- **Your plan:** not specified, though you wanted criteria "general enough so that we don't miss critical errors".
- **Decision:** a template with no catalogue row is treated as an alert until it is classified.
- **Why:** in operations and in security, a missed problem costs more than a wasted investigation.
- **What it costs:** a format change that creates many new templates at once causes a burst of agent calls. The quarantine counter and the once-per-template cache limit the damage.
- **Backed by:** the template novelty plot (1 to 12 new templates every quarter).
- **In the interview:** "I chose to fail open: unknown means look at it, not ignore it."

### D4. The knowledge base is mandatory, and deliberately simple

- **Your plan:** leave the knowledge base out of round one, evaluate, then add it and evaluate again.
- **Decision:** your two-round experiment stays. The knowledge base is a fixed item on day 2: a folder of markdown runbooks, searched by keyword ranking (BM25). No embeddings, no vector database.
- **Why:** citations are a stated requirement, so a system without a knowledge source is incomplete. Ten documents do not need semantic search. A folder of files means adding a recommendation is adding a file.
- **What it costs:** the runbooks are written by us from public manuals, so they are partly synthetic. The evaluation therefore measures whether the agent uses and cites them faithfully, not whether the advice is what a real operator of that cluster would do. Keyword search also misses paraphrases, which is acceptable at this size.
- **Backed by:** experiment E2.
- **In the interview:** "I ran the agent without knowledge first to get a baseline, so I can show exactly what the knowledge base adds."

### D5. Two datasets, and the first is written before the agent exists

- **Your plan:** one golden dataset of trajectories produced by the system, labelled by you.
- **Decision:** (a) golden incidents: inputs with expected answers, written at the end of Step 1. (b) a judge calibration set: agent outputs that you graded.
- **Why:** they answer different questions. (a) tells you if the agent is right. (b) tells you if the judge is right. Expected answers written before seeing any agent output are not anchored by it. Incident labels stay valid when the agent changes, so they work as a regression suite; trajectory labels expire with every new agent version.
- **What it costs:** writing an expected root cause needs real understanding, so only confident cases qualify, and 25 is a small sample.
- **Backed by:** `labeling/golden_incidents.yaml` with a dev and holdout mark on every entry.
- **In the interview:** "I separated evaluating the agent from evaluating the evaluator."

### D6. You label with hindsight; the agent cannot see the future

- **Your plan:** you wanted cases you could grade with high confidence, without saying how to get that confidence.
- **Decision:** when labelling, you look at what happened after the incident: a recovery message means it cleared by itself, an operator command means a human acted. The agent's tools never return logs later than the incident.
- **Why:** hindsight is the only source of trustworthy labels without a domain expert. Blocking the agent from the future keeps the evaluation honest, because in real use that information does not exist yet.
- **What it costs:** an operator action after an incident is correlation, not proof of cause. Incidents with no clear aftermath are excluded, so the golden set leans toward clear-cut cases and likely overstates accuracy on ambiguous ones.
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

### D8. The judge is tuned on one half of your labels and reported on the other

- **Your plan:** compare the judge to your labels, study its mistakes, improve it.
- **Decision:** the same, with a split: adjust the judge prompts on one half, report agreement on the untouched half. A rule fixed in advance: a criterion whose judge catches fewer than 70% of your fails is not used for conclusions.
- **Why:** tuning a prompt on the labels you report on inflates the agreement, for the same reason you do not report training accuracy.
- **What it costs:** it halves a sample that is already small, so the uncertainty is about plus or minus 20 points.
- **Backed by:** the agreement table, with counts.
- **In the interview:** "The judge is a classifier, so I evaluated it like one: held-out data and a threshold set beforehand."

### D9. Bad outputs come from a weak model and from injected defects

- **Your plan:** perhaps tell the main agent to do a bad job on purpose, and use several models of different sizes.
- **Decision:** keep the different models. Replace "do a bad job" with injected defects: take a good output and break it in one known way (wrong citation, invented fact, wrong root cause).
- **Why:** an agent told to fail produces exaggerated failures unlike real ones. A weak model fails the way agents really fail. An injected defect has a known label and tells you which type of error the judge misses.
- **What it costs:** injected defects are easier to spot than natural ones, so they are reported separately and never mixed into the main agreement number.
- **Backed by:** detection rate per defect type.
- **In the interview:** "It is mutation testing for the judge."

### D10. A hand-written agent loop instead of a framework

- **Your plan:** LangChain, LangGraph or ReAct, preferring ready-made.
- **Decision:** about 80 lines on the OpenAI client pointed at NVIDIA. This is the default from open decision 1; tell me if you would rather use LangGraph and I will change the Step 2 brief.
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

### D12. A different model for each role

- **Your plan:** choose a model.
- **Decision:** a small model classifies templates, a main model investigates, and the strongest available model from a different family judges.
- **Why:** template classification is a narrow task where a small model may be enough. A judge from the same family as the agent tends to favour its own style.
- **What it costs:** three models to keep working on a free tier with a shared rate limit.
- **Backed by:** the model smoke test, E1 and E3.
- **In the interview:** "I matched model size to task difficulty and measured the trade."

### D13. From the `labeling-helper` branch, only the log store changes are kept (2026-10-06)

- **Earlier work:** an unmerged branch holds a labelling form with an eight-field label per template, LLM draft labels and a human-against-LLM agreement check, plus changes to the log store.
- **Decision:** Aviv's choice. Take the log store changes: a template is identified by component, state and masked text; shared parsing; named masks; `requirements.txt`. Leave the labelling package on the branch. A template label is two columns: alert or not, and a category.
- **Why:** this is my reading of the reasons, so edit it if yours differ. The pipeline consumes one decision per template, so eight fields multiply the labelling time without changing what the system does in two days. A yes or no label also gives a plain precision and recall for experiment E1.
- **What it costs:** the richer fields (event role, whether a number matters, what context is needed) are not collected. The branch's ready agreement check is not reused, so E1 needs its own small scoring function.
- **Backed by:** the time Step 1 labelling actually takes, and E1.
- **In the interview:** "I had started a richer labelling tool and cut it back once I saw the pipeline needed one decision per template."

### Deliberately left out

| Left out | Reason |
|---|---|
| Several cooperating agents | One agent has to work and be measured first. More agents add cost, latency and new ways to fail |
| Fine-tuning | Two days. The catalogue labels are the training set a later fine-tune would use |
| Vector database | Ten documents |
| Frequency rules per template | A second mechanism to tune and evaluate. The agent sees counts instead |
| Reusing a verdict for a repeated incident shape | The same shape in a different context can need a different answer. Its numbers are used in the cost section only |
| Streaming ingestion | The assignment asks for a diagram |

## Part 2: Notes by date

Two or three lines per finding: what was tried, what was seen, what changed, what was learned.

### 2026-10-06, planning session

All numbers here are rough. They were measured read-only on `data/hpc.db` with a crude keyword filter, before any labelling. Re-measure in Step 1 before quoting them.

- **Size.** 433,490 lines from 2003-07-31 to 2006-04-30. The flag notebook counted 411,483 distinct events after dropping identical copies. Median 235 lines a day, 12,205 on the busiest day.
- **Templates.** 249 template keys (component, state, masked text) and 201 distinct masked texts. 123 of the 249 keys are four messages with lists of different lengths: `Targeting domains` 58, `inconsistent nodesets` 26, `Command Failed on` 26, `Failed subcommands` 13. Collapsing the lists should leave about 140 keys. The approved plan said about 130; that estimate ignored that the same text under a different component or state is a separate key.
- **New templates keep arriving.** After the first year, every quarter still brings between 1 and 12 keys never seen before. This is the empirical case for the future-proof design.
- **Lines against incidents.** A keyword filter marks 133,631 lines over 149 keys as error-like. Grouped by component with a 60-minute gap they form 6,676 incidents (10,352 with 30 minutes, 2,288 with 6 hours; 28,323 if grouped by component and node). Median incident: 2 lines. 1% exceed 250 lines. The largest has 13,867 lines, the longest runs 23 days. Only 298 distinct shapes (component plus set of templates); the 20 most common cover 5,912 incidents.
- **What the cluster probably is.** The vocabulary (SRM, RIS boot, LMF, NIFF, interfaces `ee0` and `alt0`, file domains, RMS-style partitions) points at a Compaq/HP AlphaServer SC running Tru64 UNIX with a Quadrics interconnect. Not verified. A "Compaq AlphaServer SC RMS Reference Manual" is online and not yet read.
- **Model access.** NVIDIA's free tier is reported to allow about 40 requests a minute, shared across all models on one key. From a web search, not tested.
- **Repo.** The database on disk was built from the `labeling-helper` branch, so its `templates` table has `component` and `state` columns that the code on `main` does not know. See D13.
- **Learned:** I planned the first draft from `main` alone and missed a whole branch of existing work. Check every local branch before planning on top of a repository.

