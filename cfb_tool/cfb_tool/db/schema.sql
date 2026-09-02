-- CFB Research Tool — core schema
-- Design notes:
--   * coach_stints is what lets us look up a coordinator's history
--     independent of which school they're at *this* season.
--   * coordinator_tendencies is a DERIVED table — computed from
--     team_game_stats/play data, not pulled directly from the API.
--   * Everything keys off CFBD's own IDs where possible so re-syncing
--     is just an upsert, not a rebuild.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS teams (
    team_id     INTEGER PRIMARY KEY,   -- CFBD team id
    school      TEXT NOT NULL,
    conference  TEXT,
    division    TEXT,
    classification TEXT,              -- fbs / fcs
    logo_url    TEXT                  -- CFBD CDN logo, ~128px
);

-- Betting lines, sourced from CFBD's own /lines endpoint (it aggregates
-- several sportsbooks — no separate odds API/account needed). One row
-- per (game, sportsbook) since a game can carry several books' numbers;
-- lines.py picks a single "consensus" one at query time rather than
-- flattening to one book here, so nothing is thrown away on ingest.
CREATE TABLE IF NOT EXISTS betting_lines (
    game_id         INTEGER NOT NULL REFERENCES games(game_id),
    provider        TEXT NOT NULL,
    spread          REAL,     -- home-relative: negative = home favored
    spread_open     REAL,
    over_under      REAL,
    over_under_open REAL,
    home_moneyline  INTEGER,
    away_moneyline  INTEGER,
    PRIMARY KEY (game_id, provider)
);

CREATE TABLE IF NOT EXISTS coaches (
    coach_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name  TEXT,
    last_name   TEXT NOT NULL,
    UNIQUE(first_name, last_name)
);

-- One row per coach per team per season per role.
-- This is the backbone of the "new OC" tracking.
CREATE TABLE IF NOT EXISTS coach_stints (
    stint_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    coach_id    INTEGER NOT NULL REFERENCES coaches(coach_id),
    team_id     INTEGER NOT NULL REFERENCES teams(team_id),
    season      INTEGER NOT NULL,
    role        TEXT NOT NULL,          -- 'HC', 'OC', 'DC', 'ST', etc.
    UNIQUE(coach_id, team_id, season, role)
);

CREATE TABLE IF NOT EXISTS games (
    game_id         INTEGER PRIMARY KEY,   -- CFBD game id
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    season_type     TEXT DEFAULT 'regular',
    start_date      TEXT,
    home_team_id    INTEGER REFERENCES teams(team_id),
    away_team_id    INTEGER REFERENCES teams(team_id),
    home_points     INTEGER,
    away_points     INTEGER,
    venue           TEXT,
    venue_id        INTEGER REFERENCES venues(venue_id),
    conference_game INTEGER DEFAULT 0,
    neutral_site    INTEGER DEFAULT 0
);

-- Venue locations, sourced from CFBD's /venues endpoint — used to fetch
-- live weather forecasts (see weather.py) and to skip weather entirely
-- for dome games, where it's not a factor.
CREATE TABLE IF NOT EXISTS venues (
    venue_id    INTEGER PRIMARY KEY,   -- CFBD venue id
    name        TEXT,
    city        TEXT,
    state       TEXT,
    dome        INTEGER DEFAULT 0,
    latitude    REAL,
    longitude   REAL
);

CREATE TABLE IF NOT EXISTS team_game_stats (
    game_id             INTEGER NOT NULL REFERENCES games(game_id),
    team_id             INTEGER NOT NULL REFERENCES teams(team_id),
    opponent_id         INTEGER REFERENCES teams(team_id),
    is_home             INTEGER,
    plays               INTEGER,
    total_yards         INTEGER,
    rush_attempts       INTEGER,
    rush_yards          INTEGER,
    pass_attempts       INTEGER,
    pass_completions    INTEGER,
    pass_yards          INTEGER,
    third_down_att      INTEGER,
    third_down_conv     INTEGER,
    fourth_down_att     INTEGER,
    fourth_down_conv    INTEGER,
    turnovers           INTEGER,
    time_of_possession  TEXT,           -- store as "MM:SS" text from API
    PRIMARY KEY (game_id, team_id)
);

-- Roster snapshot, sourced from CFBD's /roster endpoint — one row per
-- player per season (a player who's on multiple seasons' rosters gets
-- multiple rows). This is what lets returning.py answer "is last year's
-- top producer actually still on this team" instead of just trusting a
-- team-wide returning-production percentage.
CREATE TABLE IF NOT EXISTS players (
    player_id       INTEGER NOT NULL,   -- CFBD athlete id
    season          INTEGER NOT NULL,
    name            TEXT NOT NULL,
    team_id         INTEGER REFERENCES teams(team_id),
    position        TEXT,
    year            TEXT,               -- class year (CFBD returns this as a number, e.g. 4)
    height          INTEGER,
    weight          INTEGER,
    home_town       TEXT,
    PRIMARY KEY (player_id, season)
);

CREATE TABLE IF NOT EXISTS player_game_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       INTEGER NOT NULL,
    game_id         INTEGER NOT NULL REFERENCES games(game_id),
    team_id         INTEGER REFERENCES teams(team_id),
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    category        TEXT NOT NULL,      -- 'passing' | 'rushing' | 'receiving'
    -- passing
    pass_completions INTEGER,
    pass_attempts     INTEGER,
    pass_yards        INTEGER,
    pass_td           INTEGER,
    pass_int          INTEGER,
    -- rushing
    rush_attempts     INTEGER,
    rush_yards        INTEGER,
    rush_td           INTEGER,
    -- receiving
    receptions        INTEGER,
    rec_yards         INTEGER,
    rec_td            INTEGER,
    UNIQUE(player_id, game_id, category),
    FOREIGN KEY (player_id, season) REFERENCES players(player_id, season)
);

-- Derived / computed table — rebuilt by ingest.py's tendency calculator,
-- not written directly from raw API responses.
CREATE TABLE IF NOT EXISTS coordinator_tendencies (
    coach_id            INTEGER NOT NULL REFERENCES coaches(coach_id),
    team_id             INTEGER NOT NULL REFERENCES teams(team_id),
    season              INTEGER NOT NULL,
    games_sample        INTEGER,
    plays_per_game      REAL,
    run_rate            REAL,     -- rush_attempts / (rush_attempts+pass_attempts)
    pass_rate           REAL,
    yards_per_play       REAL,
    PRIMARY KEY (coach_id, team_id, season)
);

-- Season-level totals, sourced from the /stats/player/season endpoint.
-- This endpoint returns a clean flat shape (unlike /games/players, which
-- nests categories/types/athletes) so it's the reliable source for
-- leaderboards and season pages. Per-game granularity (player_game_stats
-- above) is wired up but its source endpoint needs response-shape
-- verification against a live API key — see README "Known gaps".
CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id       INTEGER NOT NULL,
    player_name     TEXT NOT NULL,
    team_id         INTEGER REFERENCES teams(team_id),
    team_name       TEXT,
    season          INTEGER NOT NULL,
    category        TEXT NOT NULL,     -- passing / rushing / receiving
    stat_type       TEXT NOT NULL,     -- YDS / TD / ATT / CAR / REC / INT etc.
    stat_value      REAL,
    PRIMARY KEY (player_id, season, category, stat_type)
);

-- Opponent-adjusted SP+ ratings, sourced from CFBD's /ratings/sp endpoint.
-- CFBD computes these from before week 1 (using returning production,
-- recruiting, and last year's play), so they're meaningful all season,
-- not just once a team has games in the book.
CREATE TABLE IF NOT EXISTS sp_plus_ratings (
    team_id             INTEGER NOT NULL REFERENCES teams(team_id),
    season              INTEGER NOT NULL,
    rating              REAL,
    ranking             INTEGER,
    off_rating          REAL,
    off_ranking         INTEGER,
    def_rating          REAL,
    def_ranking         INTEGER,
    special_teams_rating REAL,
    PRIMARY KEY (team_id, season)
);

-- Team-level returning production, sourced from CFBD's /player/returning
-- endpoint. Drives the REBUILD badge (see team_stats.py) — a plain roster
-- fact about how much of last year's production is still around, shown
-- alongside this year's stats rather than blended into them.
CREATE TABLE IF NOT EXISTS returning_production (
    team_id     INTEGER NOT NULL REFERENCES teams(team_id),
    season      INTEGER NOT NULL,
    pct_ppa     REAL,        -- fraction (0-1ish) of last year's total PPA still on the roster
    usage_pct   REAL,        -- fraction of last year's snap/usage still on the roster
    PRIMARY KEY (team_id, season)
);

-- Small key/value table for things like "last ingested at" — not
-- CFBD-sourced data, just local bookkeeping for the UI.
CREATE TABLE IF NOT EXISTS meta (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

CREATE INDEX IF NOT EXISTS idx_pss_season_cat ON player_season_stats(season, category, stat_type);
CREATE INDEX IF NOT EXISTS idx_pgs_player_season ON player_game_stats(player_id, season);
CREATE INDEX IF NOT EXISTS idx_pgs_team_season ON player_game_stats(team_id, season);
CREATE INDEX IF NOT EXISTS idx_tgs_team_season ON team_game_stats(team_id);
CREATE INDEX IF NOT EXISTS idx_games_season_week ON games(season, week);
