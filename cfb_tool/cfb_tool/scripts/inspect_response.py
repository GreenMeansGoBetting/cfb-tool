"""
Debug helper: dump a raw CFBD API response so you (or Claude) can see the
exact field names and fix a parser without guessing.

Usage examples:
    python3 scripts/inspect_response.py teams --year 2026
    python3 scripts/inspect_response.py team_game_stats --year 2026 --week 1
    python3 scripts/inspect_response.py player_season_stats --year 2026 --category rushing
    python3 scripts/inspect_response.py coaches --year 2026

If a sync_* function in ingest.py comes back with 0 rows, run the matching
command here, paste the output back to Claude, and it'll fix the field
mapping in one pass instead of guessing blind.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from cfbd_client import CFBDClient  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("endpoint", choices=[
        "teams", "coaches", "games", "team_game_stats",
        "player_season_stats", "roster",
    ])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--week", type=int)
    parser.add_argument("--team", type=str)
    parser.add_argument("--category", type=str)
    parser.add_argument("--limit", type=int, default=1,
                         help="Only print this many top-level items (default 1)")
    args = parser.parse_args()

    client = CFBDClient()
    method_map = {
        "teams": lambda: client.get_teams(year=args.year),
        "coaches": lambda: client.get_coaches(year=args.year, team=args.team),
        "games": lambda: client.get_games(year=args.year, week=args.week),
        "team_game_stats": lambda: client.get_team_game_stats(
            year=args.year, week=args.week, team=args.team),
        "player_season_stats": lambda: client.get_player_season_stats(
            year=args.year, team=args.team, category=args.category),
        "roster": lambda: client.get_roster(year=args.year, team=args.team),
    }
    data = method_map[args.endpoint]()
    print(f"Total items returned: {len(data)}\n")
    print(json.dumps(data[:args.limit], indent=2))


if __name__ == "__main__":
    main()
