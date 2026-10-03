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
- He has a math + data engineering + data science background, but is new to cyber defense and to building
  LLM agents. Explain domain and agent concepts briefly when they come up.
- He must be able to defend every design decision in a follow-up interview. Keep core logic simple and
  explicit: classification, agent prompts and loop, evaluation.
- Build **one stage at a time** and run it on a representative sample of 1000 logs before moving on. Don't build everything at once.
- After writing a module, give a short summary of what it does and any assumptions it makes, so he can
  review selectively instead of reading every line.
- Suggest a git commit after each working stage.

## Notebook and comment style
- Never put findings, conclusions, or reasoning about implementation choices in notebook markdown cells or code comments. Report those in chat only.
- Markdown cells: a short title or one line saying what the next code cell does. Comments: only to clarify what a line of code does, kept minimal.

## Editing files
- Always re-read a file immediately before editing it (notebooks, AGENTS.md, anything). Aviv edits files by hand in the IDE, and stale copies overwrite his changes.
- Never regenerate a file from a script or from memory. Make targeted edits on top of the current contents.
