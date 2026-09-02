"""
Current-season team-level offense/defense stats, plus the returning-
production number used to flag low-certainty teams (the REBUILD badge).

This used to blend in last season's stats as a cold-start prior for a
team with few/no games played yet. Dropped per direction from actually
using the tool for a week: too much can change roster/scheme-wise for
last year's box score to be a meaningful stand-in for this year's team,
and it's only relevant for a couple of weeks anyway before real 2026
data takes over on its own. A team with 0 games now just shows no
stats — depth_chart.py's "likely contributors" list is the intended
thing to look at in that gap, not a blended guess dressed up as data.

Returning production is kept (unlike the box-score blend) — it's a
roster fact, not a past-season stat, and it's exactly why the reference
screenshots' "REBUILD" framing is worth keeping around.
"""


def _raw_offense(conn, team_id, season):
    return conn.execute(
        """SELECT COUNT(*) games, AVG(tgs.total_yards) yards_pg,
                  AVG(tgs.rush_yards) rush_pg, AVG(tgs.pass_yards) pass_pg,
                  AVG(tgs.plays) plays_pg, AVG(tgs.turnovers) to_pg,
                  (100.0 * SUM(tgs.third_down_conv) / NULLIF(SUM(tgs.third_down_att), 0)) td_pct
           FROM team_game_stats tgs
           JOIN games g ON tgs.game_id = g.game_id
           WHERE tgs.team_id = ? AND g.season = ? AND g.home_points IS NOT NULL""",
        (team_id, season),
    ).fetchone()


def _raw_defense_allowed(conn, team_id, season):
    return conn.execute(
        """SELECT COUNT(*) games, AVG(opp.total_yards) yards_pg, AVG(opp.rush_yards) rush_pg,
                  AVG(opp.pass_yards) pass_pg, AVG(opp.plays) plays_pg, AVG(opp.turnovers) to_pg,
                  (100.0 * SUM(opp.third_down_conv) / NULLIF(SUM(opp.third_down_att), 0)) td_pct
           FROM team_game_stats tgs
           JOIN games g ON tgs.game_id = g.game_id
           JOIN team_game_stats opp ON opp.game_id = tgs.game_id AND opp.team_id != tgs.team_id
           WHERE tgs.team_id = ? AND g.season = ? AND g.home_points IS NOT NULL""",
        (team_id, season),
    ).fetchone()


def _returning_pct(conn, team_id, season):
    row = conn.execute(
        "SELECT pct_ppa FROM returning_production WHERE team_id = ? AND season = ?",
        (team_id, season),
    ).fetchone()
    return row["pct_ppa"] if row and row["pct_ppa"] is not None else None


_FIELDS = ["yards_pg", "rush_pg", "pass_pg", "plays_pg", "to_pg", "td_pct"]


def _season_stats(raw, returning_pct):
    games = raw["games"] or 0
    result = {f: (raw[f] if games else None) for f in _FIELDS}
    result.update(games=games, returning_pct=returning_pct)
    return result


def team_offense(conn, team_id, season):
    return _season_stats(_raw_offense(conn, team_id, season), _returning_pct(conn, team_id, season))


def team_defense_allowed(conn, team_id, season):
    return _season_stats(_raw_defense_allowed(conn, team_id, season), _returning_pct(conn, team_id, season))
