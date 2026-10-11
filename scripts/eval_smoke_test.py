"""Smoke test of the trajectory evaluation: the whole of scripts/evaluate_trajectories.py on one saved trajectory.

The trajectory is one that ended with a verdict, so the judge is called (its reply is read from runs/llm_cache when
it is there). The test checks the shape of what comes out, not the grades themselves: one scored row with the
outcome, the checks and a True/False grade on every criterion; one judgement row with a reasoning per criterion;
one summary row with every share as 'k of n'; the four figures. Nothing is written outside runs/scratch/.

Run from the repo root: python -m scripts.eval_smoke_test
"""
import sys

import pandas as pd

from agent.llm import ROOT
from agent.schema import CRITERIA
from evals.figures import FIGURES
from evals.score import OUTCOMES
from scripts.evaluate_trajectories import TRAJECTORIES_DIR, evaluate, load

# any trajectory whose investigation ended with a verdict; the judge has to see a verdict to grade it
TRAJECTORY = "c12_nemotron-3-super-120b-a12b_think200_4r__a247b0d36766.txt"
OUT_DIR = ROOT / "runs" / "scratch" / "eval_smoke"


def main():
    sys.stdout.reconfigure(errors="replace")
    items = load([TRAJECTORIES_DIR / TRAJECTORY])
    assert len(items) == 1 and items[0]["case_id"] == "c12" and items[0]["trajectory"].verdict is not None
    scores, summary = evaluate(items, out_dir=OUT_DIR, figures_dir=OUT_DIR / "figures")

    assert len(scores) == 1, f"{len(scores)} scored rows for one trajectory"
    row = scores.iloc[0]
    assert row.outcome in OUTCOMES and row.outcome == "verdict", f"the outcome is {row.outcome!r}"
    for column in ("rounds", "tool_calls", "tokens_in", "tokens_out", "tool_errors", "repeated_calls"):
        assert int(row[column]) >= 0, f"{column} is {row[column]!r}"
    for column in ("evidence_anchored", "new_log_cited", "remediation_ok", *CRITERIA):
        assert row[column] in (True, False), f"{column} is {row[column]!r}, not a pass or a fail"
    print("scored row: " + ", ".join(f"{c}={row[c]}" for c in ("outcome", "rounds", "tool_calls", "evidence_anchored", "new_log_cited", "remediation_ok")))

    judgements = pd.read_csv(OUT_DIR / "judgements.csv")
    assert len(judgements) == 1 and judgements.iloc[0].request_id == items[0]["request_id"]
    for criterion in CRITERIA:
        assert judgements.iloc[0][criterion] in (True, False), f"the judge's {criterion} is {judgements.iloc[0][criterion]!r}"
        assert isinstance(judgements.iloc[0][f"{criterion}_reasoning"], str) and judgements.iloc[0][f"{criterion}_reasoning"].strip(), f"no reasoning for {criterion}"
    assert isinstance(judgements.iloc[0].missing, str) and judgements.iloc[0].missing.strip()
    print("judge: " + ", ".join(f"{c}={'pass' if judgements.iloc[0][c] else 'fail'}" for c in CRITERIA))

    assert len(summary) == 1 and summary.iloc[0].n == 1 and summary.iloc[0].verdict == 1
    for column in ("evidence_anchored", "new_log_cited", "remediation_ok", *CRITERIA):
        assert summary.iloc[0][column] in ("0 of 1", "1 of 1"), f"summary {column} is {summary.iloc[0][column]!r}"
    written = pd.read_csv(OUT_DIR / "summary.csv")
    assert len(written) == 1 and set(CRITERIA) <= set(written.columns)

    for name in FIGURES:
        assert (OUT_DIR / "figures" / name).stat().st_size > 0, f"{name} was not drawn"
    print(f"summary and {len(FIGURES)} figures written under {OUT_DIR}")
    print("\nOK: one trajectory scored, judged, summarised and drawn")


if __name__ == "__main__":
    main()
