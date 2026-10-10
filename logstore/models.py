from dataclasses import dataclass
from datetime import datetime


# the columns that identify a log shape; `template` is the masked message text
LOG_SHAPE_KEY = ("component", "state", "template")


@dataclass(frozen=True, slots=True)
class LogShape:
    id: int
    component: str
    state: str
    template: str

    @property
    def key(self):
        return (self.component, self.state, self.template)


@dataclass(slots=True)
class Log:
    # id and log_shape_id are None until the log is stored
    id: int | None
    event_id: int
    node: str
    component: str
    state: str
    time: float
    flag: int
    message: str
    bad_time: bool
    ts: datetime | None
    original_log: str
    log_shape_id: int | None
    # how many lines of the file reported this event
    n_copies: int = 1


@dataclass(frozen=True, slots=True)
class LogStats:
    # counts over a set of logs; first_seen and last_seen are None when the set is empty
    n_logs: int
    n_nodes: int
    first_seen: str | None
    last_seen: str | None


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    component: str
    state: str
    template: str
    log_shape_id: int
    first_ts: str
    last_ts: str
    count: int
