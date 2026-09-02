# CFB Research Hub

A college football matchup research tool built for a weekly betting/content
workflow: a schedule you click through game by game, with tension points
(pace mismatches, matchup edges, turnover regression, weather, a new
coordinator's blended tendencies, and the gap between our power rating and
the market line) surfaced as plain facts — never a pick.

Runs two ways: **locally** via `python app.py` (full interactivity, every
season you've ingested), or as a **static site** rebuilt daily and deployed
free to your own domain via GitHub Pages (current season only). Most weeks
you'll just let the hosted site auto-refresh and only touch the local
version when you're building something new.

## First-time local setup

**1. Install the two things this needs, if you don't already have them:**
   - Python (3.9 or newer) — https://www.python.org/downloads/
   - That's it — everything else installs itself in step 3.

**2. Get a free data key** (emailed to your inbox):
   - Go to https://collegefootballdata.com/key, enter your email, submit
   - Check your email for the key — copy it

**3. Open a terminal in this folder and run these one at a time:**

```bash
pip install -r requirements.txt
```
```bash
export CFBD_API_KEY="paste_your_key_here"
```
*(Windows PowerShell: `$env:CFBD_API_KEY="paste_your_key_here"`)*
```bash
python3 ingest.py --year 2026
```
```bash
python3 ingest.py --year 2025
```
The second one is last season's data, used for the "who's actually back"
roster check and the depth chart's usage rankings — takes a few minutes,
the current-season pull is quicker.

**4. Start the site:**
```bash
python3 app.py
```
Then open **http://127.0.0.1:5000** (use `127.0.0.1`, not `localhost` — on
some Windows setups `localhost` resolves slowly for no good reason).

## Every time you want fresh data

Re-run the two `ingest.py` commands from step 3 (re-export the API key
first if you closed the terminal). Safe to run repeatedly — it updates
instead of duplicating. If you're using the hosted static site, this
happens automatically once a day (see below) — you only need to do this
manually for the local `python app.py` version, or to force an
off-schedule refresh before filming.

## Hosting on your own domain (free)

The site is rebuilt daily as flat HTML by `build_static.py` and deployed
to GitHub Pages by `.github/workflows/deploy.yml` — no server to pay for
or maintain.

**One-time setup, in the repo's GitHub settings:**

1. **Add your CFBD key as a secret**: Settings → Secrets and variables →
   Actions → New repository secret → name it `CFBD_API_KEY`, paste the
   key as the value.
2. **Turn on Pages**: Settings → Pages → under "Build and deployment",
   set Source to **GitHub Actions**.
3. **Custom domain**: create a file named `CNAME` (no extension) in this
   `cfb_tool/cfb_tool/` folder containing just your domain, e.g.
   `cfbtool.yourdomain.com`, and commit it. Then at your domain
   registrar, add a DNS record pointing that subdomain at GitHub Pages
   (a CNAME record → `<your-github-username>.github.io`, or an A record
   to GitHub's IPs if you're using an apex domain — GitHub's own docs at
   https://docs.github.com/pages/configuring-a-custom-domain-for-your-github-pages-site
   cover exactly which record type your case needs).
4. Run the workflow once manually (Actions tab → "Refresh data and
   deploy site" → Run workflow) rather than waiting for the next 12:00
   UTC cron run.

After that, it refreshes and redeploys itself daily on its own. Every
`git push` to `main` also triggers a redeploy, so pushing a code change
updates the live site within a couple minutes.

**Scope note:** the hosted static build only covers the *current* season
(schedule, weekly overview, and every matchup page) — last season stays
browsable only through the local `python app.py` version. Everything else
(flags, model-vs-market gap, depth charts, etc.) is identical between the
two; static hosting just means the season/week/flag-sensitivity controls
navigate between pre-built pages instead of hitting a live server.

## The coordinator-tracking piece (the TCU problem)

This is the part built specifically to answer "the new OC is run-heavy,
but should I trust one big game yet?"

**One-time-ish maintenance (a few times a year, ~10-15 min):**
Open `data/coordinator_hires.csv` in Excel/Sheets/Notepad and add a row
whenever a team hires a new OC or DC — just their name, team, season, and
role. There's no good free API for this, so this list is hand-kept.

**Then run these two, in order, any time you've added new rows or pulled
new games:**
```bash
python3 load_coordinators.py
python3 compute_tendencies.py
```
`compute_tendencies.py` prints every coach who's changed schools, so you
can see at a glance who's carrying history into a new job this year. The
blended tendency then shows up automatically as a flag on that team's
matchup card — no separate step needed.

## If something breaks

CollegeFootballData occasionally tweaks field names in their API
responses. If `ingest.py` prints "0 rows synced" for something, run:
```bash
python3 scripts/inspect_response.py team_game_stats --year 2026 --week 1
```
(swap `team_game_stats` for whichever step failed) and paste the output
back to Claude — that's enough to fix the parser in one pass rather than
guessing.

## What's in here

- **`db/schema.sql`** — the data model
- **`cfbd_client.py`** — talks to the CollegeFootballData API
- **`ingest.py`** — pulls teams/games/stats/roster/odds/SP+ into the local database
- **`app.py`** + **`templates/`** — the site, both for local dev and as the source the static build renders
- **`build_static.py`** — renders the whole site to flat HTML for hosting
- **`flags.py`** — the tension-point engine (tempo, matchup edges, turnover regression, weather, shootout/under, new-coordinator tendency)
- **`team_stats.py`**, **`sos.py`**, **`lines.py`**, **`weather.py`**, **`returning.py`**, **`depth_chart.py`**, **`coordinator.py`** — one module per signal type the flag engine and matchup card draw on
- **`data/coordinator_hires.csv`** + **`load_coordinators.py`** — hand-kept OC/DC tracking
- **`compute_tendencies.py`** + **`blend.py`** — coordinator history blending
- **`scripts/inspect_response.py`** — debug helper for when the API changes shape
- **`.github/workflows/deploy.yml`** — the daily refresh + static deploy job
