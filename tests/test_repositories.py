import sqlite3
from dataclasses import replace
from datetime import datetime

import pytest

from logstore.models import LogShape
from logstore.parsing import parse_line


RUNNING = ("node", "status", "running")
AMBIENT = ("node", "status", "ambient=<N>")
# the day every log of these tests falls in
DAY = (datetime(2004, 11, 9), datetime(2004, 11, 10))


def key(template):
    return ("node", "status", template)


def add_shape(log_shapes, shape_key):
    return log_shapes.add_many([shape_key])[shape_key]


def make_log(time, node, message, log_shape_id, flag=1, event_id=7):
    return replace(parse_line(f"{event_id} {node} node status {time} {flag} {message}"), log_shape_id=log_shape_id)


def ids(rows):
    return [log.id for log in rows]


@pytest.fixture
def log_shape_ids(logs, log_shapes):
    t = log_shapes.add_many([RUNNING, AMBIENT])
    logs.add_many([
        make_log(1100000300, "node-1", "running", t[RUNNING]),     # id 1, 11:38:20
        make_log(1100000100, "node-2", "ambient=30", t[AMBIENT]),  # id 2, 11:35:00
        make_log(1100000200, "node-1", "ambient=31", t[AMBIENT]),  # id 3, 11:36:40
        make_log(1100000200, "node-2", "running", t[RUNNING]),     # id 4, same ts as id 3
        make_log("15.560", "node-3", "running", t[RUNNING]),       # id 5, bad timestamp
        make_log(1100000400, "node-2", "ambient=32", t[AMBIENT]),  # id 6, 11:40:00
    ])
    return t


def test_log_shapes_get_ids_in_insertion_order(log_shapes):
    assert log_shapes.add_many([key("b"), key("a")]) == {key("b"): 1, key("a"): 2}
    assert log_shapes.list_all() == [LogShape(1, "node", "status", "b"), LogShape(2, "node", "status", "a")]


def test_the_same_text_under_another_component_or_state_is_another_log_shape(log_shapes):
    keys = [("node", "status", "not responding"), ("domain", "status", "not responding"), ("node", "boot", "not responding")]
    assert log_shapes.add_many(keys) == {keys[0]: 1, keys[1]: 2, keys[2]: 3}
    assert log_shapes.list_all()[1] == LogShape(2, "domain", "status", "not responding")


def test_adding_a_known_log_shape_returns_its_id(log_shapes):
    log_shapes.add_many([key("a"), key("b")])
    assert log_shapes.add_many([key("a")]) == {key("a"): 1}
    assert log_shapes.add_many([key("c")]) == {key("c"): 3}
    assert log_shapes.count() == 3


def test_add_many_with_a_mix_of_known_and_new_log_shapes(log_shapes):
    log_shapes.add_many([key("a"), key("b")])
    added = log_shapes.add_many([key("b"), key("c"), key("a"), key("d")])
    assert added == {key("b"): 2, key("c"): 3, key("a"): 1, key("d"): 4}
    assert [(s.id, s.template) for s in log_shapes.list_all()] == [(1, "a"), (2, "b"), (3, "c"), (4, "d")]


def test_duplicate_log_shapes_in_one_call_are_stored_once(log_shapes):
    assert log_shapes.add_many([key("a"), key("a"), key("b")]) == {key("a"): 1, key("b"): 2}
    assert log_shapes.count() == 2


def test_stored_logs_get_ids_and_read_back_unchanged(logs, log_shapes):
    log_shape_id = add_shape(log_shapes, RUNNING)
    first = make_log(1100000300, "node-1", "running", log_shape_id)
    second = make_log(1100000300, "node-2", "running", log_shape_id)
    assert logs.add_many([first, second]) == 2
    assert logs.search(*DAY) == [replace(second, id=2), replace(first, id=1)]
    assert logs.count() == 2


def test_a_repeated_line_updates_its_row_instead_of_adding_one(logs, log_shapes):
    log_shape_id = add_shape(log_shapes, RUNNING)
    first = make_log(1100000300, "node-1", "running", log_shape_id, flag=0, event_id=10)
    repeat = make_log(1100000300, "node-1", "running", log_shape_id, flag=1, event_id=11)
    assert logs.add_many([first, repeat]) == 1
    assert logs.search(*DAY) == [replace(repeat, id=1, n_copies=2)]


def test_a_repeat_of_a_line_stored_by_an_earlier_call_updates_that_row(logs, log_shapes):
    log_shape_id = add_shape(log_shapes, RUNNING)
    first = make_log(1100000300, "node-1", "running", log_shape_id, flag=0)
    other = make_log(1100000300, "node-2", "running", log_shape_id)
    repeat = make_log(1100000300, "node-1", "running", log_shape_id, flag=1)
    assert logs.add_many([first, other]) == 2
    assert logs.add_many([repeat, repeat]) == 0
    assert logs.search(*DAY) == [replace(other, id=2), replace(repeat, id=1, n_copies=3)]


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("7 node-2 node status 1100000300 1 running", id="node"),
        pytest.param("7 node-1 domain status 1100000300 1 running", id="component"),
        pytest.param("7 node-1 node state 1100000300 1 running", id="state"),
        pytest.param("7 node-1 node status 1100000301 1 running", id="time"),
        pytest.param("7 node-1 node status 1100000300 1 halted", id="message"),
    ],
)
def test_a_line_that_differs_in_one_identifying_field_gets_its_own_row(logs, log_shapes, line):
    log_shape_id = add_shape(log_shapes, RUNNING)
    first = make_log(1100000300, "node-1", "running", log_shape_id)
    assert logs.add_many([first, replace(parse_line(line), log_shape_id=log_shape_id)]) == 2
    assert [log.n_copies for log in logs.search(*DAY)] == [1, 1]


def test_log_needs_a_stored_log_shape(logs):
    with pytest.raises(sqlite3.IntegrityError):
        logs.add_many([make_log(1100000300, "node-1", "running", 99)])
    assert logs.count() == 0


def test_failed_batch_stores_nothing(logs, log_shapes):
    good = make_log(1100000300, "node-1", "running", add_shape(log_shapes, RUNNING))
    bad = make_log(1100000300, "node-2", "running", 99)
    with pytest.raises(sqlite3.IntegrityError):
        logs.add_many([good, bad])
    assert logs.count() == 0


def test_reads_are_newest_first_and_leave_out_logs_without_ts(logs, log_shape_ids):
    assert ids(logs.search(*DAY)) == [6, 1, 4, 3, 2]
    assert ids(logs.search(*DAY, log_shape_id=log_shape_ids[RUNNING])) == [1, 4]
    assert logs.count() == 6
