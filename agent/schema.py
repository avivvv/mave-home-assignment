"""The two structured answers: the investigator's verdict and the judge's grades."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# what kind of thing the log is about. The first group names problems, the second names logs that are not a problem
PROBLEM_CATEGORIES = ("hardware", "temperature", "interconnect", "network", "filesystem", "node_state", "boot", "scheduler", "other")
BENIGN_CATEGORIES = ("telemetry", "operations", "recovery", "info")
Category = Literal[*PROBLEM_CATEGORIES, *BENIGN_CATEGORIES]


class Strict(BaseModel):
    # a field the model invents is an error, not something to drop silently
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidence(Strict):
    line: str = Field(min_length=1, description="A line you saw, copied from the starting context or a tool result with the id it starts with: a log's id, or a log_shape_id")
    why: str = Field(min_length=1, description="What this line shows, in one sentence")


# a number standing on its own: not part of a time, a date, a name such as node-7 or a decimal
LONE_NUMBER = re.compile(r"(?<![\w:.\-])\d+(?![\w.\-])(?!:\d)")


def unanchored_evidence(verdict, log_ids, log_shape_ids):
    """The evidence lines of a verdict that name no id the agent was shown.

    A cheap signal, not a proof: a line passes when any number standing on its own in it is a log id or a log shape id
    that the starting context or a tool result returned. A line that fails it was probably not copied from a result.
    """
    shown = set(log_ids) | set(log_shape_ids)
    return [item.line for item in verdict.evidence if not shown & {int(number) for number in LONE_NUMBER.findall(item.line)}]


class RemediationStep(Strict):
    step: str = Field(min_length=1, description="One concrete action for the operator, naming the node or device")
    reason: str = Field(min_length=1, description="Why this step, tied to the evidence")
    risk: Literal["safe", "disruptive"] = Field(description="disruptive when the step interrupts a node, a job or a service, e.g. a reboot")
    citation: str = Field(default="", description="Leave empty")


class Verdict(Strict):
    reasoning: str = Field(min_length=1, description="One to three sentences: how the evidence leads to this verdict")
    verdict: Literal["actionable", "benign", "insufficient_evidence"]
    severity: Literal["none", "low", "medium", "high", "critical"] = Field(description="none unless the verdict is actionable")
    category: Category
    scope: Literal["single_source", "several_sources", "cluster_wide"]
    summary: str = Field(min_length=1, description="What happened, in two or three sentences, with sources and times")
    root_cause: str = Field(min_length=1, description="Why the log was written. Say so when it is a hypothesis")
    evidence: list[Evidence] = Field(min_length=1, description="The lines your conclusion rests on, the new log among them")
    remediation: list[RemediationStep] = Field(description="What the operator should do. Empty when nothing needs doing")
    confidence: Literal["low", "medium", "high"]

    @model_validator(mode="after")
    def severity_goes_with_the_verdict(self):
        if self.verdict == "actionable" and (self.severity == "none" or not self.remediation):
            raise ValueError("an actionable verdict needs a severity other than none and at least one remediation step")
        if self.verdict != "actionable" and self.severity != "none":
            raise ValueError(f"a {self.verdict} verdict has severity none")
        return self


class Grade(Strict):
    reasoning: str = Field(min_length=1, description="Two or three sentences naming what the agent did, written before the result")
    result: Literal["pass", "fail"]


class Judgement(Strict):
    grounded: Grade
    sufficient_investigation: Grade
    tool_use: Grade
    verdict_supported: Grade
    remediation_quality: Grade
    did_well: str = Field(min_length=1, description="What the agent did correctly")
    missing: str = Field(min_length=1, description="What was missing or wrong")


CRITERIA = tuple(name for name, field in Judgement.model_fields.items() if field.annotation is Grade)


def json_schema(model):
    """The JSON schema of a pydantic model with its $ref pointers replaced by what they point at, as tool calling wants it."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def inline(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(definitions[node["$ref"].split("/")[-1]])
            return {key: inline(value) for key, value in node.items() if key != "title"}
        if isinstance(node, list):
            return [inline(item) for item in node]
        return node

    return inline(schema)


SUBMIT_VERDICT = {
    "type": "function",
    "function": {
        "name": "submit_verdict",
        "description": "Your final answer about the new log. It ends the investigation. Call it alone, never together with another tool.",
        "parameters": json_schema(Verdict),
    },
}
