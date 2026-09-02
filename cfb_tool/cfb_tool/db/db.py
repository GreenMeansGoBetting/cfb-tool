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


# Columns added to existing tables after their initial release —
# CREATE TABLE IF NOT EXISTS won't retrofit these onto a db.py that already
# ran once, so each entry here is applied by init_db() if missing.
_MIGRATIONS = [
    ("games", "venue_id", "INTEGER REFERENCES venues(venue_id)"),
]


def _apply_migrations(conn):
    for table, column, coltype in _MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            print(f"  migrated: added {table}.{column}")
    conn.commit()


def _drop_stale_tables(conn):
    """One-off reshapes that ALTER TABLE can't express (a changed primary
    key, or a foreign key that needs to follow it) — safe to
    drop-and-recreate because these tables were never populated under
    their old shape (neither has a sync_* step in ingest.py yet /
    player_game_stats is a known-unwired gap per the README).

    Each table's staleness is checked independently — CREATE TABLE IF NOT
    EXISTS silently no-ops on a table that already exists, so a partial
    migration (e.g. players rebuilt but a dependent table's stale FK
    surviving because ITS create statement never got to run) needs its
    own check rather than assuming one shared condition covers both."""
    players_cols = {r[1] for r in conn.execute("PRAGMA table_info(players)").fetchall()}
    if players_cols and "season" not in players_cols:
        conn.execute("DROP TABLE IF EXISTS player_game_stats")
        conn.execute("DROP TABLE players")

    pgs_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_game_stats'"
    ).fetchone()
    if pgs_exists:
        fk_rows = conn.execute("PRAGMA foreign_key_list(player_game_stats)").fetchall()
        players_fk_cols = [r[3] for r in fk_rows if r[2] == "players"]
        if players_fk_cols == ["player_id"]:  # old single-column FK — stale
            conn.execute("DROP TABLE player_game_stats")

    conn.commit()


def init_db():
    """Create tables if they don't already exist, then apply any column
    migrations for tables that already existed. Safe to run repeatedly."""
    conn = get_conn()
    _drop_stale_tables(conn)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    _apply_migrations(conn)
    conn.close()
    print(f"Database ready at {DB_PATH}")


if __name__ == "__main__":
    init_db()
