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
TURNOVER_MARGIN_THRESHOLD = 1.0     # per game
SHOOTOUT_UNDER_THRESHOLD = 40.0     # yards/game off the FBS average


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
    """Plain factual sample-size note for a blended offense/defense dict —
    states the actual current-season game count, and flags plainly when
    the number itself leans on last season's blended-in prior."""
    phrase = _gm(stat_ctx["games"])
    if stat_ctx.get("is_blended"):
        if stat_ctx["games"] == 0:
            return f"{phrase} this season — based on last season's stats"
        return f"{phrase}, blended with last season"
    return phrase


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
    if gap < threshold:
        return []
    off_name = off_ctx["team"]["school"]
    def_name = def_ctx["team"]["school"]
    text = (
        f"{off_name} averages {off_pg:.0f} {label} yds/game "
        f"({_sample_phrase(off_ctx['offense'])}) — {def_name} allows "
        f"{def_pg:.0f} {label} yds/game on defense ({_sample_phrase(def_ctx['defense'])})."
    )
    moniker = f"{off_name} {label} advantage"
    return [Flag(icon, f"{label.title()} matchup", text, off_side, "side", gap, threshold, moniker)]


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


def _shootout_under_flags(conn, season, away, home):
    avg = fbs_avg_yards_allowed(conn, season)
    a_allowed = away["defense"]["yards_pg"]
    h_allowed = home["defense"]["yards_pg"]
    if a_allowed is None or h_allowed is None:
        return []
    a_gap = a_allowed - avg
    h_gap = h_allowed - avg
    away_name, home_name = away["team"]["school"], home["team"]["school"]
    if a_gap > SHOOTOUT_UNDER_THRESHOLD and h_gap > SHOOTOUT_UNDER_THRESHOLD:
        text = (
            f"Both defenses are giving up more than the FBS average of ~{avg:.0f} yds/game "
            f"({away_name} allows {a_allowed:.0f}, {home_name} allows {h_allowed:.0f}) "
            f"— two defenses on the softer side, a shootout-friendly signal for the total."
        )
        return [Flag("🔥", "Two-directional: shootout", text, "both", "total", (a_gap + h_gap) / 2, SHOOTOUT_UNDER_THRESHOLD, "Shootout signal — two soft defenses", lean="over")]
    if a_gap < -SHOOTOUT_UNDER_THRESHOLD and h_gap < -SHOOTOUT_UNDER_THRESHOLD:
        text = (
            f"Both defenses are well under the FBS average of ~{avg:.0f} yds/game "
            f"({away_name} allows {a_allowed:.0f}, {home_name} allows {h_allowed:.0f}) "
            f"— two stout defenses, an under-friendly signal for the total."
        )
        return [Flag("🧊", "Two-directional: low-scoring", text, "both", "total", (abs(a_gap) + abs(h_gap)) / 2, SHOOTOUT_UNDER_THRESHOLD, "Low-scoring signal — two stout defenses", lean="under")]
    return []


def compute_game_flags(conn, season, away, home):
    """away/home are team_matchup_context()-shaped dicts (offense/defense/team)."""
    flags = []
    flags += _tempo_flags(away, home)
    flags += _rush_pass_flags(away, home)
    flags += _turnover_margin_flags("away", away)
    flags += _turnover_margin_flags("home", home)
    flags += _shootout_under_flags(conn, season, away, home)
    flags.sort(key=lambda f: f.score, reverse=True)
    return flags


def conflicting_total_leans(flags):
    leans = {f.lean for f in flags if f.bet_type == "total" and f.lean}
    return "over" in leans and "under" in leans
