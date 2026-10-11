# Project: HPC Log Problem-Resolution System (Mave Security DS home assignment)

## Context
This is a take-home assignment for a Data Scientist role at Mave Security, a Tel Aviv startup building an
agentic SecOps platform: AI agents that investigate security alerts and return root-cause verdicts with an
audit trail. The assignment is a small version of that product, applied to HPC logs.
The report and the design reasoning matter as much as the code.

## The assignment
Build an end-to-end system that:
1. Processes the HPC logs and identifies errors.
2. Recommends specific, actionable remediation steps for each error, backed by citations and reasons.
3. Adapts to new log templates, formats and recommendations over time without code changes ("future-proof").
4. Is realistic about cost and latency. Latency is not the main concern, but this should work in a real environment.


## How to work with the developer (Aviv)
- He has a math + data engineering + data science background, but is new to incident resolution on HPC clusters, and to building
  LLM agents. Explain domain and agent concepts briefly when they come up.
- He must be able to defend every design decision in a follow-up interview. Keep core logic simple and
  explicit: classification, agent prompts and loop, evaluation.
- Build **one stage at a time** and run it on a representative sample of 1000 logs before moving on. Don't build everything at once.
- After writing a module, give a short summary of what it does and any assumptions it makes, so he can
  review selectively instead of reading every line.
- After large changes, always run all unit tests, and run only the relevant smoke tests (for example if made changes to the logstore, run the `scripts.db_smoke_test`. if made changes to prompts/llm calls/agent tools, then  run `scripts.agent_smoke_test`). If anything is broken, fix it. The smoke tests are `python -m scripts.db_smoke_test`, `python -m scripts.agent_smoke_test` and `python -m scripts.eval_smoke_test` (run the last one after changes to `evals/` or the judge); the second calls the real models and needs the key in `.env`, the third reads the judge's reply from the cache when it is there. If possible, run the added code on your own and read the output to see that it matches expectations.
- Suggest a git commit after each working stage.

## Notebook and comment style
- Do not put findings, conclusions, or reasoning about implementation choices in notebook markdown cells or code comments. Report those in chat only.
- Markdown cells: a short title or one line saying what the next code cell does. Comments: only to clarify what a line of code does, kept minimal.

## Editing files
- Always re-read a file immediately before editing it (notebooks, AGENTS.md, anything). Aviv might edit files by hand in the IDE, and stale copies overwrite his changes.
- Never regenerate a file from a script or from memory. Make targeted edits on top of the current contents.

## Numbers
- Every number written into the report, the lab notes or the plan must come from code that is in the repo, a notebook or a script, saved with its output, and the text says where. A number from a throwaway script does not go into the repo until that code does.

## Code organisation
- Before creating a new module, check whether the functionality belongs on an existing class or in an existing file. For example, a new query to the db goes on the repository that owns the table, not in a new file on a separate module.

## Plan and decisions
- The plan lives in `docs/plan/`. Assume always that we are following the plan, unless the chat is only about understanding/reviewing the project, or stated otherwise. If indeed following the plan, then before writing any code, read `00_overview.md` and the brief of the step you are executing. One step per chat.
- `docs/lab_notes.md` opens with the decision log. Never change a design decision silently: tell Aviv, then add or amend its entry. The second part holds one short dated entry per work session: what was done, what was found, what was learned. It should read smoothly. Write outcomes only: no rejected ideas, no back-and-forth, no open questions, and only decisions that shape the system.
