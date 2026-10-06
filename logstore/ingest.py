from dataclasses import dataclass

from logstore.parsing import parse_lines
from logstore.templating import to_template


@dataclass(frozen=True)
class IngestResult:
    inserted: int
    new_templates: int
    unparsed: list[str]
    dropped_copies: int


def drop_copies(logs):
    """Keep the first log of each (node, component, state, time, message). Returns (kept, number dropped)."""
    seen, kept = set(), []
    for log in logs:
        key = (log.node, log.component, log.state, log.time, log.message)
        if key not in seen:
            seen.add(key)
            kept.append(log)
    return kept, len(logs) - len(kept)


def ingest_lines(lines, logs, templates):
    """Parse raw log lines, drop copies, register the templates and store the logs."""
    parsed, unparsed = parse_lines(lines)
    parsed, dropped = drop_copies(parsed)

    # mask each distinct message once
    template_of = {}
    for log in parsed:
        if log.message not in template_of:
            template_of[log.message] = to_template(log.message)

    keys = [(log.component, log.state, template_of[log.message]) for log in parsed]
    known = templates.count()
    template_ids = templates.add_many(keys)
    for log, key in zip(parsed, keys):
        log.template_id = template_ids[key]
    inserted = logs.add_many(parsed)
    return IngestResult(inserted, templates.count() - known, unparsed, dropped)
