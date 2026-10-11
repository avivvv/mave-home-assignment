"""The record of an investigation: every event of a request is one row in a SQLite file, and a Trajectory reads them back.

EventLog writes. The loop adds a row for the request, for each reply of the model, for each tool result, for the
verdict and for each failure, all under one request_id. Trajectory(request_id) reads the rows of one request and
gives the text a person or the judge reads, the verdict, and the counts.
"""
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "runs" / "agent.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY,   -- also the order of the events
    request_id TEXT NOT NULL,
    at         TEXT NOT NULL,         -- wall-clock time the row was written, UTC
    kind       TEXT NOT NULL,         -- request | llm_response | tool_result | verdict | failure
    round      INTEGER,               -- the round of the investigation, empty for the request
    name       TEXT,                  -- the tool of a tool_result, the reason of a failure
    content    TEXT NOT NULL,         -- JSON; what it holds depends on the kind
    tokens_in  INTEGER,
    tokens_out INTEGER,
    latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS ix_events_request ON events(request_id, id);
"""
KINDS = ("request", "llm_response", "tool_result", "verdict", "failure")


class EventLog:
    def __init__(self, path=DB_PATH):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def new_request(self, **content):
        """Start a request: write its first row and return its id."""
        request_id = uuid.uuid4().hex[:12]
        self.add(request_id, "request", content=content)
        return request_id

    def add(self, request_id, kind, round=None, name=None, content=None, tokens_in=None, tokens_out=None, latency_ms=None):
        if kind not in KINDS:
            raise ValueError(f"unknown kind of event: {kind!r}")
        at = datetime.now(UTC).isoformat(sep=" ", timespec="milliseconds")
        row = (request_id, at, kind, round, name, json.dumps(content, ensure_ascii=False), tokens_in, tokens_out, latency_ms)
        with self.conn:
            self.conn.execute(
                "INSERT INTO events (request_id, at, kind, round, name, content, tokens_in, tokens_out, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", row
            )

    def request_ids(self):
        """Every request in the file, oldest first."""
        return [row[0] for row in self.conn.execute("SELECT request_id FROM events WHERE kind = 'request' ORDER BY id")]


class Trajectory:
    """Everything logged for one request, read from the events file."""

    def __init__(self, request_id, path=DB_PATH):
        self.request_id = request_id
        conn = path if isinstance(path, sqlite3.Connection) else sqlite3.connect(path)
        rows = conn.execute(
            "SELECT at, kind, round, name, content, tokens_in, tokens_out, latency_ms FROM events WHERE request_id = ? ORDER BY id", (request_id,)
        ).fetchall()
        if not rows:
            raise ValueError(f"no events are logged for the request {request_id!r}")
        columns = ("at", "kind", "round", "name", "content", "tokens_in", "tokens_out", "latency_ms")
        self.events = [{**dict(zip(columns, row)), "content": json.loads(row[4])} for row in rows]

    def of_kind(self, kind):
        return [event for event in self.events if event["kind"] == kind]

    @property
    def request(self):
        """What was asked: the log, the prompt file, the model, the round limit and the starting context."""
        return self.of_kind("request")[0]["content"]

    @property
    def verdict(self):
        """The accepted verdict as a dict, or None when the request ended without one."""
        verdicts = self.of_kind("verdict")
        return verdicts[-1]["content"]["verdict"] if verdicts else None

    @property
    def unanchored_evidence(self):
        """The evidence lines of the verdict that name no id the agent was shown."""
        verdicts = self.of_kind("verdict")
        return verdicts[-1]["content"]["unanchored_evidence"] if verdicts else []

    @property
    def failures(self):
        """Each failure as (round, reason, detail), in order."""
        return [(event["round"], event["name"], event["content"]["detail"]) for event in self.of_kind("failure")]

    @property
    def status(self):
        """'ok' when a verdict was accepted, otherwise the reason of the failure that ended the request."""
        if self.verdict is not None:
            return "ok"
        return self.failures[-1][1] if self.failures else "unfinished"

    @property
    def shown_ids(self):
        """The log ids and the log shape ids that the starting context and the tool results showed."""
        sources = [self.request, *(event["content"] for event in self.of_kind("tool_result"))]
        log_ids = {log_id for source in sources for log_id in source["log_ids"]}
        shape_ids = {shape_id for source in sources for shape_id in source["log_shape_ids"]}
        return log_ids, shape_ids

    @property
    def totals(self):
        """The telemetry of the request: rounds, calls, tokens and time."""
        replies, results = self.of_kind("llm_response"), self.of_kind("tool_result")
        first, last = (datetime.fromisoformat(self.events[i]["at"]) for i in (0, -1))
        return {
            "status": self.status,
            "rounds": max((event["round"] or 0 for event in self.events), default=0),
            "llm_calls": len(replies),
            "tool_calls": len(results),
            "failures": len(self.failures),
            "tokens_in": sum(event["tokens_in"] or 0 for event in replies),
            "tokens_out": sum(event["tokens_out"] or 0 for event in replies),
            "llm_seconds": round(sum(event["latency_ms"] or 0 for event in replies) / 1000, 1),
            "tool_seconds": round(sum(event["latency_ms"] or 0 for event in results) / 1000, 1),
            "elapsed_seconds": round((last - first).total_seconds(), 1),
        }

    def text(self):
        """The trajectory as text, for a person or the judge: the starting context, each step with its result, the verdict."""
        parts, step = [f"## STARTING CONTEXT\n{self.request['context']}"], 0
        for event in self.events:
            content = event["content"]
            if event["kind"] == "llm_response" and content["message"].get("content"):
                parts.append(f"## ROUND {event['round']}: THE AGENT WROTE\n{content['message']['content']}")
            elif event["kind"] == "tool_result":
                step += 1
                parts.append(
                    f"## STEP {step} (round {event['round']}): the agent called {event['name']}\n"
                    f"arguments: {json.dumps(content['arguments'], ensure_ascii=False)}\nresult:\n{content['result']}"
                )
            elif event["kind"] == "failure":
                parts.append(f"## ROUND {event['round']}: FAILURE, {event['name']}\n{content['detail']}")
            elif event["kind"] == "verdict":
                parts.append(f"## FINAL VERDICT (round {event['round']})\n{json.dumps(content['verdict'], ensure_ascii=False, indent=1)}")
        if self.verdict is None:
            parts.append(f"## NO VERDICT\nThe investigation ended without a verdict: {self.status}.")
        return "\n\n".join(parts)
