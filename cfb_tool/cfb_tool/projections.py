"""
Rough player projections for the single upcoming game -- never further out
than that, and never blended with last season.

The naive version of this (an earlier pass) just averaged a player's own
raw per-game stats and multiplied by the upcoming opponent's raw allowed
number vs. the FBS average. Two problems with that, both schedule-strength
illusions of the same kind flags.py already guards against elsewhere:

  1. The player's own history is itself a product of who they already
     played. Julian Sayin's 320 pass yds/game "pace" is one game against
     Ball State (a bad defense) -- taken at face value, it overstates what
     he'd do against an average defense.
  2. The upcoming opponent's raw allowed number has the same problem in
     the other direction. Texas's raw pass yards allowed can look great
     purely because Texas has played a soft schedule so far, not because
     their pass defense is actually elite.

Both get corrected the same way: instead of raw allowed yards, use the
opponent's overall SP+ defensive rank (CFBD's own opponent-adjusted
rating -- already the trusted signal flags.py leans on for the same
reason) converted to a percentile, then to a symmetric multiplier via
_matchup_factor(). That one function is applied twice --
  - to each of the player's own past games (dividing out how tough/soft
    THAT game's specific opponent was, producing a schedule-neutral
    "vacuum pace"), and
  - to the upcoming opponent (multiplying the vacuum pace back up or down
    for how tough THIS matchup is).
Using the same function both ways keeps it self-consistent and avoids
inventing a second, uncalibrated formula.

Real limitation, stated plainly rather than hidden: SP+ only rates a
defense as a whole -- CFBD doesn't publish a rush-defense/pass-defense
split -- so the matchup factor is one number applied to passing, rushing,
and receiving alike. The category-specific raw allowed number is still
shown alongside the projection for context, just not used as the
adjustment's basis.
"""
import sos
import team_stats

MIN_ADJUSTMENT = 0.6
MAX_ADJUSTMENT = 1.6

_CATEGORIES = {
    "passing":   {"label": "Passing",   "yards_col": "pass_yards", "td_col": "pass_td", "def_field": "pass_pg", "limit": 1},
    "rushing":   {"label": "Rushing",   "yards_col": "rush_yards", "td_col": "rush_td", "def_field": "rush_pg", "limit": 2},
    "receiving": {"label": "Receiving", "yards_col": "rec_yards",  "td_col": "rec_td",  "def_field": "pass_pg", "limit": 3},
}

_FBS_COUNT_CACHE = {}


def _fbs_sp_plus_count(conn, season):
    token = conn.execute("SELECT value FROM meta WHERE key = 'last_updated'").fetchone()
    key = (token["value"] if token else None, season)
    if key not in _FBS_COUNT_CACHE:
        _FBS_COUNT_CACHE[key] = conn.execute(
            """SELECT COUNT(*) FROM sp_plus_ratings sp JOIN teams t ON sp.team_id = t.team_id
               WHERE sp.season = ? AND t.classification = 'fbs'""",
            (season,),
        ).fetchone()[0]
    return _FBS_COUNT_CACHE[key]


def _def_percentile(sp_plus, total_teams):
    """1.0 = best defense in the country, 0.0 = worst. None if we don't
    have an opponent-adjusted rank for this team yet."""
    if not sp_plus or sp_plus["def_ranking"] is None or not total_teams:
        return None
    return 1 - (sp_plus["def_ranking"] - 1) / total_teams


def _matchup_factor(percentile):
    """percentile 1.0 (elite defense) -> MIN_ADJUSTMENT (suppresses production);
    percentile 0.0 (worst defense) -> MAX_ADJUSTMENT (boosts it);
    percentile 0.5 (average) -> 1.0 (no change)."""
    if percentile is None:
        return None
    return MAX_ADJUSTMENT - percentile * (MAX_ADJUSTMENT - MIN_ADJUSTMENT)


def _vacuum_pace(conn, player_id, season, category, yards_col, td_col, total_teams):
    """Each of the player's own logged games this season, each divided by
    that specific game's opponent-defense matchup factor -- so a player's
    baseline pace reflects their own output adjusted for opponent quality,
    not just whatever raw number a soft or tough matchup happened to produce."""
    rows = conn.execute(
        f"""SELECT pgs.{yards_col} yds, pgs.{td_col} td, pgs.team_id,
                   g.home_team_id, g.away_team_id
            FROM player_game_stats pgs
            JOIN games g ON g.game_id = pgs.game_id
            WHERE pgs.player_id = ? AND pgs.season = ? AND pgs.category = ?""",
        (player_id, season, category),
    ).fetchall()
    if not rows:
        return None
    norm_yards, norm_td = [], []
    for r in rows:
        opp_id = r["away_team_id"] if r["team_id"] == r["home_team_id"] else r["home_team_id"]
        factor = _matchup_factor(_def_percentile(sos.team_sp_plus(conn, opp_id, season), total_teams)) or 1.0
        norm_yards.append((r["yds"] or 0) / factor)
        norm_td.append((r["td"] or 0) / factor)
    return {
        "games": len(rows),
        "vacuum_yards": sum(norm_yards) / len(norm_yards),
        "vacuum_td": sum(norm_td) / len(norm_td),
    }


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


def team_player_projections(conn, team_id, season, opponent_team_id):
    """One entry per key current-season producer who's logged a game --
    each with a schedule-neutral "vacuum" pace and a rough projection for
    the single upcoming game against opponent_team_id. Never projects
    beyond that one game."""
    total_teams = _fbs_sp_plus_count(conn, season)
    opp_sp_plus = sos.team_sp_plus(conn, opponent_team_id, season)
    opp_factor = _matchup_factor(_def_percentile(opp_sp_plus, total_teams))
    opp_defense = team_stats.team_defense_allowed(conn, opponent_team_id, season)

    results = []
    for category, cfg in _CATEGORIES.items():
        for (player_id, name), _stats in _top_producers(conn, team_id, season, category, cfg["limit"]):
            vac = _vacuum_pace(conn, player_id, season, category, cfg["yards_col"], cfg["td_col"], total_teams)
            if vac is None:
                continue
            entry = {
                "name": name,
                "category": cfg["label"],
                "games": vac["games"],
                "vacuum_yards": vac["vacuum_yards"],
                "vacuum_td": vac["vacuum_td"],
                "opponent_def_rank": opp_sp_plus["def_ranking"] if opp_sp_plus else None,
                "opponent_allowed_pg": opp_defense.get(cfg["def_field"]),
                "projected_yards": None,
                "projected_td": None,
            }
            if opp_factor is not None:
                entry["projected_yards"] = vac["vacuum_yards"] * opp_factor
                entry["projected_td"] = vac["vacuum_td"] * opp_factor
            results.append(entry)
    return results
