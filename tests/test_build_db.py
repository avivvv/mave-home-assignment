import pytest

from logstore.db import connect
from logstore.repositories import LogRepository
from scripts.build_db import build, sample_lines

LINES = [
    "1 node-1 node temperature 1100000100 1 ambient=30",
    "2 node-2 node temperature 1100000200 1 ambient=31",
    "3 node-1 node status 1100000300 1 running",
]


@pytest.fixture
def log_path(tmp_path):
    path = tmp_path / "test.log"
    path.write_bytes("\r\n".join(LINES).encode("ascii") + b"\r\n")
    return path


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


def count_logs(db_path):
    conn = connect(db_path)
    try:
        return LogRepository(conn).count()
    finally:
        conn.close()


def test_build_loads_the_file_and_creates_the_indexes(log_path, db_path):
    result = build(log_path, db_path)
    assert (result.inserted, result.new_templates, result.unparsed) == (3, 2, [])
    conn = connect(db_path)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    conn.close()
    assert {"ix_logs_ts", "ix_logs_template_ts"} <= names


def test_build_refuses_to_load_twice(log_path, db_path):
    build(log_path, db_path)
    with pytest.raises(SystemExit):
        build(log_path, db_path)
    assert count_logs(db_path) == 3


def test_rebuild_starts_from_an_empty_database(log_path, db_path):
    build(log_path, db_path)
    build(log_path, db_path, rebuild=True)
    assert count_logs(db_path) == 3


def test_build_with_sample_loads_only_that_many_lines(log_path, db_path):
    build(log_path, db_path, sample=2)
    assert count_logs(db_path) == 2


def test_sample_lines_is_repeatable_and_keeps_file_order():
    lines = [str(i) for i in range(100)]
    picked = sample_lines(lines, 10)
    assert picked == sample_lines(lines, 10)
    assert len(set(picked)) == 10
    assert picked == sorted(picked, key=int)
