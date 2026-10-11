# Investigating the most common log shapes by hand

One log was picked for each of the 17 most common log shapes and investigated by hand, with the same queries the agent's tools will use. The aim is to learn what an investigation of each shape takes, how severe the log is, and whether a deterministic rule could decide it without an agent.

The 17 shapes hold 90.6% of the logs (printed by `00_log_shapes_and_tools.ipynb`). That is coverage of shapes, not of cases: only one log per shape was investigated, and logs of the same shape can differ.

## What is here

| File | Content |
|---|---|
| `00_log_shapes_and_tools.ipynb` | The most common log shapes, an example of each query, and the table of the 17 logs |
| `01_...ipynb` to `17_...ipynb` | One investigation per log, numbered in order of how common the log shape is |
| `common.py` | Shared setup: the database connection, the 17 pinned logs, and the helpers. Most helpers are the agent's own tools from `agent/tools.py`, called here with no limit on what they may see; three at the end of the file (`gige_levels`, `minutes_at_level`, `preceded_by`) exist for these notebooks only |

One line per notebook. "Verdict" says whether the notebook ends with a verdict cell; four do not and stop with a to-do. "Golden" marks the ten whose verdict Aviv was sure about; they are the cases in `labeling/golden_cases.yaml`, under the id in brackets, and the agent is evaluated on them.

| # | Log shape (component, state) | What the investigation looks at | Verdict | Golden |
|---|---|---|---|---|
| 01 | `Linkerror event interval expired` (switch_module, error) | The switch's day before, its hourly pattern over 31 days, what the whole cluster logged in the hour, the interleaving with `not responding` | Yes: the first minute of a cluster-wide outage, critical, the line is a symptom | c01 |
| 02 | `ambient=<N>` (node, temperature) | Every reading of the shape over 30 days, the log shapes that mention temperature, the `threshold exceeded` logs, the node's own timeline | Yes: normal, a reading a node writes after boot | c02 |
| 03 | `warning` (gige, temperature) | The device's day before, minutes spent at each level, level changes of every gige over 30 days | Yes: low severity, this device lives in `warning` | c03 |
| 04 | `normal` (gige, temperature) | The starting log alone | Yes: nothing to do | |
| 05 | `Fan speeds ( <N> ... )` (switch_module, fan) | Seven days of fan reports per fan, which fans have no reading, every heat message a switch can write, whether this switch ever ran hot | Yes: low severity, a hardware ticket for fan 4 | c05 |
| 06 | `running` (node, status) | The node's two days before, which nodes reported `running` in the same minutes | Yes: a recovery that ends a nine-hour outage, no action | c06 |
| 07 | `configured out` (node, status) | The node's hour before, whether `configured out` follows `not responding` in general, which other nodes stopped responding; hindsight on the boot commands after | Yes: the system's reaction to `not responding`; the real event is 29 neighbouring nodes going down | c07 |
| 08 | `link errors remain current` (switch_module, error) | The switch's two days, its hourly rate over a week, every message the switch modules ever wrote and when each text appeared, what the other switches logged | No, ends with a to-do | |
| 09 | `boot (command <N>)` (action, start) | The node's day before, the command number as a source, nodes that stopped responding and nodes booted around it | Yes: the line is the operator's fix for a cluster-wide outage, no action | c09 |
| 10 | `wait (command <N>)` (action, start) | The boot-then-wait pairs on this node, the sequence a node writes after a reboot, every operator action on the node over 30 days, the shutdown command that preceded it | Yes: the second step of a boot after a planned cluster-wide shutdown, no action | c10 |
| 11 | `NIFF: ... via interface alt<N>` (unix.hw, net.niff.up) | The starting log alone, with what NIFF is | Yes: a step of a node booting, no action | |
| 12 | `not responding` (node, status) | The node's day before, every command in the cluster that day, other nodes that stopped responding in the ten minutes before, everything the cluster logged in that window | Yes: critical, an outage of most of the cluster, one alarm for the whole cluster not 256 | c12 |
| 13 | `NIFF: ... via interface ee<N>` (unix.hw, net.niff.up) | The node's hour before | Yes: same as 11, no action | |
| 14 | `There is no server for ... domain storage<N>` (clusterfilesystem) | The day before | No, ends with a to-do | |
| 15 | `critical` (gige, temperature) | Minutes at each level that day, level changes of every gige over 30 days, nodes that stopped responding within an hour | No, the last cell is a question | |
| 16 | `running` (partition, status) | The partition's day before, seconds from each `blocked` to the next line, what happened around an earlier `blocked`, nodes down that day | No, the last cell is an observation | |
| 17 | `Component ... is in the unavailable state` (unix.hw, state_change.unavailable) | The node's state changes in the two hours before, seconds each outage lasts, how many nodes show it, whether they go down, the shape's hourly rate over 30 days, whether crashes followed in the past | Yes: a warning, a busy network interface that drops and returns within seconds | c17 |

## How an investigation notebook is built

1. The first code cell imports `common.py` and calls `show(n)`, which prints the log shape and the log.
2. Each following cell asks one question of the logs, looking only at the log and what came before it, which is all the agent will have. The markdown line above a cell says what it looks at.
3. Then comes the verdict.
4. Anything that looks at what happened after the log is hindsight. It comes after the verdict, to check it, and is marked as hindsight.

Read the two kinds of content differently. What the question cells print comes from the data. The verdict holds the reading of what the messages mean, what caused what, and how severe the log is. That part is inference and judgment, and no source confirms the meaning of the messages.

## Running

The notebooks need the database, built once from the repository root:

```
python -m scripts.build_db --rebuild
```

Re-run one notebook, from the repository root:

```
python -m nbconvert --config jupyter_nbconvert_config.py --to notebook --execute --inplace notebooks/incidents/01_linkerror_event_interval_expired.ipynb
```

With this command an unchanged notebook writes the same file byte for byte. The 17 logs are pinned in `common.py` by their line in `HPC.log`, so a rebuilt database gives the same logs.

Queries over logs go through `LogRepository` (`search`, `count_by`, `stats`, `node_timeline`), and each call covers at most 31 days. Log shapes are searched with `LogShapeRepository.search`, by text in the template, component and state.
