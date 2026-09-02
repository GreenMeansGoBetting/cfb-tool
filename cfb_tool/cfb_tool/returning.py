"""
Player-level "who's actually still here" — the concrete complement to the
team-wide returning-production percentage (team_stats.py). A "41%
production returning" number doesn't say WHOSE production that is; this
pulls last season's top producer at each offensive skill spot and checks
it against this year's actual roster (players table, synced from CFBD's
/roster).
"""

_CATEGORY_LABELS = {"passing": "Passing", "rushing": "Rushing", "receiving": "Receiving"}
_LEAD_STAT = {"passing": "YDS", "rushing": "YDS", "receiving": "YDS"}


def _top_producer(conn, team_id, prior_season, category):
    """(player_id, name, stats) for last season's #1 producer in a
    category, or None if there's no data for it."""
    rows = conn.execute(
        """SELECT player_id, player_name, stat_type, stat_value
           FROM player_season_stats
           WHERE team_id = ? AND season = ? AND category = ?""",
        (team_id, prior_season, category),
    ).fetchall()
    if not rows:
        return None
    by_player = {}
    for r in rows:
        by_player.setdefault((r["player_id"], r["player_name"]), {})[r["stat_type"]] = r["stat_value"]
    lead_stat = _LEAD_STAT[category]
    (player_id, name), stats = max(by_player.items(), key=lambda kv: kv[1].get(lead_stat) or 0)
    return player_id, name, stats


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
        top = _top_producer(conn, team_id, prior_season, category)
        if top is None:
            continue
        player_id, name, stats = top
        lead_stat = _LEAD_STAT[category]
        results.append({
            "category": label,
            "name": name,
            "stat_value": stats.get(lead_stat),
            "stat_label": lead_stat,
            "returning": player_id in roster_ids if roster_ids else None,
        })
    return results
