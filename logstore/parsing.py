import random
import re
from datetime import UTC, datetime
from pathlib import Path

from logstore.models import Log

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "original_dataset" / "HPC.log"
SAMPLE_SEED = 0

LINE_RE = re.compile(r"^(\d+) (.*?) (\S+) (\S+) (\d+(?:\.\d+)?) (-?\d)(?: (.*))?$")
EPOCH_RE = re.compile(r"\d{10}")


def read_log_lines(path):
    with open(path, "rb") as f:
        return [l for l in f.read().decode("ascii").split("\r\n") if l]


def sample_lines(lines, n, seed=SAMPLE_SEED):
    """n random lines, kept in file order."""
    if n > len(lines):
        raise ValueError(f"cannot sample {n:,} lines from {len(lines):,}")
    picked = sorted(random.Random(seed).sample(range(len(lines)), n))
    return [lines[i] for i in picked]


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
        log_shape_id=None,
    )


def parse_lines(lines):
    """Returns (parsed logs, lines that did not parse), each in input order."""
    logs, unparsed = [], []
    for line in lines:
        log = parse_line(line)
        if log is None:
            unparsed.append(line)
        else:
            logs.append(log)
    return logs, unparsed
