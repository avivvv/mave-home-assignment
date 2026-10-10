"""Smoke test of the log store on its own database file.

Loads a sample with build_db, ingests three lines through the API and reads them back.

Run from the repo root: python -m scripts.db_smoke_test
"""
from datetime import datetime, timedelta

from logstore.db import DEFAULT_DB_PATH, connect
from logstore.ingest import ingest_lines
from logstore.repositories import LogRepository, LogShapeRepository
from logstore.templating import to_template
from scripts.build_db import build

SMOKE_DB_PATH = DEFAULT_DB_PATH.with_name("smoke_test.db")
SAMPLE_SIZE = 1000
NEW_MESSAGE = "smoke test message 42"
NEW_KEY = ("node", "status", "smoke test message <N>")
GARBAGE = "this is not a log line"


def check_read(label, rows, expected_ids):
    print(f"   {label}")
    for log in rows:
        source = "api" if log.id > SAMPLE_SIZE else "build_db"
        print(f"      {log.id:>4}  {log.ts}  {source:8}  {log.node}  {log.message}")
    assert [log.id for log in rows] == expected_ids, label


def run(conn, logs, log_shapes):
    assert logs.count() == SAMPLE_SIZE
    shape_id = {s.key: s.id for s in log_shapes.list_all()}
    # the checks on the sample read the table directly: the repository reads take a time range
    sampled = conn.execute("SELECT component, state, message, log_shape_id FROM logs").fetchall()
    assert all(
        shape_id[(component, state, to_template(message))] == log_shape_id
        for component, state, message, log_shape_id in sampled
    )

    print("2. ingest three lines through the API: a known log shape, a new log shape, garbage")
    node, component, state, time, message, newest_ts, known_shape_id = conn.execute(
        "SELECT node, component, state, time, message, ts, log_shape_id FROM logs "
        "WHERE ts IS NOT NULL ORDER BY ts DESC, id DESC LIMIT 1"
    ).fetchone()
    time = int(time)
    lines = [
        f"900001 {node} {component} {state} {time + 60} 1 {message}",
        f"900002 smoke-node node status {time + 120} 1 {NEW_MESSAGE}",
        GARBAGE,
    ]
    result = ingest_lines(lines, logs, log_shapes)
    print(f"   inserted {result.inserted}, new log shapes {result.new_log_shapes}, unparsed {result.unparsed}")
    assert result.inserted == 2
    assert result.new_log_shapes == 1
    assert result.unparsed == [GARBAGE]
    assert logs.count() == SAMPLE_SIZE + 2

    print("3. read them back")
    first, second = SAMPLE_SIZE + 1, SAMPLE_SIZE + 2
    new_shape_id = {s.key: s.id for s in log_shapes.list_all()}[NEW_KEY]
    # the hour after the newest sampled log holds exactly the two ingested lines
    start = datetime.fromisoformat(newest_ts) + timedelta(seconds=1)
    hour = (start, start + timedelta(hours=1))
    check_read("search(the hour after the newest sampled log)", logs.search(*hour), [second, first])
    check_read(f"search(log_shape_id={known_shape_id})", logs.search(*hour, log_shape_id=known_shape_id), [first])
    check_read(f"search(log_shape_id={new_shape_id})", logs.search(*hour, log_shape_id=new_shape_id), [second])
    check_read("search(node='smoke-node')", logs.search(*hour, node="smoke-node"), [second])
    assert logs.stats(*hour).n_logs == 2
    assert logs.count_by("log_shape", *hour) == [(known_shape_id, 1), (new_shape_id, 1)]


def main():
    print(f"1. load {SAMPLE_SIZE} sampled lines into {SMOKE_DB_PATH.name} with build_db")
    build(db_path=SMOKE_DB_PATH, sample=SAMPLE_SIZE, rebuild=True)

    conn = connect(SMOKE_DB_PATH)
    try:
        run(conn, LogRepository(conn), LogShapeRepository(conn))
    finally:
        conn.close()
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
