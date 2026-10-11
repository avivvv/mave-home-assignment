# Analysis notebooks

Nine notebooks, numbered in the order the work happened. They are committed with their outputs, and the lab notes and the root README quote their numbers by pointing at them. The hand investigations of single logs are in the [`incidents/`](incidents/README.md) folder, which has its own README.

## What each notebook does

| Notebook | Question it answers | Reads | Writes | Calls a model |
|---|---|---|---|---|
| `01_initial_EDA.ipynb` | What is in the raw file: column distributions, the time span, how many distinct events remain after dropping identical copies, whether the first column identifies an event (it does not), what kinds of source the node column holds, events per day, how many log shapes there are and when each quarter brings new ones, and a first rough count of error-like events, incidents and incident signatures with a keyword filter | `data/original_dataset/HPC.log` directly, with its own parser | Nothing | No |
| `02_loghub_template_check.ipynb` | Do the repository's masks agree with Loghub's hand-annotated templates on its 2,000-line sample? Grouping accuracy, the groups that merge two annotated templates, the annotated templates the masks split, and templates that appear under more than one component or state | `data/loghub/HPC_2k.log_structured.csv`, `data/loghub/HPC_2k.log_templates.csv`, `logstore/templating.py` | Nothing | No |
| `03_flag_column_analysis.ipynb` | Is the undocumented `flag` column an error label? Its values by component, state and message; how it behaves among identical copies of one event (0 and -1 mark repeats; among copies the flag only ever moves from 0 to 1, in file order); the flag of the last copy of each event; two worked examples | `HPC.log` directly | Nothing | No |
| `04_log_shape_novelty.ipynb` | When was each of the 141 log shapes first seen? New shapes per month and per quarter, and the shapes that arrive more than a year after the first log. This is the measured reason for sending unknown log shapes to the agent | `data/hpc.db` | `docs/figures/log_shape_novelty.png` | No |
| `05_cluster_facts.ipynb` | What can be read about the cluster from the logs alone: the kinds of source, the 256 compute nodes, how nodes are grouped into the 8 domains (from operator commands that name one domain and one node), which nodes serve which file domains and whether the name of a storage file domain gives its serving node, the interconnect switch modules, the network interfaces in the NIFF messages, and the other devices. Every `[data]` statement in `kb/cluster_facts.md` is a count printed here | `data/hpc.db` | Nothing; the fact sheet was written by hand from its output | No |
| `06_model_selection.ipynb` | Which NVIDIA models can drive the agent and the judge? Checks each candidate against the live catalogue, runs three tool-calling checks on pretend tools (one call, a two-step chain, a forced choice), tries each as judge on the smoke test's plainly bad trajectory, and measures the investigator's first round five times under four hidden-thinking settings (on, budget 500, budget 200, off) for latency and the number of tools called. The choices in `config/models.yaml` rest on this | The NVIDIA models endpoint, `config/models.yaml`, the made-up logs of `scripts/agent_smoke_test.py` | Nothing besides the LLM cache | Yes, cached under the tag `model-selection` |
| `07_create_golden_set_trajectories.ipynb` | Runs the agent on all ten golden cases in parallel under the current configuration and saves each trajectory as text. The configuration tag (model, thinking, rounds, `_kb`) is part of the file name, so changing `config/models.yaml` and re-running produces a new set beside the old ones. As committed, the first cell forces `knowledge = True`: the last run was the knowledge arm | `labeling/golden_cases.yaml`, `data/hpc.db`, `config/models.yaml` | `labeling/trajectories/*.txt`, new requests in `runs/agent.db`, new replies in `runs/llm_cache/` | Yes, cached under the configuration tag |
| `08_trajectory_labeling.ipynb` | A form for grading one trajectory by hand: lists the trajectory files and which are graded, prints the judge's prompt and tool list, prints one trajectory, and saves a pasted JSON grade as one row. It is interactive: set `TRAJECTORY`, run, read, paste, run the save cell. The reference grades committed in `labeling/human_grades.csv` were produced by pasting the same material into Gemini 2.5 Pro's web UI and recording its answer, not by a person grading | `labeling/trajectories/`, `prompts/judge_v1.md` | `labeling/human_grades.csv` (appends or replaces one row) | No |
| `09_judge_calibration.ipynb` | How well does the judge agree with the reference grades? Splits the graded trajectories into a tune set (seven, listed in the notebook) and a held-out set, runs three judge configurations (GPT-OSS-20B at low and medium effort, Nemotron 3 Super at low effort) on the chosen set, saves one CSV per configuration with judge and reference grades side by side, prints agreement per criterion and the disagreements with the judge's reasoning, and draws two figures | `labeling/human_grades.csv`, `labeling/trajectories/`, `config/models.yaml` | `labeling/judge_results/<tag>.csv`, `docs/figures/judge_calibration.png`, `docs/figures/judge_pass_rates.png` | Yes, the judge, cached under each configuration's tag |

## Running a notebook

Notebooks 04 to 09 need the database, built once from the repository root:

```
python -m scripts.build_db --rebuild
```

Notebooks 06, 07 and 09 need `NVIDIA_API_KEY` in `.env` unless every call they make is already in `runs/llm_cache/`. All of them resolve the repository root from their own location, so they are run from the repository root with nbconvert:

```
python -m nbconvert --config jupyter_nbconvert_config.py --to notebook --execute --inplace notebooks/04_log_shape_novelty.ipynb
```

The config file stops nbconvert from stamping run times into cells and joins the chunks in which a cell's prints arrive, so an unchanged notebook writes the same file byte for byte. Use `python -m nbconvert`, not `jupyter nbconvert`: on the development machine the latter runs on a different Python install.

Three cautions before re-running:

- **07 creates new files.** Each run writes ten new trajectory files and ten new requests into `runs/agent.db`, and if the request is not in the cache it calls the investigator model up to four times per case. Remove the `config["knowledge"] = True` line in its first cell to run the configuration that `config/models.yaml` describes.
- **09 overwrites the calibration CSVs and figures** for the configurations it lists, and a fresh judge call at temperature 0 does not always return the same grades as the cached one.
- **08 is meant to be run cell by cell**, not with nbconvert.

## What is not here

There is no results notebook: the evaluation tables and figures come from `python -m scripts.evaluate_trajectories` (see the root README). The notebooks that produced the golden cases are in `incidents/`.
