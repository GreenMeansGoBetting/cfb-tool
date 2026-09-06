"""
Current-season team-level offense/defense stats -- current year only, no
prior-season blending or returning-production framing of any kind. A team
with 0 games this season just shows no stats -- quality reads off this
season's own numbers plus SOS/SP+ (sos.py) and national rank (rankings.py),
game by game, nothing carried over from last year.
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


_FIELDS = ["yards_pg", "rush_pg", "pass_pg", "plays_pg", "to_pg", "td_pct"]


def _season_stats(raw):
    games = raw["games"] or 0
    result = {f: (raw[f] if games else None) for f in _FIELDS}
    result.update(games=games)
    return result


def team_offense(conn, team_id, season):
    return _season_stats(_raw_offense(conn, team_id, season))


def team_defense_allowed(conn, team_id, season):
    return _season_stats(_raw_defense_allowed(conn, team_id, season))
