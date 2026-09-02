"""
Cold-start blending for team-level offense/defense stats — the same
"trust the sample as it grows" philosophy already validated for
coordinator tendencies in blend.py, applied one level up to raw team
box-score stats (see cfb_tool_concept.md, "Week 1 / cold-start plan").

Layered priors, most to least reliable:
  1. Last season's final stats, decaying in weight as this season's
     games accumulate — implemented here.
  2. Returning production (% of last year's production still on the
     roster, from CFBD's /player/returning) scales how much that prior
     season is trusted — implemented here.
  3. Coordinator tendencies — already built in blend.py /
     compute_tendencies.py, not yet wired into this team-level blend.
  4. Market win totals / preseason lines — not implemented (no odds
     source integrated yet).

Every value returned here is either a plain current-season number or a
labeled blend (`is_blended=True` plus the weights that produced it) —
never presented as in-season data when it isn't, per the "plainly label
Week 1-type situations" rule.
"""

SAMPLE_WEIGHT_GAMES = 6      # same constant/philosophy as blend.py
MIN_TRUST_FACTOR = 0.3       # floor so heavy roster turnover never fully zeroes the prior
CONFIRMED_DEPARTURE_TRUST = 0.1  # trust ceiling when we've directly confirmed the top producer left

_FIELDS = ["yards_pg", "rush_pg", "pass_pg", "plays_pg", "to_pg", "td_pct"]

# Which raw field each confirmed-departure override applies to. A team-wide
# returning-production percentage can stay comfortably high while the one
# player who drove a SPECIFIC stat is definitely gone (e.g. Baylor's
# passing production reads 60%+ returning overall, but the QB who threw
# for 3,681 of those yards isn't on the roster) — when we've directly
# confirmed that via returning.top_producer_returning(), it overrides the
# aggregate trust for just that field, not the whole blend.
_OVERRIDE_FIELD = {"passing_returning": "pass_pg", "rushing_returning": "rush_pg"}


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


def _blend(current, prior, returning_pct, **field_returning):
    current_games = current["games"] or 0
    have_prior = prior is not None and (prior["games"] or 0) > 0
    confirmed_departed = {
        _OVERRIDE_FIELD[k] for k, v in field_returning.items() if v is False
    }

    if not have_prior:
        result = {f: current[f] for f in _FIELDS}
        result.update(games=current_games, is_blended=False,
                       prior_weight=0.0, current_weight=1.0, returning_pct=returning_pct)
        return result

    if current_games == 0:
        # Nothing to blend the prior against yet. Normally we show last
        # season's numbers as-is, labeled a pre-season estimate — but if
        # we've directly confirmed the player who drove a specific field
        # is gone, showing that field at all would misstate it as a
        # meaningful estimate when it's really just that departed
        # player's number. Withhold it (None / "—") instead of guessing.
        result = {f: (None if f in confirmed_departed else prior[f]) for f in _FIELDS}
        result.update(games=0, is_blended=True,
                       prior_weight=1.0, current_weight=0.0, returning_pct=returning_pct)
        return result

    current_weight_raw = min(current_games / SAMPLE_WEIGHT_GAMES, 1.0)
    prior_weight_raw = 1 - current_weight_raw
    default_trust = max(returning_pct, MIN_TRUST_FACTOR) if returning_pct is not None else 1.0
    prior_weight = prior_weight_raw * default_trust
    current_weight = 1 - prior_weight

    result = {}
    for f in _FIELDS:
        cv, pv = current[f], prior[f]
        if f in confirmed_departed:
            # Skip the aggregate trust floor here on purpose — a confirmed
            # departure is stronger, more specific evidence than the
            # team-wide percentage, so it's allowed to push trust in the
            # prior lower than MIN_TRUST_FACTOR would otherwise permit.
            f_prior_weight = prior_weight_raw * CONFIRMED_DEPARTURE_TRUST
            f_current_weight = 1 - f_prior_weight
        else:
            f_prior_weight, f_current_weight = prior_weight, current_weight
        if cv is None and pv is None:
            result[f] = None
        elif cv is None:
            result[f] = pv
        elif pv is None:
            result[f] = cv
        else:
            result[f] = f_prior_weight * pv + f_current_weight * cv
    result.update(games=current_games, is_blended=prior_weight > 0.01,
                   prior_weight=round(prior_weight, 2), current_weight=round(current_weight, 2),
                   returning_pct=returning_pct)
    return result


def blended_offense(conn, team_id, season, passing_returning=None, rushing_returning=None):
    """passing_returning/rushing_returning: True/False/None — whether last
    season's #1 producer for that stat is confirmed on this year's roster
    (see returning.top_producer_returning). False overrides the aggregate
    returning-production trust for just that field; None/True defer to it."""
    current = _raw_offense(conn, team_id, season)
    prior = _raw_offense(conn, team_id, season - 1)
    returning = _returning_pct(conn, team_id, season)
    return _blend(current, prior, returning, passing_returning=passing_returning, rushing_returning=rushing_returning)


def blended_defense_allowed(conn, team_id, season):
    current = _raw_defense_allowed(conn, team_id, season)
    prior = _raw_defense_allowed(conn, team_id, season - 1)
    returning = _returning_pct(conn, team_id, season)
    return _blend(current, prior, returning)
