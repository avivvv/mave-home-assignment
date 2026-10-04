from dataclasses import dataclass

from logstore.parsing import parse_line
from logstore.templating import to_template


@dataclass(frozen=True)
class IngestResult:
    inserted: int
    new_templates: int
    unparsed: list[str]


def ingest_lines(lines, logs, templates):
    """Parse raw log lines, register their templates and store them."""
    parsed, unparsed = [], []
    for line in lines:
        log = parse_line(line)
        if log is None:
            unparsed.append(line)
        else:
            parsed.append(log)

    # mask each distinct message once
    template_of = {}
    for log in parsed:
        if log.message not in template_of:
            template_of[log.message] = to_template(log.message)

    known = templates.count()
    template_ids = templates.add_many(template_of.values())
    for log in parsed:
        log.template_id = template_ids[template_of[log.message]]
    inserted = logs.add_many(parsed)
    return IngestResult(inserted, templates.count() - known, unparsed)
