import pytest

from logstore.db import connect
from logstore.repositories import LogRepository
from scripts.build_db import build, main

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
    assert (result.inserted, result.new_log_shapes, result.unparsed) == (3, 2, [])
    conn = connect(db_path)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    conn.close()
    assert {"ix_logs_ts", "ix_logs_log_shape_ts"} <= names


def test_build_refuses_to_load_twice(log_path, db_path):
    build(log_path, db_path)
    with pytest.raises(FileExistsError, match="already holds 3 logs"):
        build(log_path, db_path)
    assert count_logs(db_path) == 3


def test_rebuild_with_a_missing_log_file_keeps_the_database(tmp_path, log_path, db_path):
    build(log_path, db_path)
    with pytest.raises(FileNotFoundError, match="missing.log"):
        build(tmp_path / "missing.log", db_path, rebuild=True)
    assert count_logs(db_path) == 3


def test_a_missing_log_file_does_not_create_a_database(tmp_path, db_path):
    with pytest.raises(FileNotFoundError):
        build(tmp_path / "missing.log", db_path)
    assert not db_path.exists()


def test_sampling_more_lines_than_the_file_has_is_an_error(log_path, db_path):
    with pytest.raises(ValueError, match="cannot sample 5 lines from 3"):
        build(log_path, db_path, sample=5)
    assert not db_path.exists()


def test_rebuild_with_too_large_a_sample_keeps_the_database(log_path, db_path):
    build(log_path, db_path)
    with pytest.raises(ValueError):
        build(log_path, db_path, sample=5, rebuild=True)
    assert count_logs(db_path) == 3


def test_main_exits_with_the_error_message(tmp_path, db_path):
    with pytest.raises(SystemExit, match="missing.log"):
        main(["--log", str(tmp_path / "missing.log"), "--db", str(db_path)])


def test_rebuild_starts_from_an_empty_database(log_path, db_path):
    build(log_path, db_path)
    build(log_path, db_path, rebuild=True)
    assert count_logs(db_path) == 3


def test_build_with_sample_loads_only_that_many_lines(log_path, db_path):
    build(log_path, db_path, sample=2)
    assert count_logs(db_path) == 2
