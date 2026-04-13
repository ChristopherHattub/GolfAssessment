import sqlite3
import os
from contextlib import contextmanager


DB_PATH = os.environ.get("DB_PATH", "reservations.db")



@contextmanager
def get_conn():
    """Yield a connection, commit on success, rollback on error, always close."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(255) NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS bays (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS reservations (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL REFERENCES users(id),
                bay_id    INTEGER NOT NULL REFERENCES bays(id),
                date      DATE    NOT NULL,
                timeslot  SMALLINT NOT NULL CHECK (timeslot BETWEEN 6 AND 17),
                UNIQUE (user_id, bay_id, date, timeslot)
            );
        """)
