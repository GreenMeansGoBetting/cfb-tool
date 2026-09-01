"""
Strength-of-schedule context, built on top of CFBD's opponent-adjusted
SP+ ratings (sp_plus_ratings table — see ingest.py's sync_sp_plus).

Raw box-score stats aren't comparable across teams who've faced different
schedule difficulty, especially early in the season when a small sample
against a weak or strong slate is misleading. SP+ is CFBD's answer to
"how good is this team accounting for who they've played" — this module
adds a plain-language "opponents faced so far" line on top of it, computed
directly from games already in our own schedule (not a CFBD black box),
so it's inspectable and always in sync with what the matchup card shows.
"""


def team_sp_plus(conn, team_id, season):
    return conn.execute(
        "SELECT * FROM sp_plus_ratings WHERE team_id = ? AND season = ?",
        (team_id, season),
    ).fetchone()


def opponents_faced(conn, team_id, season):
    """Opponent team_ids from games this team has actually played (final
    score in) so far this season — not the full schedule, just what's
    happened."""
    rows = conn.execute(
        """SELECT CASE WHEN g.home_team_id = ? THEN g.away_team_id ELSE g.home_team_id END AS opp_id
           FROM games g
           WHERE (g.home_team_id = ? OR g.away_team_id = ?)
             AND g.season = ? AND g.home_points IS NOT NULL""",
        (team_id, team_id, team_id, season),
    ).fetchall()
    return [r["opp_id"] for r in rows]


def sos_summary(conn, team_id, season):
    """Average national SP+ rank of opponents actually played so far,
    split by side of the ball: avg_def_rank is what this team's OFFENSE
    has faced, avg_off_rank is what this team's DEFENSE has faced."""
    opp_ids = opponents_faced(conn, team_id, season)
    if not opp_ids:
        return {"games": 0, "avg_off_rank": None, "avg_def_rank": None}
    placeholders = ",".join("?" * len(opp_ids))
    row = conn.execute(
        f"""SELECT AVG(off_ranking) avg_off_rank, AVG(def_ranking) avg_def_rank
            FROM sp_plus_ratings WHERE team_id IN ({placeholders}) AND season = ?""",
        (*opp_ids, season),
    ).fetchone()
    return {
        "games": len(opp_ids),
        "avg_off_rank": round(row["avg_off_rank"]) if row["avg_off_rank"] is not None else None,
        "avg_def_rank": round(row["avg_def_rank"]) if row["avg_def_rank"] is not None else None,
    }
