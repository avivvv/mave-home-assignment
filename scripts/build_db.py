"""Load HPC.log into the SQLite log store. Run from the repo root: python -m scripts.build_db"""
import argparse
import time
from pathlib import Path

from logstore.db import DEFAULT_DB_PATH, connect, create_indexes, init_schema
from logstore.ingest import ingest_lines
from logstore.parsing import DEFAULT_LOG_PATH, read_log_lines, sample_lines
from logstore.repositories import LogRepository, TemplateRepository


def build(log_path=DEFAULT_LOG_PATH, db_path=DEFAULT_DB_PATH, sample=None, rebuild=False):
    log_path, db_path = Path(log_path), Path(db_path)
    if not log_path.exists():
        raise FileNotFoundError(f"no log file at {log_path}")
    started = time.perf_counter()
    lines = read_log_lines(log_path)
    if sample is not None:
        lines = sample_lines(lines, sample)

    # the database is touched only once the lines to load are in hand
    if rebuild:
        db_path.unlink(missing_ok=True)
    conn = connect(db_path)
    try:
        init_schema(conn)
        logs, templates = LogRepository(conn), TemplateRepository(conn)
        if logs.count():
            raise FileExistsError(f"{db_path} already holds {logs.count():,} logs. Pass --rebuild to start over.")

        result = ingest_lines(lines, logs, templates)
        # indexes are built once, after the bulk insert
        create_indexes(conn)
        elapsed = time.perf_counter() - started

        print(f"logs:           {result.inserted:,}")
        print(f"templates:      {result.new_templates:,}")
        print(f"unparsed lines: {len(result.unparsed):,}")
        print(f"bad timestamps: {len(logs.find(bad_time=True)):,}")
        print(f"elapsed:        {elapsed:.1f}s")
        print(f"db:             {db_path}")
        return result
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Load HPC.log into the SQLite log store.")
    parser.add_argument("--log", default=DEFAULT_LOG_PATH, help="log file to load")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="database file to write")
    parser.add_argument("--sample", type=int, help="load only N random lines")
    parser.add_argument("--rebuild", action="store_true", help="delete the database file first")
    args = parser.parse_args(argv)
    try:
        build(args.log, args.db, args.sample, args.rebuild)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    main()
