# Step 1: understand the data and define "good"

Read first: `AGENTS.md`, [00_overview.md](00_overview.md), Part 1 of [docs/lab_notes.md](../lab_notes.md).

Budget: 3 hours. This step is done together with Aviv, in a notebook.

## Goal

By the end of this step a few dozen log shapes have a route, a severity and a category, and there is a short list of problem categories, and about 25 golden incidents with expected answers. No agent exists yet, and that is deliberate: "good" is defined before anything is built to produce it (decision D5).

## Why it matters

Every number in the report is measured against what is written here. It is also where the report shows that the domain was understood without any documentation being given.

## Before you start

- You are on `main` with a clean working tree.
- `data/original_dataset/HPC.log` exists (433,490 lines).
- The branch `labeling-helper` exists locally.

## Who does what

Aviv makes every labelling decision and writes every expected answer. You build the helpers, show him the evidence, explain what a log message means, and may propose a label with your reasoning. You never fill a label file on his behalf without his confirmation, because he must be able to defend each one.

## Concepts to explain when they come up

- A **compute node**, the **interconnect** (the fast network between nodes), a **shared filesystem**, the **scheduler** (which hands nodes to user jobs), and the **console** or **terminal server** (remote access to a node that is not running its operating system).
- **MTTR**, mean time to repair, and **alert fatigue**: operators ignore a channel that cries wolf.
- **Triage**: deciding quickly what deserves attention.
- **Hindsight labelling**: using what happened afterwards to decide what an event was.

## A head start on the domain

These are hypotheses from the vocabulary of the logs. Task 1.1 checks them.

| In the logs | Likely meaning |
|---|---|
| `node-N` (about 256), `node-DN` (8) | Compute nodes, grouped into 8 "domains" of 32 nodes managed as sub-clusters |
| `SRM`, "node went to SRM" | The Alpha firmware console. A node that lands there did not boot its operating system |
| `risBoot`, `bootGenvmunix`, `clusterAddMember` | Stages of installing and booting a node and joining it to the cluster |
| `LMF licenses` | Tru64's licence manager, loaded during boot |
| `NIFF ... via interface alt0 / ee0` | A Tru64 daemon that watches network interfaces. `ee0` and `alt0` are network card names |
| `ServerFileSystem domain ... is full`, `fdmn.panic` | A storage pool ("file domain") filled up or crashed |
| `ClusterFileSystem ... no longer served by node X`, "no server for" | The node serving a shared filesystem stopped serving it. "No server" means nobody took over |
| `partition status running / blocked / down` | The scheduler's view of the pool of nodes that runs user jobs |
| `switch_module`, `Interconnect-NNN`, `Link error`, `broadcast tree` | The interconnect and its switches |
| `tserver`, "Console-Busy Port already in use" | The terminal server |
| `gige` temperature, `psu failure`, `fan` | Hardware health of ethernet switches and nodes |
| `boot_cmd`, `shutdown_cmd`, `action start halt` | **Operator commands.** These are the hindsight signal: they show what a human did after a problem |

## Tasks

### Task 1.0. Merge copies and collapse list variants, then rebuild once (Must)

Both change what is in the database, so do both before anything is counted or labelled.

**One row per event**, enforced by the `logs` table (decision D15). A line is a copy when a stored row has the same node, component, state, time and message. It does not add a row: the row takes that line's flag, record counter and raw text, and `n_copies` goes up by one. `IngestResult` reports how many lines were merged. Background: [notebooks/03_flag_column_analysis.ipynb](../../notebooks/03_flag_column_analysis.ipynb) found that rows with flag 0 or -1 are almost always repeated copies, and that among copies the flag only moves from 0 to 1 in file order.

**Collapse list variants**, in `logstore/templating.py`. Half of the 249 log shapes are four messages whose only difference is the length of a list:

| Family | Keys today | After |
|---|---|---|
| `Targeting domains:... and nodes:...` | 58 | One per component and state, plus one for the form ending in `child of command <N>` |
| `inconsistent nodesets <NODE> <HEX> <ok> ...` | 26 | One |
| `Command Failed on: <NODE>\ <NODE> ...` | 26 | One per component and state |
| `Failed subcommands <N>\ <N> ...` | 13 | One per component and state |

A list of one item and a list of twenty must give the same template. Each new placeholder gets an entry in `PLACEHOLDERS` with its meaning. One existing test asserts the exact set of placeholders and needs updating.

- [ ] Write the tests first, then the masks.
- [ ] Rebuild: `python -m scripts.build_db --rebuild`.
- [ ] Check: about 411,000 logs (the flag notebook counted 411,483 distinct events) and about 140 log shapes. Record the real numbers in lab notes.

### Task 1.1. Check what the cluster is (Must, 30 minutes at most)

- [ ] Search for public documentation matching the table above. One manual is known to be online and has not been read: the "Compaq AlphaServer SC RMS Reference Manual". Tru64 UNIX administration guides and man pages are archived in several places.
- [ ] Write what you found to `kb/sources.md`: title, URL, what it covers, date checked.
- [ ] Tell Aviv which rows of the table are confirmed, which are corrected and which stay guesses.

If nothing usable turns up in 30 minutes, stop. The knowledge base will then be marked as general practice, and the report will say so.

### Task 1.2. Exploration helpers and notebook (Must)

- [ ] inside`logstore/repositories.py`, add read-only helpers over the database. Every one takes a time range, `start` and `end`, both included and both required, and refuses a range longer than 31 days, so no call can pull the whole table (decision D22). They serve the agent's tools; code that only a notebook or a script needs stays in that notebook or script.
  - `LogRepository.search(start, end, node, component, text, log_shape_id, limit)`: the logs of the range that pass every given filter, newest first. `text` is a part of the message in any letter case. The agent's `search_logs` tool in Step 2B wraps this function.
  - `LogRepository.count_by(group_by, start, end, ...)`: log counts per `node`, `component`, `log_shape` or `hour`, largest first, 20 groups by default, with the filters of `search`. The agent's `count_logs` tool wraps this function.
  - `LogRepository.node_timeline(node, start, end)`: the logs of one node in a time range, oldest first, with runs of the same log shape collapsed into one entry holding the first time, last time and count. The agent's `node_timeline` tool in Step 2B wraps this function.
  - `LogRepository.stats(start, end, node, component, text, log_shape_id)`: log count, node count, first seen and last seen of the logs that `search` would return. **Stats that look only at the past** (overview 5.5, decision D18) are this query with a window that ends at the log: `stats(ts - window, ts, log_shape_id=...)`, over the cluster or with `node` for one node. The existing index on `log_shape_id` and `ts` serves it. Test it on a window with nothing in it and make sure it does not return anything past the given ts (no look ahead). The router, the incident card and the agent's `get_stats` tool all use this one query.
- [ ] The notebooks in `notebooks/incidents/`, which use them. Follow the notebook rules in `AGENTS.md`: titles only in markdown cells, findings in chat.

### Task 1.3. Label a few dozen log shapes (Must)

- [ ] `scripts/export_log_shapes.py` writes `labeling/log_shapes.csv` (format in overview 5.3), one row for every log shape. The counts over the whole history are the script's own SQL, the query in `notebooks/incidents/common.py`: the repository reads are bounded to 31 days and serve the agent. Running it again must never lose a label: existing rows keep the columns Aviv fills; new keys are appended; keys that disappeared are reported, not deleted.
- [ ] Aviv labels a few dozen rows and leaves the others empty (decision D21). Label the most frequent log shapes first, because they decide most of the volume and most of the agent's load, then every log shape that appears in a golden incident of task 1.6. An empty row has no catalogue row, so its logs go to the agent, and the evaluation shows how the agent copes with them.
- [ ] Report the share of all logs that the labelled rows cover, from a cell of the notebook.

**The route of a log shape** says what the pipeline does when a log of that shape arrives.

| Kind of message | Route | Category |
|---|---|---|
| Routine reading (`ambient=<N>`, `Fan speeds`, `temperature normal`) | `ignore` | `telemetry` |
| Operator command started or finished normally | `ignore` | `operations` |
| Something came back (`Link ok`, `available`, `responding`) | `ignore` | `recovery` |
| A problem on its own, with no fixed answer (`fdmn.panic`, an operator command that failed) | `investigate` | a problem category |
| A problem whose fix is known and always the same | `handle`, with a handler | a problem category |
| A problem only when it repeats or spreads (one `Link error` against a burst) | `rule`, with a rule | a problem category |

Rows that are hard to call (`not responding`, `configured out`, `Linkerror event interval expired`) are decided with the evidence from task 1.5, so leave them for last.

- [ ] **Aviv picks the one log shape that gets a deterministic handler.** It needs a known cause and a fix that is the same every time. A candidate is `ServerFileSystem domain ... is full` (state `fdmn.full`). Record the choice and the fix; Step 2A writes the handler. **Do not finish task 1.3 without this choice.**
- [ ] **Aviv picks the one log shape that gets a rule**, and writes the rule in words, in the form "ignore when it happens once, investigate when it happens more than 3 times on a node within an hour". The placeholder `burst_on_node` in overview 5.5 stands in for it until then. Step 2A puts the real rule in `config/triage.yaml`. **Do not finish task 1.3 without this choice.** If Aviv has not raised it by the time the labelling is done, remind him.
- [ ] When the rows are labelled, agree the final list of six to eight problem categories with Aviv. The starting proposal is in overview 5.3. Record the list in lab notes; Step 2A puts it in `config/triage.yaml`.

### Task 1.4. Try the incident rule (Must)

In the notebook, a prototype of the active incidents of overview 5.5, without rules or handlers: take the logs whose log shape is not labelled `ignore`, unlabelled ones included, in time order per log shape. A new incident opens when the gap to the previous log of the shape exceeds the TTL, or when the incident would exceed the maximum duration. Do it for TTLs of 5, 15 and 60 minutes.

- [ ] For each TTL: number of incidents, incidents per day, the distribution of size and duration, and how many incidents come from unlabelled log shapes. Incidents per day is close to the number of agent runs per day.
- [ ] Read ten random incidents for two or three of the TTLs with Aviv. Too short a TTL opens a second incident for a problem that is still going on; too long a TTL keeps an incident open across unrelated occurrences.
- [ ] Choose the default `ttl_minutes`, any TTL that differs by severity, and `max_hours`, with Aviv. The starting value is 15 minutes. Record them with the reasoning.
- [ ] Pick one contiguous week that has incidents in several components. Step 2A replays it as its sample. Record the dates.

Rough numbers from planning, for the earlier rule that grouped by component and with a keyword filter instead of real labels (the last cells of `notebooks/01_EDA.ipynb`): 60 minutes gave about 6,700 incidents, about 7 a day, with a median of 2 lines. One incident per log shape will give different numbers.

### Task 1.5. Hindsight mining (Must, 1 hour at most)

For each labelled log shape whose route is not `ignore`, and for the most frequent unlabelled ones, look at what follows on the same node within a few hours.

- [ ] The share followed by a log shape labelled `recovery`, and the median time to it. A high share means the problem usually clears by itself.
- [ ] The share followed by a log shape labelled `operations`, which ones, and the median time. This shows whether a human acted and what they did.
- [ ] One table, one row per log shape looked at. Show it to Aviv and use it to settle the hard rows of task 1.3.

What this is for: it tells which incidents were real, how long they lasted, and what the operators' actual remediation was (decision D6). It is correlation, not proof, and the report will say so.

### Task 1.6. Write the golden incidents (Must)

- [ ] With Aviv, choose about 25 incidents from task 1.4's output. Two or three per problem category, and these on purpose:
  - at least 6 **benign** cases: errors during a planned shutdown, links that recover within seconds, "not responding" while a node is being rebooted;
  - **rare but critical** ones: `fdmn.panic`, fan failure, PSU failure, "cluster would lose quorum";
  - one **chronic noisy** case: `Linkerror event interval expired`;
  - one **cascade**: a filesystem server lost, followed by "no longer served" on other nodes. With one incident per log shape this is two or more incidents; make the later one the golden entry, so that a good answer names the earlier incident as the cause;
  - at least four incidents of **log shapes left unlabelled** in task 1.3, since those reach the agent with no catalogue row;
  - one incident of the log shape that has the **handler**, and one of the log shape that has the **rule**.
- [ ] For each, show Aviv the incident (its log shape, counts per node, first and last lines), the 24 hours before it on the nodes involved, and what followed. He investigates on `data/hpc.db` with the same query helpers the agent's tools will wrap. He writes the entry in `labeling/golden_incidents.yaml` (format in overview 5.3).
- [ ] The agent will start at the incident's opening and see only what was visible from then on (decisions D6 and D20). So the expected root cause must be one an investigator could reach from the logs up to the opening and the history before it. What happened afterwards goes in `hindsight` and backs Aviv's confidence; it is not something the agent is expected to say.
- [ ] Keep only cases where the hindsight evidence makes Aviv confident. Drop the rest and say how many were dropped.
- [ ] Mark 8 of the 25 as `holdout`, drawn at random within categories with a fixed seed. From this point nobody looks at agent output on those 8 until the final run of Step 4.

### Task 1.7. Log shape novelty plot (Should)

- [ ] Number of log shapes first seen in each month, as a bar chart saved to `docs/figures/log_shape_novelty.png`. It is the empirical argument for the future-proof design.

### Task 1.8. Cluster fact sheet (Should)

- [ ] `kb/cluster_facts.md` in the format of overview 5.11: node naming, the domains, which nodes serve filesystems, how many switches and of what kind. Everything in it is inferred from the data or taken from a source in `kb/sources.md`, and says which.

### Task 1.9. The stats cache (Could)

Optional, and the first thing to cut. In production the stats of overview 5.5 are not SQL scans: they come from a cache that is updated in batches as chunks are ingested (decision D18). This task builds that cache over the database, to show the principle working.

- [ ] A cache that is fed logs in processing order and answers the same stats as the SQL query of task 1.2. Counts are kept in time buckets per log shape and node, and a window is a sum over buckets. Distinct nodes cannot be summed, so each bucket keeps the set of nodes seen. Longer windows can use coarser buckets.
- [ ] The order of updates is the contract: before a chunk is routed the cache holds every earlier log, and each log is added as it is routed, so the cache is current for exactly the next log.
- [ ] Test: feed the sample week in 5-minute chunks and check that, for every log, cache and SQL return the same value of every stat.
- [ ] Measure the time per stat for both, on the most frequent log shape and a 30-day window, in a notebook cell.

## Done when

- Unit tests and the smoke test pass on the rebuilt database.
- A few dozen rows of `labeling/log_shapes.csv` have a route, a severity and a category, and the share of logs they cover is known.
- The log shape that gets the handler and the log shape that gets the rule are chosen, with the fix and the rule written down.
- `labeling/golden_incidents.yaml` has about 25 entries, each with an expected root cause, a hindsight note and a `dev` or `holdout` mark.
- `ttl_minutes`, `max_hours`, the category list and the sample week are recorded.
- Aviv can explain each problem category in two sentences.

## Lab notes should answer

- How many logs and log shapes are there after merging copies and collapsing lists?
- Which rows of the domain table were confirmed, and from which source?
- Which log shapes were labelled, what share of the logs do they cover, and which were hard to label?
- Which log shape got the handler and which got the rule, and why those?
- Which TTL was chosen, and what did the incidents look like at the TTLs that were rejected?
- How many incidents a day come from unlabelled log shapes?
- What did hindsight mining show: which problems clear by themselves, which draw an operator, and how fast?
- How many candidate incidents were dropped for lack of confidence? This bounds what the golden set can claim.

## Suggested commits

1. Log store changes from `labeling-helper`.
2. Merge copies at ingest and collapse list variants.
3. Query helpers, past-only stats and the exploration notebook.
4. Log shape labels, with the handler and rule choices.
5. Golden incidents, novelty plot, fact sheet.
6. The stats cache, if built.

## Not in this step

No LLM calls, no catalogue table, no incident table, no router, no replay, no agent. The incidents here are a prototype in a notebook; Step 2A builds the router, the active incidents and the replay.
