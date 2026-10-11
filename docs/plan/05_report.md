# Step 5: report, README, ingestion diagram

Read first: `AGENTS.md`, [00_overview.md](00_overview.md), all of [docs/lab_notes.md](../lab_notes.md).

Budget: 2.5 hours.

## Goal

A report that a Mave engineer can read in fifteen minutes and that shows what was built, how well it works, how that was measured, and what was learned. A README that takes a stranger from a fresh clone to a verdict.

## Who reads the report

Engineers and researchers at Mave who build agents for security operations. They know LLM agents and evaluation well. They do not know this dataset, and they have not seen the repository. They are judging design reasoning and rigour, and whether Aviv, who is new to agents, learned quickly.

So: lead with what was built and the main results. Give reasons for decisions, not only the decisions. State limits plainly; a small honest number is worth more to this reader than a large vague one.

## Before you start

- The build stopped on 2026-10-11 after the agent, the knowledge base and `scripts/evaluate_trajectories.py` (decisions D23 and D24). Steps 2A, 3 and 4 were not done as written: no routing, no incidents, no replay, no holdout run, no experiments E1 to E7. The result files are `runs/eval/*.csv` and the figures are in `docs/figures/`.
- `docs/lab_notes.md` has a decision log and dated notes from every step.
- The README was rewritten on 2026-10-11 (lab notes, "the README") and is done.
- The sources for the report, in order of trust: the assignment brief, then the repository, then these plan files and Aviv's own notes. Where the plan or the notes say something the repository does not back, the report follows the repository.

## Who does what

The report is Aviv's and must sound like him. You draft section by section from the lab notes and the result files; he edits. Do not write a claim that is not backed by a file or a lab note. If a section has no material behind it, tell him instead of filling it.

## The report: `report.md`, at the repository root

Structure decided with Aviv on 2026-10-11; every section drafted on 2026-10-12. Written in Aviv's voice. The executive summary is a draft for Aviv to rewrite in his own words.

**Tone.** Plain and specific. Achievements are stated as what they are, with the number and the file behind them. Nothing is inflated and nothing is hidden. The reader should come away knowing that the parts that are missing were understood, designed and deliberately left for later.

| # | Section | Content | Material |
|---|---|---|---|
| 1 | Executive summary | Aviv writes it last | Sections 6, 9, 10 |
| 2 | Background: the data and the domain | The dataset and its missing labels, the flag finding and one row per event; what the cluster is and how it was identified from vocabulary and public sources; log shapes, the Loghub check, the novelty plot; what counts as an error here: hindsight and operator commands | Lab notes Part 2, notebooks 01 to 05, `kb/` |
| 3 | Goal and metrics | The verdict the system has to produce. The metrics an incident-resolution system and an investigating agent should be measured on, from the literature, as goals of the full system. A table of what this project measures and by what. No source list: the literature is named in the text | `agent/schema.py` |
| 4 | Approach and system design | Design principles with reasons. The target-system diagram (also the ingestion diagram the assignment asks for), built and designed parts in two styles. How the system gets cheaper as it grows. The evaluation-design diagram. What runs today. The main challenges, each tied to a decision. Both diagrams drafted on 2026-10-11 | Overview sections 4 and 5, decision log, Aviv's notes |
| 5 | The solution in detail | Log store; hand investigations and the golden cases; the agent: loop, starting context, tools, round limit, reasoning in every call, evidence anchoring, event log, LLM client with cache and pacing, model selection, thinking budget; the knowledge base; one trajectory walked through, case c12; the evaluation harness | The code, the prompts, notebook 06, lab notes |
| 6 | Results | One subsection per figure: outcomes, verdict quality with the gap between judge and code checks, the knowledge arm with its hypothesis, judge calibration across three judge configurations. Cost and latency as measured per investigation | `runs/eval/`, notebooks 06 and 09 |
| 7 | Process | The main stages in order, not every commit: EDA and the flag; the log store; the plan; sources and the cluster; log shapes and the routing design; hand investigations; the agent; model selection; trajectories, reference grades, judge calibration; the evaluation script; the knowledge base; the README | `git log`, lab notes Part 2 |
| 8 | What I learned | Lessons tied to events from the lab notes, and what was learned while writing: how agents and incident-resolution systems are evaluated, multi-agent architectures considered and not built, RAG, how messy logs are | Lab notes, section 3, Aviv's notes |
| 9 | Limitations | See below | Decision log |
| 10 | Future work | Aviv's categories in priority order, each tied to the part of the system or the metric it improves | Aviv's notes, `future_work.md` |
| A | Repository map | One line per folder | README |
| B | Every number and the code behind it | One table | `runs/eval/`, notebooks |

### Points that must come across

- **The deterministic layer is the core of the cost argument and is not built.** Catalogue, rules, handlers, incidents, replay and cap are designed only. The report says, in the design section and in future work, that their criticality was understood, that the assignment asked for the ingestion flow as a sketch, and that the time went to the agent and its evaluation.
- **The rule miner.** As resolved incidents accumulate, a log shape whose incidents keep getting the same verdict becomes a candidate rule, handler or fixed remediation set, submitted for human review. More of the system becomes deterministic and cheap over time. Stated in the design section, in future work and in the executive summary.
- **Incident grouping rules** save cost and latency, are data that can be extended as the system grows, and were too complex to implement at this stage.
- **No look-ahead** exists so that experiments are honest. A deployed system would let the agent's view move and send it updates about logs ingested while it works.
- **The knowledge base is one fact sheet.** Runbooks and fixed remediation sets per incident type are a data-mining task for later, and a stage before an incident type becomes a deterministic rule.
- **The judge's reference labels** came from Gemini 2.5 Pro, not a human. The judge model is gpt-oss-20b because it is from another family than the investigator (D12), although the nemotron judge agreed more with the reference. One judge run at temperature 0 is one sample.
- **Cost is reported per investigation, not per day.** The report says what a deployment would measure to project a cost per day per client: the share of logs that become incidents, the share of incidents that need the agent, incidents per day per cluster.
- **Enlarging every dataset** is future work, and each set improves a distinct part: logs from other times and clusters, incidents investigated, trajectories, reference grades, the knowledge base.

### Section 8, "What I learned"

Each lesson from the lab notes is tied to something that actually happened, in the form: what I expected, what I saw, what I changed. A lesson with no event behind it is left out. Added to these, what was learned while writing: the metrics of agent evaluation and of incident resolution (section 3), the multi-agent architectures considered (planner and executor, enricher and analyser, judge in the loop, an actor agent that holds user preferences), retrieval-augmented generation and its lexical form here, and how messy the logs are.

### Section 9, limitations

In order of weight:

1. **The golden cases are chosen, not sampled.** One log per shape, among the most common shapes, chosen because they could be investigated by hand. Say what a better sample needs: domain knowledge to stratify by incident type, severity and ambiguity; hard negatives; cases from the long tail of rare shapes; several logs per shape; an operator to confirm each verdict. This is the limitation to elaborate most.
2. **No safety or privacy measures.** Above all, logs leave the cluster unmasked: a deployment needs masking of host names, users, paths and addresses before anything reaches a hosted model, or models that run on site. Also guardrails on consequential actions and on prompt injection through tool results.
3. **The judge is not calibrated.** The infrastructure exists: reference grades, a tune and test split, the agreement notebook. The test half is kept untouched for the real calibration against human grades.
4. **One run per arm**, so the model's own variance is unknown.
5. **Single logs, not incidents**, so cost follows log volume until the routing layer exists.
6. **Six fixed general tools**, where a deployment would list its own.
7. **The knowledge base is a fact sheet**, and the evidence check only tells whether a line names a shown id.

Not limitations, and said so: the visible time that does not move during a run is a design choice for experiments; the test half of the judge labels being unrun is deliberate.

### The decision log in the report

Part 1 of the lab notes is not copied in. Its content appears where each decision is used: the "why" line in the design sections, the "what it costs" line in limitations. Aviv keeps the log itself for the interview.

## The diagrams

The assignment asks for an ingestion diagram, not an implementation. Two mermaid diagrams were drafted on 2026-10-11 and live in `report.md`, section 4: the target system (ingestion, routing and incidents, investigation, learning loop) and the evaluation design. Built parts are solid, designed parts dashed, human steps shaded. The paragraph under the first says, for each box, what plays its role in the repository and what a real deployment adds: ingestion in parallel with the stats cache kept in order across workers, ordering across sources, retention, a store built for time-range queries at volume.

## The README

Replace the current README, which only repeats the assignment text. Sections, in order:

1. **What this is**, in three sentences, with a link to the report.
2. **Requirements**: the Python version, `pip install -r requirements.txt`.
3. **Key**: `NVIDIA_API_KEY` in `.env`, and which commands work without a key because their LLM responses are in the committed cache.
4. **Run it**, as exact commands in order, each with one line saying what it prints:
   build the database; load the catalogue; replay the log, which routes every event and opens incidents; investigate one incident; run the evaluation on the dev incidents; score and judge; rebuild the report's tables.
5. **Notebooks**: what does each one contain and the important findings it exemplifies. 
6. **Tests**: the one command that runs all of them (unit, smoke, e2e).
7. **Layout**: the folder table from overview 5.1.

- [ ] Verify the README by following it literally in a fresh clone in a new folder with a new virtual environment. Every command is run, not assumed. Fix what breaks.

## Checks before handing in

- [ ] Every number in the report appears in a file under `runs/eval/` or is printed by a notebook or script in the repo, and Appendix B says which.
- [ ] Every percentage has its counts next to it.
- [ ] Every figure has a title that states what it shows and labelled axes. The figures are used as they are; no re-drawing.
- [ ] The knowledge base is described as it is: one fact sheet, with the provenance marks, and no citation in any saved run.
- [ ] The judge's reference labels are stated as Gemini's wherever an agreement number appears.
- [ ] `requirements.txt` lists everything that is imported.
- [ ] No key in the repository: search the history as well as the working tree.
- [ ] `.gitignore` leaves `runs/eval/` and `runs/llm_cache/` in and `runs/scratch/`, `data/*.log`, `data/*.db` out.
- [ ] The repository is pushed and its link opens for someone who is not logged in as Aviv.

## Done when

A person with the repository link reaches a verdict for one incident by following the README, and the report's tables match the committed result files.

## Suggested commits

Report draft; ingestion diagram; README; fixes from the fresh-clone check.
