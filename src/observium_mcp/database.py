"""Database connection and query handling for Observium MySQL database."""

import os
from contextlib import contextmanager
from typing import Any, Generator, Optional

import mysql.connector
from mysql.connector import MySQLConnection
from mysql.connector.cursor import MySQLCursor


def get_db_config() -> dict[str, Any]:
    """Get database configuration from environment variables."""
    return {
        "host": os.getenv("OBSERVIUM_DB_HOST", "localhost"),
        "port": int(os.getenv("OBSERVIUM_DB_PORT", "3306")),
        "database": os.getenv("OBSERVIUM_DB_NAME", "observium"),
        "user": os.getenv("OBSERVIUM_DB_USER", "observium"),
        "password": os.getenv("OBSERVIUM_DB_PASS", ""),
    }


@contextmanager
def get_connection() -> Generator[MySQLConnection, None, None]:
    """Context manager for database connections."""
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor(dictionary: bool = True) -> Generator[MySQLCursor, None, None]:
    """Context manager for database cursors with automatic connection handling."""
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=dictionary)
        try:
            yield cursor
        finally:
            cursor.close()


def execute_query(
    query: str,
    params: Optional[tuple] = None,
    dictionary: bool = True
) -> list[dict[str, Any]] | list[tuple]:
    """Execute a query and return all results."""
    with get_cursor(dictionary=dictionary) as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchall()


def execute_single(
    query: str,
    params: Optional[tuple] = None,
    dictionary: bool = True
) -> Optional[dict[str, Any] | tuple]:
    """Execute a query and return a single result."""
    with get_cursor(dictionary=dictionary) as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchone()
