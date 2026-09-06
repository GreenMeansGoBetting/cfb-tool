"""
National rank badges for the offense/defense matchup tables -- lets you
see at a glance whether a raw per-game number is actually good or bad
nationally, not just relative to the one opponent on the page.

A raw stat's national rank can be a schedule-strength illusion, though --
the same failure mode flags.py already guards against for its
matchup-advantage flags (a bad team's raw number inflated by a weak
slate, or a good team's raw number deflated by a brutal one). Rather than
inventing a new opponent-adjustment formula for each split stat (there's
no real per-stat opponent-adjusted baseline to check against -- SP+ only
rates offense/defense as a whole, no rush/pass split), this reuses that
same team's own overall SP+ national rank as a sanity check: if the raw
stat's rank and the SP+ rank disagree sharply, the badge is shown muted
(neutral gray) instead of colored, flagging "raw number and opponent-
adjusted rating disagree here" rather than asserting a color it can't
back up.
"""
import bisect
import team_stats

RANK_GAP_MUTE = 40  # national rank spots of SP+ disagreement before a raw-stat badge goes neutral

# Whether a HIGHER raw value is better, per (side, field).
_HIGHER_IS_BETTER = {
    ("offense", "yards_pg"): True,  ("defense", "yards_pg"): False,
    ("offense", "rush_pg"): True,   ("defense", "rush_pg"): False,
    ("offense", "pass_pg"): True,   ("defense", "pass_pg"): False,
    ("offense", "to_pg"): False,    ("defense", "to_pg"): True,   # offense: turnovers committed (lower better); defense: turnovers forced (higher better)
    ("offense", "td_pct"): True,    ("defense", "td_pct"): False,
}

_SP_RANK_FIELD = {"offense": "off_ranking", "defense": "def_ranking"}

_DIST_CACHE = {}


def _fbs_team_ids(conn):
    return [r[0] for r in conn.execute("SELECT team_id FROM teams WHERE classification = 'fbs'").fetchall()]


def _distribution(conn, season, side, field):
    token = conn.execute("SELECT value FROM meta WHERE key = 'last_updated'").fetchone()
    key = (token["value"] if token else None, season, side, field)
    if key in _DIST_CACHE:
        return _DIST_CACHE[key]
    fn = team_stats.team_offense if side == "offense" else team_stats.team_defense_allowed
    values = sorted(v for tid in _fbs_team_ids(conn) if (v := fn(conn, tid, season)[field]) is not None)
    _DIST_CACHE[key] = values
    return values


def _tier(good_fraction):
    if good_fraction >= 2 / 3:
        return "good"
    if good_fraction <= 1 / 3:
        return "bad"
    return "mid"


def rank_badge(conn, season, side, field, stat_ctx, sp_plus):
    """stat_ctx is the team's offense/defense dict (has the raw field +
    games); sp_plus is that team's sp_plus_ratings row. Returns
    {rank, total, tier} or None if there's not enough data to rank yet."""
    value = stat_ctx.get(field)
    if value is None:
        return None
    values = _distribution(conn, season, side, field)
    if len(values) < 10:
        return None
    higher_is_better = _HIGHER_IS_BETTER[(side, field)]
    # rank 1 = best: count teams strictly better than this value, +1
    better_count = sum(1 for v in values if (v > value if higher_is_better else v < value))
    rank = better_count + 1
    total = len(values)
    raw_good_fraction = 1 - (better_count / total)
    tier = _tier(raw_good_fraction)

    sp_rank = sp_plus[_SP_RANK_FIELD[side]] if sp_plus else None
    if sp_rank is not None and abs(rank - sp_rank) > RANK_GAP_MUTE:
        tier = "muted"

    return {"rank": rank, "total": total, "tier": tier}
