"""The deterministic checks of evals/score.py, on scripted trajectories whose correct scores are obvious."""
import json

import pandas as pd

from evals.score import score, summarise
from tests.test_loop import END, KNOWLEDGE, PASSAGE, SEARCH, START, TIMELINE, WHY, calls, run, verdict  # noqa: F401
from tests.test_queries import populated  # noqa: F401

BAD_ARGUMENT = ("search_logs", json.dumps({"reasoning": WHY, "start": START, "end": END, "colour": "red"}))
# the log under investigation is id 4, node-1's ambient=31 of 10:15; id 6 is node-2's ambient=29 of 10:02, shown in the starting context
NEW_LOG = {"line": "4 2004-11-09 10:15:00 node-1 node status ambient=31", "why": "the reading"}
OTHER_SHOWN = {"line": "6 2004-11-09 10:02:00 node-2 node status ambient=29", "why": "another reading"}
INVENTED = {"line": "an operator rebooted node-1 at 09:00", "why": "made up"}


def search(**arguments):
    return ("search_logs", json.dumps({"reasoning": WHY, "start": START, "end": END, **arguments}))


def what_followed(shape_id, end):
    return ("what_followed", json.dumps({"reasoning": WHY, "log_shape_id": shape_id, "start": START, "end": end}))


class TestOutcome:
    def test_a_verdict_on_the_first_round(self, run):
        trajectory, _ = run(calls(verdict()))
        s = score(trajectory)
        assert s["outcome"] == "verdict" and s["rounds"] == 1 and s["max_rounds"] == 4
        assert s["verdict_round"] == 1 and s["first_verdict_attempt_round"] == 1 and s["ran_to_last_round"] is False

    def test_the_round_limit(self, run):
        trajectory, _ = run(calls(SEARCH), calls(TIMELINE), max_rounds_=2)
        s = score(trajectory)
        assert s["outcome"] == "round_limit" and s["ran_to_last_round"] is True
        assert s["verdict_round"] is None and s["first_verdict_attempt_round"] is None and s["verdict"] is None

    def test_an_invalid_verdict_names_its_error_kinds_in_order(self, run):
        trajectory, _ = run(calls(SEARCH), calls(verdict(evidence=[])), calls(verdict(category="weather")), calls(verdict()))
        s = score(trajectory)
        assert s["outcome"] == "invalid_verdict" and s["first_verdict_attempt_round"] == 2
        assert s["invalid_verdict_errors"] == "too_short;literal_error"

    def test_a_verdict_that_is_not_json(self, run):
        trajectory, _ = run(calls(("submit_verdict", "{not json")), calls(verdict()))
        s = score(trajectory)
        assert s["outcome"] == "verdict" and s["invalid_verdict_errors"] == "invalid_json" and s["verdict_round"] == 2


class TestProcess:
    def test_calls_rounds_and_repeats(self, run):
        trajectory, _ = run(calls(SEARCH, TIMELINE), calls(SEARCH), calls(verdict()))
        s = score(trajectory)
        assert s["tool_calls"] == 3 and s["llm_calls"] == 3 and s["single_call_rounds"] == 1 and s["repeated_calls"] == 1

    def test_a_tool_error_that_is_followed_by_a_good_call_of_the_same_tool(self, run):
        trajectory, _ = run(calls(BAD_ARGUMENT), calls(SEARCH), calls(verdict()))
        s = score(trajectory)
        assert s["tool_errors"] == 1 and s["tool_errors_recovered"] == 1

    def test_a_tool_error_that_is_left_alone(self, run):
        trajectory, _ = run(calls(BAD_ARGUMENT), calls(verdict()))
        s = score(trajectory)
        assert s["tool_errors"] == 1 and s["tool_errors_recovered"] == 0

    def test_empty_and_cut_results(self, run):
        # node-9 logged nothing; node-1 has four logs in the day, so a limit of one cuts three
        trajectory, _ = run(calls(search(node="node-9"), search(node="node-1", limit=1)), calls(verdict()))
        s = score(trajectory)
        assert s["empty_results"] == 1 and s["truncated_results"] == 1

    def test_what_followed_that_reaches_into_the_hour_before_the_log(self, run, populated):
        early, late = what_followed(populated["ambient"], "2004-11-09 09:00:00"), what_followed(populated["ambient"], "2004-11-09 10:00:00")
        trajectory, _ = run(calls(early, late), calls(verdict()))
        assert score(trajectory)["what_followed_into_present"] == 1

    def test_tokens_and_seconds_are_the_totals(self, run):
        trajectory, _ = run(calls(SEARCH), calls(verdict()))
        s = score(trajectory)
        assert (s["tokens_in"], s["tokens_out"]) == (22, 14) and s["llm_seconds"] >= 0


class TestVerdict:
    def test_the_fields_of_the_verdict_are_copied(self, run):
        trajectory, _ = run(calls(verdict()))
        s = score(trajectory)
        assert (s["verdict"], s["severity"], s["confidence"], s["category"], s["scope"]) == ("benign", "none", "high", "telemetry", "single_source")
        assert s["n_evidence"] == 1 and s["n_remediation"] == 0

    def test_evidence_that_is_anchored_and_cites_the_new_log(self, run):
        trajectory, _ = run(calls(verdict()))
        s = score(trajectory)
        assert s["unanchored_evidence"] == 0 and s["evidence_anchored"] is True and s["new_log_cited"] is True

    def test_evidence_that_is_shown_but_leaves_the_new_log_out(self, run):
        trajectory, _ = run(calls(verdict(evidence=[OTHER_SHOWN])))
        s = score(trajectory)
        assert s["evidence_anchored"] is True and s["new_log_cited"] is False

    def test_invented_evidence(self, run):
        trajectory, _ = run(calls(verdict(evidence=[NEW_LOG, INVENTED])))
        s = score(trajectory)
        assert s["unanchored_evidence"] == 1 and s["evidence_anchored"] is False and s["new_log_cited"] is True

    def test_a_disruptive_step_with_no_check_before_it_and_a_generic_step(self, run):
        steps = [
            {"step": "Reboot node-1", "reason": "it stopped responding", "risk": "disruptive"},
            {"step": "Monitor the system", "reason": "to be safe", "risk": "safe"},
        ]
        trajectory, _ = run(calls(verdict(verdict="actionable", severity="low", remediation=steps)))
        s = score(trajectory)
        assert s["n_remediation"] == 2 and s["disruptive_without_check"] is True and s["steps_without_source"] == 1
        assert s["remediation_ok"] is False

    def test_a_check_before_the_disruptive_step(self, run):
        steps = [
            {"step": "Read the console of node-1", "reason": "to see why it stopped", "risk": "safe"},
            {"step": "Reboot node-1", "reason": "it stopped responding", "risk": "disruptive"},
        ]
        trajectory, _ = run(calls(verdict(verdict="actionable", severity="low", remediation=steps)))
        s = score(trajectory)
        assert s["disruptive_without_check"] is False and s["steps_without_source"] == 0 and s["remediation_ok"] is True

    def test_no_verdict_means_no_verdict_fields(self, run):
        trajectory, _ = run(calls(SEARCH), calls(TIMELINE), max_rounds_=2)
        s = score(trajectory)
        assert s["evidence_anchored"] is None and s["new_log_cited"] is None and s["remediation_ok"] is None and s["n_remediation"] is None


def cited(citation):
    step = {"step": "Check node-20, which serves storage612", "reason": "the fact sheet names it", "risk": "safe", "citation": citation}
    plain = {"step": "Read the console of node-1", "reason": "to see", "risk": "safe"}
    return verdict(verdict="actionable", severity="low", category="filesystem", remediation=[step, plain])


class TestKnowledge:
    def test_a_search_and_a_citation_of_what_it_returned(self, run):
        trajectory, _ = run(calls(KNOWLEDGE), calls(cited(PASSAGE)), knowledge=True)
        s = score(trajectory)
        assert s["knowledge_calls"] == 1 and s["n_remediation"] == 2 and s["n_citations"] == 1
        assert s["unknown_citations"] == 0 and s["citations_ok"] is True

    def test_a_citation_of_a_passage_that_was_not_retrieved(self, run):
        trajectory, _ = run(calls(KNOWLEDGE), calls(cited("facts#made-up")), knowledge=True)
        s = score(trajectory)
        assert s["n_citations"] == 1 and s["unknown_citations"] == 1 and s["citations_ok"] is False

    def test_a_run_without_knowledge_has_no_searches_and_its_empty_citations_are_fine(self, run):
        s = score(run(calls(SEARCH), calls(verdict()))[0])
        assert s["knowledge_calls"] == 0 and s["n_citations"] == 0 and s["unknown_citations"] == 0 and s["citations_ok"] is True

    def test_the_score_says_whether_the_run_had_the_tool(self, run):
        assert score(run(calls(verdict()))[0])["knowledge"] is False
        assert score(run(calls(verdict()), knowledge=True)[0])["knowledge"] is True

    def test_no_verdict_means_no_citation_fields_but_the_searches_are_still_counted(self, run):
        trajectory, _ = run(calls(KNOWLEDGE), calls(TIMELINE), max_rounds_=2, knowledge=True)
        s = score(trajectory)
        assert s["knowledge_calls"] == 1 and s["n_citations"] is None and s["citations_ok"] is None


class TestSummary:
    def test_counts_shares_with_their_counts_and_tokens_per_verdict(self, run):
        good, _ = run(calls(verdict()))
        failed, _ = run(calls(SEARCH), calls(TIMELINE), max_rounds_=2)
        # a different round limit, so that the cached reply of the first run is not served to this one
        invented, _ = run(calls(verdict(evidence=[INVENTED])), max_rounds_=3)
        rows = [{"config": "a", **score(good)}, {"config": "a", **score(failed)}, {"config": "b", **score(invented)}]
        summary = summarise(pd.DataFrame(rows))
        assert list(summary.index) == ["a", "b"]
        assert summary.loc["a", "n"] == 2 and summary.loc["a", "verdict"] == 1 and summary.loc["a", "round_limit"] == 1
        assert summary.loc["a", "evidence_anchored"] == "1 of 1" and summary.loc["b", "evidence_anchored"] == "0 of 1"
        # a's runs cost 18 and 36 tokens for one verdict; b's cost 18 for one
        assert summary.loc["a", "tokens_per_verdict"] == 54 and summary.loc["b", "tokens_per_verdict"] == 18

    def test_knowledge_searches_and_citations_per_configuration(self, run):
        with_kb, _ = run(calls(KNOWLEDGE), calls(cited(PASSAGE)), knowledge=True)
        without, _ = run(calls(verdict()))
        summary = summarise(pd.DataFrame([{"config": "kb", **score(with_kb)}, {"config": "plain", **score(without)}]))
        assert summary.loc["kb", "knowledge_calls"] == 1 and summary.loc["plain", "knowledge_calls"] == 0
        assert summary.loc["kb", "cited_steps"] == "1 of 2" and summary.loc["plain", "cited_steps"] == "0 of 0"
        assert summary.loc["kb", "citations_ok"] == "1 of 1"
