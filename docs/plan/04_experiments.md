# Step 4: experiments and improvement

Read first: `AGENTS.md`, [00_overview.md](00_overview.md), Part 1 of [docs/lab_notes.md](../lab_notes.md).

Budget: 1.5 hours.

## Goal

Three or four controlled comparisons, each changing one thing, all reported in the same table, plus one run on the holdout and a cost projection.

## Before you start

- Step 3 is done: dev traces exist for `main_nokb`, `main_kb` and `small_kb`; the judge is calibrated and `runs/eval/judge_agreement.csv` says which criteria are usable.
- The holdout incidents have not been run by anyone.

## Concepts to explain when they come up

- A **controlled experiment** changes one factor and holds the rest fixed, so a difference can be attributed to that factor.
- A **baseline** is the simple thing the new thing must beat.
- **Tuning on the test set**: if you improve the agent by looking at its mistakes on some incidents, its score on those same incidents is flattering. The holdout exists to give one honest number.
- **Nondeterminism**: the same input can give different outputs, so a single run per incident hides some of the variance.

## Rules for every experiment

1. Same golden incidents, same prompt version, same step limit. One factor changes.
2. The hypothesis is written in lab notes **before** the run.
3. Every share is reported with its counts. Seventeen incidents is a small sample: a difference of one or two incidents is not a finding.
4. Only judge criteria that passed the 70% rule in Step 3 are used to draw conclusions. The others are shown in the table, marked as not validated.
5. The 8 holdout incidents are run once, at the very end, on the final configuration.

## The results table

One row per configuration, written by `evals/score.py` plus the judge's results:

| Column | Source |
|---|---|
| n | count of runs |
| Actionable recall, benign recall, abstention rate | code, against the golden labels |
| Root cause match, grounded, citation supports step | judge |
| Citation coverage, validation failure rate | code |
| Tool calls per run, step-limit rate | code |
| Tokens per run, median and 90th percentile latency | code |

## Experiments

### E2. Without knowledge against with knowledge (Must)

`main_nokb` against `main_kb` on the dev incidents. The traces already exist from Step 3; this experiment is running the judge on all of them and reading the result.

- **Hypothesis to check or replace:** citation coverage goes from zero to nearly full. Root-cause match improves on categories that need domain knowledge (boot failures, file domains) and not on self-explanatory ones.
- **Also look at:** results per category, not only overall. And whether knowledge made anything worse, for example more tool calls or more abstentions.

### E3. Small model against main model (Must)

`small_kb` against `main_kb`.

- **Hypothesis to check or replace:** the small model uses a fraction of the tokens and time, fails validation more often, and abstains or guesses more.
- **The question behind it:** for which incidents is the small model enough? Split the result by category and by incident size. This feeds the routing argument in the report.

### E4. Fix the most common failure (Should)

- [ ] Take the best configuration. Read every dev run that failed any metric or criterion.
- [ ] Give each failure a short type name and count the types. Typical types: concluded without looking at operator activity; cited a passage that does not support the step; repeated the same tool call; treated a recovered problem as ongoing.
- [ ] With Aviv, choose the most common type and change one thing to address it: a prompt paragraph, a tool's output, or the incident card. A prompt change is a new prompt file and a new configuration name.
- [ ] Re-run the dev incidents and report before and after, per failure type. Check that fixing one type did not increase another.
- [ ] Say plainly in lab notes that this fix was tuned on the dev incidents.

### E5. Repeat runs (Could)

- [ ] Three repeats of the final configuration on the dev incidents. Report the share of incidents where all three verdicts agree, and look at the ones that disagree: are they the genuinely ambiguous incidents?

### E1 (if not done in Step 2B)

See Part B task B7 of [02_pipeline_and_agent.md](02_pipeline_and_agent.md).

## The holdout run (Must)

- [ ] Fix the final configuration with Aviv. Nothing changes after this point.
- [ ] `python -m evals.run --config <final> --split holdout --final`, then score and judge.
- [ ] Report the holdout row next to the dev row. If holdout is clearly worse, that is a finding about over-tuning and belongs in the report as it is.

## Cost and latency (Must)

- [ ] **Measured:** tokens in and out, LLM calls and seconds per incident, for each configuration.
- [ ] **Volume:** incidents per day on average and on the busiest day, from the `incidents` table.
- [ ] **Projection:** tokens per day at average and peak volume. NVIDIA's free tier has no price, so convert tokens to money with a stated public per-token price for a comparable hosted model, and label it an assumption.
- [ ] **What reuse would save:** the number of distinct incident signatures against the number of incidents. Present it as an upper bound on the saving, and say why reuse was not built: the same signature in a different context can need a different answer.
- [ ] **Routing:** which calls could go to the small model, using E1 and E3.
- [ ] **Latency:** seconds per incident against how fast an operator needs an answer, and what dominates it: model calls, or pacing under the rate limit.

## Outputs

- `notebooks/04_results.ipynb` builds every table and figure of the report from the files in `runs/eval/`. No number in the report is typed by hand.
- Tables to `runs/eval/`, figures to `docs/figures/`.

## Done when

- The results table has rows for `main_nokb`, `main_kb`, `small_kb` on dev, and the final configuration on holdout.
- Each experiment has a hypothesis written before the run and two or three sentences of interpretation after it.
- The cost section's inputs are all in files.

## Lab notes should answer

- For each experiment: the hypothesis, the result with counts, and whether the hypothesis held.
- What was the single most common failure type, and did the fix work?
- Where is the small model good enough?
- Dev against holdout: how different, and what does that say?
- What would you measure next with ten times more golden incidents?

## Suggested commits

Judge results on all dev runs and the E2 and E3 tables; the E4 fix with its new prompt file; holdout traces and final table; results notebook and figures.

## Not in this step

No new features. If an experiment suggests a larger redesign (a second agent, a different grouping rule), write it under next steps for the report and do not build it.
