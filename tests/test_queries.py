from dataclasses import replace
from datetime import UTC, datetime

import pytest

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


# --- LogShapeRepository.stats ---


class TestLogShapeStats:
    def test_returns_one_row_per_log_shape(self, log_shapes, populated):
        assert len(log_shapes.stats()) == 3

    def test_log_count(self, log_shapes, populated):
        by_key = {(s.component, s.state, s.template): s for s in log_shapes.stats()}
        assert by_key[("node", "status", "running")].n_logs == 5
        assert by_key[("node", "status", "ambient=<N>")].n_logs == 3
        assert by_key[("domain", "status", "not responding")].n_logs == 1

    def test_node_count(self, log_shapes, populated):
        by_key = {(s.component, s.state, s.template): s for s in log_shapes.stats()}
        assert by_key[("node", "status", "running")].n_nodes == 2
        assert by_key[("domain", "status", "not responding")].n_nodes == 1

    def test_first_and_last_seen(self, log_shapes, populated):
        base = populated["base"]
        by_key = {(s.component, s.state, s.template): s for s in log_shapes.stats()}
        running = by_key[("node", "status", "running")]
        assert running.first_seen == _ts(base)
        assert running.last_seen == _ts(base + 7200)

    def test_three_example_messages(self, log_shapes, populated):
        by_key = {(s.component, s.state, s.template): s for s in log_shapes.stats()}
        assert len(by_key[("node", "status", "running")].examples) == 3
        assert len(by_key[("domain", "status", "not responding")].examples) >= 1

    def test_examples_are_real_messages(self, log_shapes, populated):
        for s in log_shapes.stats():
            for ex in s.examples:
                assert isinstance(ex, str) and len(ex) > 0

    def test_empty_database(self, log_shapes):
        assert log_shapes.stats() == []


# --- LogRepository.around ---


class TestLogsAround:
    def test_returns_logs_within_window(self, logs, populated):
        base = populated["base"]
        rows = logs.around("node-1", _utc(base + 600), before_s=600, after_s=600)
        # 10:00, 10:05, 10:10, 10:15
        assert len(rows) == 4
        times = [r.ts for r in rows]
        assert times == sorted(times)

    def test_only_returns_the_given_node(self, logs, populated):
        rows = logs.around("node-1", _utc(populated["base"] + 600), before_s=86400, after_s=86400)
        assert {r.node for r in rows} == {"node-1"}

    def test_window_boundaries(self, logs, populated):
        rows = logs.around("node-1", _utc(populated["base"] + 300), before_s=0, after_s=0)
        assert len(rows) == 1

    def test_no_results_for_unknown_node(self, logs, populated):
        assert logs.around("node-99", _utc(populated["base"]), before_s=3600, after_s=3600) == []


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
