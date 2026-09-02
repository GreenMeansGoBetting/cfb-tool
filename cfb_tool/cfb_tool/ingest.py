"""
Pulls data from CFBD and loads it into the local SQLite database.

Usage:
    export CFBD_API_KEY="your_key_here"
    python3 ingest.py --year 2026                 # full sync for a season
    python3 ingest.py --year 2026 --teams-only     # just teams/coaches
"""
import argparse
import sys
from datetime import datetime, timezone
from db.db import get_conn, init_db
from cfbd_client import CFBDClient


def _pick_logo(logos):
    """CFBD returns a list of CDN URLs at several sizes — pick the ~128px
    one (small enough to load fast, big enough not to blur at the sizes
    this app displays it)."""
    if not logos:
        return None
    for url in logos:
        if "/128/" in url:
            return url
    return logos[0]


def sync_teams(client, conn, year):
    print(f"Syncing teams for {year}...")
    teams = client.get_teams(year=year)
    rows = [
        (t.get("id"), t.get("school"), t.get("conference"),
         t.get("division"), t.get("classification"), _pick_logo(t.get("logos")))
        for t in teams if t.get("id") is not None
    ]
    conn.executemany(
        """INSERT INTO teams (team_id, school, conference, division, classification, logo_url)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(team_id) DO UPDATE SET
             school=excluded.school, conference=excluded.conference,
             division=excluded.division, classification=excluded.classification,
             logo_url=excluded.logo_url""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} teams synced.")


def sync_coaches(client, conn, year):
    print(f"Syncing coaches for {year}...")
    coaches = client.get_coaches(year=year)
    stint_count = 0
    for c in coaches:
        first, last = c.get("firstName"), c.get("lastName")
        if not last:
            continue
        cur = conn.execute(
            """INSERT INTO coaches (first_name, last_name) VALUES (?, ?)
               ON CONFLICT(first_name, last_name) DO UPDATE SET last_name=excluded.last_name
               RETURNING coach_id""",
            (first, last),
        )
        row = cur.fetchone()
        if row is None:
            row = conn.execute(
                "SELECT coach_id FROM coaches WHERE first_name IS ? AND last_name = ?",
                (first, last),
            ).fetchone()
        coach_id = row[0]

        for stint in c.get("seasons", []):
            team_name = stint.get("school")
            team_row = conn.execute(
                "SELECT team_id FROM teams WHERE school = ?", (team_name,)
            ).fetchone()
            if not team_row:
                continue  # team not synced yet / name mismatch
            conn.execute(
                """INSERT INTO coach_stints (coach_id, team_id, season, role)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(coach_id, team_id, season, role) DO NOTHING""",
                (coach_id, team_row[0], stint.get("year"), "HC"),
            )
            stint_count += 1
    conn.commit()
    print(f"  {stint_count} coach-season stints synced.")
    print("  NOTE: CFBD's /coaches endpoint returns head coaches reliably; "
          "OC/DC-level data is thinner and may need a secondary source "
          "(e.g. team websites or a manually maintained CSV) for full "
          "coordinator tracking. See README.")


def _ensure_teams_exist(conn, games):
    """Games can reference teams (FCS opponents, service academies, All-Star
    game placeholders, etc.) that didn't come back from the main /teams pull.
    Add minimal stub rows for any of those so the FK constraint on games
    never breaks the sync. Real details (conference etc.) will fill in
    later if that team ever shows up in a proper /teams response."""
    known_ids = {r[0] for r in conn.execute("SELECT team_id FROM teams").fetchall()}
    stubs = {}
    for g in games:
        home_id = g.get("homeId") or g.get("home_id")
        away_id = g.get("awayId") or g.get("away_id")
        home_name = g.get("homeTeam") or g.get("home_team")
        away_name = g.get("awayTeam") or g.get("away_team")
        if home_id is not None and home_id not in known_ids:
            stubs[home_id] = home_name or f"Unknown Team {home_id}"
        if away_id is not None and away_id not in known_ids:
            stubs[away_id] = away_name or f"Unknown Team {away_id}"
    if stubs:
        conn.executemany(
            """INSERT INTO teams (team_id, school) VALUES (?, ?)
               ON CONFLICT(team_id) DO NOTHING""",
            list(stubs.items()),
        )
        conn.commit()
        print(f"  Added {len(stubs)} team(s) not in the main teams list "
              f"(likely FCS opponents / placeholders): "
              f"{', '.join(list(stubs.values())[:5])}"
              f"{' ...' if len(stubs) > 5 else ''}")


def sync_venues(client, conn):
    print("Syncing venues...")
    venues = client.get_venues()
    rows = [
        (v.get("id"), v.get("name"), v.get("city"), v.get("state"),
         int(bool(v.get("dome"))), v.get("latitude"), v.get("longitude"))
        for v in venues if v.get("id") is not None
    ]
    conn.executemany(
        """INSERT INTO venues (venue_id, name, city, state, dome, latitude, longitude)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(venue_id) DO UPDATE SET
             name=excluded.name, city=excluded.city, state=excluded.state,
             dome=excluded.dome, latitude=excluded.latitude, longitude=excluded.longitude""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} venues synced.")


def sync_games(client, conn, year):
    print(f"Syncing games for {year}...")
    games = client.get_games(year=year)
    _ensure_teams_exist(conn, games)
    known_venue_ids = {r[0] for r in conn.execute("SELECT venue_id FROM venues").fetchall()}
    rows = [
        (g.get("id"), g.get("season"), g.get("week"), g.get("seasonType"),
         g.get("startDate"), g.get("homeId") or g.get("home_id"),
         g.get("awayId") or g.get("away_id"),
         g.get("homePoints"), g.get("awayPoints"), g.get("venue"),
         g.get("venueId") if g.get("venueId") in known_venue_ids else None,
         int(bool(g.get("conferenceGame"))), int(bool(g.get("neutralSite"))))
        for g in games if g.get("id") is not None
    ]
    conn.executemany(
        """INSERT INTO games (game_id, season, week, season_type, start_date,
             home_team_id, away_team_id, home_points, away_points, venue, venue_id,
             conference_game, neutral_site)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(game_id) DO UPDATE SET
             home_points=excluded.home_points, away_points=excluded.away_points,
             venue_id=excluded.venue_id""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} games synced.")


def _split_week_zero(conn, year):
    """CFBD has no separate 'Week 0' in its data -- the small
    season-opening slate (the odd Thursday/weekend of games before the
    main slate) gets lumped into week=1, which then spans 10+ days and
    mixes already-played games in with the upcoming week. Detect the
    real-world gap (Week 0 games cluster a few days before Week 1's
    Thursday, with a multi-day dead stretch between them) and relabel
    that early cluster to week=0 in our own data. Only ever touches
    week=1 -- this specific double-slate pattern doesn't happen in later
    weeks, so there's nothing to (mis)detect there.

    Deliberately run this LAST in the ingest pipeline (see main()), after
    every step that loops over "distinct weeks this season" to query
    CFBD (team stats) -- CFBD's own API doesn't know about week=0 either,
    so relabeling before those steps run would make them waste a call on
    a week CFBD has no data for, instead of the week=1 call that actually
    covers both our week=0 and week=1 games."""
    from datetime import datetime
    rows = conn.execute(
        "SELECT game_id, start_date FROM games WHERE season = ? AND season_type = 'regular' AND week = 1 ORDER BY start_date",
        (year,),
    ).fetchall()
    if len(rows) < 3:
        return
    parsed = [(r[0], datetime.fromisoformat(r[1].replace("Z", "+00:00"))) for r in rows if r[1]]
    split_index = None
    for i in range(1, len(parsed)):
        gap_hours = (parsed[i][1] - parsed[i - 1][1]).total_seconds() / 3600
        if gap_hours >= 48:
            split_index = i
            break
    if split_index is None or split_index < 2:
        return  # no real gap, or too few games before it to be a real Week 0 slate
    early_ids = [gid for gid, _ in parsed[:split_index]]
    conn.executemany("UPDATE games SET week = 0 WHERE game_id = ?", [(gid,) for gid in early_ids])
    conn.commit()
    print(f"  Split {len(early_ids)} early game(s) into Week 0 "
          f"(gap detected before {parsed[split_index][1].date()})")


def sync_team_game_stats(client, conn, year):
    print(f"Syncing team game stats for {year}...")
    # CFBD requires week, team, or conference on this endpoint — a bare
    # ?year= is rejected, so pull it one regular-season week at a time.
    weeks = [r[0] for r in conn.execute(
        "SELECT DISTINCT week FROM games WHERE season = ? AND season_type = 'regular' ORDER BY week",
        (year,),
    ).fetchall()]
    known_team_ids = {r[0] for r in conn.execute("SELECT team_id FROM teams").fetchall()}
    known_game_ids = {r[0] for r in conn.execute(
        "SELECT game_id FROM games WHERE season = ?", (year,)
    ).fetchall()}

    rows = []
    for week in weeks:
        try:
            stats = client.get_team_game_stats(year=year, week=week)
        except Exception as e:
            print(f"  week {week}: FAILED ({e}) — skipping, rerun ingest later to fill it in")
            continue
        for g in stats:
            game_id = g.get("id")
            if game_id not in known_game_ids:
                continue  # game not in our /games sync (e.g. exhibition/all-star) — skip, FK would reject it
            for team_entry in g.get("teams", []):
                team_id = team_entry.get("teamId")
                if team_id not in known_team_ids:
                    continue
                stat_map = {s.get("category"): s.get("stat") for s in team_entry.get("stats", [])}
                rush_att = _to_int(stat_map.get("rushingAttempts"))
                pass_att = _to_int(_split_pct(stat_map.get("completionAttempts"), 1))
                # This endpoint doesn't break out a standalone "total plays"
                # figure — approximate it as rush + pass attempts (omits
                # sacks/penalties, close enough for a pace/tempo read).
                plays = (rush_att or 0) + (pass_att or 0) if (rush_att is not None or pass_att is not None) else None
                rows.append((
                    game_id, team_id, None,
                    1 if team_entry.get("homeAway") == "home" else 0,
                    plays,
                    _to_int(stat_map.get("totalYards")),
                    rush_att,
                    _to_int(stat_map.get("rushingYards")),
                    pass_att,
                    _to_int(_split_pct(stat_map.get("completionAttempts"), 0)),
                    _to_int(stat_map.get("netPassingYards")),
                    _to_int(_split_pct(stat_map.get("thirdDownEff"), 1)),
                    _to_int(_split_pct(stat_map.get("thirdDownEff"), 0)),
                    _to_int(_split_pct(stat_map.get("fourthDownEff"), 1)),
                    _to_int(_split_pct(stat_map.get("fourthDownEff"), 0)),
                    _to_int(stat_map.get("turnovers")),
                    stat_map.get("possessionTime"),
                ))
        print(f"  week {week}: {len(stats)} games")

    if rows:
        conn.executemany(
            """INSERT INTO team_game_stats
                 (game_id, team_id, opponent_id, is_home, plays, total_yards,
                  rush_attempts, rush_yards, pass_attempts, pass_completions,
                  pass_yards, third_down_att, third_down_conv, fourth_down_att,
                  fourth_down_conv, turnovers, time_of_possession)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(game_id, team_id) DO UPDATE SET
                 plays=excluded.plays, total_yards=excluded.total_yards, rush_attempts=excluded.rush_attempts,
                 rush_yards=excluded.rush_yards, pass_attempts=excluded.pass_attempts,
                 pass_completions=excluded.pass_completions, pass_yards=excluded.pass_yards,
                 third_down_att=excluded.third_down_att, third_down_conv=excluded.third_down_conv,
                 fourth_down_att=excluded.fourth_down_att, fourth_down_conv=excluded.fourth_down_conv,
                 turnovers=excluded.turnovers, time_of_possession=excluded.time_of_possession""",
            rows,
        )
        conn.commit()
    print(f"  {len(rows)} team-game stat rows synced.")
    print("  NOTE: field names in this endpoint vary a bit release to "
          "release - if this shows 0 rows, run scripts/inspect_response.py "
          "to see the raw shape and adjust the stat_map keys above.")


def _split_pct(val, idx):
    """CFBD returns completion/attempts as 'C-A' string sometimes; split it."""
    if not val or "-" not in str(val):
        return val
    parts = str(val).split("-")
    return parts[idx] if len(parts) > idx else None


def _to_int(val):
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def sync_player_season_stats(client, conn, year):
    print(f"Syncing player season stats for {year}...")
    total = 0
    for category in ("passing", "rushing", "receiving"):
        stats = client.get_player_season_stats(year=year, category=category)
        rows = []
        for s in stats:
            team_row = conn.execute(
                "SELECT team_id FROM teams WHERE school = ?", (s.get("team"),)
            ).fetchone()
            rows.append((
                s.get("playerId"), s.get("player"),
                team_row[0] if team_row else None, s.get("team"),
                year, category, s.get("statType"), _to_float(s.get("stat")),
            ))
        conn.executemany(
            """INSERT INTO player_season_stats
                 (player_id, player_name, team_id, team_name, season, category, stat_type, stat_value)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(player_id, season, category, stat_type) DO UPDATE SET
                 stat_value=excluded.stat_value""",
            rows,
        )
        conn.commit()
        total += len(rows)
        print(f"  {category}: {len(rows)} rows")
    print(f"  {total} total player-season stat rows synced.")


def _to_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def sync_roster(client, conn, year):
    print(f"Syncing roster for {year}...")
    roster = client.get_roster(year=year)
    rows = []
    for p in roster:
        pid = p.get("id")
        if pid is None:
            continue
        team_row = conn.execute(
            "SELECT team_id FROM teams WHERE school = ?", (p.get("team"),)
        ).fetchone()
        name = f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip()
        home_town = ", ".join(filter(None, [p.get("homeCity"), p.get("homeState")])) or None
        rows.append((
            pid, year, name, team_row[0] if team_row else None, p.get("position"),
            p.get("year"), p.get("height"), p.get("weight"), home_town,
        ))
    conn.executemany(
        """INSERT INTO players (player_id, season, name, team_id, position, year, height, weight, home_town)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(player_id, season) DO UPDATE SET
             name=excluded.name, team_id=excluded.team_id, position=excluded.position,
             year=excluded.year, height=excluded.height, weight=excluded.weight,
             home_town=excluded.home_town""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} roster rows synced.")


def sync_lines(client, conn, year):
    print(f"Syncing betting lines for {year}...")
    games = client.get_lines(year=year)
    known_game_ids = {r[0] for r in conn.execute(
        "SELECT game_id FROM games WHERE season = ?", (year,)
    ).fetchall()}
    rows = []
    for g in games:
        game_id = g.get("id")
        if game_id not in known_game_ids:
            continue
        for line in g.get("lines", []):
            provider = line.get("provider")
            if not provider:
                continue
            rows.append((
                game_id, provider, _to_float(line.get("spread")), _to_float(line.get("spreadOpen")),
                _to_float(line.get("overUnder")), _to_float(line.get("overUnderOpen")),
                line.get("homeMoneyline"), line.get("awayMoneyline"),
            ))
    conn.executemany(
        """INSERT INTO betting_lines
             (game_id, provider, spread, spread_open, over_under, over_under_open,
              home_moneyline, away_moneyline)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(game_id, provider) DO UPDATE SET
             spread=excluded.spread, spread_open=excluded.spread_open,
             over_under=excluded.over_under, over_under_open=excluded.over_under_open,
             home_moneyline=excluded.home_moneyline, away_moneyline=excluded.away_moneyline""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} betting-line rows synced.")


def sync_sp_plus(client, conn, year):
    print(f"Syncing SP+ ratings for {year}...")
    rows_raw = client.get_sp_plus(year=year)
    rows = []
    for r in rows_raw:
        team_row = conn.execute(
            "SELECT team_id FROM teams WHERE school = ?", (r.get("team"),)
        ).fetchone()
        if not team_row:
            continue
        off = r.get("offense") or {}
        de = r.get("defense") or {}
        st = r.get("specialTeams") or {}
        rows.append((
            team_row[0], year, _to_float(r.get("rating")), r.get("ranking"),
            _to_float(off.get("rating")), off.get("ranking"),
            _to_float(de.get("rating")), de.get("ranking"),
            _to_float(st.get("rating")),
        ))
    conn.executemany(
        """INSERT INTO sp_plus_ratings
             (team_id, season, rating, ranking, off_rating, off_ranking,
              def_rating, def_ranking, special_teams_rating)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(team_id, season) DO UPDATE SET
             rating=excluded.rating, ranking=excluded.ranking,
             off_rating=excluded.off_rating, off_ranking=excluded.off_ranking,
             def_rating=excluded.def_rating, def_ranking=excluded.def_ranking,
             special_teams_rating=excluded.special_teams_rating""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} SP+ rating rows synced.")


def sync_returning_production(client, conn, year):
    print(f"Syncing returning production for {year}...")
    rows_raw = client.get_returning_production(year=year)
    rows = []
    for r in rows_raw:
        team_row = conn.execute(
            "SELECT team_id FROM teams WHERE school = ?", (r.get("team"),)
        ).fetchone()
        if not team_row:
            continue
        rows.append((team_row[0], year, _to_float(r.get("percentPPA")), _to_float(r.get("usage"))))
    conn.executemany(
        """INSERT INTO returning_production (team_id, season, pct_ppa, usage_pct)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(team_id, season) DO UPDATE SET
             pct_ppa=excluded.pct_ppa, usage_pct=excluded.usage_pct""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} returning-production rows synced.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--teams-only", action="store_true",
                         help="Only sync teams and coaches, skip games/stats")
    args = parser.parse_args()

    init_db()
    client = CFBDClient()
    conn = get_conn()

    try:
        sync_teams(client, conn, args.year)
        sync_coaches(client, conn, args.year)
        if not args.teams_only:
            sync_venues(client, conn)
            sync_games(client, conn, args.year)
            sync_team_game_stats(client, conn, args.year)
            sync_player_season_stats(client, conn, args.year)
            sync_returning_production(client, conn, args.year)
            sync_sp_plus(client, conn, args.year)
            sync_roster(client, conn, args.year)
            sync_lines(client, conn, args.year)
            _split_week_zero(conn, args.year)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('last_updated', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
