"""
Computes coordinator_tendencies from team_game_stats + coach_stints.

This is the piece that answers "what does this OC's offense actually look
like" - both for their current team-season, and (more importantly) as a
lookup when they show up at a NEW school, so week-1 tendencies aren't a
blind guess.

Run this after ingest.py and load_coordinators.py have populated games/
team_game_stats/coach_stints for the seasons you care about.

Usage:
    python3 compute_tendencies.py
"""
from db.db import get_conn, init_db


def main():
    init_db()
    conn = get_conn()

    # One row per (coach, team, season) where that coach was HC or OC for
    # that team that season, joined against every game that team played
    # that season. (We don't separate "plays OC called" from "team's plays"
    # since play-by-play attribution isn't in this schema yet - this is a
    # team-season proxy for the coordinator's stamp on the offense.)
    rows = conn.execute(
        """
        SELECT cs.coach_id, cs.team_id, cs.season,
               COUNT(tgs.game_id) AS games_sample,
               AVG(tgs.plays) AS plays_per_game,
               SUM(tgs.rush_attempts) AS total_rush_att,
               SUM(tgs.pass_attempts) AS total_pass_att,
               SUM(tgs.total_yards) AS total_yards,
               SUM(tgs.plays) AS total_plays
        FROM coach_stints cs
        JOIN team_game_stats tgs
          ON tgs.team_id = cs.team_id
        JOIN games g
          ON g.game_id = tgs.game_id AND g.season = cs.season
        WHERE cs.role IN ('HC', 'OC')
        GROUP BY cs.coach_id, cs.team_id, cs.season
        """
    ).fetchall()

    computed = []
    for r in rows:
        rush = r["total_rush_att"] or 0
        pas = r["total_pass_att"] or 0
        total_att = rush + pas
        run_rate = rush / total_att if total_att else None
        pass_rate = pas / total_att if total_att else None
        ypp = (r["total_yards"] / r["total_plays"]) if r["total_plays"] else None
        computed.append((
            r["coach_id"], r["team_id"], r["season"], r["games_sample"],
            r["plays_per_game"], run_rate, pass_rate, ypp,
        ))

    conn.executemany(
        """INSERT INTO coordinator_tendencies
             (coach_id, team_id, season, games_sample, plays_per_game,
              run_rate, pass_rate, yards_per_play)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(coach_id, team_id, season) DO UPDATE SET
             games_sample=excluded.games_sample,
             plays_per_game=excluded.plays_per_game,
             run_rate=excluded.run_rate,
             pass_rate=excluded.pass_rate,
             yards_per_play=excluded.yards_per_play""",
        computed,
    )
    conn.commit()
    print(f"Computed tendencies for {len(computed)} coach-team-season rows.")

    # Show anyone who changed teams year-over-year - this is exactly the
    # "new OC" case, printed out so you can sanity-check it
    print("\nCoaches with a team change (their history now travels with them):")
    changes = conn.execute(
        """
        SELECT c.first_name, c.last_name, t.school, ct.season,
               ROUND(ct.run_rate * 100, 1) AS run_pct,
               ct.games_sample
        FROM coordinator_tendencies ct
        JOIN coaches c ON c.coach_id = ct.coach_id
        JOIN teams t ON t.team_id = ct.team_id
        WHERE ct.coach_id IN (
            SELECT coach_id FROM coordinator_tendencies
            GROUP BY coach_id HAVING COUNT(DISTINCT team_id) > 1
        )
        ORDER BY c.last_name, ct.season
        """
    ).fetchall()
    for row in changes:
        print(f"  {row['first_name']} {row['last_name']} — {row['school']} "
              f"({row['season']}): {row['run_pct']}% run rate, "
              f"{row['games_sample']} games")

    conn.close()


if __name__ == "__main__":
    main()
