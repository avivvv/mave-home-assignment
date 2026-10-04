from datetime import datetime

import pytest

from logstore.parsing import parse_line

LINE = "460903 resourcemgmtdaeomon node-25 server subsys 1145552216 1 failed to configure resourcemgmt subsystem err = 10"


def test_parse_line_reads_every_field():
    log = parse_line(LINE)
    assert log.event_id == 460903
    assert log.node == "resourcemgmtdaeomon node-25"
    assert log.component == "server"
    assert log.state == "subsys"
    assert log.time == 1145552216.0
    assert log.flag == 1
    assert log.message == "failed to configure resourcemgmt subsystem err = 10"
    assert log.bad_time is False
    assert log.ts == datetime(2006, 4, 20, 16, 56, 56)
    assert log.original_log == LINE
    assert log.id is None
    assert log.template_id is None


@pytest.mark.parametrize("node", ["node-25", "resourcemgmtdaeomon node-25", "rack 3 node-25"])
def test_node_can_be_one_word_or_more(node):
    log = parse_line(f"460903 {node} server subsys 1145552216 1 failed to configure resourcemgmt subsystem err = 10")
    assert log.event_id == 460903
    assert log.node == node
    assert log.component == "server"
    assert log.state == "subsys"
    assert log.message == "failed to configure resourcemgmt subsystem err = 10"


def test_negative_flag():
    log = parse_line("101441 Interconnect-1T03 switch_module control 1077729220 -1 power/control ok")
    assert log.flag == -1
    assert log.message == "power/control ok"


def test_bad_timestamp_has_no_ts():
    log = parse_line("91065 gige4 gige temperature 15.560 1 normal")
    assert log.bad_time is True
    assert log.ts is None
    assert log.time == 15.56


def test_unparseable_line_returns_none():
    assert parse_line("not a log line") is None


def test_trailing_newline_is_stripped():
    assert parse_line(LINE + "\r\n") == parse_line(LINE)


def test_empty_message():
    # with and without the space after the flag
    for line in ["281151 node-191 node temperature 1120315831 0 ", "281151 node-191 node temperature 1120315831 0"]:
        log = parse_line(line)
        assert log.message == ""
        assert log.flag == 0
        assert log.original_log == line
