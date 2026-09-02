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


HOME_FIELD_POINTS = 2.5  # standard rough modern-CFB estimate, not team/venue-specific


def team_sp_plus(conn, team_id, season):
    return conn.execute(
        "SELECT * FROM sp_plus_ratings WHERE team_id = ? AND season = ?",
        (team_id, season),
    ).fetchone()


def implied_spread(home_sp, away_sp, neutral_site=False):
    """Power-rating implied spread, per the concept doc's own stated
    mechanism: the gap between two teams' overall SP+ ratings, adjusted
    for home field (skipped for a neutral-site game — e.g. the Ireland/
    Dublin games this schedule already has, where the "home" team in our
    data gets no real home-field edge). This is intentionally the ONLY
    model-implied number built so far — a total would need combining
    offense/defense sub-ratings in a way that can't be verified against
    a known-correct reference here, so it's left unbuilt rather than
    guessed at.

    Returns {favored_team: 'home'|'away', margin: float} or None if
    either team's SP+ rating is missing.
    """
    if not home_sp or not away_sp or home_sp["rating"] is None or away_sp["rating"] is None:
        return None
    hfa = 0.0 if neutral_site else HOME_FIELD_POINTS
    home_margin = (home_sp["rating"] - away_sp["rating"]) + hfa
    return {
        "favored_team": "home" if home_margin >= 0 else "away",
        "margin": round(abs(home_margin), 1),
        "neutral_site": bool(neutral_site),
    }


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
