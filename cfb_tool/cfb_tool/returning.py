"""
Player-level "who's actually still here" — the concrete complement to the
team-wide returning-production percentage used in blending.py. A "41%
production returning" number doesn't say WHOSE production that is; if the
answer is "the starting QB left," last season's stats are a much weaker
prior than the percentage alone suggests. This pulls last season's top
producer at each offensive skill spot and checks it against this year's
actual roster (players table, synced from CFBD's /roster).
"""

_CATEGORY_LABELS = {"passing": "Passing", "rushing": "Rushing", "receiving": "Receiving"}
_LEAD_STAT = {"passing": "YDS", "rushing": "YDS", "receiving": "YDS"}


def key_returners(conn, team_id, season):
    """Last season's #1 producer in each offensive category, each tagged
    with whether they're on this season's roster for this team."""
    prior_season = season - 1
    roster_ids = {
        r["player_id"] for r in conn.execute(
            "SELECT player_id FROM players WHERE team_id = ? AND season = ?",
            (team_id, season),
        ).fetchall()
    }

    results = []
    for category, label in _CATEGORY_LABELS.items():
        rows = conn.execute(
            """SELECT player_id, player_name, stat_type, stat_value
               FROM player_season_stats
               WHERE team_id = ? AND season = ? AND category = ?""",
            (team_id, prior_season, category),
        ).fetchall()
        if not rows:
            continue
        by_player = {}
        for r in rows:
            by_player.setdefault((r["player_id"], r["player_name"]), {})[r["stat_type"]] = r["stat_value"]
        lead_stat = _LEAD_STAT[category]
        top = max(by_player.items(), key=lambda kv: kv[1].get(lead_stat) or 0)
        (player_id, name), stats = top
        results.append({
            "category": label,
            "name": name,
            "stat_value": stats.get(lead_stat),
            "stat_label": lead_stat,
            "returning": player_id in roster_ids if roster_ids else None,
        })
    return results
