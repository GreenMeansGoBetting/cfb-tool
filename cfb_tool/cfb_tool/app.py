"""
CFB Research Tool — Phase 1 web UI.

Run with:
    python3 app.py
Then visit http://localhost:5000
"""
from datetime import datetime, timezone
from flask import Flask, render_template, request, abort
from db.db import get_conn
import flags as flag_engine
import blending
import sos

app = Flask(__name__)

# Star/moniker sensitivity presets — total flag "score" (each flag scores
# 0-1) a game needs to clear to earn the schedule-row star. Loose stars
# more games, strict fewer; this is the "tunable, not hardcoded" threshold
# from the spec. Doesn't affect which flags show on the matchup card.
SENSITIVITY_PRESETS = {"loose": 1.0, "medium": 1.8, "strict": 2.6}
DEFAULT_SENSITIVITY = "medium"


def available_seasons(conn):
    rows = conn.execute(
        "SELECT DISTINCT season FROM player_season_stats ORDER BY season DESC"
    ).fetchall()
    return [r["season"] for r in rows]


def get_meta(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def last_updated_display(conn):
    raw = get_meta(conn, "last_updated")
    if not raw:
        return None
    # Avoid %-d / %-I strftime flags — not portable to Windows.
    dt = datetime.fromisoformat(raw)
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%b')} {dt.day}, {dt.year} {hour12}:{dt.minute:02d} {ampm} UTC"


def default_week(conn, season, weeks):
    """Pick the week to land on: the earliest one that still has an
    upcoming (unstarted) game, or the last week if the season's over."""
    if not weeks:
        return None
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        """SELECT MIN(week) w FROM games
           WHERE season = ? AND season_type = 'regular' AND start_date >= ?""",
        (season, now),
    ).fetchone()
    if row and row["w"] is not None:
        return row["w"]
    return weeks[-1]


@app.route("/")
def schedule():
    conn = get_conn()
    team_count = conn.execute("SELECT COUNT(*) c FROM teams").fetchone()["c"]
    last_updated = last_updated_display(conn)

    seasons = [r["season"] for r in conn.execute(
        "SELECT DISTINCT season FROM games ORDER BY season DESC"
    ).fetchall()]
    season = request.args.get("season", type=int) or (seasons[0] if seasons else None)

    weeks = []
    if season:
        weeks = [r["week"] for r in conn.execute(
            """SELECT DISTINCT week FROM games
               WHERE season = ? AND season_type = 'regular' ORDER BY week""",
            (season,),
        ).fetchall()]

    week = request.args.get("week", type=int) or default_week(conn, season, weeks)
    sensitivity = request.args.get("sensitivity", DEFAULT_SENSITIVITY)
    if sensitivity not in SENSITIVITY_PRESETS:
        sensitivity = DEFAULT_SENSITIVITY
    star_threshold = SENSITIVITY_PRESETS[sensitivity]

    raw_games = []
    if season and week:
        raw_games = conn.execute(
            """SELECT g.*, ht.school AS home_school, at.school AS away_school
               FROM games g
               JOIN teams ht ON g.home_team_id = ht.team_id
               JOIN teams at ON g.away_team_id = at.team_id
               WHERE g.season = ? AND g.week = ? AND g.season_type = 'regular'
                 AND ht.classification = 'fbs' AND at.classification = 'fbs'
               ORDER BY g.start_date""",
            (season, week),
        ).fetchall()

    games = []
    star_count = 0
    snapshot_cache = {}

    def snapshot(team_id):
        if team_id not in snapshot_cache:
            snapshot_cache[team_id] = team_stat_snapshot(conn, team_id, season)
        return snapshot_cache[team_id]

    for g in raw_games:
        away_ctx = snapshot(g["away_team_id"])
        home_ctx = snapshot(g["home_team_id"])
        game_flags = flag_engine.compute_game_flags(conn, season, away_ctx, home_ctx)
        signal = sum(f.score for f in game_flags)
        is_star = signal >= star_threshold
        if is_star:
            star_count += 1
        games.append({
            **dict(g),
            "moniker": game_flags[0].moniker if game_flags else "",
            "star": is_star,
        })

    conn.close()
    return render_template(
        "schedule.html", games=games, seasons=seasons, weeks=weeks,
        season=season, week=week, team_count=team_count, last_updated=last_updated,
        sensitivity=sensitivity, star_count=star_count,
    )


def _top_players(conn, team_id, season, category, limit=5):
    rows = conn.execute(
        """SELECT player_name, stat_type, stat_value FROM player_season_stats
           WHERE team_id = ? AND season = ? AND category = ?""",
        (team_id, season, category),
    ).fetchall()
    by_player = {}
    for r in rows:
        by_player.setdefault(r["player_name"], {})[r["stat_type"]] = r["stat_value"]
    sort_key = "YDS"
    players = sorted(by_player.items(), key=lambda kv: kv[1].get(sort_key) or 0, reverse=True)
    return players[:limit]


# Blended offense/defense is ~7 queries per team (current + prior season
# aggregates, both sides, plus returning production). The schedule page
# computes it for every team in the week, and it can't change until the
# next ingest — so cache it in-process, keyed off the ingest timestamp
# (a fresh ingest changes the key, which naturally invalidates stale
# entries without needing an explicit purge).
_SNAPSHOT_CACHE = {}


def team_stat_snapshot(conn, team_id, season):
    """Offense/defense only — the slice flag-computation needs. Used for
    every game on the schedule page, so it deliberately skips the player
    queries team_matchup_context() also does."""
    key = (get_meta(conn, "last_updated"), team_id, season)
    cached = _SNAPSHOT_CACHE.get(key)
    if cached is not None:
        return cached
    team = conn.execute("SELECT * FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    snapshot = {
        "team": team,
        "offense": blending.blended_offense(conn, team_id, season),
        "defense": blending.blended_defense_allowed(conn, team_id, season),
        "sp_plus": sos.team_sp_plus(conn, team_id, season),
        "sos": sos.sos_summary(conn, team_id, season),
    }
    _SNAPSHOT_CACHE[key] = snapshot
    return snapshot


def team_matchup_context(conn, team_id, season):
    ctx = team_stat_snapshot(conn, team_id, season)
    ctx["passing"] = _top_players(conn, team_id, season, "passing")
    ctx["rushing"] = _top_players(conn, team_id, season, "rushing")
    ctx["receiving"] = _top_players(conn, team_id, season, "receiving")
    return ctx


@app.route("/game/<int:game_id>")
def game_detail(game_id):
    conn = get_conn()
    game = conn.execute(
        """SELECT g.*, ht.school AS home_school, ht.conference AS home_conf,
                  at.school AS away_school, at.conference AS away_conf
           FROM games g
           JOIN teams ht ON g.home_team_id = ht.team_id
           JOIN teams at ON g.away_team_id = at.team_id
           WHERE g.game_id = ?""",
        (game_id,),
    ).fetchone()
    if not game:
        abort(404)

    home = team_matchup_context(conn, game["home_team_id"], game["season"])
    away = team_matchup_context(conn, game["away_team_id"], game["season"])
    all_flags = flag_engine.compute_game_flags(conn, game["season"], away, home)
    conn.close()

    grouped_flags = {
        "away": [f for f in all_flags if f.side == "away"],
        "home": [f for f in all_flags if f.side == "home"],
        "both": [f for f in all_flags if f.side == "both"],
    }
    conflicting = flag_engine.conflicting_total_leans(all_flags)

    return render_template(
        "matchup.html", game=game, home=home, away=away,
        flags=grouped_flags, conflicting=conflicting,
    )


@app.route("/teams")
def teams():
    conn = get_conn()
    conference = request.args.get("conference", "")
    query = "SELECT * FROM teams"
    params = []
    if conference:
        query += " WHERE conference = ?"
        params.append(conference)
    query += " ORDER BY school"
    team_rows = conn.execute(query, params).fetchall()
    conferences = [r["conference"] for r in conn.execute(
        "SELECT DISTINCT conference FROM teams WHERE conference IS NOT NULL ORDER BY conference"
    ).fetchall()]
    conn.close()
    return render_template("teams.html", teams=team_rows,
                            conferences=conferences, selected_conf=conference)


@app.route("/team/<int:team_id>")
def team_detail(team_id):
    conn = get_conn()
    team = conn.execute("SELECT * FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    if not team:
        abort(404)

    games = conn.execute(
        """SELECT g.*, ht.school AS home_school, at.school AS away_school
           FROM games g
           JOIN teams ht ON g.home_team_id = ht.team_id
           JOIN teams at ON g.away_team_id = at.team_id
           WHERE g.home_team_id = ? OR g.away_team_id = ?
           ORDER BY g.season DESC, g.week DESC""",
        (team_id, team_id),
    ).fetchall()

    coaches = conn.execute(
        """SELECT c.first_name, c.last_name, cs.season, cs.role
           FROM coach_stints cs JOIN coaches c ON cs.coach_id = c.coach_id
           WHERE cs.team_id = ? ORDER BY cs.season DESC""",
        (team_id,),
    ).fetchall()

    top_players = conn.execute(
        """SELECT player_name, category, stat_type, stat_value, season
           FROM player_season_stats
           WHERE team_id = ? AND stat_type IN ('YDS','TD')
           ORDER BY season DESC, stat_value DESC LIMIT 15""",
        (team_id,),
    ).fetchall()

    conn.close()
    return render_template("team.html", team=team, games=games,
                            coaches=coaches, top_players=top_players)


@app.route("/players")
def players():
    conn = get_conn()
    season = request.args.get("season", type=int)
    category = request.args.get("category", "passing")
    stat_type = request.args.get("stat_type", "YDS")

    if not season:
        seasons = available_seasons(conn)
        season = seasons[0] if seasons else None

    rows = []
    if season:
        rows = conn.execute(
            """SELECT player_name, team_name, stat_value
               FROM player_season_stats
               WHERE season = ? AND category = ? AND stat_type = ?
               ORDER BY stat_value DESC LIMIT 50""",
            (season, category, stat_type),
        ).fetchall()

    seasons = available_seasons(conn)
    conn.close()
    return render_template(
        "leaderboard.html", rows=rows, seasons=seasons,
        selected_season=season, category=category, stat_type=stat_type,
    )


@app.route("/coaches")
def coaches():
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.coach_id, c.first_name, c.last_name,
                  GROUP_CONCAT(t.school || ' (' || cs.season || ')', ', ') AS history
           FROM coaches c
           JOIN coach_stints cs ON c.coach_id = cs.coach_id
           JOIN teams t ON cs.team_id = t.team_id
           GROUP BY c.coach_id
           ORDER BY c.last_name"""
    ).fetchall()
    conn.close()
    return render_template("coaches.html", coaches=rows)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
