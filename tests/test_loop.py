"""The investigation loop against a scripted model, and the trajectory read back from the event log."""
import json

import httpx2
import pytest
from openai import APITimeoutError

from agent.context import load_prompt
from agent.loop import NO_TOOL_CALL, NOT_ALONE, investigate
from agent.tools import LogTools
from agent.trajectory import EventLog, Trajectory
from tests.test_llm import completion, make
from tests.test_queries import DAY, _utc, populated  # noqa: F401

CONFIG = {"base_url": "http://test", "requests_per_minute": 6000, "max_retries": 0, "timeout_seconds": 5, "models": {"main": "fake-model"}}
START, END = (d.isoformat(sep=" ") for d in DAY)
WHY = "To see what the node logged."
SEARCH = ("search_logs", json.dumps({"reasoning": WHY, "start": START, "end": END, "node": "node-1"}))
TIMELINE = ("node_timeline", json.dumps({"reasoning": WHY, "node": "node-1", "start": START, "end": END}))
STEP = {"step": "Boot node-1 from its console", "reason": "it stopped responding", "risk": "disruptive"}


def verdict(**changes):
    answer = {
        "reasoning": "The reading is inside the normal range.", "verdict": "benign", "severity": "none", "category": "telemetry",
        "scope": "single_source", "summary": "A routine reading.", "root_cause": "The node reports its temperature.",
        "evidence": [{"line": "4 2004-11-09 10:15:00 node-1 node status ambient=31", "why": "the reading"}], "remediation": [], "confidence": "high",
    }
    return ("submit_verdict", json.dumps({**answer, **changes}))


def calls(*tool_calls):
    return completion(tool_calls=list(tool_calls))


@pytest.fixture
def run(conn, populated, tmp_path):
    """Investigate node-1's 'ambient=31' of 10:15 with a model that gives the scripted answers. Returns the trajectory and the fake client."""
    def run(*answers, max_rounds_=4):
        tools = LogTools(conn)
        moment = _utc(populated["base"] + 900)
        log = next(found for found in tools.logs.search(moment, moment))
        tools.visible = log.ts
        llm, client, _ = make(tmp_path, *answers, config=CONFIG)
        events = EventLog(":memory:")
        request_id = investigate(log, tools, llm, events, max_rounds_=max_rounds_)
        return Trajectory(request_id, events.conn), client
    return run


def kinds(trajectory):
    return [(event["kind"], event["round"], event["name"]) for event in trajectory.events]


def sent(client, call_number):
    """The messages of the nth call to the model, as (role, content) pairs."""
    return [(message["role"], message.get("content")) for message in client.requests[call_number]["messages"]]


class TestLoop:
    def test_a_verdict_on_the_first_round_ends_the_investigation(self, run):
        trajectory, client = run(calls(verdict()))
        assert kinds(trajectory) == [("request", None, None), ("llm_response", 1, None), ("verdict", 1, None)]
        assert trajectory.status == "ok" and trajectory.verdict["verdict"] == "benign" and len(client.requests) == 1

    def test_the_first_message_is_the_prompt_then_the_context_with_the_round(self, run):
        trajectory, client = run(calls(verdict()))
        (system_role, system), (user_role, user) = sent(client, 0)
        assert (system_role, user_role) == ("system", "user") and system == load_prompt("investigator_v1")
        assert user == f"{trajectory.request['context']}\n\nRound 1 of 4."
        assert [tool["function"]["name"] for tool in client.requests[0]["tools"]][-1] == "submit_verdict"

    def test_tool_calls_are_run_logged_and_sent_back_with_the_next_round(self, run):
        trajectory, client = run(calls(SEARCH), calls(verdict()))
        assert kinds(trajectory) == [
            ("request", None, None), ("llm_response", 1, None), ("tool_result", 1, "search_logs"), ("llm_response", 2, None), ("verdict", 2, None),
        ]
        result = trajectory.of_kind("tool_result")[0]["content"]
        assert result["arguments"]["node"] == "node-1" and "ambient=31" in result["result"] and len(result["log_ids"]) == 4
        roles = sent(client, 1)
        assert [role for role, _ in roles] == ["system", "user", "assistant", "tool", "user"]
        assert roles[3][1] == result["result"] and roles[4][1] == "Round 2 of 4."

    def test_several_calls_of_one_reply_are_all_run_in_the_same_round(self, run):
        trajectory, client = run(calls(SEARCH, TIMELINE), calls(verdict()))
        assert kinds(trajectory)[2:4] == [("tool_result", 1, "search_logs"), ("tool_result", 1, "node_timeline")]
        assert [role for role, _ in sent(client, 1)] == ["system", "user", "assistant", "tool", "tool", "user"]
        assert trajectory.totals["tool_calls"] == 2 and trajectory.totals["rounds"] == 2

    def test_the_agent_sees_nothing_later_than_its_log(self, run):
        trajectory, _ = run(calls(("search_logs", json.dumps({"reasoning": WHY, "start": START, "end": END}))), calls(verdict()))
        # 'not responding' is logged five minutes after the log under investigation
        assert "not responding" not in trajectory.text()

    @pytest.mark.parametrize("bad_call, message", [
        (("search_logs", '{"reasoning": "x", "start": '), "the arguments are not valid JSON"),
        (("delete_logs", "{}"), "unknown tool"),
        (("search_logs", json.dumps({"start": START, "end": END})), "has no `reasoning`"),
        (("search_logs", json.dumps({"reasoning": WHY, "start": START, "end": END, "colour": "red"})), "has no argument colour"),
    ])
    def test_a_bad_tool_call_gets_its_error_back_and_the_investigation_goes_on(self, run, bad_call, message):
        trajectory, client = run(calls(bad_call), calls(verdict()))
        result = trajectory.of_kind("tool_result")[0]["content"]
        assert result["result"].startswith("error:") and message in result["result"] and result["log_ids"] == []
        assert sent(client, 1)[3] == ("tool", result["result"]) and trajectory.status == "ok"

    def test_a_reply_with_no_tool_call_is_a_failure_and_gets_a_reminder(self, run):
        trajectory, client = run(completion("I think it is fine."), calls(verdict()))
        assert trajectory.failures == [(1, "no_tool_call", "I think it is fine.")]
        assert sent(client, 1)[-1] == ("user", f"{NO_TOOL_CALL}\n\nRound 2 of 4.")
        assert trajectory.status == "ok" and trajectory.totals["rounds"] == 2

    def test_an_invalid_verdict_gets_its_errors_back_once(self, run):
        trajectory, client = run(calls(verdict(severity="high")), calls(verdict()))
        assert [(r, reason) for r, reason, _ in trajectory.failures] == [(1, "invalid_verdict")]
        assert "has severity none" in trajectory.failures[0][2]
        role, answer = sent(client, 1)[3]
        assert role == "tool" and answer.startswith("error: the verdict is not valid") and "has severity none" in answer
        assert trajectory.status == "ok" and kinds(trajectory)[-1] == ("verdict", 2, None)

    @pytest.mark.parametrize("first", [verdict(evidence=[]), verdict(reasoning=""), ("submit_verdict", '{"verdict": '), ("submit_verdict", "[]")])
    def test_a_second_invalid_verdict_ends_the_investigation_as_failed(self, run, first):
        trajectory, client = run(calls(first), calls(verdict(category="weather")), calls(verdict()))
        assert [reason for _, reason, _ in trajectory.failures] == ["invalid_verdict", "invalid_verdict"]
        assert trajectory.status == "invalid_verdict" and trajectory.verdict is None and len(client.requests) == 2

    def test_a_verdict_called_together_with_a_tool_is_taken_and_the_tool_is_not_run(self, run):
        trajectory, _ = run(calls(SEARCH, verdict()))
        assert kinds(trajectory) == [("request", None, None), ("llm_response", 1, None), ("verdict", 1, None)]

    def test_when_such_a_verdict_is_invalid_every_call_of_the_reply_is_answered(self, run):
        trajectory, client = run(calls(SEARCH, verdict(severity="low")), calls(verdict()))
        answers = [content for role, content in sent(client, 1) if role == "tool"]
        assert answers[0] == NOT_ALONE and answers[1].startswith("error: the verdict is not valid")
        assert trajectory.status == "ok"

    def test_the_last_round_is_announced_and_tool_calls_in_it_fail_the_investigation(self, run):
        trajectory, client = run(calls(SEARCH), calls(TIMELINE), max_rounds_=2)
        assert sent(client, 1)[-1] == ("user", "Round 2 of 2. This is the last round.")
        assert trajectory.failures == [(2, "round_limit", "the last round ended with tool calls and no verdict: ['node_timeline']")]
        # the tool of the last round is not run
        assert [event["name"] for event in trajectory.of_kind("tool_result")] == ["search_logs"]
        assert trajectory.status == "round_limit" and trajectory.verdict is None and len(client.requests) == 2

    def test_a_verdict_on_the_last_round_is_accepted(self, run):
        trajectory, _ = run(calls(SEARCH), calls(verdict()), max_rounds_=2)
        assert trajectory.status == "ok" and trajectory.totals["rounds"] == 2

    def test_an_invalid_verdict_on_the_last_round_has_no_second_try(self, run):
        trajectory, client = run(calls(verdict(severity="high")), calls(verdict()), max_rounds_=1)
        assert trajectory.status == "invalid_verdict" and len(client.requests) == 1

    def test_a_model_error_is_logged_and_ends_the_investigation(self, run):
        timeout = APITimeoutError(httpx2.Request("POST", "http://test"))
        trajectory, client = run(calls(SEARCH), timeout, calls(verdict()))
        assert trajectory.status == "model_error" and trajectory.failures[0][:2] == (2, "model_error")
        assert "timed out" in trajectory.failures[0][2] and len(client.requests) == 2

    def test_evidence_that_names_no_shown_id_is_recorded_with_the_verdict(self, run):
        invented = {"line": "an operator rebooted node-1 at 09:00", "why": "made up"}
        seen = {"line": "4 2004-11-09 10:15:00 node-1 node status ambient=31", "why": "the reading"}
        trajectory, _ = run(calls(verdict(evidence=[seen, invented])))
        assert trajectory.unanchored_evidence == ["an operator rebooted node-1 at 09:00"]


class TestTrajectory:
    def test_the_request_row_says_what_was_asked(self, run):
        trajectory, _ = run(calls(verdict()))
        request = trajectory.request
        assert request["prompt"] == "investigator_v1.md" and request["model"] == "fake-model" and request["max_rounds"] == 4
        assert request["log_line"].endswith("ambient=31") and "# 1. THE NEW LOG" in request["context"]
        assert request["log_id"] in request["log_ids"]

    def test_the_totals_add_up_tokens_calls_and_time(self, run):
        trajectory, _ = run(calls(SEARCH, TIMELINE), completion("hm"), calls(verdict()))
        totals = trajectory.totals
        # the scripted completions report 11 tokens in and 7 out each
        assert (totals["llm_calls"], totals["tool_calls"], totals["failures"], totals["rounds"]) == (3, 2, 1, 3)
        assert (totals["tokens_in"], totals["tokens_out"], totals["status"]) == (33, 21, "ok")
        assert totals["elapsed_seconds"] >= 0 and totals["llm_seconds"] >= 0 and totals["tool_seconds"] >= 0

    def test_the_shown_ids_are_those_of_the_context_and_of_every_tool_result(self, run, populated):
        trajectory, _ = run(calls(SEARCH), calls(verdict()))
        log_ids, shape_ids = trajectory.shown_ids
        assert len(log_ids) == 5 and shape_ids == {populated["running"], populated["ambient"]}

    def test_the_text_has_the_context_every_step_with_its_reasoning_and_result_and_the_verdict(self, run):
        trajectory, _ = run(calls(SEARCH, TIMELINE), completion("hm"), calls(verdict()))
        text = trajectory.text()
        marks = ["## STARTING CONTEXT", "## STEP 1 (round 1): the agent called search_logs", "## STEP 2 (round 1): the agent called node_timeline",
                 "## ROUND 2: THE AGENT WROTE\nhm", "## ROUND 2: FAILURE, no_tool_call", "## FINAL VERDICT (round 3)"]
        positions = [text.index(mark) for mark in marks]
        assert positions == sorted(positions)
        assert WHY in text and "result:\n" in text and '"verdict": "benign"' in text and "investigator_v1" not in text

    def test_the_text_of_a_failed_investigation_says_there_is_no_verdict(self, run):
        trajectory, _ = run(calls(SEARCH), calls(TIMELINE), max_rounds_=2)
        assert trajectory.text().endswith("## NO VERDICT\nThe investigation ended without a verdict: round_limit.")

    def test_requests_are_kept_apart_and_an_unknown_one_is_an_error(self):
        events = EventLog(":memory:")
        first, second = events.new_request(context="a", log_ids=[], log_shape_ids=[]), events.new_request(context="b", log_ids=[], log_shape_ids=[])
        events.add(first, "failure", round=1, name="model_error", content={"detail": "x"})
        assert events.request_ids() == [first, second]
        assert Trajectory(first, events.conn).status == "model_error" and Trajectory(second, events.conn).status == "unfinished"
        with pytest.raises(ValueError, match="no events are logged"):
            Trajectory("nope", events.conn)
        with pytest.raises(ValueError, match="unknown kind"):
            events.add(first, "judgement", content={})

    def test_the_log_is_a_file_that_another_process_can_read(self, tmp_path):
        path = tmp_path / "runs" / "agent.db"
        request_id = EventLog(path).new_request(context="a", log_ids=[1], log_shape_ids=[2])
        assert Trajectory(request_id, path).shown_ids == ({1}, {2})
