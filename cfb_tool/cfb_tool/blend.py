"""
blend.py — the "new OC" answer.

Given a coach + their CURRENT team + CURRENT season, this blends:
  - their historical tendency (from prior stops, weighted by games coached)
  - this season's actual tendency so far (weighted by games played)

...into a single blended estimate that shifts from "trust the history" in
week 1 toward "trust this year's data" as the sample grows.

This is a starting formula, not gospel — it's meant to be a concrete,
inspectable starting point you can tune once you're watching it against
real weeks. The weighting curve (SAMPLE_WEIGHT_GAMES) is the main knob.

Usage:
    python3 blend.py --coach-id 1 --team-id 5 --season 2026
    (find IDs via the /coaches and /teams pages in the web UI, or query
    the coaches/teams tables directly)
"""
import argparse
from db.db import get_conn, init_db

# How many games of CURRENT-season data it takes to fully trust the new
# sample over the historical prior. 6 is a reasonable starting point for
# CFB (usage/tendency rates start stabilizing meaningfully by mid-season) -
# tune this once you've watched it play out.
SAMPLE_WEIGHT_GAMES = 6


def get_prior(conn, coach_id, team_id, season):
    """Historical tendency from every OTHER team/season this coach has data for,
    weighted by games coached at each stop (more games = more signal)."""
    rows = conn.execute(
        """SELECT run_rate, pass_rate, yards_per_play, games_sample
           FROM coordinator_tendencies
           WHERE coach_id = ? AND NOT (team_id = ? AND season = ?)
             AND run_rate IS NOT NULL""",
        (coach_id, team_id, season),
    ).fetchall()
    if not rows:
        return None
    total_games = sum(r["games_sample"] for r in rows)
    if total_games == 0:
        return None
    weighted_run = sum(r["run_rate"] * r["games_sample"] for r in rows) / total_games
    weighted_ypp = sum((r["yards_per_play"] or 0) * r["games_sample"] for r in rows) / total_games
    return {"run_rate": weighted_run, "yards_per_play": weighted_ypp, "games": total_games}


def get_current(conn, coach_id, team_id, season):
    row = conn.execute(
        """SELECT run_rate, pass_rate, yards_per_play, games_sample
           FROM coordinator_tendencies
           WHERE coach_id = ? AND team_id = ? AND season = ?""",
        (coach_id, team_id, season),
    ).fetchone()
    if not row or row["games_sample"] is None:
        return None
    return {"run_rate": row["run_rate"], "yards_per_play": row["yards_per_play"],
            "games": row["games_sample"]}


def blend(prior, current):
    """Returns blended run_rate and the weight breakdown, or explains what's missing."""
    if not current:
        if prior:
            return {"blended_run_rate": prior["run_rate"], "prior_weight": 1.0,
                     "current_weight": 0.0,
                     "note": "No current-season games yet - using prior stop(s) only."}
        return {"note": "No data at all for this coach - need at least one "
                         "season ingested (this or a prior stop)."}
    if not prior:
        return {"blended_run_rate": current["run_rate"], "prior_weight": 0.0,
                 "current_weight": 1.0,
                 "note": "No prior-stop history found - using current season only "
                         f"({current['games']} games)."}

    current_weight = min(current["games"] / SAMPLE_WEIGHT_GAMES, 1.0)
    prior_weight = 1 - current_weight
    blended = prior["run_rate"] * prior_weight + current["run_rate"] * current_weight
    return {
        "blended_run_rate": round(blended, 3),
        "prior_run_rate": round(prior["run_rate"], 3),
        "prior_games_sample": prior["games"],
        "current_run_rate": round(current["run_rate"], 3),
        "current_games_sample": current["games"],
        "prior_weight": round(prior_weight, 2),
        "current_weight": round(current_weight, 2),
        "note": f"{current['games']}/{SAMPLE_WEIGHT_GAMES} games into the season - "
                f"{round(current_weight*100)}% weight on this year's actual data.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coach-id", type=int, required=True)
    parser.add_argument("--team-id", type=int, required=True)
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()

    init_db()
    conn = get_conn()
    prior = get_prior(conn, args.coach_id, args.team_id, args.season)
    current = get_current(conn, args.coach_id, args.team_id, args.season)
    result = blend(prior, current)
    conn.close()

    print(f"\nCoach {args.coach_id} @ team {args.team_id}, {args.season} season:")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
