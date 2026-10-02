"""Єдине з'єднання SQLite для всього проєкту (уникає database is locked)."""
from __future__ import annotations

import sqlite3
import threading

from config import DB_PATH

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA synchronous=NORMAL")
            _conn.execute("PRAGMA busy_timeout=10000")
            _conn.execute("PRAGMA foreign_keys=ON")
        return _conn
