"""
Loads data/coordinator_hires.csv into the coach_stints table.

Why this exists: CFBD's /coaches endpoint reliably covers head coaches but
not offensive/defensive coordinators, which is exactly the level you need
for "new OC changes the offense" tracking. There's no good free API for
FBS-wide coordinator hires, so this is a small hand-maintained list you
update a few times a year (coordinator hires are news events - there are
only ~130 FBS programs, so this is maybe 10-20 minutes, 2-3 times a year,
not a constant chore).

Usage:
    python3 load_coordinators.py
"""
import csv
from pathlib import Path
from db.db import get_conn, init_db

CSV_PATH = Path(__file__).parent / "data" / "coordinator_hires.csv"


def main():
    init_db()
    conn = get_conn()
    added, skipped = 0, 0

    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            school = row["school"].strip()
            if school == "Example School":
                continue  # skip the template row

            team_row = conn.execute(
                "SELECT team_id FROM teams WHERE school = ?", (school,)
            ).fetchone()
            if not team_row:
                print(f"  SKIP: '{school}' not found in teams table "
                      f"(run ingest.py for this season first, or check spelling)")
                skipped += 1
                continue

            cur = conn.execute(
                """INSERT INTO coaches (first_name, last_name) VALUES (?, ?)
                   ON CONFLICT(first_name, last_name) DO UPDATE SET last_name=excluded.last_name
                   RETURNING coach_id""",
                (row["first_name"].strip(), row["last_name"].strip()),
            )
            coach_row = cur.fetchone()
            if coach_row is None:
                coach_row = conn.execute(
                    "SELECT coach_id FROM coaches WHERE first_name = ? AND last_name = ?",
                    (row["first_name"].strip(), row["last_name"].strip()),
                ).fetchone()
            coach_id = coach_row[0]

            conn.execute(
                """INSERT INTO coach_stints (coach_id, team_id, season, role)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(coach_id, team_id, season, role) DO NOTHING""",
                (coach_id, team_row[0], int(row["season"]), row["role"].strip()),
            )
            added += 1
            print(f"  Added: {row['first_name']} {row['last_name']} — "
                  f"{school} {row['role']} ({row['season']})")

    conn.commit()
    conn.close()
    print(f"\nDone. {added} coordinator stints added/confirmed, {skipped} skipped.")


if __name__ == "__main__":
    main()
