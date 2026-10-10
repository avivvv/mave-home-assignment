from datetime import datetime, timedelta
from operator import attrgetter

from logstore.models import Log, LogShape, LogStats, TimelineEntry

LOG_COLUMNS = (
    "id", "event_id", "node", "component", "state", "time", "flag",
    "message", "bad_time", "ts", "original_log", "log_shape_id", "n_copies",
)
INSERT_COLUMNS = LOG_COLUMNS[1:]
TS_POSITION = INSERT_COLUMNS.index("ts")
insert_values = attrgetter(*INSERT_COLUMNS)
# the columns that identify an event; a line that repeats them is the same event again
EVENT_KEY = ("node", "component", "state", "time", "message")

SELECT_LOGS = f"SELECT {', '.join(LOG_COLUMNS)} FROM logs"
# a repeated line does not add a row: the row takes the latest line and counts it
INSERT_LOG = (
    f"INSERT INTO logs ({', '.join(INSERT_COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(INSERT_COLUMNS))}) "
    f"ON CONFLICT ({', '.join(EVENT_KEY)}) DO UPDATE SET "
    "event_id = excluded.event_id, flag = excluded.flag, original_log = excluded.original_log, "
    "n_copies = logs.n_copies + 1"
)
# what count_by can group on, and the SQL that gives the group; an hour is 'YYYY-MM-DD HH'
GROUP_BY = {
    "node": "node",
    "component": "component",
    "log_shape": "log_shape_id",
    "hour": "substr(ts, 1, 13)",
}
# the longest time range one read may cover
MAX_RANGE = timedelta(days=31)


def _check_time_range(start, end):
    # every read is bounded in time, so no call can pull the whole table
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise ValueError(f"start and end must be datetimes, got {start!r} and {end!r}")
    if end < start:
        raise ValueError(f"the time range ends before it starts: {start} to {end}")
    if end - start > MAX_RANGE:
        raise ValueError(f"the time range is longer than {MAX_RANGE.days} days: {start} to {end}")


def _to_db(value):
    # datetimes are stored as 'YYYY-MM-DD HH:MM:SS'
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return value


def _to_row(log):
    row = list(insert_values(log))
    row[TS_POSITION] = _to_db(row[TS_POSITION])
    return row


def _to_log(row):
    values = dict(zip(LOG_COLUMNS, row))
    values["bad_time"] = bool(values["bad_time"])
    values["ts"] = datetime.fromisoformat(values["ts"]) if values["ts"] else None
    return Log(**values)


class LogShapeRepository:
    def __init__(self, conn):
        self.conn = conn

    def add_many(self, keys):
        """Insert the (component, state, template) keys that are not stored yet. Returns {key: id} for all of them."""
        keys = list(dict.fromkeys(keys))
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO log_shapes (component, state, template) VALUES (?, ?, ?)",
                keys,
            )
        ids = {s.key: s.id for s in self.list_all()}
        return {key: ids[key] for key in keys}

    def list_all(self):
        rows = self.conn.execute("SELECT id, component, state, template FROM log_shapes ORDER BY id")
        return [LogShape(*row) for row in rows]

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM log_shapes").fetchone()[0]


class LogRepository:
    """Every read takes a time range, start <= ts <= end, of at most MAX_RANGE."""

    def __init__(self, conn):
        self.conn = conn

    def add_many(self, logs):
        """Bulk insert in one transaction. Ids are assigned by the database. Returns the number of new rows."""
        before = self.count()
        with self.conn:
            self.conn.executemany(INSERT_LOG, map(_to_row, logs))
        return self.count() - before

    def search(self, start, end, node=None, component=None, text=None, log_shape_id=None, limit=1000) -> list[Log]:
        """The logs of a time range that pass every given filter, newest first.

        `text` is a part of the message, in any letter case.
        """
        where, params = self._filters(start, end, node, component, text, log_shape_id)
        sql = f"{SELECT_LOGS} WHERE {where} ORDER BY ts DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params = (*params, limit)
        return [_to_log(row) for row in self.conn.execute(sql, params)]

    def count_by(self, group_by, start, end, node=None, component=None, text=None, log_shape_id=None, limit=20) -> list[tuple[str, int]]:
        """Log counts per group, as (group, count), largest first. Takes the filters of search.

        `group_by` is node, component, log_shape (the group is the log shape id) or hour ('YYYY-MM-DD HH').
        """
        if group_by not in GROUP_BY:
            raise ValueError(f"unknown group: {group_by!r}, expected one of {sorted(GROUP_BY)}")
        where, params = self._filters(start, end, node, component, text, log_shape_id)
        sql = f"SELECT {GROUP_BY[group_by]} AS grp, COUNT(*) AS n FROM logs WHERE {where} GROUP BY grp ORDER BY n DESC, grp LIMIT ?"
        return self.conn.execute(sql, (*params, limit)).fetchall()

    def stats(self, start, end, node=None, component=None, text=None, log_shape_id=None) -> LogStats:
        """Log count, node count, first seen and last seen of the logs that search would return.

        The stats of a log shape in the hour before a moment are stats(ts - hour, ts, log_shape_id=...).
        """
        where, params = self._filters(start, end, node, component, text, log_shape_id)
        sql = f"SELECT COUNT(*), COUNT(DISTINCT node), MIN(ts), MAX(ts) FROM logs WHERE {where}"
        return LogStats(*self.conn.execute(sql, params).fetchone())

    def node_timeline(self, node, start, end) -> list[TimelineEntry]:
        """Logs of one node in a time range, oldest first, with runs of the same log shape collapsed."""
        _check_time_range(start, end)
        rows = self.conn.execute(
            "SELECT l.ts, l.component, l.state, s.template, l.log_shape_id "
            "FROM logs l JOIN log_shapes s ON l.log_shape_id = s.id "
            "WHERE l.node = ? AND l.ts >= ? AND l.ts <= ? "
            "ORDER BY l.ts, l.id",
            (node, _to_db(start), _to_db(end)),
        ).fetchall()
        if not rows:
            return []
        timeline = []
        cur_ts, cur_comp, cur_state, cur_tpl, cur_tid = rows[0]
        cur_last, cur_count = cur_ts, 1
        for ts_s, comp, state, tpl, tid in rows[1:]:
            if tid == cur_tid:
                cur_last = ts_s
                cur_count += 1
            else:
                timeline.append(TimelineEntry(cur_comp, cur_state, cur_tpl, cur_tid, cur_ts, cur_last, cur_count))
                cur_ts, cur_last, cur_comp, cur_state, cur_tpl, cur_tid = ts_s, ts_s, comp, state, tpl, tid
                cur_count = 1
        timeline.append(TimelineEntry(cur_comp, cur_state, cur_tpl, cur_tid, cur_ts, cur_last, cur_count))
        return timeline

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]

    def _filters(self, start, end, node, component, text, log_shape_id):
        """The WHERE clause and parameters shared by search, count_by and stats. A filter left as None is not applied."""
        _check_time_range(start, end)
        clauses, params = ["ts >= ?", "ts <= ?"], [_to_db(start), _to_db(end)]
        for column, value in (("node", node), ("component", component), ("log_shape_id", log_shape_id)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if text is not None:
            clauses.append("instr(lower(message), lower(?)) > 0")
            params.append(text)
        return " AND ".join(clauses), tuple(params)
