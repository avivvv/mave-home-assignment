"""Evaluate the saved trajectories: deterministic checks on every one, the judge on every one that has a verdict, five figures.

    python -m scripts.evaluate_trajectories                      every trajectory of labeling/trajectories/
    python -m scripts.evaluate_trajectories --only c01_ c12_     only the files whose name starts with one of these

A trajectory file is named {case_id}_{config}__{request_id}.txt and its events are read from runs/agent.db, so the
checks see the structured events, the tokens and the latency, not the text. Both the text files and the event log
are committed; a fresh clone runs this without a key as long as the judge's replies are in runs/llm_cache.

Writes runs/eval/trajectory_scores.csv (one row per trajectory: checks and grades), runs/eval/judgements.csv (the
judge's reasoning), runs/eval/summary.csv (one row per agent configuration, every share with its counts) and the
figures of evals/figures.py into docs/figures/.

THE JUDGE IS NOT REALLY CALIBRATED. ITS AGREEMENT WAS MEASURED AGAINST GEMINI PRO, NOT A HUMAN, ON 7 TUNE ITEMS
(notebooks/09_judge_calibration.ipynb), AND IT MISSED MOST OF THE REFERENCE FAILS ON `grounded` AND
`verdict_supported`. THIS SCRIPT TREATS ITS GRADES AS IF THEY WERE CALIBRATED. TAKE EVERY JUDGE NUMBER WITH A GRAIN
OF SALT.
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from agent.judge import judge
from agent.llm import LLM, ROOT
from agent.schema import CRITERIA
from agent.trajectory import Trajectory
from evals.figures import draw_all
from evals.score import score, summarise

TRAJECTORIES_DIR = ROOT / "labeling" / "trajectories"
OUT_DIR = ROOT / "runs" / "eval"
FIGURES_DIR = ROOT / "docs" / "figures"
# judge calls that run at once; each has its own client, so the spacing between calls is per thread
WORKERS = 4


def load(files):
    """The trajectories of the given files: case id, config and request id from the name, the events from runs/agent.db."""
    items = []
    for path in sorted(files):
        case_id, rest = path.stem.split("_", 1)
        config, request_id = rest.rsplit("__", 1)
        items.append({"case_id": case_id, "config": config, "request_id": request_id, "trajectory": Trajectory(request_id)})
    return items


def grade(item, make_llm):
    """The judge's grades on one trajectory: True for pass, False for fail, with the reasoning and what was missing."""
    # the judge is told which tools the agent had; a run made before the knowledge tool existed recorded none, and had the log tools
    judgement, _ = judge(make_llm(), item["trajectory"].text(), tools=item["trajectory"].request.get("tools"))
    row = {"case_id": item["case_id"], "config": item["config"], "request_id": item["request_id"]}
    for criterion in CRITERIA:
        result = getattr(judgement, criterion)
        row[criterion] = result.result == "pass"
        row[f"{criterion}_reasoning"] = result.reasoning
    row["missing"] = judgement.missing
    return row


def evaluate(items, make_llm=LLM, out_dir=OUT_DIR, figures_dir=FIGURES_DIR, log=print):
    """Score, judge and draw. Returns the scores table; the judge columns are None where there was no verdict."""
    scores = pd.DataFrame([{"case_id": i["case_id"], "config": i["config"], "request_id": i["request_id"], **score(i["trajectory"])} for i in items])
    log(f"{len(items)} trajectories scored; {int((scores.outcome == 'verdict').sum())} ended with a verdict and go to the judge")

    with_verdict = [item for item in items if item["trajectory"].verdict is not None]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        graded = list(pool.map(lambda item: grade(item, make_llm), with_verdict))
    judgements = pd.DataFrame(graded) if graded else pd.DataFrame(columns=["case_id", "config", "request_id", *CRITERIA])
    for criterion in CRITERIA:
        scores[criterion] = None
    if len(judgements):
        grades = judgements.set_index("request_id")[list(CRITERIA)]
        for criterion in CRITERIA:
            scores[criterion] = scores.request_id.map(grades[criterion]).astype(object).where(scores.request_id.isin(grades.index), None)
    for item in with_verdict:
        row = judgements[judgements.request_id == item["request_id"]].iloc[0]
        log(f"  judged {item['case_id']} {item['config']}: " + ", ".join(f"{c}={'pass' if row[c] else 'fail'}" for c in CRITERIA))

    out_dir.mkdir(parents=True, exist_ok=True)
    scores.to_csv(out_dir / "trajectory_scores.csv", index=False)
    judgements.to_csv(out_dir / "judgements.csv", index=False)
    summary = summarise(scores)
    summary.to_csv(out_dir / "summary.csv")
    paths = draw_all(scores, figures_dir)
    log(f"\nwrote {out_dir / 'trajectory_scores.csv'}, {out_dir / 'judgements.csv'}, {out_dir / 'summary.csv'} and {len(paths)} figures to {figures_dir}")
    return scores, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="+", metavar="PREFIX", help="evaluate only the trajectory files whose name starts with one of these")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    files = [path for path in TRAJECTORIES_DIR.glob("*.txt") if not args.only or any(path.name.startswith(prefix) for prefix in args.only)]
    if not files:
        raise SystemExit(f"no trajectory in {TRAJECTORIES_DIR} matches {args.only}")
    print(__doc__.split("\n\n")[-1].strip(), "\n")
    _, summary = evaluate(load(files))
    pd.set_option("display.width", 200)
    print("\n" + summary.T.to_string())


if __name__ == "__main__":
    main()
