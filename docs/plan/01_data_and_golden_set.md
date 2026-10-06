# Step 1: understand the data and define "good"

Read first: `AGENTS.md`, [00_overview.md](00_overview.md), Part 1 of [docs/lab_notes.md](../lab_notes.md).

Budget: 3 hours. This step is done together with Aviv, in a notebook.

## Goal

By the end of this step there is a label for every template, a short list of problem categories, and about 25 golden incidents with expected answers. No agent exists yet, and that is deliberate: "good" is defined before anything is built to produce it (decision D5).

## Why it matters

Every number in the report is measured against what is written here. It is also where the report shows that the domain was understood without any documentation being given.

## Before you start

- You are on `main` with a clean working tree.
- `data/HPC.log` exists (433,490 lines).
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

### Task 1.0. Drop copies and collapse list variants, then rebuild once (Must)

Both change what is in the database, so do both before anything is counted or labelled.

**Drop identical copies at ingest**, in `logstore/ingest.py`. A line is a copy when an earlier line has the same node, component, state, time and message. Keep the first and drop the rest. `IngestResult` reports how many were dropped. Background: [notebooks/flag_column_analysis.ipynb](../../notebooks/flag_column_analysis.ipynb) found that rows with flag 0 or -1 are almost always repeated copies, and concluded they should be dropped.

**Collapse list variants**, in `logstore/templating.py`. Half of the 249 template keys are four messages whose only difference is the length of a list:

| Family | Keys today | After |
|---|---|---|
| `Targeting domains:... and nodes:...` | 58 | One per component and state, plus one for the form ending in `child of command <N>` |
| `inconsistent nodesets <NODE> <HEX> <ok> ...` | 26 | One |
| `Command Failed on: <NODE>\ <NODE> ...` | 26 | One per component and state |
| `Failed subcommands <N>\ <N> ...` | 13 | One per component and state |

A list of one item and a list of twenty must give the same template. Each new placeholder gets an entry in `PLACEHOLDERS` with its meaning. One existing test asserts the exact set of placeholders and needs updating.

- [ ] Write the tests first, then the masks.
- [ ] Rebuild: `python -m scripts.build_db --rebuild`.
- [ ] Check: about 411,000 logs (the flag notebook counted 411,483 distinct events) and about 140 template keys. Record the real numbers in lab notes.

### Task 1.1. Check what the cluster is (Must, 30 minutes at most)

- [ ] Search for public documentation matching the table above. One manual is known to be online and has not been read: the "Compaq AlphaServer SC RMS Reference Manual". Tru64 UNIX administration guides and man pages are archived in several places.
- [ ] Write what you found to `kb/sources.md`: title, URL, what it covers, date checked.
- [ ] Tell Aviv which rows of the table are confirmed, which are corrected and which stay guesses.

If nothing usable turns up in 30 minutes, stop. The knowledge base will then be marked as general practice, and the report will say so.

### Task 1.2. Exploration helpers and notebook (Must)

- [ ] `logstore/queries.py`, read-only helpers over the database:
  - `template_stats(conn)`: one row per template key with log count, node count, first seen, last seen and three example messages spread over time.
  - `logs_around(conn, node, ts, before_s, after_s)`: the logs of one node around a moment.
  - `node_timeline(conn, node, start, end)`: the logs of one node in a window, with runs of the same template collapsed into one entry holding the first time, last time and count. The agent's `node_timeline` tool in Step 2B wraps this function.
- [ ] `notebooks/01_incidents.ipynb`, which uses them. Follow the notebook rules in `AGENTS.md`: titles only in markdown cells, findings in chat.

### Task 1.3. Label every template (Must)

- [ ] `scripts/export_templates.py` writes `labeling/templates.csv` (format in overview 5.3) from `template_stats`. Running it again must never lose a label: existing rows keep their `is_alert`, `category` and `note`; new keys are appended; keys that disappeared are reported, not deleted.
- [ ] Aviv fills `is_alert` and `category` for every row.

**Definition of an alert:** on its own, this message means something a cluster operator should look at.

| Kind of message | Alert? | Category |
|---|---|---|
| Routine reading (`ambient=<N>`, `Fan speeds`, `temperature normal`) | no | `telemetry` |
| Operator command started or finished normally | no | `operations` |
| Something came back (`Link ok`, `available`, `responding`) | no | `recovery` |
| An operator command that failed (`action error ...`, `Command Failed on`) | yes | a problem category |
| A threshold was exceeded, something failed, filled up or stopped responding | yes | a problem category |

Rows that are hard to call (`not responding`, `configured out`, `Linkerror event interval expired`) are decided with the evidence from task 1.5, so leave them for last.

- [ ] When all rows are labelled, agree the final list of six to eight problem categories with Aviv. The starting proposal is in overview 5.3. Record the list in lab notes; Step 2A puts it in `config/triage.yaml`.

### Task 1.4. Try the grouping rule (Must)

In the notebook, group the alert logs by the rule in overview 5.5 for gaps of 15, 30, 60 and 180 minutes.

- [ ] For each gap: number of incidents, incidents per day, and the distribution of size and duration.
- [ ] Read ten random incidents for two or three of the gaps with Aviv. Too small a gap splits one event into several; too large a gap glues unrelated events together.
- [ ] Choose `gap_minutes` and `max_hours` with Aviv. Record them and the reasoning as a decision log entry.
- [ ] Pick one contiguous week that has incidents in several components. Step 2A uses it as its sample. Record the dates.

Rough numbers from planning, with a keyword filter instead of real labels (the last cells of `notebooks/EDA.ipynb`): 60 minutes gave about 6,700 incidents, about 7 a day, with a median of 2 lines.

### Task 1.5. Hindsight mining (Must, 1 hour at most)

For each alert template, look at what follows on the same node within a few hours.

- [ ] The share followed by a `recovery` template, and the median time to it. A high share means the problem usually clears by itself.
- [ ] The share followed by an `operations` template, which ones, and the median time. This shows whether a human acted and what they did.
- [ ] One table, one row per alert template. Show it to Aviv and use it to settle the hard rows of task 1.3.

What this is for: it tells which incidents were real, how long they lasted, and what the operators' actual remediation was (decision D6). It is correlation, not proof, and the report will say so.

### Task 1.6. Write the golden incidents (Must)

- [ ] With Aviv, choose about 25 incidents from task 1.4's output. Two or three per problem category, and these on purpose:
  - at least 6 **benign** cases: errors during a planned shutdown, links that recover within seconds, "not responding" while a node is being rebooted;
  - **rare but critical** ones: `fdmn.panic`, fan failure, PSU failure, "cluster would lose quorum";
  - one **chronic noisy** case: `Linkerror event interval expired`;
  - one **cascade**: a filesystem server lost, followed by "no longer served" on other nodes.
- [ ] For each, show Aviv the incident (counts per template and node, first and last lines), the 24 hours before it on the nodes involved, and what followed. He writes the entry in `labeling/golden_incidents.yaml` (format in overview 5.3).
- [ ] Keep only cases where the hindsight evidence makes Aviv confident. Drop the rest and say how many were dropped.
- [ ] Mark 8 of the 25 as `holdout`, drawn at random within categories with a fixed seed. From this point nobody looks at agent output on those 8 until the final run of Step 4.

### Task 1.7. Template novelty plot (Should)

- [ ] Number of template keys first seen in each month, as a bar chart saved to `docs/figures/template_novelty.png`. It is the empirical argument for the future-proof design.

### Task 1.8. Cluster fact sheet (Should)

- [ ] `kb/cluster_facts.md` in the format of overview 5.11: node naming, the domains, which nodes serve filesystems, how many switches and of what kind. Everything in it is inferred from the data or taken from a source in `kb/sources.md`, and says which.

## Done when

- Unit tests and the smoke test pass on the rebuilt database.
- Every row of `labeling/templates.csv` has `is_alert` and `category`.
- `labeling/golden_incidents.yaml` has about 25 entries, each with an expected root cause, a hindsight note and a `dev` or `holdout` mark.
- `gap_minutes`, `max_hours`, the category list and the sample week are recorded.
- Aviv can explain each problem category in two sentences.

## Lab notes should answer

- How many logs and template keys are there after dropping copies and collapsing lists?
- Which rows of the domain table were confirmed, and from which source?
- Which templates were hard to label, and what settled them?
- Which gap was chosen, and what did the incidents look like at the gaps that were rejected?
- What did hindsight mining show: which problems clear by themselves, which draw an operator, and how fast?
- How many candidate incidents were dropped for lack of confidence? This bounds what the golden set can claim.

## Suggested commits

1. Log store changes from `labeling-helper`.
2. Drop copies at ingest and collapse list variants.
3. Query helpers and the exploration notebook.
4. Template labels.
5. Golden incidents, novelty plot, fact sheet.

## Not in this step

No LLM calls, no catalogue table, no incident table, no agent. The grouping here is a prototype in a notebook; Step 2A turns it into a module.
