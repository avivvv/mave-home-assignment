from datetime import datetime

from logstore.ingest import ingest_lines

LINES = [
    "1 node-1 node temperature 1100000100 1 ambient=30",
    "2 node-2 node temperature 1100000200 1 ambient=31",
    "3 node-1 node status 1100000300 1 running",
]
# the day the lines of these tests fall in; reads come back newest first
DAY = (datetime(2004, 11, 9), datetime(2004, 11, 10))


def test_ingest_stores_logs_and_their_log_shapes(logs, log_shapes):
    result = ingest_lines(LINES, logs, log_shapes)
    assert (result.inserted, result.new_log_shapes, result.unparsed) == (3, 2, [])
    assert [s.key for s in log_shapes.list_all()] == [("node", "temperature", "ambient=<N>"), ("node", "status", "running")]
    assert [(log.original_log, log.log_shape_id) for log in logs.search(*DAY)] == [
        (LINES[2], 2),
        (LINES[1], 1),
        (LINES[0], 1),
    ]


def test_unparsed_lines_are_returned_and_not_stored(logs, log_shapes):
    result = ingest_lines([LINES[0], "garbage"], logs, log_shapes)
    assert result.inserted == 1
    assert result.unparsed == ["garbage"]
    assert logs.count() == 1


def test_later_ingest_reuses_known_log_shapes_and_adds_new_ones(logs, log_shapes):
    ingest_lines(LINES, logs, log_shapes)
    result = ingest_lines(
        [
            "4 node-3 node temperature 1100000400 1 ambient=32",
            "5 node-3 node status 1100000500 1 halted",
        ],
        logs,
        log_shapes,
    )
    assert (result.inserted, result.new_log_shapes) == (2, 1)
    assert [(s.id, s.key) for s in log_shapes.list_all()][2] == (3, ("node", "status", "halted"))
    assert [log.log_shape_id for log in logs.search(*DAY, limit=2)] == [3, 1]


def test_ingesting_nothing(logs, log_shapes):
    result = ingest_lines([], logs, log_shapes)
    assert (result.inserted, result.new_log_shapes, result.unparsed) == (0, 0, [])
    assert logs.count() == 0


def test_empty_message_gets_the_empty_template(logs, log_shapes):
    line = "281151 node-191 node temperature 1120315831 0 "
    ingest_lines([line], logs, log_shapes)
    assert [(s.id, s.key) for s in log_shapes.list_all()] == [(1, ("node", "temperature", ""))]
    stored = logs.search(datetime(2005, 7, 2), datetime(2005, 7, 3))
    assert [(log.message, log.log_shape_id) for log in stored] == [("", 1)]


def test_the_same_message_under_another_component_or_state_gets_its_own_log_shape(logs, log_shapes):
    lines = [
        "1 node-1 node status 1100000100 1 not responding",
        "2 node-D1 domain status 1100000200 1 not responding",
    ]
    result = ingest_lines(lines, logs, log_shapes)
    assert result.new_log_shapes == 2
    assert [log.log_shape_id for log in logs.search(*DAY)] == [2, 1]
    assert [log.event_id for log in logs.search(*DAY, component="domain")] == [2]


def test_a_repeated_line_is_merged_into_its_row_and_the_latest_line_is_kept(logs, log_shapes):
    lines = [
        "10 node-1 node status 1100000300 0 running",
        "11 node-1 node status 1100000300 1 running",
    ]
    result = ingest_lines(lines, logs, log_shapes)
    assert (result.inserted, result.copies_merged, result.new_log_shapes) == (1, 1, 1)
    assert [(log.event_id, log.flag, log.n_copies, log.original_log) for log in logs.search(*DAY)] == [(11, 1, 2, lines[1])]


def test_a_repeat_is_merged_even_when_other_lines_come_between(logs, log_shapes):
    lines = [
        "10 node-1 node status 1100000300 1 running",
        "11 node-2 node status 1100000300 1 running",
        "12 node-1 node status 1100000300 1 running",
    ]
    result = ingest_lines(lines, logs, log_shapes)
    assert (result.inserted, result.copies_merged) == (2, 1)
    assert [(log.event_id, log.n_copies) for log in logs.search(*DAY)] == [(11, 1), (12, 2)]


def test_a_repeat_that_arrives_in_a_later_ingest_is_merged_too(logs, log_shapes):
    ingest_lines(["10 node-1 node status 1100000300 0 running"], logs, log_shapes)
    result = ingest_lines(["11 node-1 node status 1100000300 1 running"], logs, log_shapes)
    assert (result.inserted, result.copies_merged, result.new_log_shapes) == (0, 1, 0)
    assert [(log.flag, log.n_copies) for log in logs.search(*DAY)] == [(1, 2)]


def test_ingest_without_repeats_merges_nothing(logs, log_shapes):
    assert ingest_lines(LINES, logs, log_shapes).copies_merged == 0
    assert [log.n_copies for log in logs.search(*DAY)] == [1, 1, 1]
