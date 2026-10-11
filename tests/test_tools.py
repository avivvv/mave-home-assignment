from datetime import datetime, timedelta

import pytest

from agent.tools import MAX_ROWS, RUNNERS, TOOLS, LogTools, run_tool, tool_purposes
from tests.test_queries import DAY, _ts, _utc, make_log, populated  # noqa: F401

START, END = (d.isoformat(sep=" ") for d in DAY)
HOUR = timedelta(hours=1)


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

    def test_what_followed_sees_nothing_after_the_visible_time(self, tools, populated):
        # at 10:10 node-1 has logged 'running' three times and its 'ambient' of 10:15 does not exist yet
        tools.visible = at(populated, 600)
        occurrences, nothing_after, followed = tools.what_followed(populated["running"], *DAY, HOUR)
        assert (occurrences, nothing_after) == (3, 1)
        assert followed.template.tolist() == ["running"] and followed.occurrences_followed.tolist() == [2]


# --- the tables ---


class TestTables:
    def test_find_log_shapes_gives_whole_history_counts_most_common_first(self, tools):
        shapes = tools.find_log_shapes()
        assert list(shapes.template) == ["running", "ambient=<N>", "not responding"]
        assert list(shapes.n_logs) == [5, 3, 1]

    def test_an_empty_timeline_is_an_empty_table(self, tools):
        assert tools.node_timeline("node-9", *DAY).empty

    def test_a_timeline_can_carry_log_shape_ids(self, tools, populated):
        assert "log_shape_id" not in tools.node_timeline("node-1", *DAY)
        assert tools.node_timeline("node-1", *DAY, shape_ids=True).log_shape_id.tolist() == [populated["running"], populated["ambient"], populated["running"]]

    def test_shapes_between_is_in_order_of_first_appearance(self, tools):
        assert list(tools.shapes_between(*DAY).template) == ["running", "ambient=<N>", "not responding"]


class TestWhatFollowed:
    def test_it_counts_per_occurrence_what_the_same_source_logged_after(self, tools, populated):
        # 'running': node-1 at 10:00, 10:05, 10:10 and 12:00, node-2 at 10:30. node-1 logs 'ambient' at 10:15
        occurrences, nothing_after, followed = tools.what_followed(populated["running"], *DAY, HOUR)
        assert (occurrences, nothing_after) == (5, 2)
        rows = followed.set_index("template")
        # 'ambient' follows the first three, after 15, 10 and 5 minutes; 'running' follows the first two, after 5 minutes
        assert rows.occurrences_followed.to_dict() == {"ambient=<N>": 3, "running": 2}
        assert rows.share.to_dict() == {"ambient=<N>": 0.6, "running": 0.4}
        assert rows.median_minutes.to_dict() == {"ambient=<N>": 10.0, "running": 5.0}
        assert rows.log_shape_id.to_dict() == {"ambient=<N>": populated["ambient"], "running": populated["running"]}

    def test_a_shorter_wait_and_a_single_source_narrow_it(self, tools, populated):
        occurrences, nothing_after, followed = tools.what_followed(populated["running"], *DAY, timedelta(minutes=5))
        assert (occurrences, nothing_after) == (5, 2) and followed.occurrences_followed.to_dict() == {0: 2, 1: 1}
        assert tools.what_followed(populated["running"], *DAY, HOUR, node="node-2")[:2] == (1, 1)

    def test_another_source_never_counts_as_following(self, tools, populated):
        # domain-1's only log is 'not responding' at 10:20; other sources log after it, domain-1 does not
        assert tools.what_followed(populated["notresp"], *DAY, HOUR)[:2] == (1, 1)

    def test_a_shape_with_no_log_in_the_range_gives_nothing(self, tools):
        occurrences, nothing_after, followed = tools.what_followed(999, *DAY, HOUR)
        assert (occurrences, nothing_after) == (0, 0) and followed.empty


# --- the tools as the model calls them ---


WHY = {"reasoning": "To see what the node logged."}


def call(tools, name, **args):
    return run_tool(tools, name, {**WHY, **args})


class TestRunTool:
    def test_every_tool_described_to_the_model_can_be_run(self):
        assert [tool["function"]["name"] for tool in TOOLS] == list(RUNNERS)
        assert list(RUNNERS) == ["search_logs", "node_timeline", "log_shapes_between", "count_logs", "find_log_shapes", "what_followed"]

    def test_every_tool_asks_for_a_reasoning_first(self):
        for tool in TOOLS:
            parameters = tool["function"]["parameters"]
            assert list(parameters["properties"])[0] == "reasoning" and parameters["required"][0] == "reasoning"

    def test_every_description_says_what_the_tool_returns_and_what_it_is_for(self):
        for tool in TOOLS:
            description = tool["function"]["description"]
            assert "Returns" in description or "returns" in description, tool["function"]["name"]
            assert "Use it" in description, tool["function"]["name"]
        assert tool_purposes().count("\n") == len(TOOLS) - 1 and "- what_followed: Hindsight" in tool_purposes()

    @pytest.mark.parametrize("args", [{}, {"reasoning": ""}, {"reasoning": "   "}])
    def test_a_call_with_no_reasoning_is_refused(self, tools, args):
        result = run_tool(tools, "search_logs", {"start": START, "end": END, **args})
        assert result.text.startswith("error:") and "reasoning" in result.text and result.log_ids == ()

    def test_search_logs_returns_the_ids_it_showed(self, tools, populated):
        result = call(tools, "search_logs", start=START, end=END, node="node-2")
        assert "ambient=29" in result.text and len(result.log_ids) == 3
        assert set(result.log_shape_ids) == {populated["ambient"], populated["running"]}
        assert all(str(log_id) in result.text for log_id in result.log_ids)

    def test_search_logs_says_how_many_logs_it_left_out_and_returns_only_the_ids_shown(self, tools):
        result = call(tools, "search_logs", start=START, end=END, limit=2)
        assert "7 older logs not shown" in result.text and "newest 2 of 9" in result.text and len(result.log_ids) == 2

    @pytest.mark.parametrize("limit, shown", [(0, 1), (-5, 1), (10_000, 9)])
    def test_a_limit_outside_1_to_max_rows_is_brought_inside(self, tools, limit, shown):
        assert len(call(tools, "search_logs", start=START, end=END, limit=limit).log_ids) == shown

    def test_the_shape_tools_return_log_shape_ids_and_show_them(self, tools, populated):
        every = {populated["running"], populated["ambient"], populated["notresp"]}
        timeline = call(tools, "node_timeline", node="node-1", start=START, end=END)
        assert set(timeline.log_shape_ids) == {populated["running"], populated["ambient"]} and "log_shape_id" in timeline.text
        between = call(tools, "log_shapes_between", start=START, end=END)
        assert set(between.log_shape_ids) == every and "log_shape_id" in between.text
        # still in order of first appearance: 'running' at 10:00, 'ambient' at 10:02, 'not responding' at 10:20
        assert between.text.index("running") < between.text.index("ambient=<N>") < between.text.index("not responding")
        assert set(call(tools, "find_log_shapes", text=["respond"]).log_shape_ids) == {populated["notresp"]}
        followed = call(tools, "what_followed", log_shape_id=populated["running"], start=START, end=END)
        assert set(followed.log_shape_ids) == {populated["running"], populated["ambient"]}
        assert "5 occurrences" in followed.text and "2 of them had no other log" in followed.text
        assert f"no logs of log shape 999" in call(tools, "what_followed", log_shape_id=999, start=START, end=END).text

    def test_count_logs_gives_counts_and_no_ids(self, tools):
        per_hour = call(tools, "count_logs", group_by="hour", start=START, end=END)
        assert "2004-11-09 10" in per_hour.text and per_hour.log_ids == () and per_hour.log_shape_ids == ()
        assert "node-1" in call(tools, "count_logs", group_by="node", start=START, end=END).text

    def test_a_long_table_says_how_many_rows_it_left_out(self, conn, logs, populated):
        # with node-1, node-2 and domain-1 already there, node-100 onwards makes MAX_ROWS + 6 groups
        logs.add_many([make_log(populated["base"] + 20000 + i, f"node-{100 + i}", "node", "status", "running", populated["running"]) for i in range(MAX_ROWS + 3)])
        result = call(LogTools(conn), "count_logs", group_by="node", start=START, end=END)
        assert "6 more rows not shown" in result.text

    def test_a_tool_never_shows_a_log_after_the_visible_time(self, tools, populated):
        tools.visible = at(populated, 900)
        result = call(tools, "search_logs", start=START, end=END)
        assert "ambient=31" in result.text and "not responding" not in result.text and len(result.log_ids) == 5
        assert populated["notresp"] not in call(tools, "log_shapes_between", start=START, end=END).log_shape_ids

    def test_a_range_that_starts_exactly_at_the_visible_time_is_allowed(self, tools, populated):
        tools.visible = at(populated, 900)
        assert len(call(tools, "search_logs", start=_ts(populated["base"] + 900), end=END).log_ids) == 1

    def test_an_empty_result_says_so(self, tools):
        assert call(tools, "node_timeline", node="node-9", start=START, end=END).text == "no rows"
        assert call(tools, "search_logs", start=START, end=END, text="no such text").text == "no rows"
        assert call(tools, "find_log_shapes", text=["no such text"]).text == "no rows"

    @pytest.mark.parametrize("name, args, message", [
        ("delete_logs", {}, "unknown tool"),
        ("get_stats", {"start": START, "end": END}, "unknown tool"),
        ("search_logs", {"start": START}, "missing"),
        ("search_logs", {"start": START, "end": END, "colour": "red"}, "search_logs has no argument colour"),
        # the mistake a real model made: an argument of another tool
        ("log_shapes_between", {"start": START, "end": END, "limit": 5}, "log_shapes_between has no argument limit"),
        ("search_logs", {"start": "yesterday", "end": END}, "Invalid isoformat"),
        ("search_logs", {"start": "2004-10-01 00:00:00", "end": END}, "longer than 31 days"),
        ("search_logs", {"start": END, "end": START}, "ends before it starts"),
        ("count_logs", {"group_by": "colour", "start": START, "end": END}, "unknown group"),
        ("search_logs", {"start": START, "end": END, "limit": "many"}, "invalid literal"),
        ("what_followed", {"log_shape_id": 1, "start": START, "end": END, "within_minutes": "soon"}, "invalid literal"),
    ])
    def test_a_bad_call_returns_an_error_and_does_not_raise(self, tools, name, args, message):
        result = run_tool(tools, name, {**WHY, **args})
        assert result.text.startswith("error:") and message in result.text
        assert result.log_ids == () and result.log_shape_ids == ()

    @pytest.mark.parametrize("args", [["start", "end"], "start=now", None, 7])
    def test_arguments_that_are_not_an_object_return_an_error(self, tools, args):
        assert run_tool(tools, "search_logs", args).text.startswith("error:")


def test_shape_history_counts_everything_up_to_a_time(logs, populated):
    whole = {row[0]: row[1:] for row in logs.shape_history()}
    assert whole[populated["running"]][:2] == (5, 2)
    early = {row[0]: row[1:] for row in logs.shape_history(datetime(2004, 11, 9, 10, 15))}
    assert populated["notresp"] not in early
    assert early[populated["ambient"]] == (2, 2, _ts(populated["base"] + 120), _ts(populated["base"] + 900))


def test_find_by_line_returns_the_log_with_exactly_that_raw_line(logs, populated):
    line = f"9 domain-1 domain status {populated['base'] + 1200} 1 not responding"
    found = logs.find_by_line(line)
    assert [(log.node, log.message, log.log_shape_id) for log in found] == [("domain-1", "not responding", populated["notresp"])]
    assert logs.find_by_line(line + " ") == [] and logs.find_by_line("no such line") == []
