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
GIGE_LEVELS = ["normal", "warning", "critical"]


def as_frame(found):
    """The logs returned by LogRepository.search as a table, oldest first."""
    return pd.DataFrame([asdict(log) for log in found], columns=LOG_COLUMNS).sort_values(["ts", "id"], ignore_index=True)


def minutes_at_level(entries):
    """For a timeline in which every line is a change of level: the minutes from each line to the next, per level."""
    changes = pd.to_datetime(entries.first_ts)
    minutes = changes.diff().shift(-1).dt.total_seconds().div(60)
    return minutes.groupby(entries.template).agg(times="count", median="median", longest="max", total="sum").round(1)


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

    def node_timeline(self, node, start, end):
        """One node's logs, oldest first, with runs of the same log shape collapsed into one line."""
        entries = self.logs.node_timeline(node, start, self._until(start, end))
        return pd.DataFrame([asdict(e) for e in entries], columns=TIMELINE_COLUMNS)

    def history(self):
        """Per log shape: log count, node count, first seen and last seen, over everything up to the visible time."""
        if self.visible not in self._history:
            self._history[self.visible] = pd.DataFrame(self.logs.shape_history(self.visible), columns=HISTORY_COLUMNS)
        return self._history[self.visible]

    def find_log_shapes(self, text=None, component=None, state=None):
        """The log shapes that pass the filters, with their counts up to the visible time, most common first.

        `text` is a part of the template, or a list of parts to find any of them. A shape not seen yet is not returned.
        """
        found = pd.DataFrame([asdict(s) for s in self.log_shapes.search(text, component, state)], columns=["id", "component", "state", "template"])
        history = self.history()
        found = found.rename(columns={"id": "log_shape_id"}).merge(history, on="log_shape_id")
        found["share"] = (found.n_logs / history.n_logs.sum()).round(3)
        return found.sort_values("n_logs", ascending=False, ignore_index=True)

    def shapes_between(self, start, end, **filters):
        """Every log shape seen in the range, in order of first appearance."""
        found = self.search_logs(start, end, limit=None, **filters)
        found = found.merge(self.find_log_shapes()[["log_shape_id", "template"]], on="log_shape_id")
        summary = found.groupby(["component", "state", "template"]).agg(
            n_logs=("id", "size"), n_sources=("node", "nunique"), first=("ts", "min"), last=("ts", "max")
        )
        return summary.sort_values("first").reset_index()

    def gige_levels(self, start, end):
        """How many times each gige device reported each temperature level."""
        levels = {level: dict(self.count_logs("node", start, end, component="gige", text=level)) for level in GIGE_LEVELS}
        return pd.DataFrame(levels).fillna(0).astype(int).sort_index()

    def preceded_by(self, found, log_shape_id, within):
        """For each row of a table from search_logs: True when the same node has a log of the given shape up to `within` before it."""
        earlier = self.search_logs(found.ts.min() - within, found.ts.max(), log_shape_id=log_shape_id, limit=None)
        earlier = earlier.rename(columns={"ts": "earlier_ts"})[["earlier_ts", "node"]]
        joined = pd.merge_asof(found[["ts", "node"]], earlier, left_on="ts", right_on="earlier_ts", by="node", tolerance=pd.Timedelta(within))
        return joined.earlier_ts.notna()


# --- the tools as the model sees them ---

# the most rows one tool result shows; a result always says how many it left out
MAX_ROWS = 50


@dataclass(frozen=True)
class ToolResult:
    text: str
    # the ids of the logs shown, which are the only ones a verdict may cite
    log_ids: tuple = ()


def _table(frame, keep="first", index=False):
    """A table as text, cut to MAX_ROWS, with a line saying what was left out."""
    if frame.empty:
        return "no rows"
    shown = frame.head(MAX_ROWS) if keep == "first" else frame.tail(MAX_ROWS)
    text = shown.to_string(index=index)
    if len(frame) > len(shown):
        text += f"\n{len(frame) - len(shown)} more rows not shown; these are the {keep} {len(shown)}. Narrow the range or the filters to see the others."
    return text


def _search_logs(tools, start, end, limit=30, **filters):
    limit = max(1, min(int(limit), MAX_ROWS))
    found = tools.search_logs(start, end, limit=limit, **filters)
    total = tools.stats(start, end, **filters).n_logs
    text = _table(found)
    if total > len(found):
        text += f"\n{total - len(found)} older logs not shown; these are the newest {len(found)} of {total}."
    return ToolResult(text, tuple(found.id.tolist()))


def _count_logs(tools, group_by, start, end, **filters):
    if group_by == "hour":
        counts = tools.per_hour(start, end, **filters).astype(int)
        return ToolResult(_table(counts.rename_axis("hour").reset_index(name="n_logs"), keep="last"))
    counts = pd.DataFrame(tools.count_logs(group_by, start, end, limit=100_000, **filters), columns=[group_by, "n_logs"])
    return ToolResult(_table(counts))


def _get_stats(tools, start, end, **filters):
    stats = tools.stats(start, end, **filters)
    return ToolResult(f"n_logs={stats.n_logs}, n_nodes={stats.n_nodes}, first_seen={stats.first_seen}, last_seen={stats.last_seen}")


def _node_timeline(tools, node, start, end):
    return ToolResult(_table(tools.node_timeline(node, start, end), keep="last"))


def _find_log_shapes(tools, text=None, component=None, state=None):
    return ToolResult(_table(tools.find_log_shapes(text, component, state)))


def _log_shapes_between(tools, start, end, **filters):
    return ToolResult(_table(tools.shapes_between(start, end, **filters)))


def _gige_levels(tools, start, end):
    return ToolResult(_table(tools.gige_levels(start, end), index=True))


def _minutes_at_level(tools, node, start, end):
    entries = tools.node_timeline(node, start, end)
    if entries.empty:
        return ToolResult("no rows")
    return ToolResult(_table(minutes_at_level(entries), index=True))


def _preceded_by(tools, log_shape_id, earlier_log_shape_id, start, end, within_minutes=60, node=None):
    found = tools.search_logs(start, end, limit=None, log_shape_id=log_shape_id, node=node)
    if found.empty:
        return ToolResult(f"no logs of log shape {log_shape_id} in the range")
    preceded = tools.preceded_by(found, earlier_log_shape_id, timedelta(minutes=within_minutes))
    return ToolResult(
        f"{len(found)} logs of log shape {log_shape_id} in the range. {preceded.sum()} of them ({preceded.mean():.0%}) "
        f"have a log of shape {earlier_log_shape_id} on the same node in the {within_minutes} minutes before."
    )


RUNNERS = {
    "search_logs": _search_logs,
    "count_logs": _count_logs,
    "get_stats": _get_stats,
    "node_timeline": _node_timeline,
    "find_log_shapes": _find_log_shapes,
    "log_shapes_between": _log_shapes_between,
    "gige_levels": _gige_levels,
    "minutes_at_level": _minutes_at_level,
    "preceded_by": _preceded_by,
}


def run_tool(tools, name, args):
    """Run one tool call of the model. A call that fails returns its error as the result; it never raises."""
    if name not in RUNNERS:
        return ToolResult(f"error: unknown tool {name!r}. The tools are: {', '.join(RUNNERS)}")
    try:
        args = dict(args)
        for key in ("start", "end"):
            if key in args:
                args[key] = datetime.fromisoformat(args[key])
        return RUNNERS[name](tools, **args)
    except (TypeError, ValueError, KeyError) as error:
        return ToolResult(f"error: {error}")


TIME = {"type": "string", "description": "A time as 'YYYY-MM-DD HH:MM:SS'"}
RANGE = {"start": TIME, "end": TIME}
FILTERS = {
    "node": {"type": "string", "description": "Only this source, for example node-12 or gige3"},
    "component": {"type": "string", "description": "Only this component, for example node or switch_module"},
    "state": {"type": "string", "description": "Only this state, for example status or temperature"},
    "text": {"type": "string", "description": "Only messages that contain this text, in any letter case"},
    "log_shape_id": {"type": "integer", "description": "Only this log shape"},
}
NODE = {"type": "string", "description": "The source, for example node-12 or gige3"}
RANGE_RULE = "A range covers at most 31 days, and nothing later than the present moment is returned."


def _tool(name, description, properties, required):
    parameters = {"type": "object", "properties": properties, "required": required}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


TOOLS = [
    _tool(
        "search_logs",
        f"The logs of a time range that pass every given filter, oldest first. When there are more than `limit`, the newest are shown. {RANGE_RULE}",
        {**RANGE, **FILTERS, "limit": {"type": "integer", "description": f"How many logs to show, 30 by default, at most {MAX_ROWS}"}},
        ["start", "end"],
    ),
    _tool(
        "count_logs",
        f"Log counts per group over a time range. Per node or component: largest first. Per hour: every hour that has logs, in time order. {RANGE_RULE}",
        {"group_by": {"type": "string", "enum": ["node", "component", "hour"]}, **RANGE, **FILTERS},
        ["group_by", "start", "end"],
    ),
    _tool(
        "get_stats",
        f"Log count, count of distinct sources, first seen and last seen of the logs of a time range that pass every given filter. {RANGE_RULE}",
        {**RANGE, **FILTERS},
        ["start", "end"],
    ),
    _tool(
        "node_timeline",
        f"Everything one source logged in a time range, oldest first. A run of the same log shape is one line with its first time, last time and count. {RANGE_RULE}",
        {"node": NODE, **RANGE},
        ["node", "start", "end"],
    ),
    _tool(
        "find_log_shapes",
        "The log shapes (kinds of message) seen so far that pass every given filter, with how often each was seen, on how many sources, "
        "and when first and last. Use it to learn which messages exist, for example every shape that mentions 'temperature'.",
        {
            "text": {"type": "array", "items": {"type": "string"}, "description": "Parts of the message template; a shape that contains any of them is found"},
            "component": FILTERS["component"],
            "state": FILTERS["state"],
        },
        [],
    ),
    _tool(
        "log_shapes_between",
        f"Every log shape seen in a time range, in order of first appearance, with its log count, source count, first and last time. "
        f"Use it to see everything the cluster logged around a moment. {RANGE_RULE}",
        {**RANGE, **FILTERS},
        ["start", "end"],
    ),
    _tool(
        "gige_levels",
        f"How many times each gige device reported each temperature level (normal, warning, critical) in a time range. {RANGE_RULE}",
        RANGE,
        ["start", "end"],
    ),
    _tool(
        "minutes_at_level",
        "For a source whose lines are changes of level, such as a gige device's temperature: the minutes it spent at each level in a time range. "
        f"Per level: how many times, the median stay, the longest stay and the total. {RANGE_RULE}",
        {"node": NODE, **RANGE},
        ["node", "start", "end"],
    ),
    _tool(
        "preceded_by",
        "Of the logs of one log shape in a time range, how many have a log of another log shape on the same source shortly before. "
        f"Use it to check whether one message usually follows another. {RANGE_RULE}",
        {
            "log_shape_id": {"type": "integer", "description": "The log shape whose logs are checked"},
            "earlier_log_shape_id": {"type": "integer", "description": "The log shape looked for before each of them"},
            **RANGE,
            "within_minutes": {"type": "integer", "description": "How far back to look, 60 by default"},
            "node": FILTERS["node"],
        },
        ["log_shape_id", "earlier_log_shape_id", "start", "end"],
    ),
]
