"""
Thin wrapper around the CollegeFootballData.com REST API.

Get a free key at https://collegefootballdata.com/key and set it as an
environment variable before running ingest.py:

    export CFBD_API_KEY="your_key_here"

Docs / endpoint reference: https://api.collegefootballdata.com
"""
import os
import time
import requests

BASE_URL = "https://api.collegefootballdata.com"


class CFBDClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("CFBD_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "No CFBD API key found. Set the CFBD_API_KEY environment "
                "variable, or pass api_key= directly. Get a free key at "
                "https://collegefootballdata.com/key"
            )
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        })

    def _get(self, path, params=None, retries=5, timeout=60):
        url = f"{BASE_URL}{path}"
        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
            except requests.exceptions.RequestException as e:
                wait = 2 ** attempt
                print(f"  request failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 ** attempt
                print(f"  {resp.status_code} from API, retrying in {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
        raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")

    # --- Teams & coaches -------------------------------------------------
    def get_teams(self, year=None):
        return self._get("/teams", {"year": year} if year else None)

    def get_coaches(self, year=None, team=None):
        params = {}
        if year:
            params["year"] = year
        if team:
            params["team"] = team
        return self._get("/coaches", params)

    # --- Games -------------------------------------------------------------
    def get_games(self, year, week=None, season_type="regular"):
        params = {"year": year, "seasonType": season_type}
        if week:
            params["week"] = week
        return self._get("/games", params)

    def get_team_game_stats(self, year, week=None, team=None):
        params = {"year": year}
        if week:
            params["week"] = week
        if team:
            params["team"] = team
        return self._get("/games/teams", params)

    # --- Players -------------------------------------------------------
    def get_roster(self, year, team=None):
        params = {"year": year}
        if team:
            params["team"] = team
        return self._get("/roster", params)

    def get_player_game_stats(self, year, week=None, team=None,
                               season_type="regular", category=None):
        """Raw per-game box score stats (nested shape - Phase 2)."""
        params = {"year": year, "seasonType": season_type}
        if week:
            params["week"] = week
        if team:
            params["team"] = team
        if category:
            params["category"] = category
        return self._get("/games/players", params)

    def get_player_season_stats(self, year, team=None, category=None,
                                 season_type="regular"):
        """Flat season-total player stats. Reliable source for MVP leaderboards."""
        params = {"year": year, "seasonType": season_type}
        if team:
            params["team"] = team
        if category:
            params["category"] = category
        return self._get("/stats/player/season", params)

    def get_sp_plus(self, year, team=None):
        """Opponent-adjusted SP+ ratings (overall/offense/defense/special
        teams) — CFBD computes these from day one of a season using last
        year's performance, returning production, and recruiting, so
        they're meaningful even in week 1."""
        params = {"year": year}
        if team:
            params["team"] = team
        return self._get("/ratings/sp", params)

    def get_returning_production(self, year, team=None):
        """Team-level % of last year's production (PPA/usage) still on the
        roster — the cold-start 'how much to trust last season's stats' input."""
        params = {"year": year}
        if team:
            params["team"] = team
        return self._get("/player/returning", params)
