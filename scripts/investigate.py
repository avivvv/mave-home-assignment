"""Investigate one log with the agent and print its trajectory.

    python -m scripts.investigate --case c12          a golden case of labeling/golden_cases.yaml
    python -m scripts.investigate --line "<raw line>"  any log, by its line in HPC.log
    python -m scripts.investigate --case c12 --judge   also grade the trajectory with the judge
    python -m scripts.investigate --case c12 --fresh   ask the models again instead of reading the cache
    python -m scripts.investigate --case c12 --kb      give the agent the knowledge tool, whatever config/models.yaml says

Every event of the investigation is written to runs/agent.db under the request id that is printed.
The judge's grades are printed only: they belong to offline evaluation, not to the agent's log.
"""
import argparse
import sys
import time

import yaml

from agent.judge import judge
from agent.knowledge import from_config
from agent.llm import LLM, ROOT, load_config
from agent.loop import investigate
from agent.schema import CRITERIA
from agent.tools import LogTools
from agent.trajectory import EventLog, Trajectory
from logstore.db import connect

GOLDEN_PATH = ROOT / "labeling" / "golden_cases.yaml"


def golden_case(case_id):
    cases = {case["id"]: case for case in yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))}
    if case_id not in cases:
        raise SystemExit(f"no golden case {case_id!r}. The cases are: {', '.join(cases)}")
    return cases[case_id]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--case", help="the id of a golden case, for example c12")
    which.add_argument("--line", help="the raw line of the log to investigate")
    parser.add_argument("--judge", action="store_true", help="grade the trajectory with the judge and print the grades")
    parser.add_argument("--fresh", action="store_true", help="ask the models again instead of reading the cache")
    parser.add_argument("--kb", action="store_true", help="give the agent the knowledge tool, whatever config/models.yaml says")
    args = parser.parse_args()
    # a model may write a character the Windows console cannot show
    sys.stdout.reconfigure(errors="replace")

    config = load_config()
    if args.kb:
        config["knowledge"] = True
    case = golden_case(args.case) if args.case else None
    line = case["log_line"] if case else args.line
    tools = LogTools(connect(), knowledge=from_config(config))
    found = tools.logs.find_by_line(line)
    if len(found) != 1:
        raise SystemExit(f"{len(found)} logs have the line {line!r}")
    log = found[0]
    # the agent sees nothing later than the log it investigates
    tools.visible = log.ts

    llm = LLM(config=config)
    cache_tag = f"fresh-{time.time()}" if args.fresh else ""
    request_id = investigate(log, tools, llm, EventLog(), cache_tag=cache_tag)
    trajectory = Trajectory(request_id)
    print(trajectory.text())
    print(f"\n## REQUEST {request_id}")
    for name, value in trajectory.totals.items():
        print(f"{name}: {value}")
    if trajectory.unanchored_evidence:
        print(f"evidence lines that name no id the agent was shown: {trajectory.unanchored_evidence}")
    if trajectory.unknown_citations:
        print(f"citations that name no passage the agent retrieved: {trajectory.unknown_citations}")

    if args.judge:
        judgement, _ = judge(llm, trajectory.text(), cache_tag=cache_tag, tools=trajectory.request["tools"])
        print("\n## THE JUDGE")
        for criterion in CRITERIA:
            grade = getattr(judgement, criterion)
            print(f"{criterion}: {grade.result}. {grade.reasoning}")
        print(f"missing: {judgement.missing}")


if __name__ == "__main__":
    main()
