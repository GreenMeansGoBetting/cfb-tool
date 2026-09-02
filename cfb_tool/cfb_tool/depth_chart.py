"""
A usage-ranked "likely contributors" list per position group — NOT an
official team-released depth chart. CFBD has no depth-chart data (checked:
no such endpoint exists), and unofficial ones are unreliable even when
someone publishes them. This instead ranks each position group's CURRENT
roster by last season's actual usage, which is a defensible stand-in for
"who's likely to see the field" until real 2026 stats exist.

Last season's usage is looked up by player_id ACROSS ALL TEAMS, not just
the current one — a transfer's production at their old school is exactly
the kind of signal that matters here (someone who threw for 3,000 yards
elsewhere last year is a real answer to "who's going to produce," not a
blank). When that happens, the player's prior team is noted so it reads
as "transferred in with production," not misattributed to this team.

Anyone on the current roster at that position with no 2025 production
ANYWHERE is listed separately, unranked — there's no signal to rank them
by (a true freshman, mostly), and guessing would be exactly the kind of
manufactured signal this tool avoids elsewhere.
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
    this_team = conn.execute("SELECT school FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    this_team_name = this_team["school"] if this_team else None

    category, usage_stat = _POSITION_USAGE.get(position, (None, None))
    ranked = []
    if category:
        placeholders = ",".join("?" * len(roster_by_id))
        rows = conn.execute(
            f"""SELECT player_id, team_name, stat_type, stat_value FROM player_season_stats
                WHERE player_id IN ({placeholders}) AND season = ? AND category = ?""",
            (*roster_by_id.keys(), season - 1, category),
        ).fetchall()
        by_player = {}
        for r in rows:
            entry = by_player.setdefault(r["player_id"], {"team_name": r["team_name"]})
            entry[r["stat_type"]] = r["stat_value"]
        for player_id, stats in by_player.items():
            usage = stats.get(usage_stat) or 0
            if usage <= 0:
                continue
            prior_team = stats.get("team_name")
            ranked.append({
                "name": roster_by_id[player_id],
                "usage": usage,
                "usage_label": usage_stat,
                "yards": stats.get("YDS"),
                "td": stats.get("TD"),
                "transferred_from": prior_team if prior_team and prior_team != this_team_name else None,
            })
    ranked.sort(key=lambda r: r["usage"], reverse=True)
    ranked = ranked[:limit]

    ranked_names = {r["name"] for r in ranked}
    others = sorted(name for name in roster_by_id.values() if name not in ranked_names)
    return {"ranked": ranked, "others": others}


def team_depth_chart(conn, team_id, season):
    return {pos: likely_contributors(conn, team_id, season, pos) for pos in _POSITION_USAGE}
