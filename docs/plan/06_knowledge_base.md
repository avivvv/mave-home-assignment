# Step 6: the knowledge base, and the agent with it

Read first: `AGENTS.md`, [00_overview.md](00_overview.md), and the decision of 2026-10-06 on the knowledge base, as amended on 2026-10-11.

Written on 2026-10-11, after the agent, the judge and `scripts/evaluate_trajectories.py` existed. It replaces Part C of [02_pipeline_and_agent.md](02_pipeline_and_agent.md), which assumed runbooks and incidents.

## Goal

The agent can query a knowledge source and cite it, the citations are checked by code, and the ten golden cases run with the knowledge on are evaluated beside the runs without it, by the same script and in the same figures.

## What the knowledge is

`kb/cluster_facts.md` alone: the fact sheet read from the logs and the public sources, with every statement marked `[data]`, `[source]` or `[guess]`. No runbooks are written. A file in `kb/` is knowledge when it has the front-matter header (`id`, `title`, `source_urls`, `categories`); `kb/sources.md` has none and is not indexed.

## Concepts to explain when they come up

- **RAG**, retrieval-augmented generation: the model is given passages retrieved for its question instead of being expected to know them. Here it is the agentic form: the model decides when to retrieve, by calling a tool, and every retrieval is logged.
- **BM25**: a ranking of passages by the words they share with the query, weighted by how rare each word is across the passages. Lexical, not semantic: a paraphrase that shares no word is missed.
- **A passage**: one `##` section of a knowledge file. Its id is `<file id>#<heading slug>`, and that id is what a citation names.

## Decisions taken with Aviv

- The system prompt does not change. The tool's description is what tells the agent that knowledge exists and how to cite it.
- A citation that names no passage the agent retrieved is recorded, like an evidence line that names no shown id. Nothing is rejected.
- BM25 from `rank_bm25`, pinned.
- The judge prompt does not change. The judge is told which tools the agent had.
- The flag lives in `config/models.yaml` as `knowledge`, beside the thinking options and `max_rounds`. A configuration with it on gets `_kb` at the end of its tag, so its trajectory files sit beside the others and the evaluation treats it as one more configuration.

## Tasks

- [ ] **K1. `agent/knowledge.py`** (Must). `Knowledge(kb_dir)` loads every file with a header, splits it at `##` headings into `Passage(passage_id, title, text)`, and ranks passages against a query with BM25 over lowercased word tokens. `search(query, k=3)` returns the best `k` with a score above zero, so a query that shares no word with any passage returns nothing. Text before the first heading is a passage too. Tests: loading and ids, a query made of a passage's own words returns that passage first, no shared word returns nothing, `k` caps the result, a file with no header is skipped.
- [ ] **K2. The tool** (Must). `search_knowledge(reasoning, query, k)` in `agent/tools.py`, registered only when the `LogTools` has a `knowledge`. Its result lists each passage under its id, and `ToolResult.passage_ids` records them as log tools record log ids. `available_tools(tools)` gives the tools of a run; the loop, the judge and the smoke tests take that list, and `run_tool` refuses the knowledge tool when knowledge is off. The request row of the event log records the tool names and whether knowledge was on. Tests: present only with knowledge, ids recorded, refused when off.
- [ ] **K3. Citations** (Must). `RemediationStep.citation` is described as the id of a retrieved passage, or empty. An evidence line is anchored when it names a shown log id, log shape id or passage id. `unknown_citations(verdict, passage_ids)` lists the non-empty citations that name no retrieved passage; the loop writes it next to `unanchored_evidence` in the verdict event, and `Trajectory.unknown_citations` reads it back (empty for older runs). Tests on the schema and on the loop with a scripted model that searches and cites.
- [ ] **K4. Config and script** (Must). `knowledge: false` in `config/models.yaml`; `config_tag` ends in `_kb` when it is on; `python -m scripts.investigate --kb` turns it on for one run. `describe` in `evals/figures.py` reads the suffix as "with knowledge base".
- [ ] **K5. Scores and figures** (Must). `evals/score.py` adds `knowledge_calls`, `n_citations`, `unknown_citations` and `citations_ok`. `scripts/evaluate_trajectories.py` tells the judge which tools the run had. One more figure, `eval_knowledge.png`: knowledge searches per investigation and the share of remediation steps with a citation, per configuration.
- [ ] **K6. Smoke test** (Must). `python -m scripts.kb_smoke_test`: build the index from `kb/`, list what was indexed, find a passage that must exist, get nothing for a query that cannot match, and run the tool through `run_tool` with knowledge on and off. No model is called.
- [ ] **K7. The knowledge arm** (Must). The hypothesis is written down first. `notebooks/07_create_golden_set_trajectories.ipynb` gets a `KNOWLEDGE` switch; run it on with the main model and the current settings, so the ten golden cases get a `_kb` trajectory each. Then `python -m scripts.evaluate_trajectories`, which judges the new trajectories and redraws every figure with the third configuration.
- [ ] **K8. Figures for the report** (Must). Notebook 09 saves its two figures to `docs/figures/`. Re-run everything that draws a figure: notebooks 04 and 09 and the evaluation script.

## Done when

- `python -m scripts.investigate --case c12 --kb` prints a trajectory with a `search_knowledge` step and a verdict, and the unit and smoke tests pass.
- `labeling/trajectories/` holds a `_kb` trajectory for each of the ten cases, `runs/eval/summary.csv` has a row for it, and the five figures in `docs/figures/` show three configurations.
- The hypothesis written before the run and the result after it are in the report.

## Questions this step should answer

- In how many of the ten cases did the agent search the knowledge, and what did it ask?
- How many remediation steps carry a citation, and how many citations name a passage that was not retrieved?
- Did the code checks or the judge's grades move against the run without knowledge, and by how many cases?
- What did the knowledge cost in tokens and rounds?

## Suggested commits

Knowledge module and tool; citations and the loop; config, script and figures; smoke test; the knowledge arm and its evaluation; figures for the report.

## Not in this step

No runbooks, no new judge criterion, no prompt change, no routing. A `citation_supports_step` criterion needs its own reference labels and waits.
