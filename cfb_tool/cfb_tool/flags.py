"""
Flag engine — finds tension points in a matchup from stats already in the
database and states them as plain facts (never a pick).

Each Flag carries a fixed "raw" strength (how far past a fixed noise-floor
threshold the underlying stat gap is) which schedule.py normalizes into a
0-1 score to rank flags against each other and decide the schedule-row
star/moniker. The per-game matchup card always shows every flag that
clears its baseline threshold — the adjustable "sensitivity" setting only
controls how many/how-strong flags a game needs to earn the schedule star,
never which flags are hidden on the card itself.
"""

# Fixed noise-floor thresholds. Not user-adjustable — these decide whether
# a gap is worth mentioning at all, as opposed to the star/moniker
# sensitivity setting, which decides how many flagged games stand out.
TEMPO_DIFF_THRESHOLD = 6.0          # plays/game
RUSH_MATCHUP_THRESHOLD = 40.0       # yards/game
PASS_MATCHUP_THRESHOLD = 50.0       # yards/game
OVERALL_RANK_GAP_SUPPRESS = 40      # national SP+ rank spots — suppresses a raw gap SP+ contradicts
CORROBORATE_RANK_GAP = 60           # national SP+ rank spots — fires a sub-threshold raw gap SP+ backs up
TURNOVER_MARGIN_THRESHOLD = 1.0     # per game
SHOOTOUT_UNDER_THRESHOLD = 40.0     # yards/game off the FBS average
WIND_THRESHOLD_MPH = 15             # sustained/gust wind worth flagging
COLD_THRESHOLD_F = 25               # temperature worth flagging
PRECIP_THRESHOLD_PCT = 50           # chance of precipitation worth flagging


# The schedule page recomputes flags for every game in a week — cache this
# league-wide average per (ingest timestamp, season) instead of re-running
# the full-table aggregate on every single game.
_AVG_ALLOWED_CACHE = {}


def fbs_avg_yards_allowed(conn, season):
    token = conn.execute("SELECT value FROM meta WHERE key = 'last_updated'").fetchone()
    key = (token["value"] if token else None, season)
    if key in _AVG_ALLOWED_CACHE:
        return _AVG_ALLOWED_CACHE[key]
    row = conn.execute(
        """SELECT AVG(tgs.total_yards) avg_yards
           FROM team_game_stats tgs
           JOIN games g ON tgs.game_id = g.game_id
           JOIN teams t ON tgs.team_id = t.team_id
           WHERE g.season = ? AND g.home_points IS NOT NULL AND t.classification = 'fbs'""",
        (season,),
    ).fetchone()
    value = row["avg_yards"] if row and row["avg_yards"] is not None else 380.0
    _AVG_ALLOWED_CACHE[key] = value
    return value


class Flag:
    def __init__(self, icon, label, text, side, bet_type, strength, threshold, moniker, lean=None):
        self.icon = icon
        self.label = label            # short type name, e.g. "Tempo"
        self.text = text              # the full plain-language sentence (matchup card)
        self.moniker = moniker        # short team-specific phrase (schedule row)
        self.side = side              # 'away' | 'home' | 'both'
        self.bet_type = bet_type      # 'side' | 'total' | 'prop'
        self.strength = strength      # raw magnitude past the threshold
        self.score = min(1.0, strength / (threshold * 2)) if threshold else 0.5
        self.lean = lean              # 'over' | 'under' | None — for conflict detection


def _gm(games):
    n = games or 0
    return f"{n} game" if n == 1 else f"{n} games"


def _sample_phrase(stat_ctx):
    """Plain factual sample-size note for an offense/defense dict."""
    return _gm(stat_ctx["games"])


def _tempo_flags(away, home):
    a_pace = away["offense"]["plays_pg"]
    h_pace = home["offense"]["plays_pg"]
    if a_pace is None or h_pace is None:
        return []
    diff = a_pace - h_pace
    if abs(diff) < TEMPO_DIFF_THRESHOLD:
        return []
    fast, slow = (away, home) if diff > 0 else (home, away)
    fast_name = fast["team"]["school"]
    slow_name = slow["team"]["school"]
    text = (
        f"{fast_name} averages {fast['offense']['plays_pg']:.0f} plays/game "
        f"({_sample_phrase(fast['offense'])}) vs. {slow_name}'s "
        f"{slow['offense']['plays_pg']:.0f} plays/game ({_sample_phrase(slow['offense'])}) "
        f"— a pace mismatch that tends to push total plays run, and scoring chances, up."
    )
    moniker = f"{fast_name} tempo mismatch"
    return [Flag("⚡", "Tempo mismatch", text, "both", "total", abs(diff), TEMPO_DIFF_THRESHOLD, moniker, lean="over")]


def _matchup_advantage_flags(off_side, off_ctx, def_side, def_ctx, stat_key, pg_field, label, icon, threshold):
    off_pg = off_ctx["offense"][pg_field]
    def_pg = def_ctx["defense"][pg_field]
    if off_pg is None or def_pg is None:
        return []
    gap = off_pg - def_pg

    # Raw per-game numbers aren't comparable across teams who've faced
    # very different schedules — a bad team's yardage against a weak
    # slate can out-number a great team's yardage-allowed against a
    # strong one, with the raw gap alone saying nothing true about who'd
    # actually win this matchup. Cross-check against each team's OVERALL
    # SP+ national rank (opponent-adjusted, and unambiguous — no sign or
    # scale-mixing risk the way subtracting offense/defense sub-ratings
    # would have) in BOTH directions:
    #   - a raw gap that clears the threshold gets suppressed if SP+
    #     flatly contradicts it (offense's team ranked way worse overall
    #     than the defense's team — the false-positive case)
    #   - a raw gap that's positive but doesn't clear the threshold can
    #     still fire if SP+ strongly corroborates it (a real mismatch
    #     that raw numbers alone understate, e.g. a great offense whose
    #     opponent's weak-schedule "yards allowed" looks unremarkable) —
    #     the false-negative case
    off_sp = off_ctx.get("sp_plus")
    def_sp = def_ctx.get("sp_plus")
    rank_gap = None  # positive = defense's team ranked worse overall (favors the offense)
    if off_sp and def_sp and off_sp["ranking"] is not None and def_sp["ranking"] is not None:
        rank_gap = def_sp["ranking"] - off_sp["ranking"]

    raw_clears = gap >= threshold
    sp_contradicts = rank_gap is not None and rank_gap <= -OVERALL_RANK_GAP_SUPPRESS
    sp_corroborates = gap > 0 and rank_gap is not None and rank_gap >= CORROBORATE_RANK_GAP

    if raw_clears and sp_contradicts:
        return []
    if not raw_clears and not sp_corroborates:
        return []

    off_name = off_ctx["team"]["school"]
    def_name = def_ctx["team"]["school"]
    text = (
        f"{off_name} averages {off_pg:.0f} {label} yds/game "
        f"({_sample_phrase(off_ctx['offense'])}) — {def_name} allows "
        f"{def_pg:.0f} {label} yds/game on defense ({_sample_phrase(def_ctx['defense'])})."
    )
    if raw_clears and rank_gap is not None:
        text += (
            f" Overall SP+ doesn't contradict it either: {off_name} #{off_sp['ranking']} nat'l, "
            f"{def_name} #{def_sp['ranking']} nat'l."
        )
    elif sp_corroborates:
        text += (
            f" The raw gap alone is modest, but opponent-adjusted SP+ is decisive here: "
            f"{off_name}'s offense (#{off_sp['ranking']} nat'l) is far ahead of "
            f"{def_name}'s defense (#{def_sp['ranking']} nat'l overall) — the raw number likely "
            f"understates this given the schedules each team's faced."
        )
    moniker = f"{off_name} {label} advantage"
    # Strength drives the score used for the schedule star/moniker — when
    # the raw gap itself doesn't clear the bar and SP+ is doing the work,
    # treat it as a baseline (not-yet-more-confident-than-that) flag
    # rather than scoring it near zero off a tiny raw gap.
    strength = gap if raw_clears else threshold
    return [Flag(icon, f"{label.title()} matchup", text, off_side, "side", strength, threshold, moniker)]


def _rush_pass_flags(away, home):
    flags = []
    flags += _matchup_advantage_flags("away", away, "home", home, "rush", "rush_pg", "rush", "🏃", RUSH_MATCHUP_THRESHOLD)
    flags += _matchup_advantage_flags("home", home, "away", away, "rush", "rush_pg", "rush", "🏃", RUSH_MATCHUP_THRESHOLD)
    flags += _matchup_advantage_flags("away", away, "home", home, "pass", "pass_pg", "pass", "🎯", PASS_MATCHUP_THRESHOLD)
    flags += _matchup_advantage_flags("home", home, "away", away, "pass", "pass_pg", "pass", "🎯", PASS_MATCHUP_THRESHOLD)
    return flags


def _turnover_margin_flags(side, ctx):
    off = ctx["offense"]
    de = ctx["defense"]
    if off["to_pg"] is None or de["to_pg"] is None:
        return []
    margin = de["to_pg"] - off["to_pg"]  # forced minus committed, per game
    if abs(margin) < TURNOVER_MARGIN_THRESHOLD:
        return []
    name = ctx["team"]["school"]
    direction = "forcing more turnovers than it commits" if margin > 0 else "committing more turnovers than it forces"
    text = (
        f"{name} is {direction} by {abs(margin):.1f}/game ({_sample_phrase(off)}) "
        f"— turnover margin is one of the least sticky season-over-season stats, a candidate to regress."
    )
    moniker = f"{name} turnover regression"
    return [Flag("🔄", "Turnover margin", text, side, "side", abs(margin), TURNOVER_MARGIN_THRESHOLD, moniker)]


MID_DEF_RANK = 68  # roughly the median FBS defensive SP+ rank (~136 teams) — the sanity-check midpoint below


def _sp_def_rank(ctx):
    sp = ctx.get("sp_plus")
    return sp["def_ranking"] if sp and sp["def_ranking"] is not None else None


def _shootout_under_flags(conn, season, away, home):
    avg = fbs_avg_yards_allowed(conn, season)
    a_allowed = away["defense"]["yards_pg"]
    h_allowed = home["defense"]["yards_pg"]
    if a_allowed is None or h_allowed is None:
        return []
    a_gap = a_allowed - avg
    h_gap = h_allowed - avg
    away_name, home_name = away["team"]["school"], home["team"]["school"]
    a_rank, h_rank = _sp_def_rank(away), _sp_def_rank(home)

    # Same schedule-strength problem as the matchup-advantage flag: raw
    # "yards allowed" can look great against a weak slate or poor against
    # a strong one without saying anything true about defensive quality.
    # Sanity-check both teams' opponent-adjusted SP+ defensive rank before
    # calling it a two-directional signal — unknown rank doesn't block it
    # (nothing to contradict with), but a rank that actively disagrees does.
    if a_gap > SHOOTOUT_UNDER_THRESHOLD and h_gap > SHOOTOUT_UNDER_THRESHOLD:
        if (a_rank is not None and a_rank <= MID_DEF_RANK) or (h_rank is not None and h_rank <= MID_DEF_RANK):
            return []  # SP+ says at least one of these is actually a good defense
        text = (
            f"Both defenses are giving up more than the FBS average of ~{avg:.0f} yds/game "
            f"({away_name} allows {a_allowed:.0f}, {home_name} allows {h_allowed:.0f}) "
            f"— two defenses on the softer side, a shootout-friendly signal for the total."
        )
        if a_rank is not None and h_rank is not None:
            text += f" SP+ agrees: {away_name} #{a_rank} nat'l defense, {home_name} #{h_rank} nat'l."
        return [Flag("🔥", "Two-directional: shootout", text, "both", "total", (a_gap + h_gap) / 2, SHOOTOUT_UNDER_THRESHOLD, "Shootout signal — two soft defenses", lean="over")]
    if a_gap < -SHOOTOUT_UNDER_THRESHOLD and h_gap < -SHOOTOUT_UNDER_THRESHOLD:
        if (a_rank is not None and a_rank > MID_DEF_RANK) or (h_rank is not None and h_rank > MID_DEF_RANK):
            return []  # SP+ says at least one of these is actually a below-average defense
        text = (
            f"Both defenses are well under the FBS average of ~{avg:.0f} yds/game "
            f"({away_name} allows {a_allowed:.0f}, {home_name} allows {h_allowed:.0f}) "
            f"— two stout defenses, an under-friendly signal for the total."
        )
        if a_rank is not None and h_rank is not None:
            text += f" SP+ agrees: {away_name} #{a_rank} nat'l defense, {home_name} #{h_rank} nat'l."
        return [Flag("🧊", "Two-directional: low-scoring", text, "both", "total", (abs(a_gap) + abs(h_gap)) / 2, SHOOTOUT_UNDER_THRESHOLD, "Low-scoring signal — two stout defenses", lean="under")]
    return []


def _weather_flags(forecast):
    if not forecast:
        return []
    wind = forecast["wind_mph"]
    temp = forecast["temperature"]
    precip = forecast["precip_pct"]
    hit_wind = wind is not None and wind >= WIND_THRESHOLD_MPH
    hit_cold = temp is not None and forecast["temperature_unit"] == "F" and temp <= COLD_THRESHOLD_F
    hit_precip = precip is not None and precip >= PRECIP_THRESHOLD_PCT
    if not (hit_wind or hit_cold or hit_precip):
        return []

    bits = []
    if temp is not None:
        bits.append(f"{temp}°{forecast['temperature_unit']}")
    if wind is not None:
        bits.append(f"wind {wind} mph" + (f" {forecast['wind_direction']}" if forecast["wind_direction"] else ""))
    if precip is not None:
        bits.append(f"{precip}% chance of precipitation")
    conditions = ", ".join(bits) if bits else (forecast.get("short_forecast") or "adverse conditions")

    strength = max(
        (wind - WIND_THRESHOLD_MPH) if hit_wind else 0,
        (COLD_THRESHOLD_F - temp) if hit_cold else 0,
        (precip - PRECIP_THRESHOLD_PCT) / 5 if hit_precip else 0,
    )
    text = (
        f"Forecast at kickoff: {conditions} ({forecast.get('short_forecast', '')}) "
        f"— conditions like this tend to suppress passing efficiency and total scoring."
    )
    return [Flag("🌧", "Weather", text, "both", "total", strength, 5.0,
                  "Weather could affect scoring", lean="under")]


def compute_game_flags(conn, season, away, home, forecast=None):
    """away/home are team_matchup_context()-shaped dicts (offense/defense/team)."""
    flags = []
    flags += _tempo_flags(away, home)
    flags += _rush_pass_flags(away, home)
    flags += _turnover_margin_flags("away", away)
    flags += _turnover_margin_flags("home", home)
    flags += _shootout_under_flags(conn, season, away, home)
    flags += _weather_flags(forecast)
    flags.sort(key=lambda f: f.score, reverse=True)
    return flags


def conflicting_total_leans(flags):
    leans = {f.lean for f in flags if f.bet_type == "total" and f.lean}
    return "over" in leans and "under" in leans
