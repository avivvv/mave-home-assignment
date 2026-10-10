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

### E6. A judge inside the loop (Could, about 1.5 hours outside the budget)

Aviv's question: what happens when the judge reviews the agent's answer before it is returned? This is the simplest form of one agent verifying another's work (decision D14).

**Run it only if** Step 3 left at least one of `grounded` and `citation_supports_step` usable under the 70% rule. A judge that misses failures cannot help, and a judge that fails good answers pushes the agent to "fix" correct work.

**The change.** A new configuration, `main_kb_judge`, identical to `main_kb` except for one thing. After the validator accepts an answer, the judge checks it on the usable criteria among `grounded` and `citation_supports_step`. If any fails, the critiques are sent back to the agent, which may call tools again and submits a revised answer. There is one review round at most. The revised answer goes through the validator again and is returned without a second review.

- `root_cause_match` cannot run in the loop. It compares against the expected answer, which exists only for golden incidents and never in real use.
- `investigate` gets an optional `reviewer` argument. Without it the loop behaves exactly as before, so earlier traces stay comparable.
- The trace records the review (overview 5.9). The reviewer's tokens and latency are counted in the totals and also kept separately.
- Because of the LLM cache, each `main_kb_judge` run replays `main_kb` up to its first accepted answer. Before and after therefore differ only by the review.
- Test with a scripted fake model and a fake reviewer: the review passes; the review fails and the revised answer is accepted; the revised answer fails the validator.

**The measurement trap.** The judge that steered an answer cannot be the one that scores its own influence. The pass rates of the criteria used in the loop will rise almost by construction. So the conclusion rests on measures the in-loop judge never saw:

1. Root-cause match against the expected answer, and actionable and benign recall.
2. Aviv's own reading of every run that was sent back, before and after the revision. Expect ten to fifteen pairs. For each he says: was the flagged problem real, is it fixed, and did anything that was right become wrong.

The in-loop criteria still appear in the results table, marked as steered.

| Number | Meaning |
|---|---|
| Revision rate | Share of runs the judge sent back |
| False alarm rate | Of the runs sent back, the share where Aviv says the flagged problem was not real |
| Fix rate | Of the runs sent back for a real problem, the share where it is fixed after revision |
| Harm rate | Of the runs sent back, the share where something right became wrong: a verdict flipped wrongly, a root cause that no longer matches, a supported step removed |
| Abstention shift | Change in the share of `insufficient_evidence` |
| Added cost | Extra LLM calls, tokens and seconds per incident, over all runs and over the revised runs alone |

- **Hypothesis to check or replace:** the reviewer fixes some unsupported claims and citations, at between one and a half and two times the tokens. It leaves root-cause match unchanged and makes the agent abstain more often.
- **What to conclude:** the gain per added token, and whether review belongs always on, only for some answers (actionable verdicts, high severity, low confidence), or off. `main_kb_judge` may become the final configuration for the holdout run only if its gain shows on the measures the judge did not steer.

### E7. Cost against lag (Should, about 1 hour outside the budget)

Aviv's question: what do the active incidents and the cap on agent runs save, and what do they cost in waiting? (Decisions D19 and D20.)

**The runs.** `python -m scripts.replay --no-agent` over the whole file, once per setting. No model is called, so the whole experiment costs minutes. One factor changes at a time:

| Factor | Settings |
|---|---|
| Active incidents | Off, which means one agent run for every log routed to `investigate`, against on with the chosen TTL. This is the baseline comparison |
| TTL | 5, 15 and 60 minutes, with no cap |
| Cap | The chosen TTL with no cap and with two caps on agent runs per hour of log time, one loose and one tight. Choose the two values with Aviv from the busiest hours of the first replay |

**From counts to cost.** A replay without the agent counts runs; it does not measure them. Each counted run is given a number of tokens and an elapsed time drawn, with a fixed seed, from the runs of the final configuration on the dev incidents. Tokens become dollars with the assumed prices in `config/models.yaml`. Every dollar figure in the report says that the price is an assumption and that the tokens are resampled, not measured on that incident.

**What to report**, per setting, saved to `runs/eval/e7_cost.csv`:

- Agent runs in total and per day of logs.
- Tokens and dollars per incident and per day of logs: a histogram, and the median, the 90th percentile and the total.
- Lag to verdict per incident (overview 5.12), which is the wait under the cap in log time plus the run's elapsed time: a histogram, the median and the 90th percentile.
- How many incidents waited, and the longest wait.
- The busiest day on its own, since that is when a cap matters.
- One figure with cost on one axis and lag on the other, one point per setting. This is the trade the experiment is about.

- **Hypothesis to check or replace:** active incidents cut agent runs by orders of magnitude against one run per routed log. A longer TTL saves further runs with quickly shrinking returns. The cap changes total cost little and removes the peaks, at the price of long waits on the few busiest days.
- **What to be honest about:** the tokens of a run come from about 17 dev incidents, which were chosen to be clear-cut and are not a sample of all incidents. The lag leaves out the pacing a free tier imposes. The numbers are projections that show the shape of the trade, not a bill.
- If the settle time of Step 2B task B9 was built, add it as one more factor.

### E1 (if not done in Step 2B)

See Part B task B8 of [02_pipeline_and_agent.md](02_pipeline_and_agent.md).

## The holdout run (Must)

- [ ] Fix the final configuration with Aviv. Nothing changes after this point.
- [ ] `python -m evals.run --config <final> --split holdout --final`, then score and judge.
- [ ] Report the holdout row next to the dev row. If holdout is clearly worse, that is a finding about over-tuning and belongs in the report as it is.

## Cost and latency (Must)

- [ ] **Measured:** tokens in and out, LLM calls and seconds per incident, for each configuration.
- [ ] **Volume:** incidents and agent runs per day on average and on the busiest day, from the `incidents` table of `data/replay.db`. Say how many were answered by the handler and cost nothing.
- [ ] **Projection:** tokens per day at average and peak volume. NVIDIA's free tier has no price, so convert tokens to money with the assumed per-token price in `config/models.yaml`, taken from a public price for a comparable hosted model, and label it an assumption. If E7 was run, this section is its summary.
- [ ] **What the active incidents save:** agent runs against logs routed to `investigate`, from the replay.
- [ ] **What reuse would save:** the number of log shapes that had an incident against the number of incidents. Present it as an upper bound on the saving, and say why reuse across incidents was not built: the same log shape in a different context can need a different answer.
- [ ] **Routing:** which calls could go to the small model, using E1 and E3.
- [ ] **Latency:** seconds per incident against how fast an operator needs an answer, and what dominates it: model calls, or pacing under the rate limit.

## Outputs

- `notebooks/06_results.ipynb` builds every table and figure of the report from the files in `runs/eval/`. No number in the report is typed by hand.
- Tables to `runs/eval/`, figures to `docs/figures/`.

## Done when

- The results table has rows for `main_nokb`, `main_kb`, `small_kb` on dev, and the final configuration on holdout.
- Each experiment has a hypothesis written before the run and two or three sentences of interpretation after it.
- The cost section's inputs are all in files.

## Lab notes should answer

- For each experiment: the hypothesis, the result with counts, and whether the hypothesis held.
- What was the single most common failure type, and did the fix work?
- Where is the small model good enough?
- If E6 was run: how often did the judge send an answer back, how often was it right to, and what did the revision cost? Would you turn review on?
- If E7 was run: what do the active incidents save, where does the cap start to cost lag, and which TTL and cap would you ship?
- Dev against holdout: how different, and what does that say?
- What would you measure next with ten times more golden incidents?

## Suggested commits

Judge results on all dev runs and the E2 and E3 tables; the E4 fix with its new prompt file; the reviewer argument and the E6 traces, if run; holdout traces and final table; results notebook and figures.

## Not in this step

No new features, with one exception: the optional `reviewer` argument that E6 adds to the agent loop. If an experiment suggests a larger redesign (a planner, several specialised agents, merging incidents), write it under next steps for the report and do not build it.
