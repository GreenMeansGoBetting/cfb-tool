"""
Betting lines — a single "consensus" number per game (per the concept
doc: "one consensus number is enough — you already shop lines yourself"),
picked from whichever sportsbooks CFBD's /lines endpoint returned for
that game, plus the model-vs-market gap comparison against sos.py's SP+
implied spread.
"""

# Preference order when a game has multiple books — DraftKings first
# since it's the most consistently present/liquid book in CFBD's data;
# CFBD has been observed to spell it two different ways.
_PREFERRED_PROVIDERS = ["draftkings", "bovada", "espn bet", "consensus"]

MARKET_GAP_THRESHOLD = 3.0  # points — how big a model/market disagreement is worth stating


def preferred_line(conn, game_id):
    rows = conn.execute(
        "SELECT * FROM betting_lines WHERE game_id = ?", (game_id,)
    ).fetchall()
    if not rows:
        return None
    for pref in _PREFERRED_PROVIDERS:
        for r in rows:
            if r["provider"] and r["provider"].lower().replace(" ", "") == pref.replace(" ", ""):
                return r
    return rows[0]


def preferred_lines_for_games(conn, game_ids):
    """Batch version for the schedule page — one query instead of one
    per row, still picking each game's preferred provider the same way."""
    if not game_ids:
        return {}
    placeholders = ",".join("?" * len(game_ids))
    rows = conn.execute(
        f"SELECT * FROM betting_lines WHERE game_id IN ({placeholders})", game_ids
    ).fetchall()
    by_game = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r)
    result = {}
    for gid, lines in by_game.items():
        chosen = None
        for pref in _PREFERRED_PROVIDERS:
            chosen = next(
                (r for r in lines if r["provider"] and r["provider"].lower().replace(" ", "") == pref.replace(" ", "")),
                None,
            )
            if chosen:
                break
        result[gid] = chosen or lines[0]
    return result


def market_gap(model_spread, market_line):
    """Compares the SP+ implied spread against the market spread, stated
    as a plain fact — no pick, matching the concept doc's own example
    phrasing exactly. Returns None if there's nothing to compare, or the
    gap doesn't clear the noise floor."""
    if not model_spread or not market_line or market_line["spread"] is None:
        return None
    model_home_margin = model_spread["margin"] if model_spread["favored_team"] == "home" else -model_spread["margin"]
    market_home_margin = -market_line["spread"]  # CFBD spread is negative when home is favored
    gap = model_home_margin - market_home_margin
    if abs(gap) < MARKET_GAP_THRESHOLD:
        return None
    return {"gap": round(abs(gap), 1), "model_more_favors": "home" if gap > 0 else "away"}
