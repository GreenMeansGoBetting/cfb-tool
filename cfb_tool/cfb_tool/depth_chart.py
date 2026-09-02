"""
A usage-ranked "likely contributors" list per position group — NOT an
official team-released depth chart. CFBD has no depth-chart data (checked:
no such endpoint exists), and unofficial ones are unreliable even when
someone publishes them. This instead ranks each position group's CURRENT
roster by last season's actual usage among players still on the team,
which is a defensible stand-in for "who's likely to see the field" until
real 2026 stats exist — exactly the gap the user asked this to fill.

Anyone on the current roster at that position with no 2025 production
here (a transfer-in, a true freshman, a walk-on who barely played) is
listed separately, unranked — there's no signal to rank them by, and
guessing would be exactly the kind of manufactured signal this tool
avoids elsewhere.
"""

_POSITION_USAGE = {
    "QB": ("passing", "ATT"),
    "RB": ("rushing", "CAR"),
    "WR": ("receiving", "REC"),
    "TE": ("receiving", "REC"),
}


def _roster_at_position(conn, team_id, season, position):
    return conn.execute(
        "SELECT player_id, name FROM players WHERE team_id = ? AND season = ? AND position = ?",
        (team_id, season, position),
    ).fetchall()


def likely_contributors(conn, team_id, season, position, limit=4):
    roster = _roster_at_position(conn, team_id, season, position)
    if not roster:
        return {"ranked": [], "others": []}
    roster_by_id = {r["player_id"]: r["name"] for r in roster}

    category, usage_stat = _POSITION_USAGE.get(position, (None, None))
    ranked = []
    if category:
        rows = conn.execute(
            """SELECT player_id, stat_type, stat_value FROM player_season_stats
               WHERE team_id = ? AND season = ? AND category = ?""",
            (team_id, season - 1, category),
        ).fetchall()
        by_player = {}
        for r in rows:
            by_player.setdefault(r["player_id"], {})[r["stat_type"]] = r["stat_value"]
        for player_id, stats in by_player.items():
            if player_id not in roster_by_id:
                continue
            usage = stats.get(usage_stat) or 0
            if usage > 0:
                ranked.append({
                    "name": roster_by_id[player_id],
                    "usage": usage,
                    "usage_label": usage_stat,
                    "yards": stats.get("YDS"),
                })
    ranked.sort(key=lambda r: r["usage"], reverse=True)
    ranked = ranked[:limit]

    ranked_names = {r["name"] for r in ranked}
    others = sorted(name for name in roster_by_id.values() if name not in ranked_names)
    return {"ranked": ranked, "others": others}


def team_depth_chart(conn, team_id, season):
    return {pos: likely_contributors(conn, team_id, season, pos) for pos in _POSITION_USAGE}
