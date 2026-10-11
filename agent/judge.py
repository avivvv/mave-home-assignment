"""The judge: one LLM call that reads a complete trajectory and grades it on the criteria of prompts/judge_v1.md.

It sees the trajectory and nothing else: no expected answer.
"""
import json

from pydantic import ValidationError

from agent.context import load_prompt
from agent.schema import Judgement
from agent.tools import tool_purposes

JUDGE_PROMPT = "judge_v1"
# a reply that is not a valid Judgement is sent back with the error this many times
RETRIES = 1


def transcript(messages):
    """A conversation of the investigator as text: the starting context, each tool call with its result, the final verdict."""
    # steps: tool call id -> (step number, tool name), so a result can say which call it answers
    steps, parts, context_shown = {}, [], False
    for message in messages:
        if message["role"] == "user":
            parts.append(f"## {'THE AGENT WAS TOLD' if context_shown else 'STARTING CONTEXT'}\n{message['content']}")
            context_shown = True
        elif message["role"] == "assistant":
            for call in message.get("tool_calls") or []:
                function = call["function"]
                if function["name"] == "submit_verdict":
                    parts.append(f"## FINAL VERDICT\n{function['arguments']}")
                else:
                    steps[call["id"]] = (len(steps) + 1, function["name"])
                    parts.append(f"## STEP {len(steps)}: the agent called {function['name']}\narguments: {function['arguments']}")
            if message.get("content") and not message.get("tool_calls"):
                parts.append(f"## THE AGENT WROTE\n{message['content']}")
        elif message["role"] == "tool" and message["tool_call_id"] in steps:
            step, name = steps[message["tool_call_id"]]
            parts.append(f"result of step {step} ({name}):\n{message['content']}")
    return "\n\n".join(parts)


def parse_json(text):
    """The JSON object in a reply, whatever the model wrote around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("the reply holds no JSON object")
    return json.loads(text[start:end + 1])


def judge(llm, trajectory, cache_tag="", retries=RETRIES):
    """Grade one trajectory. Returns the Judgement and the replies it took."""
    question = f"# THE AGENT'S TOOLS\n{tool_purposes()}\n\n# THE TRAJECTORY\n{trajectory}"
    messages = [{"role": "system", "content": load_prompt(JUDGE_PROMPT)}, {"role": "user", "content": question}]
    replies = []
    for attempt in range(retries + 1):
        reply = llm.chat("judge", messages, cache_tag=cache_tag)
        replies.append(reply)
        try:
            return Judgement.model_validate(parse_json(reply.message["content"] or "")), replies
        except (ValueError, ValidationError) as error:
            problem = str(error)
            messages = [*messages, reply.message, {"role": "user", "content": f"Your answer was not valid: {problem}\nAnswer again with the JSON object only."}]
    raise ValueError(f"the judge gave no valid answer in {retries + 1} attempts: {problem}")
