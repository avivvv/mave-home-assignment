"""What a model is given before it starts: its system prompt, and the starting context of the log under investigation."""
from datetime import timedelta
from pathlib import Path

import pandas as pd

from agent.tools import ToolResult, table_text

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
HOUR = timedelta(hours=1)
# how many sources and how many lines of the log shape the starting context shows
CONTEXT_ROWS = 20
# how many rounds an investigation may take; prompts/investigator_v1.md states the same number
MAX_ROUNDS = 4


def round_notice(round_number, max_rounds=MAX_ROUNDS):
    """The line that ends every message to the investigator: which round it is in, and when it is the last."""
    notice = f"Round {round_number} of {max_rounds}."
    return notice + " This is the last round." if round_number >= max_rounds else notice


def load_prompt(name):
    """The text of prompts/<name>.md, for example investigator_v1."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def starting_context(tools, log) -> ToolResult:
    """The message every investigation starts from, and the ids it shows.

    Three parts: the new log, its source's timeline for the hour before, and the same log shape over the whole
    cluster for the hour before. Both windows end at the log's own time and include it.
    """
    shape = next(s for s in tools.log_shapes.list_all() if s.id == log.log_shape_id)
    start = log.ts - HOUR
    timeline = tools.node_timeline(log.node, start, log.ts, shape_ids=True)
    stats = tools.stats(start, log.ts, log_shape_id=shape.id)
    per_source = pd.DataFrame(tools.count_logs("node", start, log.ts, limit=100_000, log_shape_id=shape.id), columns=["source", "n_logs"])
    newest = tools.search_logs(start, log.ts, limit=CONTEXT_ROWS, log_shape_id=shape.id)
    left_out = stats.n_logs - len(newest)

    text = "\n".join([
        "# 1. THE NEW LOG",
        f"It arrived just now. The present moment is {log.ts}.",
        f"log id: {log.id}",
        f"time: {log.ts}",
        f"source: {log.node}",
        f"component: {log.component}",
        f"state: {log.state}",
        f"message: {log.message}",
        f"log shape {shape.id}: {shape.component} | {shape.state} | {shape.template}",
        "",
        f"# 2. TIMELINE OF {log.node} IN THE HOUR BEFORE",
        f"Everything this source logged from {start} to {log.ts}, oldest first. The new log is in the last line.",
        table_text(timeline, keep="last"),
        "",
        "# 3. THE SAME LOG SHAPE OVER THE WHOLE CLUSTER IN THE HOUR BEFORE",
        f"Logs of log shape {shape.id} from {start} to {log.ts}, the new log included.",
        f"n_logs={stats.n_logs}, n_sources={stats.n_nodes}, first_seen={stats.first_seen}, last_seen={stats.last_seen}",
        "",
        "Logs per source, largest first:",
        table_text(per_source, max_rows=CONTEXT_ROWS),
        "",
        f"The newest {len(newest)} of these logs, oldest first" + (f" ({left_out} older ones are not shown):" if left_out else ":"),
        newest.to_string(index=False),
    ])
    log_ids = tuple(dict.fromkeys([log.id, *newest.id.tolist()]))
    shape_ids = tuple(dict.fromkeys(int(i) for i in [shape.id, *timeline.log_shape_id]))
    return ToolResult(text, log_ids, shape_ids)
