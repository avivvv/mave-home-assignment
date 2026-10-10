import pytest

from logstore.db import connect, create_indexes, init_schema
from logstore.repositories import LogRepository, LogShapeRepository


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    create_indexes(conn)
    yield conn
    conn.close()


@pytest.fixture
def logs(conn):
    return LogRepository(conn)


@pytest.fixture
def log_shapes(conn):
    return LogShapeRepository(conn)
