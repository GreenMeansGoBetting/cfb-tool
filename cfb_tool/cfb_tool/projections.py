"""
Rough, opponent-adjusted player projections for this week's matchup.

Takes each side's current-season top producers (from player_season_stats)
and adjusts their own per-game pace by how the upcoming opponent's defense
has allowed that stat category so far, relative to the FBS average
(same defense-allowed numbers team_stats.py already computes). It's a
plain ratio against a real opponent number, not a calibrated model --
always shown alongside the raw inputs (the player's own pace, the
opponent's raw allowed number, the league average) so the adjustment is
inspectable rather than a black box, in keeping with "state the tension,
don't hand over a verdict."

Current-season only, game-by-game -- no prior-season blending of any kind.
"""
import team_stats

_CATEGORIES = {
    "passing":   {"label": "Passing",   "yards_col": "pass_yards", "td_col": "pass_td", "def_field": "pass_pg", "limit": 1},
    "rushing":   {"label": "Rushing",   "yards_col": "rush_yards", "td_col": "rush_td", "def_field": "rush_pg", "limit": 2},
    "receiving": {"label": "Receiving", "yards_col": "rec_yards",  "td_col": "rec_td",  "def_field": "pass_pg", "limit": 3},
}

# A single opponent's raw allowed-per-game can be a small-sample outlier
# early in the season -- clamp how far the adjustment can swing the
# player's own pace so one soft/tough matchup a defense had doesn't
# produce an absurd projection.
MIN_ADJUSTMENT = 0.6
MAX_ADJUSTMENT = 1.6

_LEAGUE_AVG_CACHE = {}


def _league_avg_allowed(conn, season, def_field):
    """FBS-wide average of a raw defense-allowed field (rush or pass
    yards/game) -- the baseline an opponent's own allowed number gets
    compared against to decide if this is a soft or tough matchup."""
    token = conn.execute("SELECT value FROM meta WHERE key = 'last_updated'").fetchone()
    key = (token["value"] if token else None, season, def_field)
    if key in _LEAGUE_AVG_CACHE:
        return _LEAGUE_AVG_CACHE[key]
    column = {"rush_pg": "rush_yards", "pass_pg": "pass_yards"}[def_field]
    row = conn.execute(
        f"""SELECT AVG(opp.{column}) avg_allowed
            FROM team_game_stats tgs
            JOIN games g ON tgs.game_id = g.game_id
            JOIN teams t ON tgs.team_id = t.team_id
            JOIN team_game_stats opp ON opp.game_id = tgs.game_id AND opp.team_id != tgs.team_id
            WHERE g.season = ? AND g.home_points IS NOT NULL AND t.classification = 'fbs'""",
        (season,),
    ).fetchone()
    value = row["avg_allowed"] if row and row["avg_allowed"] is not None else None
    _LEAGUE_AVG_CACHE[key] = value
    return value


def _top_producers(conn, team_id, season, category, limit):
    rows = conn.execute(
        """SELECT player_id, player_name, stat_type, stat_value FROM player_season_stats
           WHERE team_id = ? AND season = ? AND category = ?""",
        (team_id, season, category),
    ).fetchall()
    by_player = {}
    for r in rows:
        by_player.setdefault((r["player_id"], r["player_name"]), {})[r["stat_type"]] = r["stat_value"]
    ranked = sorted(by_player.items(), key=lambda kv: kv[1].get("YDS") or 0, reverse=True)
    return ranked[:limit]


def _player_game_log(conn, player_id, season, category, yards_col, td_col):
    row = conn.execute(
        f"""SELECT COUNT(*) games, AVG({yards_col}) avg_yards, AVG({td_col}) avg_td
            FROM player_game_stats
            WHERE player_id = ? AND season = ? AND category = ?""",
        (player_id, season, category),
    ).fetchone()
    games = row["games"] or 0
    if games == 0:
        return None
    return {"games": games, "avg_yards": row["avg_yards"], "avg_td": row["avg_td"]}


def team_player_projections(conn, team_id, season, opponent_team_id):
    """One entry per key current-season producer who's actually logged a
    game -- each with a rough opponent-adjusted yardage expectation,
    always paired with the raw player pace and opponent/league numbers
    the adjustment came from."""
    results = []
    for category, cfg in _CATEGORIES.items():
        for (player_id, name), _stats in _top_producers(conn, team_id, season, category, cfg["limit"]):
            log = _player_game_log(conn, player_id, season, category, cfg["yards_col"], cfg["td_col"])
            if log is None:
                continue
            opp_allowed = team_stats.team_defense_allowed(conn, opponent_team_id, season)[cfg["def_field"]]
            league_avg = _league_avg_allowed(conn, season, cfg["def_field"])
            entry = {
                "name": name,
                "category": cfg["label"],
                "avg_yards": log["avg_yards"],
                "avg_td": log["avg_td"],
                "games": log["games"],
                "opponent_allowed_pg": opp_allowed,
                "league_avg_allowed_pg": league_avg,
                "adjustment": None,
                "projected_yards": None,
            }
            if opp_allowed is not None and league_avg:
                adjustment = max(MIN_ADJUSTMENT, min(MAX_ADJUSTMENT, opp_allowed / league_avg))
                entry["adjustment"] = adjustment
                entry["projected_yards"] = log["avg_yards"] * adjustment
            results.append(entry)
    return results
