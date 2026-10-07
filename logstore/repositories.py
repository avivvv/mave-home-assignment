from datetime import datetime, timedelta
from operator import attrgetter

from logstore.models import Log, Template, TemplateStat, TimelineEntry

LOG_COLUMNS = (
    "id", "event_id", "node", "component", "state", "time", "flag",
    "message", "bad_time", "ts", "original_log", "template_id", "n_copies",
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
SELECT_TEMPLATES = "SELECT id, component, state, template FROM templates"
KEY_EQUALS = "component = ? AND state = ? AND template = ?"
T_KEY_EQUALS = "t.component = ? AND t.state = ? AND t.template = ?"


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


class TemplateRepository:
    def __init__(self, conn):
        self.conn = conn

    def add_many(self, keys):
        """Insert the (component, state, template) keys that are not stored yet. Returns {key: id} for all of them."""
        keys = list(dict.fromkeys(keys))
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO templates (component, state, template) VALUES (?, ?, ?)",
                keys,
            )
        ids = {t.key: t.id for t in self.list_all()}
        return {key: ids[key] for key in keys}

    def add(self, key):
        return self.add_many([key])[key]

    def get(self, template_id):
        row = self.conn.execute(f"{SELECT_TEMPLATES} WHERE id = ?", (template_id,)).fetchone()
        return Template(*row) if row else None

    def get_by_key(self, key):
        row = self.conn.execute(f"{SELECT_TEMPLATES} WHERE {KEY_EQUALS}", tuple(key)).fetchone()
        return Template(*row) if row else None

    def list_all(self):
        rows = self.conn.execute(f"{SELECT_TEMPLATES} ORDER BY id")
        return [Template(*row) for row in rows]

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]

    def stats(self):
        """One row per template: log count, node count, first/last seen, three example messages."""
        rows = self.conn.execute("""
            SELECT t.component, t.state, t.template,
                   COUNT(*)               AS n_logs,
                   COUNT(DISTINCT l.node) AS n_nodes,
                   MIN(l.ts)              AS first_seen,
                   MAX(l.ts)              AS last_seen
            FROM templates t
            JOIN logs l ON l.template_id = t.id
            GROUP BY t.id
            ORDER BY n_logs DESC
        """).fetchall()
        return [
            TemplateStat(comp, state, tpl, n, nn, fs, ls,
                         self._spread_examples(comp, state, tpl, n))
            for comp, state, tpl, n, nn, fs, ls in rows
        ]

    def _spread_examples(self, component, state, template, n_logs):
        if n_logs == 0:
            return []
        if n_logs <= 3:
            rows = self.conn.execute(
                "SELECT l.message FROM logs l "
                "JOIN templates t ON l.template_id = t.id "
                f"WHERE {T_KEY_EQUALS} ORDER BY l.ts, l.id",
                (component, state, template),
            ).fetchall()
            return [r[0] for r in rows]
        messages = []
        for offset in [0, n_logs // 2, n_logs - 1]:
            row = self.conn.execute(
                "SELECT l.message FROM logs l "
                "JOIN templates t ON l.template_id = t.id "
                f"WHERE {T_KEY_EQUALS} ORDER BY l.ts, l.id LIMIT 1 OFFSET ?",
                (component, state, template, offset),
            ).fetchone()
            if row:
                messages.append(row[0])
        return messages


class LogRepository:
    """Reads return logs oldest first (ts, then id). The last* methods return newest first."""

    def __init__(self, conn):
        self.conn = conn

    def add_many(self, logs):
        """Bulk insert in one transaction. Ids are assigned by the database. Returns the number of new rows."""
        before = self.count()
        with self.conn:
            self.conn.executemany(INSERT_LOG, map(_to_row, logs))
        return self.count() - before

    def by_time_range(self, start, end, limit=None):
        """Logs with start <= ts < end."""
        return self._select("ts >= ? AND ts < ?", (_to_db(start), _to_db(end)), limit=limit)

    def last(self, n):
        return self._select("ts IS NOT NULL", order="ts DESC, id DESC", limit=n)

    def by_template_id(self, template_id, limit=None):
        return self._select("template_id = ?", (template_id,), limit=limit)

    def last_by_template(self, key, n):
        """The n newest logs of the template with this (component, state, template) key."""
        where = f"template_id = (SELECT id FROM templates WHERE {KEY_EQUALS}) AND ts IS NOT NULL"
        return self._select(where, tuple(key), order="ts DESC, id DESC", limit=n)

    def find(self, limit=None, **equals):
        """Logs where every given column equals the given value, e.g. find(node="node-25", flag=1)."""
        unknown = sorted(set(equals) - set(LOG_COLUMNS))
        if unknown:
            raise ValueError(f"unknown log columns: {unknown}")
        clauses, params = [], []
        for column, value in equals.items():
            if value is None:
                clauses.append(f"{column} IS NULL")
            else:
                clauses.append(f"{column} = ?")
                params.append(_to_db(value))
        return self._select(" AND ".join(clauses), tuple(params), limit=limit)

    def around(self, node, ts, before_s, after_s):
        """The logs of one node in a window around a moment, oldest first."""
        start = _to_db(ts - timedelta(seconds=before_s))
        end = _to_db(ts + timedelta(seconds=after_s))
        return self._select("node = ? AND ts >= ? AND ts <= ?", (node, start, end))

    def node_timeline(self, node, start, end):
        """Logs of one node in a window, with runs of the same template collapsed."""
        rows = self.conn.execute(
            "SELECT l.ts, l.component, l.state, t.template, l.template_id "
            "FROM logs l JOIN templates t ON l.template_id = t.id "
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

    def _select(self, where="", params=(), order="ts, id", limit=None):
        sql = SELECT_LOGS
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY {order}"
        if limit is not None:
            sql += " LIMIT ?"
            params = (*params, limit)
        return [_to_log(row) for row in self.conn.execute(sql, params)]
