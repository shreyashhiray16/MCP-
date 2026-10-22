"""
src/db/connection.py

SQLite connection management for Pune Transit MCP Server.
Provides read-only connections for queries and read-write connections for user saved places.
"""

import sqlite3
from typing import Generator
from contextlib import contextmanager
from ..config import DB_PATH


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


@contextmanager
def get_db(db_path: str = DB_PATH, readonly: bool = False) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager yielding a SQLite connection configured with dict_factory.
    """
    if readonly:
        # URI mode for read-only
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(db_path)

    conn.row_factory = dict_factory
    try:
        yield conn
    finally:
        conn.close()
