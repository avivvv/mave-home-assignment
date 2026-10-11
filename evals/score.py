"""The deterministic checks on a trajectory: what code can measure about an investigation without a model.

score(trajectory) gives one flat row: the outcome, how the tools were used, what the run cost, and checks on the
verdict's form. Whether the verdict is right is the judge's question, not this file's. summarise(rows) turns the rows
of many trajectories into one row per agent configuration, every share shown with its counts.
"""
import re
from datetime import datetime, timedelta

import pandas as pd

from agent.schema import LONE_NUMBER

OUTCOMES = ("verdict", "round_limit", "invalid_verdict", "no_tool_call", "model_error", "unfinished")
# the sources of this cluster, as a remediation step has to name one: nodes, domains, switches, ethernet switches,
# terminal servers, power supplies and file domains
SOURCE_NAME = re.compile(r"\b(node-D?\d+|Interconnect-\w+|gige\d*|tserver\d*|psu\d*|storage\d+|domain\w*)\b", re.I)
# what_followed may not reach into the event under investigation; the hour before the log is the event's window
HOUR = timedelta(hours=1)
# a pydantic error line names its kind as [type=...]; a verdict that is not JSON has no such line
ERROR_KIND = re.compile(r"\[type=(\w+)")


def _log_time(trajectory):
    """The time of the log under investigation, read from the starting context's 'time:' line."""
    match = re.search(r"^time: (.+)$", trajectory.request["context"], re.M)
    return datetime.fromisoformat(match.group(1))


def _call_key(event):
    """A tool call without its reasoning, so that two calls asking the same thing compare equal."""
    arguments = event["content"]["arguments"]
    if not isinstance(arguments, dict):
        return (event["name"], str(arguments))
    return (event["name"], tuple(sorted((key, str(value)) for key, value in arguments.items() if key != "reasoning")))


def _error_kinds(failures):
    kinds = []
    for _, reason, detail in failures:
        if reason != "invalid_verdict":
            continue
        found = ERROR_KIND.findall(detail) or ["invalid_json"]
        kinds.extend(kind for kind in found if kind not in kinds)
    return ";".join(kinds) or None


def _process(trajectory):
    results = trajectory.of_kind("tool_result")
    log_time = _log_time(trajectory)
    per_round = pd.Series([event["round"] for event in results]).value_counts()
    errors = [event for event in results if event["content"]["result"].startswith("error:")]
    recovered = 0
    for error in errors:
        later = [e for e in results if e["name"] == error["name"] and e["at"] > error["at"] and not e["content"]["result"].startswith("error:")]
        recovered += bool(later)
    keys = [_call_key(event) for event in results]
    into_present = 0
    for event in results:
        arguments = event["content"]["arguments"]
        if event["name"] == "what_followed" and isinstance(arguments, dict) and "end" in arguments:
            try:
                into_present += datetime.fromisoformat(arguments["end"]) > log_time - HOUR
            except ValueError:
                pass
    return {
        "single_call_rounds": int((per_round == 1).sum()),
        "tool_errors": len(errors),
        "tool_errors_recovered": recovered,
        "empty_results": sum(event["content"]["result"] == "no rows" for event in results),
        "truncated_results": sum("not shown" in event["content"]["result"] for event in results),
        "repeated_calls": len(keys) - len(set(keys)),
        "what_followed_into_present": into_present,
        "knowledge_calls": sum(event["name"] == "search_knowledge" for event in results),
    }


VERDICT_FIELDS = (
    "verdict", "severity", "confidence", "category", "scope", "n_evidence", "unanchored_evidence", "evidence_anchored", "new_log_cited",
    "n_remediation", "disruptive_without_check", "steps_without_source", "remediation_ok", "n_citations", "unknown_citations", "citations_ok",
)


def _verdict(trajectory):
    verdict = trajectory.verdict
    if verdict is None:
        return dict.fromkeys(VERDICT_FIELDS)
    log_id = trajectory.request["log_id"]
    cited = any(log_id in {int(n) for n in LONE_NUMBER.findall(item["line"])} for item in verdict["evidence"])
    steps = verdict["remediation"]
    first_disruptive = next((i for i, step in enumerate(steps) if step["risk"] == "disruptive"), None)
    disruptive_without_check = first_disruptive is not None and not any(step["risk"] == "safe" for step in steps[:first_disruptive])
    without_source = sum(not SOURCE_NAME.search(step["step"]) for step in steps)
    unanchored = len(trajectory.unanchored_evidence)
    # a citation names a knowledge passage; one that names a passage the agent never retrieved is unknown
    unknown = len(trajectory.unknown_citations)
    return {
        "verdict": verdict["verdict"], "severity": verdict["severity"], "confidence": verdict["confidence"],
        "category": verdict["category"], "scope": verdict["scope"],
        "n_evidence": len(verdict["evidence"]), "unanchored_evidence": unanchored, "evidence_anchored": unanchored == 0, "new_log_cited": cited,
        "n_remediation": len(steps), "disruptive_without_check": disruptive_without_check, "steps_without_source": without_source,
        "remediation_ok": not disruptive_without_check and without_source == 0,
        "n_citations": sum(bool(step.get("citation")) for step in steps), "unknown_citations": unknown, "citations_ok": unknown == 0,
    }


def score(trajectory):
    """Every deterministic check on one trajectory, as a flat dict. Verdict checks are None when there is no verdict."""
    totals = trajectory.totals
    max_rounds = trajectory.request["max_rounds"]
    verdicts = trajectory.of_kind("verdict")
    attempts = [event["round"] for event in [*trajectory.of_kind("failure"), *verdicts] if event["kind"] == "verdict" or event["name"] == "invalid_verdict"]
    return {
        "outcome": "verdict" if totals["status"] == "ok" else totals["status"],
        "rounds": totals["rounds"],
        "max_rounds": max_rounds,
        "ran_to_last_round": totals["rounds"] >= max_rounds,
        "verdict_round": verdicts[-1]["round"] if verdicts else None,
        "first_verdict_attempt_round": min(attempts) if attempts else None,
        "invalid_verdict_errors": _error_kinds(trajectory.failures),
        "llm_calls": totals["llm_calls"],
        "tool_calls": totals["tool_calls"],
        # whether the run had the knowledge tool; a run made before the tool existed recorded nothing, and had not
        "knowledge": bool(trajectory.request.get("knowledge", False)),
        **_process(trajectory),
        "tokens_in": totals["tokens_in"],
        "tokens_out": totals["tokens_out"],
        "llm_seconds": totals["llm_seconds"],
        **_verdict(trajectory),
    }


def _is_bool_column(series):
    values = series.dropna()
    return len(values) > 0 and values.map(lambda v: isinstance(v, bool)).all()


def summarise(rows):
    """One row per config: outcome counts, cost, and every True/False check as 'k of n' over the runs it applies to."""
    rows = pd.DataFrame(rows)
    summary = []
    for config, group in rows.groupby("config", sort=True):
        verdicts = int((group.outcome == "verdict").sum())
        tokens = group.tokens_in + group.tokens_out
        row = {"config": config, "n": len(group)}
        row.update({outcome: int((group.outcome == outcome).sum()) for outcome in OUTCOMES})
        row.update({
            "median_rounds": group.rounds.median(), "median_tool_calls": group.tool_calls.median(),
            "tool_errors": int(group.tool_errors.sum()), "repeated_calls": int(group.repeated_calls.sum()),
            "median_tokens": tokens.median(), "tokens_per_verdict": int(tokens.sum() / verdicts) if verdicts else None,
            "median_llm_seconds": group.llm_seconds.median(),
            "knowledge_calls": int(group.knowledge_calls.sum()),
            "cited_steps": f"{int(group.n_citations.dropna().sum())} of {int(group.n_remediation.dropna().sum())}",
        })
        for column in rows.columns:
            if column not in row and _is_bool_column(rows[column]):
                values = group[column].dropna()
                row[column] = f"{int(values.sum())} of {len(values)}"
        summary.append(row)
    return pd.DataFrame(summary).set_index("config")
