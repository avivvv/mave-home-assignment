# Investigating the most common log shapes by hand

One log was picked for each of the 17 most common log shapes and investigated by hand, with the same queries the agent's tools will use. The aim is to learn what an investigation of each shape takes, how severe the log is, and whether a deterministic rule could decide it without an agent.

The 17 shapes hold 90.6% of the logs (printed by `00_log_shapes_and_tools.ipynb`). That is coverage of shapes, not of cases: only one log per shape was investigated, and logs of the same shape can differ.

## What is here

| File | Content |
|---|---|
| `00_log_shapes_and_tools.ipynb` | The most common log shapes, an example of each query, and the table of the 17 logs |
| `01_...ipynb` to `17_...ipynb` | One investigation per log, numbered in order of how common the log shape is |
| `common.py` | Shared setup: the database connection, `find_shapes` for searching log shapes, the 17 pinned logs, and a few helpers that reshape query results into tables |

| # | Log shape | # | Log shape |
|---|---|---|---|
| 01 | `Linkerror event interval expired` | 10 | `wait (command <N>)` |
| 02 | `ambient=<N>` | 11 | `NIFF: ... available ... via interface alt<N>` |
| 03 | `warning` (gige temperature) | 12 | `not responding` (node) |
| 04 | `normal` (gige temperature) | 13 | `NIFF: ... available ... via interface ee<N>` |
| 05 | `Fan speeds ( ... )` | 14 | `There is no server for ... domain storage<N>` |
| 06 | `running` (node) | 15 | `critical` (gige temperature) |
| 07 | `configured out` | 16 | `running` (partition) |
| 08 | `link errors remain current` | 17 | `Component ... is in the unavailable state` |
| 09 | `boot (command <N>)` | | |

## How an investigation notebook is built

1. The first code cell imports `common.py` and calls `show(n)`, which prints the log shape and the log.
2. Each following cell asks one question of the logs, looking only at the log and what came before it, which is all the agent will have. The markdown line above a cell says what it looks at.
3. Then comes the verdict.
4. Anything that looks at what happened after the log is hindsight. It comes after the verdict, to check it, and is marked as hindsight.

Read the two kinds of content differently. What the question cells print comes from the data. The verdict holds the reading of what the messages mean, what caused what, and how severe the log is. That part is inference and judgment, and no source confirms the meaning of the messages.

The investigations were started by hand by Aviv and completed together with an AI coding assistant.

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
