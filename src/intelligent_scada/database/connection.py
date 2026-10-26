"""PostgreSQL connection lifecycle helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class DatabaseConfigurationError(RuntimeError):
    """Raised when a database operation is attempted without a connection string."""


def connect(conn_str: str | None) -> Any:
    if not conn_str:
        raise DatabaseConfigurationError(
            "PG_CONN_STR is not configured. Copy .env.example to .env and set it."
        )
    import psycopg2

    return psycopg2.connect(conn_str)


@contextmanager
def transaction(conn_str: str | None) -> Iterator[Any]:
    connection = connect(conn_str)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
