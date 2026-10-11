"""What goes into the models and what comes out: the starting context, the prompts, the verdict, the judge."""
import json
import re

import pytest
from pydantic import ValidationError

from agent.context import CONTEXT_ROWS, MAX_ROUNDS, load_prompt, round_notice, starting_context
from agent.judge import judge, parse_json
from agent.schema import BENIGN_CATEGORIES, CRITERIA, PROBLEM_CATEGORIES, SUBMIT_VERDICT, Judgement, Verdict, unanchored_evidence
from agent.tools import RUNNERS, LogTools, tool_purposes
from tests.test_llm import completion, make
from tests.test_queries import _utc, make_log, populated  # noqa: F401

JUDGE_CONFIG = {"base_url": "http://test", "requests_per_minute": 30, "max_retries": 0, "timeout_seconds": 5, "models": {"judge": "fake-judge"}}
BENIGN = {
    "reasoning": "The reading is inside the normal range.",
    "verdict": "benign", "severity": "none", "category": "telemetry", "scope": "single_source",
    "summary": "A routine reading.", "root_cause": "The node reports its temperature.",
    "evidence": [{"line": "2004-11-09 10:15:00 node-1 node status ambient=31", "why": "the reading"}], "remediation": [], "confidence": "high",
}
STEP = {"step": "Boot node-1 from its console", "reason": "it stopped responding", "risk": "disruptive"}
ACTIONABLE = {**BENIGN, "verdict": "actionable", "severity": "high", "category": "node_state", "remediation": [STEP]}
GRADES = {
    **{criterion: {"reasoning": "It did the thing.", "result": "pass"} for criterion in CRITERIA},
    "missing": "nothing",
}


class TestVerdict:
    def test_a_benign_and_an_actionable_verdict_are_accepted(self):
        assert Verdict.model_validate(BENIGN).severity == "none"
        assert Verdict.model_validate(ACTIONABLE).remediation[0].citation == ""

    @pytest.mark.parametrize("change", [{"severity": "none"}, {"remediation": []}])
    def test_an_actionable_verdict_needs_a_severity_and_a_step(self, change):
        with pytest.raises(ValidationError, match="needs a severity other than none and at least one remediation step"):
            Verdict.model_validate({**ACTIONABLE, **change})

    @pytest.mark.parametrize("verdict", ["benign", "insufficient_evidence"])
    def test_only_an_actionable_verdict_has_a_severity(self, verdict):
        with pytest.raises(ValidationError, match="has severity none"):
            Verdict.model_validate({**BENIGN, "verdict": verdict, "severity": "high"})

    @pytest.mark.parametrize("change", [{"reasoning": ""}, {"reasoning": "   "}, {"evidence": []}, {"evidence": [{"line": " ", "why": "x"}]}, {"summary": ""}])
    def test_reasoning_evidence_and_summary_cannot_be_empty(self, change):
        with pytest.raises(ValidationError):
            Verdict.model_validate({**BENIGN, **change})

    def test_a_field_left_out_is_refused(self):
        for field in ("reasoning", "evidence", "severity", "scope"):
            with pytest.raises(ValidationError, match=field):
                Verdict.model_validate({key: value for key, value in BENIGN.items() if key != field})

    def test_evidence_is_any_line_of_text(self):
        lines = [{"line": "2004-11-08 11:33:20 2004-11-08 11:33:20 1 node status not responding", "why": "a timeline entry"}, {"line": "log 106433", "why": "by id"}]
        assert len(Verdict.model_validate({**BENIGN, "evidence": lines}).evidence) == 2

    @pytest.mark.parametrize("change", [{"verdict": "fine"}, {"category": "weather"}, {"scope": "galaxy"}, {"confidence": "total"}, {"severity": None}, {"mood": "calm"}])
    def test_an_unknown_value_or_field_is_refused(self, change):
        with pytest.raises(ValidationError):
            Verdict.model_validate({**BENIGN, **change})

    def test_the_tool_schema_is_self_contained_and_starts_with_the_reasoning(self):
        parameters = SUBMIT_VERDICT["function"]["parameters"]
        assert "$ref" not in json.dumps(parameters) and "$defs" not in parameters
        assert list(parameters["properties"])[0] == "reasoning"
        assert parameters["properties"]["evidence"]["items"]["required"] == ["line", "why"]
        assert set(parameters["required"]) == set(Verdict.model_fields)


class TestEvidenceCheck:
    def lines(self, *lines):
        return Verdict.model_validate({**BENIGN, "evidence": [{"line": line, "why": "because"} for line in lines]})

    @pytest.mark.parametrize("line", [
        "106433 2004-07-15 12:17:53 node-221 node status not responding 85",
        "log 106433: node-221 not responding",
        "85 2004-07-15 12:15:16 2004-07-15 12:17:53 203 node status not responding",
        "shape 85 (not responding) on 203 sources",
        "id=106433, not responding",
    ])
    def test_a_line_that_names_a_shown_log_id_or_shape_id_is_anchored(self, line):
        assert unanchored_evidence(self.lines(line), log_ids={106433}, log_shape_ids={85}) == []

    @pytest.mark.parametrize("line", [
        "node-221 stopped responding",
        "999999 2004-07-15 12:17:53 node-221 node status not responding",
        # a number inside a time, a date, a source name or a decimal is not an id
        "2004-07-15 12:17:85 node-85 not responding, load 0.85, ip 10.0.0.85",
        "node85 said 106433x",
    ])
    def test_a_line_with_no_shown_id_is_reported(self, line):
        assert unanchored_evidence(self.lines(line), log_ids={106433}, log_shape_ids={85}) == [line]

    def test_each_line_is_checked_on_its_own(self):
        verdict = self.lines("106433 not responding", "an operator rebooted it", "shape 85 again")
        assert unanchored_evidence(verdict, log_ids=[106433], log_shape_ids=[85]) == ["an operator rebooted it"]
        assert len(unanchored_evidence(verdict, log_ids=[], log_shape_ids=[])) == 3


class TestStartingContext:
    def new_log(self, conn, populated, seconds):
        tools = LogTools(conn)
        moment = _utc(populated["base"] + seconds)
        log = next(found for found in tools.logs.search(moment, moment))
        tools.visible = log.ts
        return tools, log

    def test_it_has_the_log_the_timeline_and_the_shape_over_the_cluster(self, conn, populated):
        # node-1 logs 'ambient=31' at 10:15, after three 'running'; node-2 logged the same shape at 10:02
        tools, log = self.new_log(conn, populated, 900)
        context = starting_context(tools, log).text
        assert f"log id: {log.id}" in context and "message: ambient=31" in context
        assert f"log shape {populated['ambient']}: node | status | ambient=<N>" in context
        assert "TIMELINE OF node-1" in context and "running" in context
        assert "n_logs=2, n_sources=2" in context and "The newest 2 of these logs, oldest first:" in context

    def test_it_returns_the_ids_it_shows(self, conn, populated):
        tools, log = self.new_log(conn, populated, 900)
        context = starting_context(tools, log)
        # the new log and node-2's log of the same shape; the two shapes on node-1's timeline
        assert log.id in context.log_ids and len(context.log_ids) == 2
        assert set(context.log_shape_ids) == {populated["ambient"], populated["running"]}
        assert all(str(log_id) in context.text for log_id in context.log_ids) and "log_shape_id" in context.text

    def test_it_shows_nothing_later_than_the_log(self, conn, populated):
        tools, log = self.new_log(conn, populated, 900)
        # 'not responding' at 10:20 and node-2's 'ambient=33' at 14:00 come after the log
        context = starting_context(tools, log).text
        assert "not responding" not in context and "ambient=33" not in context

    def test_it_reaches_back_one_hour_and_no_further(self, conn, populated):
        # node-1 'running' at 12:00; its earlier lines are from 10:00 to 10:15
        tools, log = self.new_log(conn, populated, 7200)
        context = starting_context(tools, log).text
        assert "ambient" not in context and "n_logs=1, n_sources=1" in context

    def test_a_burst_is_cut_and_the_context_says_what_it_left_out(self, conn, logs, populated):
        # the same shape from 30 other sources in the minutes before the log: more than the context shows
        base = populated["base"]
        logs.add_many([make_log(base + 6600 + i, f"node-{100 + i}", "node", "status", "running", populated["running"]) for i in range(30)])
        tools, log = self.new_log(conn, populated, 7200)
        context = starting_context(tools, log).text
        assert "n_logs=31, n_sources=31" in context
        assert f"The newest {CONTEXT_ROWS} of these logs, oldest first ({31 - CONTEXT_ROWS} older ones are not shown):" in context
        assert f"{31 - CONTEXT_ROWS} more rows not shown" in context


class TestPrompts:
    def test_the_investigator_prompt_names_every_field_and_value_of_the_verdict(self):
        prompt = load_prompt("investigator_v1")
        values = [*PROBLEM_CATEGORIES, *BENIGN_CATEGORIES, "actionable", "benign", "insufficient_evidence", "none", "low", "medium", "high", "critical",
                  "single_source", "several_sources", "cluster_wide", "safe", "disruptive", "submit_verdict", "line", "why", "reason", "id", "log_shape_id"]
        assert [value for value in values if f"`{value}`" not in prompt] == []
        assert [field for field in Verdict.model_fields if f"`{field}`" not in prompt] == []

    def test_every_tool_the_investigator_prompt_names_exists(self):
        prompt = load_prompt("investigator_v1")
        named = {name for name in RUNNERS if f"`{name}`" in prompt}
        assert named == set(RUNNERS)
        # and it names no tool that is not there
        assert not re.findall(r"`(get_stats|preceded_by|gige_levels|minutes_at_level)`", prompt)

    def test_the_investigator_prompt_states_the_working_rules(self):
        prompt = load_prompt("investigator_v1")
        for rule in ("run in parallel", "`reasoning`", "smallest time range", "at most 50 rows", "at most 31 days", f"at most {MAX_ROUNDS} rounds", f"`Round 3 of {MAX_ROUNDS}`", "In the last round you must call `submit_verdict`"):
            assert rule in prompt, rule

    def test_the_round_notice_says_which_round_it_is_and_when_it_is_the_last(self):
        assert round_notice(1) == f"Round 1 of {MAX_ROUNDS}."
        assert round_notice(MAX_ROUNDS) == f"Round {MAX_ROUNDS} of {MAX_ROUNDS}. This is the last round."
        assert round_notice(3, max_rounds=3).endswith("This is the last round.")

    def test_the_judge_prompt_names_every_key_of_its_answer_and_no_expected_answer(self):
        prompt = load_prompt("judge_v1")
        assert [key for key in Judgement.model_fields if f"`{key}`" not in prompt] == []
        assert "no correct answer" in prompt and "expected answer" not in prompt.lower()
        # the example in the prompt is itself a valid answer
        example = prompt[prompt.index("```") + 3:prompt.rindex("```")]
        Judgement.model_validate(json.loads(example))


class TestJudge:
    @pytest.mark.parametrize("text, expected", [
        ('{"a": 1}', {"a": 1}),
        ('Here it is:\n```json\n{"a": {"b": 1}}\n```\nDone.', {"a": {"b": 1}}),
        ('{"a": "a brace } inside { a string"}', {"a": "a brace } inside { a string"}),
    ])
    def test_parse_json_reads_the_object_whatever_surrounds_it(self, text, expected):
        assert parse_json(text) == expected

    @pytest.mark.parametrize("text", ["I would say pass.", "", "} {", '{"a": 1} and {"b": 2}', '{"a": '])
    def test_parse_json_refuses_a_reply_with_no_single_object(self, text):
        with pytest.raises(ValueError):
            parse_json(text)

    def test_the_judge_sees_the_trajectory_and_nothing_else(self, tmp_path):
        llm, client, _ = make(tmp_path, completion(json.dumps(GRADES)), config=JUDGE_CONFIG)
        judgement, replies = judge(llm, "the trajectory")
        assert isinstance(judgement, Judgement) and judgement.grounded.result == "pass" and len(replies) == 1
        system, user = client.requests[0]["messages"]
        assert system == {"role": "system", "content": load_prompt("judge_v1")}
        # the user message is the list of tools with their purposes, then the trajectory
        assert user["content"] == f"# THE AGENT'S TOOLS\n{tool_purposes()}\n\n# THE TRAJECTORY\nthe trajectory"
        assert all(f"- {name}: " in user["content"] for name in RUNNERS)
        assert "tools" not in client.requests[0]

    @pytest.mark.parametrize("bad", [
        {**GRADES, "grounded": {"reasoning": "Hm.", "result": "maybe"}},
        {**GRADES, "grounded": {"reasoning": "Hm.", "result": "PASS"}},
        {**GRADES, "grounded": {"result": "pass"}},
        {**GRADES, "tool_use": "pass"},
        {**GRADES, "overall": "fine"},
        {key: value for key, value in GRADES.items() if key != "tool_use"},
        {key: value for key, value in GRADES.items() if key != "missing"},
        {**GRADES, "missing": ""},
    ])
    def test_an_invalid_answer_is_sent_back_once_with_the_error(self, tmp_path, bad):
        llm, client, _ = make(tmp_path, completion(json.dumps(bad)), completion(json.dumps(GRADES)), config=JUDGE_CONFIG)
        judgement, replies = judge(llm, "the trajectory")
        assert judgement.grounded.result == "pass" and len(replies) == 2
        assert "Your answer was not valid" in client.requests[1]["messages"][-1]["content"]

    def test_two_invalid_answers_are_an_error(self, tmp_path):
        llm, _, _ = make(tmp_path, completion("pass"), completion("still pass"), config=JUDGE_CONFIG)
        with pytest.raises(ValueError, match="no valid answer in 2 attempts"):
            judge(llm, "the trajectory")

    def test_with_no_retries_one_invalid_answer_is_an_error(self, tmp_path):
        llm, client, _ = make(tmp_path, completion("pass"), completion(json.dumps(GRADES)), config=JUDGE_CONFIG)
        with pytest.raises(ValueError, match="no valid answer in 1 attempts"):
            judge(llm, "the trajectory", retries=0)
        assert len(client.requests) == 1

    def test_an_answer_with_no_content_is_invalid_and_does_not_crash(self, tmp_path):
        llm, _, _ = make(tmp_path, completion(None), config=JUDGE_CONFIG)
        with pytest.raises(ValueError, match="no JSON object"):
            judge(llm, "the trajectory", retries=0)
