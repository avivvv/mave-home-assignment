"""The queries an investigation is made of.

LogTools returns tables. It is used by hand from the notebooks, with no limit, and by the agent, whose reads stop at `visible`.
The second half of the file describes the tools to the model and runs the one it asks for.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

import pandas as pd

from logstore.repositories import LogRepository, LogShapeRepository

LOG_COLUMNS = ["id", "ts", "node", "component", "state", "message", "log_shape_id"]
TIMELINE_COLUMNS = ["first_ts", "last_ts", "count", "component", "state", "template"]
HISTORY_COLUMNS = ["log_shape_id", "n_logs", "n_nodes", "first_seen", "last_seen"]
SHAPE_KEY = ["component", "state", "template"]
FOLLOWED_COLUMNS = ["log_shape_id", *SHAPE_KEY, "occurrences_followed", "share", "median_minutes"]
# what_followed looks at this many occurrences at most, the newest ones
MAX_OCCURRENCES = 200


def as_frame(found):
    """The logs returned by LogRepository.search as a table, oldest first."""
    return pd.DataFrame([asdict(log) for log in found], columns=LOG_COLUMNS).sort_values(["ts", "id"], ignore_index=True)


class LogTools:
    """Every read stops at `visible`, the latest time the caller may see. None means no limit."""

    def __init__(self, conn, visible=None):
        self.logs = LogRepository(conn)
        self.log_shapes = LogShapeRepository(conn)
        self.visible = visible
        self._history = {}

    def _until(self, start, end):
        # the end of a read: `end`, or the visible time when that is earlier
        if self.visible is None or end <= self.visible:
            return end
        if start > self.visible:
            raise ValueError(f"the time range starts after the latest visible time, {self.visible}")
        return self.visible

    def search_logs(self, start, end, limit=1000, **filters):
        """The logs of a time range that pass the filters, as a table, oldest first. A limit keeps the newest."""
        return as_frame(self.logs.search(start, self._until(start, end), limit=limit, **filters))

    def stats(self, start, end, **filters):
        """Log count, node count, first seen and last seen of the logs that search_logs would return."""
        return self.logs.stats(start, self._until(start, end), **filters)

    def count_logs(self, group_by, start, end, limit=20, **filters):
        """Log counts per node, component, log_shape or hour, as (group, count), largest first."""
        return self.logs.count_by(group_by, start, self._until(start, end), limit=limit, **filters)

    def per_hour(self, start, end, **filters):
        """Log count of every hour that has logs. count_logs alone returns only the 20 largest groups."""
        counts = self.count_logs("hour", start, end, limit=100_000, **filters)
        return pd.Series(dict(counts), dtype=float).sort_index()

    def node_timeline(self, node, start, end, shape_ids=False):
        """One node's logs, oldest first, with runs of the same log shape collapsed into one line."""
        entries = self.logs.node_timeline(node, start, self._until(start, end))
        columns = ["log_shape_id", *TIMELINE_COLUMNS] if shape_ids else TIMELINE_COLUMNS
        return pd.DataFrame([asdict(e) for e in entries], columns=columns)

    def history(self):
        """Per log shape: log count, node count, first seen and last seen, over everything up to the visible time."""
        if self.visible not in self._history:
            self._history[self.visible] = pd.DataFrame(self.logs.shape_history(self.visible), columns=HISTORY_COLUMNS)
        return self._history[self.visible]

    def find_log_shapes(self, text=None, component=None, state=None):
        """The log shapes that pass the filters, with their counts up to the visible time, most common first.

        `text` is a part of the template, or a list of parts to find any of them. A shape not seen yet is not returned.
        """
        found = pd.DataFrame([asdict(s) for s in self.log_shapes.search(text, component, state)], columns=["id", *SHAPE_KEY])
        history = self.history()
        found = found.rename(columns={"id": "log_shape_id"}).merge(history, on="log_shape_id")
        found["share"] = (found.n_logs / history.n_logs.sum()).round(3)
        return found.sort_values("n_logs", ascending=False, ignore_index=True)

    def shapes_between(self, start, end, **filters):
        """Every log shape seen in the range, in order of first appearance."""
        found = self.search_logs(start, end, limit=None, **filters)
        found = found.merge(self.find_log_shapes()[["log_shape_id", "template"]], on="log_shape_id")
        summary = found.groupby(SHAPE_KEY).agg(n_logs=("id", "size"), n_sources=("node", "nunique"), first=("ts", "min"), last=("ts", "max"))
        return summary.sort_values("first").reset_index()

    def what_followed(self, log_shape_id, start, end, within, node=None):
        """Hindsight on one log shape: what the same source logged up to `within` after each of its logs in the range.

        Returns the number of occurrences looked at, how many of them had nothing after, and a table with one row per
        log shape that followed: on how many occurrences, their share, and the median minutes to its first log.
        """
        occurrences = self.search_logs(start, end, limit=MAX_OCCURRENCES, log_shape_id=log_shape_id, node=node)
        if occurrences.empty:
            return 0, 0, pd.DataFrame(columns=FOLLOWED_COLUMNS)
        after = self.search_logs(occurrences.ts.min(), occurrences.ts.max() + within, limit=None, node=node)
        pairs = occurrences[["id", "ts", "node"]].merge(after[["ts", "node", "log_shape_id"]], on="node", suffixes=("", "_after"))
        pairs = pairs[(pairs.ts_after > pairs.ts) & (pairs.ts_after <= pairs.ts + within)]
        pairs = pairs.assign(minutes=(pairs.ts_after - pairs.ts).dt.total_seconds() / 60)
        # the first log of each shape after each occurrence
        first = pairs.groupby(["id", "log_shape_id"]).minutes.min().reset_index()
        followed = first.groupby("log_shape_id").minutes.agg(occurrences_followed="count", median_minutes="median").reset_index()
        followed["share"] = (followed.occurrences_followed / len(occurrences)).round(2)
        followed["median_minutes"] = followed.median_minutes.round(1)
        followed = followed.merge(self.find_log_shapes()[["log_shape_id", *SHAPE_KEY]], on="log_shape_id")
        followed = followed.sort_values(["occurrences_followed", "median_minutes"], ascending=[False, True], ignore_index=True)
        return len(occurrences), len(occurrences) - pairs.id.nunique(), followed[FOLLOWED_COLUMNS]


# --- the tools as the model sees them ---

# the most rows one tool result shows; a result always says how many it left out
MAX_ROWS = 50


@dataclass(frozen=True)
class ToolResult:
    text: str
    # the ids the result showed, kept so that the evidence of a verdict can be checked against them
    log_ids: tuple = ()
    log_shape_ids: tuple = ()


def table_text(frame, keep="first", index=False, max_rows=MAX_ROWS):
    """A table as text, cut to max_rows, with a line saying what was left out."""
    if frame.empty:
        return "no rows"
    shown = frame.head(max_rows) if keep == "first" else frame.tail(max_rows)
    text = shown.to_string(index=index)
    if len(frame) > len(shown):
        text += f"\n{len(frame) - len(shown)} more rows not shown; these are the {keep} {len(shown)}. Narrow the range or the filters to see the others."
    return text


def _shown(frame, keep="first"):
    # the rows table_text shows of a frame
    return frame.head(MAX_ROWS) if keep == "first" else frame.tail(MAX_ROWS)


def _ids(frame, column):
    return tuple(dict.fromkeys(int(value) for value in frame[column]))


def _search_logs(tools, start, end, limit=30, **filters):
    limit = max(1, min(int(limit), MAX_ROWS))
    found = tools.search_logs(start, end, limit=limit, **filters)
    total = tools.stats(start, end, **filters).n_logs
    text = table_text(found)
    if total > len(found):
        text += f"\n{total - len(found)} older logs not shown; these are the newest {len(found)} of {total}."
    return ToolResult(text, _ids(found, "id"), _ids(found, "log_shape_id"))


def _count_logs(tools, group_by, start, end, **filters):
    if group_by == "hour":
        counts = tools.per_hour(start, end, **filters).astype(int)
        return ToolResult(table_text(counts.rename_axis("hour").reset_index(name="n_logs"), keep="last"))
    counts = pd.DataFrame(tools.count_logs(group_by, start, end, limit=100_000, **filters), columns=[group_by, "n_logs"])
    return ToolResult(table_text(counts))


def _node_timeline(tools, node, start, end):
    entries = tools.node_timeline(node, start, end, shape_ids=True)
    return ToolResult(table_text(entries, keep="last"), log_shape_ids=_ids(_shown(entries, "last"), "log_shape_id"))


def _find_log_shapes(tools, text=None, component=None, state=None):
    shapes = tools.find_log_shapes(text, component, state)
    return ToolResult(table_text(shapes), log_shape_ids=_ids(_shown(shapes), "log_shape_id"))


def _log_shapes_between(tools, start, end, **filters):
    shapes = tools.shapes_between(start, end, **filters)
    # the table has no ids; they are looked up by the three values that identify a log shape
    shapes = tools.find_log_shapes()[["log_shape_id", *SHAPE_KEY]].merge(shapes, on=SHAPE_KEY).sort_values("first", ignore_index=True)
    return ToolResult(table_text(shapes), log_shape_ids=_ids(_shown(shapes), "log_shape_id"))


def _what_followed(tools, log_shape_id, start, end, within_minutes=60, node=None):
    occurrences, nothing_after, followed = tools.what_followed(log_shape_id, start, end, timedelta(minutes=int(within_minutes)), node=node)
    if not occurrences:
        return ToolResult(f"no logs of log shape {log_shape_id} in the range", log_shape_ids=(int(log_shape_id),))
    text = (
        f"{occurrences} occurrences of log shape {log_shape_id} in the range (at most the newest {MAX_OCCURRENCES} are looked at). "
        f"{nothing_after} of them had no other log from the same source in the {within_minutes} minutes after.\n"
        f"What the same source logged in the {within_minutes} minutes after an occurrence:\n{table_text(followed)}"
    )
    return ToolResult(text, log_shape_ids=(int(log_shape_id), *_ids(_shown(followed), "log_shape_id")))


RUNNERS = {
    "search_logs": _search_logs,
    "node_timeline": _node_timeline,
    "log_shapes_between": _log_shapes_between,
    "count_logs": _count_logs,
    "find_log_shapes": _find_log_shapes,
    "what_followed": _what_followed,
}


def run_tool(tools, name, args) -> ToolResult:
    """Run one tool call of the model. A call that fails returns its error as the result; it never raises.

    Every call carries a `reasoning`, which is checked to be there and is not passed to the tool.
    """
    if name not in RUNNERS:
        return ToolResult(f"error: unknown tool {name!r}. The tools are: {', '.join(RUNNERS)}")
    try:
        args = dict(args)
        if not str(args.pop("reasoning", "")).strip():
            return ToolResult("error: the call has no `reasoning`. Say in one to three sentences what you want to learn from it.")
        unknown = sorted(set(args) - ARGUMENTS[name])
        if unknown:
            return ToolResult(f"error: {name} has no argument {', '.join(unknown)}. Its arguments are: {', '.join(sorted(ARGUMENTS[name]))}")
        for key in ("start", "end"):
            if key in args:
                args[key] = datetime.fromisoformat(args[key])
        return RUNNERS[name](tools, **args)
    except (TypeError, ValueError, KeyError) as error:
        return ToolResult(f"error: {error}")


# the same wording for every tool, so the descriptions stay short. The rules for time ranges are in the system prompt
REASONING = {"type": "string", "description": "One to three sentences: what you want to learn from this call and why"}
TIME = {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"}
RANGE = {"start": TIME, "end": TIME}
FILTERS = {
    "node": {"type": "string", "description": "Only this source, e.g. node-12 or gige3"},
    "component": {"type": "string", "description": "Only this component, e.g. node or switch_module"},
    "state": {"type": "string", "description": "Only this state, e.g. status or temperature"},
    "text": {"type": "string", "description": "Only messages containing this text, any letter case"},
    "log_shape_id": {"type": "integer", "description": "Only this log shape"},
}
NODE = {"type": "string", "description": "The source, e.g. node-12 or gige3"}


def _tool(name, description, properties, required):
    # every tool takes a reasoning, first, so the model writes it before the other arguments
    parameters = {"type": "object", "properties": {"reasoning": REASONING, **properties}, "required": ["reasoning", *required]}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


# each description says what the tool returns and then what it is for; the judge reads them too
TOOLS = [
    _tool(
        "search_logs",
        "Returns the logs of a time range that pass every filter, oldest first, each with its id and log_shape_id; when there are more than "
        "`limit`, the newest. Use it to read the actual lines: what exactly was logged around a moment, by one source or with a given text.",
        {**RANGE, **FILTERS, "limit": {"type": "integer", "description": f"Logs to show: 30 by default, at most {MAX_ROWS}"}},
        ["start", "end"],
    ),
    _tool(
        "node_timeline",
        "Returns everything one source logged in a time range, oldest first, with a run of the same log shape collapsed into one line "
        "(log_shape_id, first time, last time, count). Use it for the history of one node or device: what led up to a log, and how the source usually behaves.",
        {"node": NODE, **RANGE},
        ["node", "start", "end"],
    ),
    _tool(
        "log_shapes_between",
        "Returns every log shape seen in a time range, in order of first appearance, with its log_shape_id, log count, source count, first and "
        "last time. Use it to see what the whole cluster did around a moment and how wide an event is; with a filter, to summarise one source or one shape.",
        {**RANGE, **FILTERS},
        ["start", "end"],
    ),
    _tool(
        "count_logs",
        "Returns log counts per group in a time range. Per node or component: largest first. Per hour: every hour that has logs, in time order. "
        "Use it to find when something happened before (per hour), to tell a burst from a steady trickle, and to see which sources are affected.",
        {"group_by": {"type": "string", "enum": ["node", "component", "hour"]}, **RANGE, **FILTERS},
        ["group_by", "start", "end"],
    ),
    _tool(
        "find_log_shapes",
        "Returns the log shapes seen so far that pass every filter, with log_shape_id, log count, source count, first seen and last seen. "
        "Use it to learn which messages exist and their ids, e.g. what a temperature warning from a switch looks like, or whether a message is new or common.",
        {
            "text": {"type": "array", "items": {"type": "string"}, "description": "Parts of the message template; a shape containing any of them is found"},
            "component": FILTERS["component"],
            "state": FILTERS["state"],
        },
        [],
    ),
    _tool(
        "what_followed",
        "Hindsight on one log shape. For its earlier logs in a time range, returns which log shapes the same source logged shortly after: on how "
        "many occurrences, the share, and the median minutes until then. Use it to judge severity from the past: did this message usually lead to "
        "'not responding', to an operator's boot command, or to nothing.",
        {
            "log_shape_id": {"type": "integer", "description": "The log shape whose earlier logs are looked at"},
            **RANGE,
            "within_minutes": {"type": "integer", "description": "How long after each occurrence to look, 60 by default"},
            "node": FILTERS["node"],
        },
        ["log_shape_id", "start", "end"],
    ),
]

# the arguments each tool takes besides the reasoning, to refuse a call that names another
ARGUMENTS = {tool["function"]["name"]: set(tool["function"]["parameters"]["properties"]) - {"reasoning"} for tool in TOOLS}


def tool_purposes():
    """The tools and what each is for, as text. The judge is given it to grade how the tools were used."""
    return "\n".join(f"- {tool['function']['name']}: {tool['function']['description']}" for tool in TOOLS)
