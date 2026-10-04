import re
from datetime import UTC, datetime

from logstore.models import Log

LINE_RE = re.compile(r"^(\d+) (.*?) (\S+) (\S+) (\d+(?:\.\d+)?) (-?\d)(?: (.*))?$")
EPOCH_RE = re.compile(r"\d{10}")


def read_log_lines(path):
    with open(path, "rb") as f:
        return [l for l in f.read().decode("ascii").split("\r\n") if l]


def parse_line(line):
    line = line.rstrip("\r\n")
    m = LINE_RE.match(line)
    if m is None:
        return None
    event_id, node, component, state, time, flag, message = m.groups()
    bad_time = EPOCH_RE.fullmatch(time) is None
    # naive UTC, same as pd.to_datetime(unit="s")
    ts = None if bad_time else datetime.fromtimestamp(int(time), UTC).replace(tzinfo=None)
    return Log(
        id=None,
        event_id=int(event_id),
        node=node,
        component=component,
        state=state,
        time=float(time),
        flag=int(flag),
        message=message or "",
        bad_time=bad_time,
        ts=ts,
        original_log=line,
        template_id=None,
    )
