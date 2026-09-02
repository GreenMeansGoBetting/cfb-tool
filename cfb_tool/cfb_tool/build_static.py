"""
Renders the whole site to flat HTML files for static hosting (GitHub
Pages, or any plain file host) — see cfb_tool_concept.md's hosting
decision. Reuses the live Flask app's own routes via its test client (an
in-process fake request, no real server needed) so there's exactly one
copy of the rendering logic; this script only decides WHICH urls to
render and WHERE to save each one.

Scope: the current season only (schedule/overview/matchup pages for
every week), plus the season-agnostic pages (teams/players/coaches).
Last season stays browsable only through the local `python app.py` dev
server for now — not part of the static build.

Usage:
    python3 build_static.py [--out dist]
"""
import argparse
import shutil
from pathlib import Path

from app import app, get_conn, _default_season_week, _season_weeks

HERE = Path(__file__).parent


def _save(client, url, out_path):
    resp = client.get(url)
    if resp.status_code != 200:
        print(f"  WARN: {url} -> {resp.status_code}, skipping")
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.data)


def build(out_dir):
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    conn = get_conn()
    season, _, _, _ = _default_season_week(conn)
    weeks = _season_weeks(conn, season)
    game_ids = [r["game_id"] for r in conn.execute(
        """SELECT g.game_id FROM games g
           JOIN teams ht ON g.home_team_id = ht.team_id
           JOIN teams at ON g.away_team_id = at.team_id
           WHERE g.season = ? AND g.season_type = 'regular'
             AND ht.classification = 'fbs' AND at.classification = 'fbs'""",
        (season,),
    ).fetchall()]
    team_ids = [r["team_id"] for r in conn.execute("SELECT team_id FROM teams").fetchall()]
    conn.close()

    client = app.test_client()

    print(f"Building static site for season {season} ({len(weeks)} weeks, {len(game_ids)} games)...")

    _save(client, "/", out / "index.html")
    for week in weeks:
        _save(client, f"/week/{season}/{week}", out / "week" / str(season) / str(week) / "index.html")

    _save(client, "/overview", out / "overview" / "index.html")
    for week in weeks:
        _save(client, f"/overview/{season}/{week}", out / "overview" / str(season) / str(week) / "index.html")

    print(f"  {len(game_ids)} matchup pages...")
    for game_id in game_ids:
        _save(client, f"/game/{game_id}", out / "game" / str(game_id) / "index.html")

    _save(client, "/teams", out / "teams" / "index.html")
    for team_id in team_ids:
        _save(client, f"/team/{team_id}", out / "team" / str(team_id) / "index.html")

    _save(client, "/players", out / "players" / "index.html")
    _save(client, "/coaches", out / "coaches" / "index.html")

    shutil.copytree(HERE / "static", out / "static")

    # Custom domain, if configured — see README. GitHub Pages needs this
    # file present in every deploy (it doesn't persist on its own), so it
    # gets copied fresh on each build rather than living in dist/ itself.
    cname_src = HERE / "CNAME"
    if cname_src.exists():
        shutil.copy(cname_src, out / "CNAME")

    print(f"Done. Static site written to {out}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist")
    args = parser.parse_args()
    build(args.out)
