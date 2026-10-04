"""Smoke test of the log store on its own database file.

Loads a sample with build_db, ingests three lines through the API and reads them back.

Run from the repo root: python -m scripts.smoke_test
"""
from datetime import timedelta

from logstore.db import DEFAULT_DB_PATH, connect
from logstore.ingest import ingest_lines
from logstore.repositories import LogRepository, TemplateRepository
from logstore.templating import to_template
from scripts.build_db import build

SMOKE_DB_PATH = DEFAULT_DB_PATH.with_name("smoke_test.db")
SAMPLE_SIZE = 1000
NEW_MESSAGE = "smoke test message 42"
NEW_TEMPLATE = "smoke test message <N>"
GARBAGE = "this is not a log line"


def check_read(label, rows, expected_ids):
    print(f"   {label}")
    for log in rows:
        source = "api" if log.id > SAMPLE_SIZE else "build_db"
        print(f"      {log.id:>4}  {log.ts}  {source:8}  {log.node}  {log.message}")
    assert [log.id for log in rows] == expected_ids, label


def run(logs, templates):
    sampled = logs.find()
    assert len(sampled) == SAMPLE_SIZE
    template_text = {t.id: t.template for t in templates.list_all()}
    assert all(template_text[log.template_id] == to_template(log.message) for log in sampled)

    print("2. ingest three lines through the API: a known template, a new template, garbage")
    newest = logs.last(1)[0]
    known_template = template_text[newest.template_id]
    time = int(newest.time)
    lines = [
        f"900001 {newest.node} {newest.component} {newest.state} {time + 60} 1 {newest.message}",
        f"900002 smoke-node node status {time + 120} 1 {NEW_MESSAGE}",
        GARBAGE,
    ]
    result = ingest_lines(lines, logs, templates)
    print(f"   inserted {result.inserted}, new templates {result.new_templates}, unparsed {result.unparsed}")
    assert result.inserted == 2
    assert result.new_templates == 1
    assert result.unparsed == [GARBAGE]
    assert logs.count() == SAMPLE_SIZE + 2

    print("3. read them back")
    first, second = SAMPLE_SIZE + 1, SAMPLE_SIZE + 2
    new_template = templates.get_by_text(NEW_TEMPLATE)
    assert new_template is not None
    after_newest = newest.ts + timedelta(seconds=1)
    check_read("last(2)", logs.last(2), [second, first])
    check_read(f"last_by_template({known_template!r}, 2)", logs.last_by_template(known_template, 2), [first, newest.id])
    check_read(f"last_by_template({NEW_TEMPLATE!r}, 5)", logs.last_by_template(NEW_TEMPLATE, 5), [second])
    check_read(f"by_template_id({new_template.id})", logs.by_template_id(new_template.id), [second])
    check_read("find(node='smoke-node')", logs.find(node="smoke-node"), [second])
    check_read(
        "by_time_range(the hour after the newest sampled log)",
        logs.by_time_range(after_newest, after_newest + timedelta(hours=1)),
        [first, second],
    )


def main():
    print(f"1. load {SAMPLE_SIZE} sampled lines into {SMOKE_DB_PATH.name} with build_db")
    build(db_path=SMOKE_DB_PATH, sample=SAMPLE_SIZE, rebuild=True)

    conn = connect(SMOKE_DB_PATH)
    try:
        run(LogRepository(conn), TemplateRepository(conn))
    finally:
        conn.close()
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
