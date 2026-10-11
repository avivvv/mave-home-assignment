"""The investigation loop: one new log in, a verdict or a logged failure out.

Each round the model is called once. It answers with tool calls, which are run and sent back, or with a verdict,
which ends the investigation. Everything that happens is written to the event log under one request id.
"""
import json
import time

from pydantic import ValidationError

from agent.context import load_prompt, max_rounds, round_notice, starting_context
from agent.llm import LLMError
from agent.schema import SUBMIT_VERDICT, Verdict, unanchored_evidence, unknown_citations
from agent.tools import TOOLS, ToolResult, available_tools, run_tool, schemas

INVESTIGATOR_PROMPT = "investigator_v1"
# the tools of a run without knowledge; a run reads its own list from its LogTools
ALL_TOOLS = [*TOOLS, SUBMIT_VERDICT]
NO_TOOL_CALL = "Your reply had no tool call. Answer with tool calls only: investigation tools, or submit_verdict alone."
NOT_ALONE = "not run: submit_verdict was called in the same reply, and it ends the investigation."


def investigate(log, tools, llm, events, prompt=INVESTIGATOR_PROMPT, max_rounds_=None, cache_tag=""):
    """Investigate one log and return the request id under which the investigation is logged.

    `tools` is a LogTools whose visible time is the log's time. The outcome is read back with Trajectory(request_id):
    a verdict, or the failure that ended it.
    """
    mr = max_rounds_ if max_rounds_ is not None else max_rounds()
    available = available_tools(tools)
    all_tools = [*schemas(available), SUBMIT_VERDICT]
    context = starting_context(tools, log)
    request_id = events.new_request(
        log_id=log.id, log_line=log.original_log, prompt=f"{prompt}.md", model=llm.config["models"]["main"], max_rounds=mr,
        tools=[tool.name for tool in available], knowledge=tools.knowledge is not None,
        context=context.text, log_ids=list(context.log_ids), log_shape_ids=list(context.log_shape_ids),
    )
    shown_log_ids, shown_shape_ids, shown_passage_ids = set(context.log_ids), set(context.log_shape_ids), set()
    messages = [{"role": "system", "content": load_prompt(prompt)}, {"role": "user", "content": f"{context.text}\n\n{round_notice(1, mr)}"}]
    verdict_retried = False

    for round_number in range(1, mr + 1):
        def fail(reason, detail):
            events.add(request_id, "failure", round=round_number, name=reason, content={"detail": detail})

        try:
            reply = llm.chat("main", messages, tools=all_tools, cache_tag=cache_tag)
        except LLMError as error:
            fail("model_error", str(error))
            return request_id
        events.add(
            request_id, "llm_response", round=round_number, content={"message": reply.message, "cached": reply.cached},
            tokens_in=reply.tokens_in, tokens_out=reply.tokens_out, latency_ms=reply.latency_ms,
        )
        messages.append(reply.message)
        calls = reply.message.get("tool_calls") or []
        last_round = round_number == mr
        next_notice = round_notice(round_number + 1, mr)

        if not calls:
            fail("no_tool_call", reply.message.get("content") or "")
            messages.append({"role": "user", "content": f"{NO_TOOL_CALL}\n\n{next_notice}"})
            continue

        submitted = [call for call in calls if call["function"]["name"] == "submit_verdict"]
        if submitted:
            try:
                verdict = Verdict.model_validate(json.loads(submitted[0]["function"]["arguments"]))
            except (json.JSONDecodeError, ValidationError) as error:
                fail("invalid_verdict", str(error))
                if verdict_retried or last_round:
                    return request_id
                # the errors go back once; every tool call of the reply has to be answered
                verdict_retried = True
                for call in calls:
                    answer = f"error: the verdict is not valid. Fix it and call submit_verdict again.\n{error}" if call is submitted[0] else NOT_ALONE
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": answer})
                messages.append({"role": "user", "content": next_notice})
                continue
            # two signals, recorded and not refused: evidence that names nothing the agent saw, and citations of passages it never retrieved
            unanchored = unanchored_evidence(verdict, shown_log_ids, shown_shape_ids, shown_passage_ids)
            unknown = unknown_citations(verdict, shown_passage_ids)
            events.add(
                request_id, "verdict", round=round_number,
                content={"verdict": verdict.model_dump(), "unanchored_evidence": unanchored, "unknown_citations": unknown},
            )
            return request_id

        if last_round:
            fail("round_limit", f"the last round ended with tool calls and no verdict: {[call['function']['name'] for call in calls]}")
            return request_id

        for call in calls:
            name = call["function"]["name"]
            started = time.perf_counter()
            try:
                arguments = json.loads(call["function"]["arguments"])
            except json.JSONDecodeError as error:
                arguments = call["function"]["arguments"]
                result = ToolResult(f"error: the arguments are not valid JSON: {error}")
            else:
                result = run_tool(tools, name, arguments)
            events.add(
                request_id, "tool_result", round=round_number, name=name, latency_ms=round((time.perf_counter() - started) * 1000),
                content={
                    "arguments": arguments, "result": result.text, "log_ids": list(result.log_ids), "log_shape_ids": list(result.log_shape_ids),
                    "passage_ids": list(result.passage_ids),
                },
            )
            shown_log_ids.update(result.log_ids)
            shown_shape_ids.update(result.log_shape_ids)
            shown_passage_ids.update(result.passage_ids)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result.text})
        messages.append({"role": "user", "content": next_notice})

    return request_id
