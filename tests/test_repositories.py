import sqlite3
from dataclasses import replace
from datetime import datetime

import pytest

from logstore.models import Template
from logstore.parsing import parse_line


def make_log(time, node, message, template_id):
    return replace(parse_line(f"7 {node} node status {time} 1 {message}"), template_id=template_id)


def ids(rows):
    return [log.id for log in rows]


@pytest.fixture
def template_ids(logs, templates):
    t = templates.add_many(["running", "ambient=<N>"])
    logs.add_many([
        make_log(1100000300, "node-1", "running", t["running"]),         # id 1, 11:38:20
        make_log(1100000100, "node-2", "ambient=30", t["ambient=<N>"]),  # id 2, 11:35:00
        make_log(1100000200, "node-1", "ambient=31", t["ambient=<N>"]),  # id 3, 11:36:40
        make_log(1100000200, "node-2", "running", t["running"]),         # id 4, same ts as id 3
        make_log("15.560", "node-3", "running", t["running"]),           # id 5, bad timestamp
        make_log(1100000400, "node-2", "ambient=32", t["ambient=<N>"]),  # id 6, 11:40:00
    ])
    return t


def test_templates_get_ids_in_insertion_order(templates):
    assert templates.add_many(["b", "a"]) == {"b": 1, "a": 2}
    assert templates.list_all() == [Template(1, "b"), Template(2, "a")]


def test_adding_a_known_template_returns_its_id(templates):
    templates.add_many(["a", "b"])
    assert templates.add("a") == 1
    assert templates.add("c") == 3
    assert templates.count() == 3


def test_add_many_with_a_mix_of_known_and_new_templates(templates):
    templates.add_many(["a", "b"])
    assert templates.add_many(["b", "c", "a", "d"]) == {"b": 2, "c": 3, "a": 1, "d": 4}
    assert templates.list_all() == [Template(1, "a"), Template(2, "b"), Template(3, "c"), Template(4, "d")]


def test_template_lookups(templates):
    templates.add("a")
    assert templates.get(1) == Template(1, "a")
    assert templates.get_by_text("a") == Template(1, "a")
    assert templates.get(2) is None
    assert templates.get_by_text("missing") is None


def test_add_many_assigns_ids_and_keeps_fields(logs, templates):
    log = make_log(1100000300, "node-1", "running", templates.add("running"))
    assert logs.add_many([log, log]) == 2
    assert logs.find() == [replace(log, id=1), replace(log, id=2)]
    assert logs.count() == 2


def test_log_needs_a_stored_template(logs):
    with pytest.raises(sqlite3.IntegrityError):
        logs.add_many([make_log(1100000300, "node-1", "running", 99)])
    assert logs.count() == 0


def test_reads_are_oldest_first(logs, template_ids):
    assert ids(logs.find()) == [5, 2, 3, 4, 1, 6]


def test_last_is_newest_first(logs, template_ids):
    assert ids(logs.last(3)) == [6, 1, 4]


def test_by_time_range_includes_start_and_excludes_end(logs, template_ids):
    start, end = datetime(2004, 11, 9, 11, 36, 40), datetime(2004, 11, 9, 11, 40, 0)
    assert ids(logs.by_time_range(start, end)) == [3, 4, 1]
    assert ids(logs.by_time_range(start, end, limit=2)) == [3, 4]


def test_by_template_id(logs, template_ids):
    assert ids(logs.by_template_id(template_ids["running"])) == [5, 4, 1]
    assert ids(logs.by_template_id(template_ids["ambient=<N>"], limit=2)) == [2, 3]


def test_last_by_template(logs, template_ids):
    assert ids(logs.last_by_template("running", 2)) == [1, 4]
    assert ids(logs.last_by_template("ambient=<N>", 10)) == [6, 3, 2]


def test_find_filters_on_all_given_columns(logs, template_ids):
    assert ids(logs.find(node="node-2")) == [2, 4, 6]
    assert ids(logs.find(node="node-2", message="running")) == [4]
    assert ids(logs.find(flag=1, limit=2)) == [5, 2]
    assert ids(logs.find(bad_time=True)) == [5]
    assert ids(logs.find(ts=datetime(2004, 11, 9, 11, 36, 40))) == [3, 4]
    assert logs.find(node="missing") == []


def test_find_rejects_unknown_columns(logs, template_ids):
    with pytest.raises(ValueError):
        logs.find(nod="node-2")


def test_duplicate_templates_in_one_call_are_stored_once(templates):
    assert templates.add_many(["a", "a", "b"]) == {"a": 1, "b": 2}
    assert templates.count() == 2


def test_failed_batch_stores_nothing(logs, templates):
    good = make_log(1100000300, "node-1", "running", templates.add("running"))
    bad = make_log(1100000300, "node-1", "running", 99)
    with pytest.raises(sqlite3.IntegrityError):
        logs.add_many([good, bad])
    assert logs.count() == 0


def test_logs_without_ts_are_left_out_of_time_queries(logs, template_ids):
    assert ids(logs.last(100)) == [6, 1, 4, 3, 2]
    assert ids(logs.last_by_template("running", 100)) == [1, 4]
    assert ids(logs.by_time_range(datetime(1970, 1, 1), datetime(2100, 1, 1))) == [2, 3, 4, 1, 6]
    assert ids(logs.find(ts=None)) == [5]


def test_last_zero_returns_nothing(logs, template_ids):
    assert logs.last(0) == []
    assert logs.last_by_template("running", 0) == []


def test_unknown_template_returns_nothing(logs, template_ids):
    assert logs.last_by_template("missing", 10) == []
    assert logs.by_template_id(99) == []


def test_find_does_not_run_sql_from_values_or_column_names(logs, template_ids):
    assert logs.find(node="node-2' OR '1'='1") == []
    with pytest.raises(ValueError):
        logs.find(**{"node = 'node-2' OR 1=1 --": 1})
    assert logs.count() == 6
