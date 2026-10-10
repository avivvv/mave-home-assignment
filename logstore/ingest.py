from dataclasses import dataclass

from logstore.parsing import parse_lines
from logstore.templating import to_template


@dataclass(frozen=True)
class IngestResult:
    inserted: int
    new_log_shapes: int
    unparsed: list[str]
    # lines that repeated an event already stored, and were merged into its row
    copies_merged: int


def ingest_lines(lines, logs, log_shapes):
    """Parse raw log lines, register their log shapes and store them. A repeated line is merged into its row."""
    parsed, unparsed = parse_lines(lines)

    # mask each distinct message once
    template_of = {}
    for log in parsed:
        if log.message not in template_of:
            template_of[log.message] = to_template(log.message)

    keys = [(log.component, log.state, template_of[log.message]) for log in parsed]
    known = log_shapes.count()
    log_shape_ids = log_shapes.add_many(keys)
    for log, key in zip(parsed, keys):
        log.log_shape_id = log_shape_ids[key]
    inserted = logs.add_many(parsed)
    return IngestResult(inserted, log_shapes.count() - known, unparsed, len(parsed) - inserted)
