from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Template:
    id: int
    template: str


@dataclass(slots=True)
class Log:
    # id and template_id are None until the log is stored
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
    template_id: int | None
