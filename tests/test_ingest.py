from logstore.ingest import ingest_lines

LINES = [
    "1 node-1 node temperature 1100000100 1 ambient=30",
    "2 node-2 node temperature 1100000200 1 ambient=31",
    "3 node-1 node status 1100000300 1 running",
]


def test_ingest_stores_logs_and_their_templates(logs, templates):
    result = ingest_lines(LINES, logs, templates)
    assert (result.inserted, result.new_templates, result.unparsed) == (3, 2, [])
    assert [t.key for t in templates.list_all()] == [("node", "temperature", "ambient=<N>"), ("node", "status", "running")]
    assert [(log.original_log, log.template_id) for log in logs.find()] == [
        (LINES[0], 1),
        (LINES[1], 1),
        (LINES[2], 2),
    ]


def test_unparsed_lines_are_returned_and_not_stored(logs, templates):
    result = ingest_lines([LINES[0], "garbage"], logs, templates)
    assert result.inserted == 1
    assert result.unparsed == ["garbage"]
    assert logs.count() == 1


def test_later_ingest_reuses_known_templates_and_adds_new_ones(logs, templates):
    ingest_lines(LINES, logs, templates)
    result = ingest_lines(
        [
            "4 node-3 node temperature 1100000400 1 ambient=32",
            "5 node-3 node status 1100000500 1 halted",
        ],
        logs,
        templates,
    )
    assert (result.inserted, result.new_templates) == (2, 1)
    assert templates.get_by_key(("node", "status", "halted")).id == 3
    assert [log.template_id for log in logs.last(2)] == [3, 1]


def test_ingesting_nothing(logs, templates):
    result = ingest_lines([], logs, templates)
    assert (result.inserted, result.new_templates, result.unparsed) == (0, 0, [])
    assert logs.count() == 0


def test_empty_message_gets_the_empty_template(logs, templates):
    line = "281151 node-191 node temperature 1120315831 0 "
    ingest_lines([line], logs, templates)
    assert templates.get_by_key(("node", "temperature", "")).id == 1
    assert [(log.message, log.template_id) for log in logs.find()] == [("", 1)]


def test_the_same_message_under_another_component_or_state_gets_its_own_template(logs, templates):
    lines = [
        "1 node-1 node status 1100000100 1 not responding",
        "2 node-D1 domain status 1100000200 1 not responding",
    ]
    result = ingest_lines(lines, logs, templates)
    assert result.new_templates == 2
    assert [log.template_id for log in logs.find()] == [1, 2]
    assert [log.event_id for log in logs.last_by_template(("domain", "status", "not responding"), 10)] == [2]


def test_a_repeated_line_is_merged_into_its_row_and_the_latest_line_is_kept(logs, templates):
    lines = [
        "10 node-1 node status 1100000300 0 running",
        "11 node-1 node status 1100000300 1 running",
    ]
    result = ingest_lines(lines, logs, templates)
    assert (result.inserted, result.copies_merged, result.new_templates) == (1, 1, 1)
    assert [(log.event_id, log.flag, log.n_copies, log.original_log) for log in logs.find()] == [(11, 1, 2, lines[1])]


def test_a_repeat_is_merged_even_when_other_lines_come_between(logs, templates):
    lines = [
        "10 node-1 node status 1100000300 1 running",
        "11 node-2 node status 1100000300 1 running",
        "12 node-1 node status 1100000300 1 running",
    ]
    result = ingest_lines(lines, logs, templates)
    assert (result.inserted, result.copies_merged) == (2, 1)
    assert [(log.event_id, log.n_copies) for log in logs.find()] == [(12, 2), (11, 1)]


def test_a_repeat_that_arrives_in_a_later_ingest_is_merged_too(logs, templates):
    ingest_lines(["10 node-1 node status 1100000300 0 running"], logs, templates)
    result = ingest_lines(["11 node-1 node status 1100000300 1 running"], logs, templates)
    assert (result.inserted, result.copies_merged, result.new_templates) == (0, 1, 0)
    assert [(log.flag, log.n_copies) for log in logs.find()] == [(1, 2)]


def test_ingest_without_repeats_merges_nothing(logs, templates):
    assert ingest_lines(LINES, logs, templates).copies_merged == 0
    assert [log.n_copies for log in logs.find()] == [1, 1, 1]
