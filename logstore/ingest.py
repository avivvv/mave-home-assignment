from dataclasses import dataclass

from logstore.parsing import parse_lines
from logstore.templating import to_template


@dataclass(frozen=True)
class IngestResult:
    inserted: int
    new_templates: int
    unparsed: list[str]


def ingest_lines(lines, logs, templates):
    """Parse raw log lines, register their templates and store them."""
    parsed, unparsed = parse_lines(lines)

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
    return IngestResult(inserted, templates.count() - known, unparsed)
