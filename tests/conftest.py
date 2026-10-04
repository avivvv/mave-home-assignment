import pytest

from logstore.db import connect, create_indexes, init_schema
from logstore.repositories import LogRepository, TemplateRepository


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
def templates(conn):
    return TemplateRepository(conn)
