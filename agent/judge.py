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


def parse_json(text):
    """The JSON object in a reply, whatever the model wrote around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("the reply holds no JSON object")
    return json.loads(text[start:end + 1])


def judge(llm, trajectory, cache_tag="", retries=RETRIES, prompt=JUDGE_PROMPT, tools=None):
    """Grade one trajectory. Returns the Judgement and the replies it took.

    `tools` names the tools the agent had, as the request row of its trajectory records them; None means the log tools.
    """
    question = f"# THE AGENT'S TOOLS\n{tool_purposes(tools)}\n\n# THE TRAJECTORY\n{trajectory}"
    messages = [{"role": "system", "content": load_prompt(prompt)}, {"role": "user", "content": question}]
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
