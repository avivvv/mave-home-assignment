"""Shared setup of the notebooks in this folder: the database, the 17 pinned logs and a few small helpers.

The helpers only reshape what the queries of LogRepository and LogShapeRepository return. They are for these notebooks only.
"""
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
from logstore.db import connect
from logstore.repositories import LogRepository, LogShapeRepository

pd.set_option("display.max_colwidth", 120)

conn = connect()
logs = LogRepository(conn)
log_shapes = LogShapeRepository(conn)
minute, hour, day = timedelta(minutes=1), timedelta(hours=1), timedelta(days=1)

# counts over the whole history of every log shape. The repository reads are bounded in time, so this stays here
_history = pd.read_sql(
    """
    SELECT log_shape_id, COUNT(*) AS n_logs, COUNT(DISTINCT node) AS n_nodes,
           MIN(ts) AS first_seen, MAX(ts) AS last_seen
    FROM logs
    GROUP BY log_shape_id
    """,
    conn,
)
total_logs = _history.n_logs.sum()


def find_shapes(text=None, component=None, state=None):
    """log_shapes.search as a table, with each shape's counts over the whole history, most common first.

    `text` is a part of the template, or a list of parts to find any of them.
    """
    found = pd.DataFrame([asdict(s) for s in log_shapes.search(text, component, state)], columns=["id", "component", "state", "template"])
    found = found.rename(columns={"id": "log_shape_id"}).merge(_history, on="log_shape_id")
    found["share"] = (found.n_logs / total_logs).round(3)
    return found.sort_values("n_logs", ascending=False, ignore_index=True)


# the log investigated for each of the 17 most common log shapes, most common first.
# each is pinned by its line in HPC.log, so a rebuilt database gives the same 17 logs
CASE_LINES = [
    "272454 Interconnect-0N02 switch_module error 1079615335 1 Linkerror event interval expired",
    "397274 node-77 node temperature 1142528008 1 ambient=26",
    "124215 gige3 gige temperature 1111285570 1 warning",
    "34965 gige7 gige temperature 1076505552 1 normal",
    "41953 Interconnect-0N00 switch_module fan 1125932190 1 Fan speeds ( 3552 3534 3375 **** 3515 3479 )",
    "206751 node-194 node status 1131561040 1 running",
    "387046 node-240 node status 1087500721 1 configured out",
    "228944 Interconnect-1N00 switch_module error 1132349919 1 link errors remain current",
    "459874 node-98 action start 1145551635 1 boot  (command 4220)",
    "257391 node-94 action start 1079070412 1 wait  (command 2616)",
    "136777 node-168 unix.hw net.niff.up 1111865528 1 NIFF: node node-168 has detected an available network connection on network 5.5.224.0 via interface alt0",
    "400027 node-221 node status 1089893873 1 not responding",
    "289439 node-155 unix.hw net.niff.up 1134671788 1 NIFF: node node-155 has detected an available network connection on network 10.128.0.0 via interface ee0",
    "172313 node-D0 clusterfilesystem clusterfilesystem.no_server 1077891371 1 ClusterFileSystem: There is no server for ServerFileSystem domain storage612",
    "443071 gige7 gige temperature 1144041012 1 critical",
    "2557201 full partition status 1072935036 1 running",
    r"350533 node-200 unix.hw state_change.unavailable 1084642252 1 Component State Change: Component \042alt0\042 is in the unavailable state (HWID=2538)",
]
top = find_shapes().head(len(CASE_LINES))


def find_log(line):
    # read the row's time from the table, then read the log through search
    rows = conn.execute("SELECT id, ts FROM logs WHERE original_log = ?", (line,)).fetchall()
    assert len(rows) == 1, f"{len(rows)} logs have the line {line!r}"
    log_id, ts = rows[0][0], datetime.fromisoformat(rows[0][1])
    return next(log for log in logs.search(ts, ts, limit=None) if log.id == log_id)


cases = [(shape, find_log(line)) for shape, line in zip(top.itertuples(), CASE_LINES)]
assert all(log.log_shape_id == shape.log_shape_id for shape, log in cases)


def show(number):
    """Print case `number` (1 to 17) and return its log shape and its log."""
    shape, log = cases[number - 1]
    print(f"log shape {shape.log_shape_id}: {shape.component} | {shape.state} | {shape.template}")
    print(f"{shape.n_logs:,} logs ({shape.share:.1%}) from {shape.n_nodes} nodes, {shape.first_seen} to {shape.last_seen}")
    print(f"log {log.id} at {log.ts}: {log.original_log}")
    return shape, log


def shape_id(component, state, template):
    return next(s.id for s in log_shapes.search(component=component, state=state) if s.template == template)


BOOT = shape_id("action", "start", "boot (command <N>)")
WAIT = shape_id("action", "start", "wait (command <N>)")
NOT_RESPONDING = shape_id("node", "status", "not responding")


def as_frame(found):
    """The logs returned by logs.search as a table, oldest first."""
    columns = ["id", "ts", "node", "component", "state", "message", "log_shape_id"]
    return pd.DataFrame([asdict(log) for log in found], columns=columns).sort_values(["ts", "id"], ignore_index=True)


def timeline(node, start, end):
    """logs.node_timeline as a table."""
    entries = pd.DataFrame([asdict(e) for e in logs.node_timeline(node, start, end)])
    return entries[["first_ts", "last_ts", "count", "component", "state", "template"]]


def per_hour(start, end, **filters):
    """Log count of every hour that has logs. count_by alone returns only the 20 largest groups."""
    counts = logs.count_by("hour", start, end, limit=100_000, **filters)
    return pd.Series(dict(counts), dtype=float).sort_index()


def shapes_between(start, end, **filters):
    """Every log shape seen in the range, in order of first appearance."""
    found = as_frame(logs.search(start, end, limit=None, **filters))
    found = found.merge(find_shapes()[["log_shape_id", "template"]], on="log_shape_id")
    summary = found.groupby(["component", "state", "template"]).agg(
        n_logs=("id", "size"), n_sources=("node", "nunique"), first=("ts", "min"), last=("ts", "max")
    )
    return summary.sort_values("first").reset_index()


def gige_levels(start, end):
    """How many times each gige device reported each temperature level."""
    levels = {level: dict(logs.count_by("node", start, end, component="gige", text=level)) for level in ["normal", "warning", "critical"]}
    return pd.DataFrame(levels).fillna(0).astype(int).sort_index()


def minutes_at_level(entries):
    """For a timeline in which every line is a change of level: the minutes from each line to the next, per level."""
    changes = pd.to_datetime(entries.first_ts)
    minutes = changes.diff().shift(-1).dt.total_seconds().div(60)
    return minutes.groupby(entries.template).agg(times="count", median="median", longest="max", total="sum").round(1)


def preceded_by(found, log_shape_id, within):
    """For each row of a table from as_frame: True when the same node has a log of the given shape up to `within` before it."""
    earlier = as_frame(logs.search(found.ts.min() - within, found.ts.max(), log_shape_id=log_shape_id, limit=None))
    earlier = earlier.rename(columns={"ts": "earlier_ts"})[["earlier_ts", "node"]]
    joined = pd.merge_asof(found[["ts", "node"]], earlier, left_on="ts", right_on="earlier_ts", by="node", tolerance=pd.Timedelta(within))
    return joined.earlier_ts.notna()
