# CFB Research Hub

A local college football research tool: team stats, player stats, coaching
history, and a "new coordinator" tracker that blends a coach's history with
this season's actual data — built for your betting/content workflow.

## First-time setup (do this once)

**1. Install the two things this needs, if you don't already have them:**
   - Python (3.9 or newer) — https://www.python.org/downloads/
   - That's it, actually — everything else installs itself in step 3.

**2. Get a free data key.** This is the one step only you can do (it gets
   emailed to your inbox):
   - Go to https://collegefootballdata.com/key
   - Enter your email, submit
   - Check your email for the key (a long string of letters/numbers) — copy it

**3. Open a terminal in this folder and run these commands one at a time:**

```bash
pip install -r requirements.txt
```

```bash
export CFBD_API_KEY="paste_your_key_here"
```
*(On Windows PowerShell, use `$env:CFBD_API_KEY="paste_your_key_here"` instead)*

```bash
python3 ingest.py --year 2026
```
This pulls teams, games, and player stats. Takes a minute or two. You'll
see progress printed as it goes.

**4. Start the site:**
```bash
python3 app.py
```
Then open your browser to **http://127.0.0.1:5000** (use the `127.0.0.1`
form, not `localhost` — on some Windows setups `localhost` resolves slowly
and every page will feel sluggish even though the app itself is fast)

That's it — you now have a working local site with teams, games, and player
leaderboards.

## Every time you want fresh data (weekly, during the season)

Just re-run step 3's `ingest.py` command again (you'll need to re-export the
API key if you closed the terminal). It's safe to run repeatedly — it
updates instead of duplicating.

## The coordinator-tracking piece (the TCU problem)

This is the part built specifically to answer "the new OC is run-heavy, but
should I trust one big game yet?"

**One-time-ish maintenance (a few times a year, ~10-15 min):**
Open `data/coordinator_hires.csv` in Excel/Sheets/Notepad and add a row
whenever a team hires a new OC or DC — just their name, team, season, and
role. There's no good free API for this, so this list is hand-kept. It's
short: ~130 FBS programs, and hires only happen a few times a year.

**Then run these two, in order, any time you've added new rows or pulled
new games:**
```bash
python3 load_coordinators.py
python3 compute_tendencies.py
```
`compute_tendencies.py` will print out every coach who's changed schools,
so you can see at a glance who's carrying history into a new job this year.

**To get an actual blended number** (historical tendency + this season's
games so far, weighted by sample size) for one coach:
```bash
python3 blend.py --coach-id <id> --team-id <id> --season 2026
```
Find the coach/team IDs by browsing the site's Coaches and Teams pages, or
by asking Claude to look them up in the database for you if you're running
this together.

## If something breaks

The most likely failure point is that CollegeFootballData occasionally
tweaks field names in their API responses. If `ingest.py` prints "0 rows
synced" for something, run:
```bash
python3 scripts/inspect_response.py team_game_stats --year 2026 --week 1
```
(swap `team_game_stats` for whichever step failed) and paste the output
back to Claude — that's enough to fix the parser in one pass rather than
guessing.

## What's in here

- **`db/schema.sql`** — the data model
- **`cfbd_client.py`** — talks to the CollegeFootballData API
- **`ingest.py`** — pulls teams/games/team-stats/player-stats into the local database
- **`data/coordinator_hires.csv`** + **`load_coordinators.py`** — hand-kept OC/DC tracking
- **`compute_tendencies.py`** — turns raw team-game stats into per-coach run/pass tendencies
- **`blend.py`** — the prior-vs-current-season weighting model
- **`app.py`** + **`templates/`** — the browsable website
- **`scripts/inspect_response.py`** — debug helper for when the API changes shape

## Known gaps / next steps

1. **Per-game player stats** (game-by-game splits, not just season totals)
   aren't wired up yet — the season-totals endpoint was more reliable to
   build the MVP against. This is the natural next addition.
2. **The web UI doesn't show blended tendencies yet** — right now `blend.py`
   is a command-line tool. Next logical step: put a "coordinator outlook"
   box on the team page that shows this automatically.
3. **Slate view** — a page that shows all of a given week's games with
   tendency mismatches flagged (Team A's run defense vs. Team B's new
   run-heavy OC) — this is the payoff step for the handicapping use case,
   sitting on top of everything built so far.
4. **Odds/line data** isn't integrated yet — that's the piece that lets you
   compare your numbers against the market.
5. **Hosting on your website:** once you're happy with this locally, it
   moves to a small VPS (Railway/Render/DigitalOcean, roughly $5-20/month)
   with minimal changes. Worth switching from SQLite to Postgres first if
   you expect real concurrent traffic once you open it up to other users.
