"""SQLite connection helper for the CFB research tool."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "cfb.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't already exist. Safe to run repeatedly."""
    conn = get_conn()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print(f"Database ready at {DB_PATH}")


if __name__ == "__main__":
    init_db()
