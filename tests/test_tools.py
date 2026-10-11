from datetime import datetime, timedelta

import pytest

from agent.tools import MAX_ROWS, RUNNERS, TOOLS, LogTools, run_tool
from tests.test_queries import DAY, _ts, _utc, make_log, populated  # noqa: F401

START, END = (d.isoformat(sep=" ") for d in DAY)


@pytest.fixture
def tools(conn, populated):
    return LogTools(conn)


def at(populated, seconds):
    return _utc(populated["base"] + seconds)


# --- nothing later than the visible time is returned ---


class TestVisibleTime:
    def test_with_no_limit_every_log_of_the_range_is_returned(self, tools):
        assert len(tools.search_logs(*DAY)) == 9

    def test_search_stops_at_the_visible_time_and_includes_it(self, tools, populated):
        tools.visible = at(populated, 900)
        found = tools.search_logs(*DAY)
        assert len(found) == 5
        assert found.ts.max() == at(populated, 900)

    def test_the_same_call_sees_more_once_the_visible_time_has_moved(self, tools, populated):
        tools.visible = at(populated, 900)
        before = len(tools.search_logs(*DAY))
        tools.visible = at(populated, 1200)
        assert len(tools.search_logs(*DAY)) == before + 1

    def test_stats_counts_and_timeline_stop_at_the_visible_time(self, tools, populated):
        tools.visible = at(populated, 900)
        assert tools.stats(*DAY).n_logs == 5
        assert dict(tools.count_logs("node", *DAY)) == {"node-1": 4, "node-2": 1}
        assert tools.per_hour(*DAY).sum() == 5
        assert tools.node_timeline("node-1", *DAY)["count"].sum() == 4
        assert tools.shapes_between(*DAY).n_logs.sum() == 5

    def test_a_range_that_starts_after_the_visible_time_is_refused(self, tools, populated):
        tools.visible = at(populated, 900)
        with pytest.raises(ValueError, match="after the latest visible time"):
            tools.search_logs(at(populated, 1000), DAY[1])

    def test_a_log_shape_not_seen_yet_is_not_found(self, tools, populated):
        # 'not responding' is first logged at 1200 seconds
        tools.visible = at(populated, 900)
        assert set(tools.find_log_shapes().template) == {"running", "ambient=<N>"}
        tools.visible = at(populated, 1200)
        assert "not responding" in set(tools.find_log_shapes().template)

    def test_log_shape_counts_stop_at_the_visible_time(self, tools, populated):
        tools.visible = at(populated, 900)
        shapes = tools.find_log_shapes().set_index("template")
        assert shapes.n_logs.to_dict() == {"running": 3, "ambient=<N>": 2}
        assert shapes.last_seen["running"] == _ts(populated["base"] + 600)


# --- the tables ---


class TestTables:
    def test_find_log_shapes_gives_whole_history_counts_most_common_first(self, tools):
        shapes = tools.find_log_shapes()
        assert list(shapes.template) == ["running", "ambient=<N>", "not responding"]
        assert list(shapes.n_logs) == [5, 3, 1]

    def test_an_empty_timeline_is_an_empty_table(self, tools):
        assert tools.node_timeline("node-9", *DAY).empty

    def test_shapes_between_is_in_order_of_first_appearance(self, tools):
        assert list(tools.shapes_between(*DAY).template) == ["running", "ambient=<N>", "not responding"]

    def test_preceded_by_looks_only_back_and_only_on_the_same_node(self, tools, populated):
        ambient = tools.search_logs(*DAY, log_shape_id=populated["ambient"], limit=None)
        preceded = tools.preceded_by(ambient, populated["running"], timedelta(hours=1))
        # node-2 at 10:02 has no earlier 'running'; node-1 at 10:15 has; node-2 at 14:00 has one, but 3.5 hours before
        assert list(preceded) == [False, True, False]


# --- the tools as the model calls them ---


class TestRunTool:
    def test_every_tool_described_to_the_model_can_be_run(self):
        assert [tool["function"]["name"] for tool in TOOLS] == list(RUNNERS)

    def test_search_logs_returns_the_ids_it_showed(self, tools):
        result = run_tool(tools, "search_logs", {"start": START, "end": END, "node": "node-2"})
        assert len(result.log_ids) == 3
        assert "ambient=29" in result.text

    def test_search_logs_says_how_many_logs_it_left_out(self, tools):
        result = run_tool(tools, "search_logs", {"start": START, "end": END, "limit": 2})
        assert len(result.log_ids) == 2
        assert "7 older logs not shown" in result.text

    def test_a_long_table_says_how_many_rows_it_left_out(self, conn, logs, populated):
        # with node-1, node-2 and domain-1 already there, node-100 onwards makes MAX_ROWS + 6 groups
        logs.add_many([make_log(populated["base"] + 20000 + i, f"node-{100 + i}", "node", "status", "running", populated["running"]) for i in range(MAX_ROWS + 3)])
        result = run_tool(LogTools(conn), "count_logs", {"group_by": "node", "start": START, "end": END})
        assert "6 more rows not shown" in result.text

    def test_a_tool_never_shows_a_log_after_the_visible_time(self, tools, populated):
        tools.visible = at(populated, 900)
        result = run_tool(tools, "search_logs", {"start": START, "end": END})
        assert len(result.log_ids) == 5
        assert "not responding" not in result.text
        assert run_tool(tools, "get_stats", {"start": START, "end": END}).text.startswith("n_logs=5,")

    def test_each_table_tool_runs(self, tools, populated):
        times = {"start": START, "end": END}
        assert "2004-11-09 10" in run_tool(tools, "count_logs", {"group_by": "hour", **times}).text
        assert "running" in run_tool(tools, "node_timeline", {"node": "node-1", **times}).text
        assert "not responding" in run_tool(tools, "find_log_shapes", {"text": ["respond"]}).text
        assert "ambient=<N>" in run_tool(tools, "log_shapes_between", times).text
        assert "running" in run_tool(tools, "minutes_at_level", {"node": "node-1", **times}).text
        assert run_tool(tools, "gige_levels", times).text == "no rows"
        preceded = run_tool(tools, "preceded_by", {"log_shape_id": populated["ambient"], "earlier_log_shape_id": populated["running"], **times})
        assert "3 logs" in preceded.text and "1 of them (33%)" in preceded.text

    @pytest.mark.parametrize("name, args, message", [
        ("delete_logs", {}, "unknown tool"),
        ("search_logs", {"start": START}, "missing"),
        ("search_logs", {"start": START, "end": END, "colour": "red"}, "unexpected keyword"),
        ("search_logs", {"start": "yesterday", "end": END}, "Invalid isoformat"),
        ("search_logs", {"start": "2004-10-01 00:00:00", "end": END}, "longer than 31 days"),
        ("search_logs", {"start": END, "end": START}, "ends before it starts"),
        ("count_logs", {"group_by": "colour", "start": START, "end": END}, "unknown group"),
    ])
    def test_a_bad_call_returns_an_error_and_does_not_raise(self, tools, name, args, message):
        result = run_tool(tools, name, args)
        assert result.text.startswith("error:") and message in result.text
        assert result.log_ids == ()


def test_shape_history_counts_everything_up_to_a_time(logs, populated):
    whole = {row[0]: row[1:] for row in logs.shape_history()}
    assert whole[populated["running"]][:2] == (5, 2)
    early = {row[0]: row[1:] for row in logs.shape_history(datetime(2004, 11, 9, 10, 15))}
    assert populated["notresp"] not in early
    assert early[populated["ambient"]] == (2, 2, _ts(populated["base"] + 120), _ts(populated["base"] + 900))
