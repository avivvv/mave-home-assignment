from dataclasses import replace
from datetime import UTC, datetime

import pytest

from logstore.models import LogStats
from logstore.parsing import parse_line


def _utc(epoch):
    """Naive UTC datetime from an epoch, matching the DB format."""
    return datetime.fromtimestamp(epoch, UTC).replace(tzinfo=None)


def _ts(epoch):
    return _utc(epoch).strftime("%Y-%m-%d %H:%M:%S")


def make_log(time, node, component, state, message, log_shape_id, flag=1, event_id=7):
    return replace(
        parse_line(f"{event_id} {node} {component} {state} {time} {flag} {message}"),
        log_shape_id=log_shape_id,
    )


# --- fixtures ---


@pytest.fixture
def populated(conn, logs, log_shapes):
    """A small dataset with three log shapes across three nodes, spread over time."""
    t = log_shapes.add_many([
        ("node", "status", "running"),
        ("node", "status", "ambient=<N>"),
        ("domain", "status", "not responding"),
    ])
    running = t[("node", "status", "running")]
    ambient = t[("node", "status", "ambient=<N>")]
    notresp = t[("domain", "status", "not responding")]

    # timestamps: 2004-11-09 around 10:00–14:00 UTC
    base = 1099994400  # 2004-11-09 10:00:00
    logs.add_many([
        # node-1: running at 10:00, 10:05, 10:10, ambient at 10:15, running at 12:00
        make_log(base,          "node-1", "node", "status", "running",    running, event_id=1),
        make_log(base + 300,    "node-1", "node", "status", "running",    running, event_id=2),
        make_log(base + 600,    "node-1", "node", "status", "running",    running, event_id=3),
        make_log(base + 900,    "node-1", "node", "status", "ambient=31", ambient, event_id=4),
        make_log(base + 7200,   "node-1", "node", "status", "running",    running, event_id=5),
        # node-2: ambient at 10:02, running at 10:30, ambient at 14:00
        make_log(base + 120,    "node-2", "node", "status", "ambient=29", ambient, event_id=6),
        make_log(base + 1800,   "node-2", "node", "status", "running",    running, event_id=7),
        make_log(base + 14400,  "node-2", "node", "status", "ambient=33", ambient, event_id=8),
        # domain-1: not responding at 10:20
        make_log(base + 1200,   "domain-1", "domain", "status", "not responding", notresp, event_id=9),
    ])
    return {
        "running": running, "ambient": ambient, "notresp": notresp,
        "base": base,
    }


# the day every log of the fixture falls in
DAY = (datetime(2004, 11, 9), datetime(2004, 11, 10))


# --- the time range every read takes ---


class TestTimeRange:
    def test_a_range_longer_than_31_days_is_refused_by_every_read(self, logs, populated):
        start, end = datetime(2004, 11, 1), datetime(2004, 12, 2, 0, 0, 1)
        with pytest.raises(ValueError, match="longer than 31 days"):
            logs.search(start, end)
        with pytest.raises(ValueError, match="longer than 31 days"):
            logs.count_by("node", start, end)
        with pytest.raises(ValueError, match="longer than 31 days"):
            logs.stats(start, end)
        with pytest.raises(ValueError, match="longer than 31 days"):
            logs.node_timeline("node-1", start, end)

    def test_a_range_of_exactly_31_days_is_allowed(self, logs, populated):
        assert len(logs.search(datetime(2004, 11, 1), datetime(2004, 12, 2))) == 9

    def test_a_range_that_ends_before_it_starts_is_refused(self, logs, populated):
        with pytest.raises(ValueError, match="ends before it starts"):
            logs.search(DAY[1], DAY[0])

    def test_a_missing_bound_is_refused(self, logs, populated):
        with pytest.raises(ValueError, match="must be datetimes"):
            logs.search(None, DAY[1])
        with pytest.raises(ValueError, match="must be datetimes"):
            logs.stats(DAY[0], "2004-11-10 00:00:00")


# --- LogRepository.search ---


class TestSearch:
    def test_returns_the_logs_of_the_range_newest_first(self, logs, populated):
        rows = logs.search(*DAY)
        assert len(rows) == 9
        assert [r.ts for r in rows] == sorted((r.ts for r in rows), reverse=True)

    def test_start_and_end_are_both_included(self, logs, populated):
        base = populated["base"]
        rows = logs.search(_utc(base + 300), _utc(base + 900), node="node-1")
        assert [r.ts for r in rows] == [_utc(base + 900), _utc(base + 600), _utc(base + 300)]

    def test_limit_keeps_the_newest(self, logs, populated):
        base = populated["base"]
        rows = logs.search(*DAY, node="node-1", limit=2)
        assert [r.ts for r in rows] == [_utc(base + 7200), _utc(base + 900)]

    def test_filters_by_node_and_component(self, logs, populated):
        assert {r.node for r in logs.search(*DAY, node="node-2")} == {"node-2"}
        assert len(logs.search(*DAY, node="node-2")) == 3
        assert [r.node for r in logs.search(*DAY, component="domain")] == ["domain-1"]

    def test_text_is_a_case_insensitive_substring_of_the_message(self, logs, populated):
        assert len(logs.search(*DAY, text="ambient")) == 3
        assert len(logs.search(*DAY, text="NOT RESP")) == 1
        assert logs.search(*DAY, text="panic") == []

    def test_text_is_not_a_pattern(self, logs, populated):
        assert logs.search(*DAY, text="%") == []
        assert logs.search(*DAY, text="runnin_") == []

    def test_filters_by_log_shape(self, logs, populated):
        rows = logs.search(*DAY, log_shape_id=populated["ambient"], node="node-2")
        assert [r.message for r in rows] == ["ambient=33", "ambient=29"]
        assert logs.search(*DAY, log_shape_id=99) == []

    def test_filters_combine(self, logs, populated):
        base = populated["base"]
        rows = logs.search(DAY[0], _utc(base + 600), node="node-1", text="running", limit=2)
        assert [r.ts for r in rows] == [_utc(base + 600), _utc(base + 300)]

    def test_a_value_is_never_run_as_sql(self, logs, populated):
        assert logs.search(*DAY, node="node-2' OR '1'='1") == []
        assert logs.count() == 9


# --- LogRepository.count_by ---


class TestCountBy:
    def test_groups_by_node_largest_first(self, logs, populated):
        assert logs.count_by("node", *DAY) == [("node-1", 5), ("node-2", 3), ("domain-1", 1)]

    def test_groups_by_component(self, logs, populated):
        assert logs.count_by("component", *DAY) == [("node", 8), ("domain", 1)]

    def test_groups_by_log_shape_id(self, logs, populated):
        assert logs.count_by("log_shape", *DAY) == [
            (populated["running"], 5), (populated["ambient"], 3), (populated["notresp"], 1),
        ]

    def test_groups_by_hour(self, logs, populated):
        assert logs.count_by("hour", *DAY) == [
            ("2004-11-09 10", 7), ("2004-11-09 12", 1), ("2004-11-09 14", 1),
        ]

    def test_takes_the_same_filters_as_search(self, logs, populated):
        base = populated["base"]
        assert logs.count_by("node", DAY[0], _utc(base + 1800), text="running") == [("node-1", 3), ("node-2", 1)]
        assert logs.count_by("hour", *DAY, log_shape_id=populated["ambient"], node="node-2") == [
            ("2004-11-09 10", 1), ("2004-11-09 14", 1),
        ]

    def test_limit_keeps_the_largest_groups(self, logs, populated):
        assert logs.count_by("node", *DAY, limit=1) == [("node-1", 5)]

    def test_nothing_matches(self, logs, populated):
        assert logs.count_by("node", *DAY, text="panic") == []

    def test_rejects_an_unknown_group(self, logs, populated):
        with pytest.raises(ValueError):
            logs.count_by("message", *DAY)


# --- LogRepository.stats ---


class TestStats:
    def test_one_log_shape(self, logs, populated):
        base = populated["base"]
        assert logs.stats(*DAY, log_shape_id=populated["running"]) == LogStats(5, 2, _ts(base), _ts(base + 7200))

    def test_no_filter_counts_every_log_of_the_range(self, logs, populated):
        stat = logs.stats(*DAY)
        assert (stat.n_logs, stat.n_nodes) == (9, 3)

    def test_a_time_window(self, logs, populated):
        base = populated["base"]
        stat = logs.stats(_utc(base - 1800), _utc(base + 1800), log_shape_id=populated["running"])
        assert stat == LogStats(4, 2, _ts(base), _ts(base + 1800))

    def test_start_and_end_are_both_included(self, logs, populated):
        base = populated["base"]
        assert logs.stats(_utc(base), _utc(base + 600), log_shape_id=populated["running"]).n_logs == 3

    def test_never_counts_a_log_after_the_end(self, logs, populated):
        base = populated["base"]
        stat = logs.stats(DAY[0], _utc(base + 600), log_shape_id=populated["running"])
        assert stat == LogStats(3, 1, _ts(base), _ts(base + 600))

    def test_empty_window(self, logs, populated):
        base = populated["base"]
        stat = logs.stats(_utc(base - 3600), _utc(base - 60), log_shape_id=populated["running"])
        assert stat == LogStats(0, 0, None, None)

    def test_one_node(self, logs, populated):
        base = populated["base"]
        stat = logs.stats(DAY[0], _utc(base + 7200), log_shape_id=populated["running"], node="node-2")
        assert (stat.n_logs, stat.n_nodes) == (1, 1)

    def test_empty_database(self, logs):
        assert logs.stats(*DAY) == LogStats(0, 0, None, None)


# --- LogRepository.node_timeline ---


class TestNodeTimeline:
    def test_collapses_consecutive_same_log_shape(self, logs, populated):
        base = populated["base"]
        tl = logs.node_timeline("node-1", _utc(base), _utc(base + 1000))
        assert len(tl) == 2
        assert tl[0].template == "running"
        assert tl[0].count == 3
        assert tl[1].template == "ambient=<N>"
        assert tl[1].count == 1

    def test_has_first_and_last_time(self, logs, populated):
        base = populated["base"]
        tl = logs.node_timeline("node-1", _utc(base), _utc(base + 1000))
        assert tl[0].first_ts == _ts(base)
        assert tl[0].last_ts == _ts(base + 600)

    def test_non_consecutive_same_log_shape_not_collapsed(self, logs, populated):
        base = populated["base"]
        tl = logs.node_timeline("node-1", _utc(base), _utc(base + 7201))
        assert len(tl) == 3
        assert [e.template for e in tl] == ["running", "ambient=<N>", "running"]
        assert tl[0].count == 3
        assert tl[2].count == 1

    def test_includes_component_and_state(self, logs, populated):
        base = populated["base"]
        tl = logs.node_timeline("node-1", _utc(base), _utc(base + 1000))
        assert tl[0].component == "node"
        assert tl[0].state == "status"

    def test_empty_for_unknown_node(self, logs, populated):
        base = populated["base"]
        assert logs.node_timeline("node-99", _utc(base), _utc(base + 86400)) == []

    def test_ordered_by_time(self, logs, populated):
        base = populated["base"]
        tl = logs.node_timeline("node-1", _utc(base), _utc(base + 86400))
        assert [e.first_ts for e in tl] == sorted(e.first_ts for e in tl)
