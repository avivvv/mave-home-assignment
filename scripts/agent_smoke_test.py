"""Smoke test of the agent module: three single calls to the real models, on four made-up logs.

Every call is given its whole conversation, so no call depends on what another one answered, and the three run together.

The made-up case: node-7 stops responding one minute after an operator's shutdown command that targets node-7.

1. First round of the investigator: the real system prompt, the real tools, the starting context, which shows only
   the new log. The model has to choose tools and give a reasoning for each call.
2. Last round of the investigator: the same conversation with one tool call already in it, whose result shows the
   shutdown command, and the notice that this is the last round. The model has to submit a verdict of the right format.
3. The judge: the real system prompt and a made-up trajectory that is plainly bad. The grades have to have the
   right format and fail it.

Nothing is retried and nothing is read from the cache: a call that fails or times out fails the test.

Run from the repo root: python -m scripts.agent_smoke_test
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from agent.context import MAX_ROUNDS, load_prompt, round_notice, starting_context
from agent.judge import judge, transcript
from agent.llm import LLM, ROOT, load_config
from agent.schema import CRITERIA, SUBMIT_VERDICT, Verdict, unanchored_evidence
from agent.tools import RUNNERS, TOOLS, LogTools, run_tool
from logstore.db import connect, create_indexes, init_schema
from logstore.ingest import ingest_lines

INVESTIGATOR_PROMPT = "investigator_v1"
# one call may take this long; there is no second attempt
TIMEOUT_SECONDS = 60
# not in git: nothing here is reused
CACHE_DIR = ROOT / "runs" / "scratch" / "smoke_cache"
ALL_TOOLS = [*TOOLS, SUBMIT_VERDICT]

# the new log arrives at NOW. Epoch seconds, 2004-11-09 11:33:20 UTC
NOW = 1100000000
NEW_LINE = f"9000 node-7 node status {NOW} 1 not responding"
LINES = [
    # two routine readings of other nodes
    f"7001 node-3 node temperature {NOW - 1800} 1 ambient=27",
    f"7002 node-8 node temperature {NOW - 900} 1 ambient=28",
    # the operator's command. Its source is the command number, so it is not on node-7's timeline
    f"7003 12 shutdown_cmd new {NOW - 60} 1 Targeting domains:node-D0 and nodes:node-7",
    NEW_LINE,
]
# the tool call that is already in the conversation of the last round
LOOK_BACK = {
    "reasoning": "See whether an operator command named node-7 shortly before it stopped responding.",
    "start": "2004-11-09 11:23:20", "end": "2004-11-09 11:33:20", "text": "node-7",
}

# the trajectory given to the judge: a call that has nothing to do with the log, then a verdict that invents its facts
BAD_CALL = {"reasoning": "Look at temperatures.", "text": ["ambient"]}
BAD_VERDICT = {
    "reasoning": "It is fine.", "verdict": "benign", "severity": "none", "category": "telemetry", "scope": "cluster_wide",
    "summary": "node-7 reported a routine temperature reading of 27 degrees. An operator rebooted it at 11:00 and all 256 nodes are healthy.",
    "root_cause": "A scheduled reboot by an operator.",
    "evidence": [{"line": "999999 2004-11-09 11:00:00 node-7 action start boot (command 555)", "why": "the reboot command"}],
    "remediation": [{"step": "Monitor the system.", "reason": "To be safe.", "risk": "safe"}],
    "confidence": "high",
}
# the criteria the bad trajectory cannot pass
MUST_FAIL = ("grounded", "sufficient_investigation", "verdict_supported")


def build_store():
    conn = connect(":memory:")
    init_schema(conn)
    create_indexes(conn)
    tools = LogTools(conn)
    result = ingest_lines(LINES, tools.logs, tools.log_shapes)
    assert result.inserted == len(LINES) and not result.unparsed
    log_id = conn.execute("SELECT id FROM logs WHERE original_log = ?", (NEW_LINE,)).fetchone()[0]
    now = datetime.fromtimestamp(NOW, UTC).replace(tzinfo=None)
    log = next(found for found in tools.logs.search(now, now) if found.id == log_id)
    # from here on the tools see nothing later than the new log
    tools.visible = log.ts
    return tools, log


def tool_call(call_id, name, arguments):
    function = {"name": name, "arguments": json.dumps(arguments)}
    return {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": function}]}


def tool_result(call_id, text):
    return {"role": "tool", "tool_call_id": call_id, "content": text}


def new_llm():
    # each call gets its own client: no spacing between the three calls, no retry, a short timeout
    config = {**load_config(), "max_retries": 0, "timeout_seconds": TIMEOUT_SECONDS}
    return LLM(config=config, cache_dir=CACHE_DIR)


def timed(call):
    """The answer of a call, or the error it raised, and the seconds it took."""
    started = time.perf_counter()
    try:
        return call(), time.perf_counter() - started
    except Exception as error:
        return error, time.perf_counter() - started


def calls_of(reply):
    return [(call["function"]["name"], json.loads(call["function"]["arguments"])) for call in reply.message.get("tool_calls") or []]


def main():
    # a model may write a character the Windows console cannot show
    sys.stdout.reconfigure(errors="replace")
    started = time.perf_counter()
    cache_tag = f"agent-smoke-{time.time()}"
    models = load_config()["models"]

    print(f"1. build a store of {len(LINES)} made-up logs and the three conversations")
    tools, log = build_store()
    context = starting_context(tools, log)
    assert "# 1. THE NEW LOG" in context.text and "# 2. TIMELINE" in context.text and "# 3. THE SAME LOG SHAPE" in context.text
    assert "shutdown_cmd" not in context.text, "the starting context must not already hold the answer"
    system = {"role": "system", "content": load_prompt(INVESTIGATOR_PROMPT)}
    first_round = [system, {"role": "user", "content": f"{context.text}\n\n{round_notice(1)}"}]
    looked_back = run_tool(tools, "search_logs", LOOK_BACK)
    assert "Targeting domains:node-D0 and nodes:node-7" in looked_back.text
    # the model is not told to submit, only that this is the last round; the system prompt says what that means
    last_round = [
        system,
        {"role": "user", "content": f"{context.text}\n\n{round_notice(MAX_ROUNDS - 1)}"},
        tool_call("call_1", "search_logs", LOOK_BACK),
        tool_result("call_1", looked_back.text),
        {"role": "user", "content": round_notice(MAX_ROUNDS)},
    ]
    shown_log_ids = {*context.log_ids, *looked_back.log_ids}
    shown_shape_ids = {*context.log_shape_ids, *looked_back.log_shape_ids}
    bad_trajectory = transcript([
        {"role": "user", "content": context.text},
        tool_call("call_1", "find_log_shapes", BAD_CALL),
        tool_result("call_1", run_tool(tools, "find_log_shapes", BAD_CALL).text),
        tool_call("call_2", "submit_verdict", BAD_VERDICT),
    ])
    # the code check of evidence, on the invented line of the bad verdict: no model is needed for this one
    assert unanchored_evidence(Verdict.model_validate(BAD_VERDICT), context.log_ids, context.log_shape_ids) == [BAD_VERDICT["evidence"][0]["line"]]

    print(f"2. call {models['main']} twice and {models['judge']} once, together, with no retry")
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(timed, lambda: new_llm().chat("main", first_round, tools=ALL_TOOLS, cache_tag=cache_tag))
        last = pool.submit(timed, lambda: new_llm().chat("main", last_round, tools=ALL_TOOLS, cache_tag=cache_tag))
        graded = pool.submit(timed, lambda: judge(new_llm(), bad_trajectory, cache_tag=cache_tag, retries=0))
    failures = []

    def check(name, future, verify):
        answer, seconds = future.result()
        print(f"\n   {name} ({seconds:.1f} s)")
        try:
            if isinstance(answer, Exception):
                raise answer
            verify(answer)
        except Exception as error:
            failures.append(name)
            print(f"      FAILED: {type(error).__name__}: {str(error)[:600]}")

    def verify_first(reply):
        calls = calls_of(reply)
        for name, args in calls:
            print(f"      {name} {json.dumps(args)}")
        assert calls, f"the model chose no tool and wrote: {reply.message.get('content')!r}"
        assert all(name in RUNNERS for name, _ in calls), "the model did not investigate: it called an unknown tool or submitted at once"
        assert all(str(args.get("reasoning", "")).strip() for _, args in calls), "a tool call has no reasoning"
        errors = [result.text for result in (run_tool(tools, name, args) for name, args in calls) if result.text.startswith("error:")]
        for error in errors:
            print(f"      a call the model got wrong: {error}")
        assert len(errors) < len(calls), "none of the chosen tool calls runs"

    def verify_last(reply):
        calls = calls_of(reply)
        assert [name for name, _ in calls] == ["submit_verdict"], f"expected submit_verdict alone, got {[name for name, _ in calls]}"
        # the schema refuses an empty reasoning and an empty evidence list
        verdict = Verdict.model_validate(calls[0][1])
        print(f"      {verdict.verdict}, severity {verdict.severity}, {verdict.category}, {verdict.scope}, confidence {verdict.confidence}")
        print(f"      reasoning: {verdict.reasoning}")
        unanchored = unanchored_evidence(verdict, shown_log_ids, shown_shape_ids)
        for evidence in verdict.evidence:
            print(f"      evidence ({'no id that was shown' if evidence.line in unanchored else 'names a shown id'}): {evidence.line}")
        assert len(unanchored) < len(verdict.evidence), "no evidence line names an id that the agent was shown"

    def verify_judge(answer):
        judgement, _ = answer
        results = {criterion: getattr(judgement, criterion).result for criterion in CRITERIA}
        for criterion in CRITERIA:
            print(f"      {criterion:<25} {results[criterion]}   {getattr(judgement, criterion).reasoning}")
        print(f"      did well: {judgement.did_well}")
        print(f"      missing: {judgement.missing}")
        passed = [criterion for criterion in MUST_FAIL if results[criterion] != "fail"]
        assert not passed, f"the judge passed a plainly bad trajectory on {passed}"

    check("investigator, first round: it has to choose tools", first, verify_first)
    check("investigator, last round: it has to submit a valid verdict", last, verify_last)
    check("judge: it has to fail a bad trajectory", graded, verify_judge)

    print(f"\n{time.perf_counter() - started:.1f} seconds in all")
    if failures:
        raise SystemExit(f"SMOKE TEST FAILED: {', '.join(failures)}")
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
