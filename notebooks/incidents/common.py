"""Shared setup of the notebooks in this folder: the database, the 17 pinned logs and the investigation helpers.

The helpers are the agent's tools (agent/tools.py), called here with no limit on what they may see.
"""
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
from agent.tools import LogTools, as_frame, minutes_at_level
from logstore.db import connect

pd.set_option("display.max_colwidth", 120)

conn = connect()
tools = LogTools(conn)
logs, log_shapes = tools.logs, tools.log_shapes
minute, hour, day = timedelta(minutes=1), timedelta(hours=1), timedelta(days=1)

find_shapes = tools.find_log_shapes
timeline = tools.node_timeline
per_hour = tools.per_hour
shapes_between = tools.shapes_between
gige_levels = tools.gige_levels
preceded_by = tools.preceded_by
total_logs = tools.history().n_logs.sum()


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
