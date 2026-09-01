# CFB Matchup Tool — Concept v2

## The objective
Support a weekly YouTube/Twitter betting content workflow (1-2 videos/week,
Thursday/Friday turnaround) by making a ~60-game slate consumable. The tool's
job is to boil the slate down and surface tension points — not to hand over
picks.

## The model: Ball Park Pal, but for matchups
Current MLB routine: open Ball Park Pal each morning, click through matchups
one at a time, look at pitcher tendencies / batter matchups, find the value
yourself.

The CFB equivalent isn't a player-stats leaderboard (that exists everywhere
already — ESPN, CFBD's own site, etc.). It's a **matchup-by-matchup
click-through** where each game shows where two things are in conflict:

- An offensive strength lined up against a specific defensive weakness
- A tempo mismatch (fast team vs. slow team, or vice versa)
- A coaching tendency (new OC, scheme change) against a vulnerable unit
- A player tendency against a specific matchup weakness
- A personnel/injury change that shifts the picture from what the season
  stats alone would suggest

## The "guide, not spoonfeed" principle
This is the core design constraint, and it should shape every feature
decision:

- **Show the tension, not the conclusion.** "This offense averages 6.2 YPC
  on outside zone; this defense allows 5.8 YPC on outside zone" is the
  right level. "Take the over" is not.
- **Nudge first, data one click away.** A short flag/headline per matchup,
  with the underlying stats available on demand — not force-fed, not
  buried either.
- **Breadth over depth.** Explicitly: "75% solid across coaching
  tendencies, player tendencies, defensive liabilities, tempo, recent form,
  and injuries" beats "100% great at just one of those." Don't over-invest
  in one signal at the expense of covering the others.
- **Situational trends (ATS in a spot, revenge games) are minor flags at
  most** — never a headline reason a game gets surfaced. Avoid becoming
  another site full of gimmick stats.

## What counts as a signal (in priority order, all "good enough" > any
one being perfect)
1. Coaching tendencies — especially new hires, scheme changes (this is
   what the original coordinator-blending work was solving for)
2. Player tendencies — usage patterns, not just season totals
3. Defensive liabilities — specific weaknesses, not just "bad defense"
4. Tempo/pace
5. Recent form (last 2-3 games) vs. full-season stats — flagged as
   related to personnel/injury changes where applicable, not just noise
6. Injuries / depth-chart changes — tracked as an explicit signal, not
   folded silently into stat lines

## Scope
- Bet types: sides, totals, AND player props all matter for content
- FCS "buy games" count as data points on a team (even though unbettable)
- FBS vs. FBS is the betting-relevant universe, but a team's FCS tune-up
  game still informs the picture of that team

## What this is NOT (v1)
- Not a picks-generator or confidence-score black box
- Not primarily a stats leaderboard/browser (that's commodity — plenty of
  sites already do this)
- Not built for multi-user/selling access yet — this season's goal is a
  working personal tool that proves the concept. Multi-tenant, access
  control, etc. are explicitly out of scope until there's a proven
  process worth productizing.

## Workflow this needs to support
Thursday/Friday, sit down, click through the week's slate matchup by
matchup (not unlike scrolling a card feed), quickly triage into "nothing
here" / "worth a second look" / "this is my angle," using tool-surfaced
tension points as the starting point for the manual research/film-watching
you'd do anyway — not a replacement for it.

## Technical context (for later — not being built yet)
- User has no coding background; comfortable using Claude Code once
  it's clear it still requires some setup (installing the app, providing
  an API key, being present) — not fully hands-off.
- Prior technical foundation exists (see cfb_tool.zip from earlier in this
  project): SQLite schema with teams/games/players/coaches, CollegeFootballData
  API ingestion, and a working coordinator-tendency blending model
  (historical tendency + current-season data, weighted by sample size).
  That foundation is reusable — the UI/product direction is what's
  changing, not the underlying data layer.
- Hosting on a personal website remains a longer-term goal, not a v1
  requirement.

## v1 scope decisions (locked in)

**In for v1:**
- **Rough current odds** — enough that you don't need to open another
  resource for a baseline number. Line movement (open vs. current) if it's
  reasonably easy to source alongside odds — not worth extra engineering
  effort beyond that.
- **Line reference / shopping** — a rough estimate or a "sharpest available"
  reference number is enough; you already do real line shopping yourself
  and don't need the tool to replace that.
- **Weather** (wind/cold) as a signal for totals and passing efficiency.
- **Travel/rest/altitude flags — with historical context, not just the
  flag itself.** Don't just note "short week" or "true road game at
  altitude" — show how that specific team has historically performed in
  that situation. The situation alone is a weaker signal than the
  situation + that team's track record in it.
- **Two-directional matchup flags** — mutual conditions (two bad defenses
  → shootout signal, two great defenses → under signal), not just
  one-sided strength-vs-weakness.
- **Notes field per matchup** — lightweight, jot talking points while
  clicking through. Should support exporting the week's notes as one
  combined sheet/summary (this is the part with real payoff — a
  shareable weekly digest built from your own notes, not just raw stats).
- **Angle tagging (lightweight track record)** — tag which flag/signal
  type led to a pick (new-OC flag, tempo flag, weather flag, etc.), so
  patterns in what's actually working can be reviewed later. This is NOT
  a full betting tracker — results tracking stays in Pikkit, which is
  already in use. This just tags the *reason*, not the outcome.
- **Sample-size confidence applied universally** — the "trust it more as
  the sample grows" logic (already validated for coordinator tendencies)
  extends to every stat category from day one: defense, tempo, player
  usage, everything. Not bolted on later per-category.

**Explicitly skipped:**
- Public bet % vs. money % (sharp-vs-public divergence) — skip entirely.
- Clip-ready visual export for social — skip for now; a screenshot is
  good enough if a flag is genuinely worth sharing.

## UI / UX decisions (locked in)

**Entry point:** A schedule/slate view, ordered by day/time (matches how
the user's brain organizes the week). "Top matchup" games get a visual
icon on the schedule row rather than being pulled into a separate curated
view — order is preserved, but attention is still directed.
- Top-matchup icon assignment: automatic, based on how many/how strong the
  flags are for that game (not manually curated).
- Each schedule row shows: matchup (team logos/names/AP rank), kickoff
  time, spread and total, the top-matchup icon if flagged, AND a small
  one-line moniker naming the single biggest flag for that game (e.g.
  "new-OC run tendency"). This is the "boil the slate down" payoff —
  useful signal visible without clicking in.

**Navigation:** Click into a matchup from the schedule list, back button
to return to the schedule. Not a swipe/next-prev flow — team logos/names/
rank on the schedule are the primary way of finding/choosing a game.

**No "reviewed" tracking needed** — the user will use notes/memory for
that, don't build a review-state system.

**Expanded matchup card structure:**
- A real side-by-side stat comparison table (box-score style) for the two
  teams — not just narrative flags.
- All flags found are shown (no artificial 1-2 limit) — organized
  **grouped by side**: everything about Team A, then everything about
  Team B, then a head-to-head / combined section (this is also where
  two-directional flags like "both bad defenses" live).
- Player prop info is a HYBRID: (1) if there's a real prop-relevant
  matchup (a specific player tendency vs. a specific weakness), it's
  flagged directly like any other signal, AND (2) there's also a
  dedicated prop section within the card, so prop research doesn't
  require piecing it together from scattered flags.
- Odds/lines are visible but secondary — smaller, off to the side, not
  the headline of the card.

**Sample size / confidence — important principle:** The tool states the
fact ("2 games this season," "established over 10 games") and does NOT
editorialize with a visual confidence indicator (no stoplight, no
color-coding, no score). The user explicitly does not want the tool
making the confidence judgment for them — that crosses into spoonfeeding.
Plain, neutral, factual statement of sample size only.

**Visual density:** In between clean/spacious and dense/data-heavy — not
minimal, not a Bloomberg terminal.

**Theme:** No strong preference — light or dark, whatever builds best.

**Platform:** Desktop-only for now. Mobile is a nice-to-have someday, not
a v1 requirement.

**Search:** A simple search bar (find a team quickly) is enough — no need
for heavy filter/sort UI on the slate.

**Notes & export:** A notes field per matchup; format for the exported
weekly summary sheet doesn't matter much — pick whatever's simplest to
build well (plain text/markdown is the likely default).

**Angle tagging:** When the user marks a matchup as "this became my
pick," the tool automatically tags it with whichever flag(s) were shown
for that game — no manual dropdown needed. This feeds the lightweight
track-record view (which angles tend to get used) without duplicating
Pikkit's job of tracking actual bet outcomes.

## Week 1 / cold-start plan
When there's no current-season sample yet, the "prior" needs to come from
elsewhere — same blending philosophy as coordinator tendencies, applied
one level up, with layered sources (most to least reliable):
1. Last season's final team/player stats as the starting prior, decaying
   in weight as this season's games accumulate (same blend math already
   validated for coordinators).
2. Returning production — % of last year's production (yards, etc.)
   walking back onto the field this year, accounting for departures/
   transfers/draft losses. Materially changes how much last year's stats
   should be trusted.
3. Coordinator/staff tendencies (already built) — if a new OC/DC, their
   history matters more than the team's own last-season stats.
4. Market win totals / preseason lines as an explicit "here's what the
   market expects" anchor — legitimate given odds are already planned to
   be visible in the tool.
The UI should plainly label Week 1-type situations (e.g. "Week 1 — based
on last season + returning production") rather than presenting a
cold-start estimate as if it were in-season data — consistent with the
plain, non-editorialized sample-size language already decided.

## Player-level detail (elevated to v1 — was previously a Phase 2 gap)
Per-game player stats (not just season totals) are required for v1, not
deferred — needed to support clicking into "how has this player run the
ball the last few games" (carries, yards, TDs per game), which is a core
ask. All-season-so-far is the relevant window (not just last 3 games).

**UI placement:** A separate "players" section per team within the
matchup card, always visible — not something you have to click a flag to
discover. Keeps player detail discoverable regardless of which flags
fired for that game.

## Schedule row — final decision
Kept deliberately lean. Only addition beyond the original spec (matchup,
kickoff, spread/total, top-matchup icon, flag moniker): a small icon for
a questionable/out key player. Explicitly NOT adding yards/play
differential, turnover margin, weather icon, records, or pace/tempo to
the row itself — those live inside the matchup card, not the schedule
list. Reinforces the existing "boil the slate down" principle — the row
is a scan surface, not a stat dump.

## Additional functionality decisions (round 3)

- **Injury/depth-chart alerts:** Fully automated from a data feed —
  accept it may occasionally miss things rather than requiring manual
  upkeep.
- **FCS buy games:** Hidden from the main schedule view (since
  unbettable), but still used behind the scenes to inform team stats.
- **Spread/total display:** One consensus number is enough — user already
  shops lines separately, doesn't need a range shown.
- **Week-over-week history:** Needed — user wants to look back at past
  weeks' schedules and flags once they've passed, not just the current
  week.
- **Notes:** Auto-save as typing, no manual save button.
- **No standalone "trend" indicator.** Considered and explicitly
  declined — CFB's short season makes a trend flag noisy and
  matchup-dependent. The existing recency-vs-season blend already covers
  this need without adding a separate, potentially misleading signal.
- **Player box score section:** Numbers-only table (carries, yards, TDs
  per game) — no chart/visualization needed.
- **Schedule grouping:** Stays purely chronological by kickoff time, no
  conference grouping.
- **Weather timing:** Auto-update if feasible; fall back to only showing
  weather once within ~24 hours of kickoff if live updating isn't
  practical, rather than showing a stale multi-day-out forecast as fact.

## Additional functionality decisions (round 4)

- **Data refresh:** Auto-refresh once daily, plus a manual on-demand
  refresh option for when fresher data is wanted (e.g. right before
  finalizing a video).
- **Post-game recap:** Shows final score AND whether your flags/notes for
  that game actually panned out — directly feeds the lightweight
  track-record concept rather than being a separate feature.
- **Defensive stat granularity:** Broken out by run D, pass D, red zone
  D, and third-down D — not just an overall yards/points-allowed number.
- **Coach click-through:** Only for coaches directly tied to a flag (e.g.
  a new-hire flag) — not a universal "click any coach" feature. Keeps
  this scoped to where it's actually earning its place.
- **No standalone team page.** Team info only needs to exist in the
  context of a specific matchup — not a separate browsable team profile
  section.

## Additional functionality decisions (round 5)

- **Conference/team focus:** Varies week to week depending on what's
  compelling — the tool should NOT hard-bias toward specific conferences
  or teams by default; the "top matchup" logic should stay purely
  signal-driven, not skewed toward a preferred conference.
- **Postseason:** In scope — bowls and CFP should be treated the same as
  regular season, not cut off at the end of the regular season.
- **Session/resume behavior:** Doesn't matter much — no need to build
  special "remember where I left off" logic; not worth engineering
  effort either way.

## Additional functionality decisions (round 6)

- **Top-matchup star transparency:** The star needs visible reasoning
  behind it, not just a bare icon — when a game is starred, the user
  should be able to see which flags/signals actually drove that
  designation. Consistent with the broader "guide, don't spoonfeed"
  principle — even the automated star shouldn't be a black box.
- **No separate "used in video" status tag.** Notes are sufficient for
  the user's own tracking; don't build a dedicated content-status field.
- **Returning production lookback:** Just last season, not multiple
  years back — keep the cold-start prior simple rather than adding
  multi-year complexity for marginal accuracy gain.

## Additional functionality decisions (round 7)

- **Flags tagged by bet type:** Each flag should carry a label for which
  bet type it's most relevant to — side / total / prop — so the user can
  quickly see what kind of angle a given signal supports.
- **Conflicting flags called out explicitly.** When two flags for the
  same game point in different directions (e.g. one leans over, another
  leans under), the tool should surface that tension directly rather than
  silently listing both and letting the user notice on their own. This is
  actually valuable "guide" behavior — showing genuine uncertainty is
  itself information, not something to smooth over.
- **Team logos:** No strong preference — real logos if simple to build
  well, otherwise team-initial badges are a fine fallback. Not worth
  extra engineering effort either way.

## Additional functionality decisions (round 8)

- **No-flag games:** Moniker stays blank/empty rather than forcing a
  "nothing notable" label or surfacing a weak flag just to fill the
  space. Silence is itself informative — consistent with not manufacturing
  signal where there isn't any.
- **Weekly summary count:** A small header summary (e.g. "4 top matchups
  this week") is wanted at the top of the schedule view.
- **Adjustable flag sensitivity:** The user wants control over how
  strict/loose the flagging logic is — a tunable threshold, not a fixed
  black-box cutoff. This is a real feature requirement, not just a
  "nice to have," and should be designed in from the start rather than
  retrofitted (likely a simple setting/slider rather than anything
  complex).

## Additional functionality decisions (round 9)

- **Last-updated timestamp:** Visible somewhere in the UI, showing data
  freshness.
- **Star reasoning clarified:** The moniker already IS the "why this got
  starred" explanation — no separate tooltip/summary mechanism needed.
  One short line does double duty as both the schedule-row preview and
  the star's justification. Keep this simple, don't over-build a
  secondary explanation layer.
- **Time zone:** Kickoff times always shown in the user's local time
  zone, not the game's home time zone.

## Additional functionality decisions (round 10)

- **No cross-game flag-type browsing view.** Game-by-game browsing is
  enough — declined a "show me every X-type flag across the week" view.
- **Recruiting/talent composite rankings:** Worth including as a signal.
  Likely most useful feeding into the Week 1/cold-start prior (talent
  composite is a standard proxy for roster quality when in-season data
  is thin) as well as a general context data point.
- **Search stays simple:** Plain team-name search only — no flag-type
  search needed.

## Additional functionality decisions (round 11)

- **Letdown/lookahead spots: genuinely undecided, not a yes.** User's own
  reaction was skepticism about whether this is a real effect teams
  actually respond to, versus a narrative story imposed after the fact —
  which is consistent with the earlier principle of preferring objective/
  measurable factors over narrative "trap game" framing. Recommendation:
  don't build this on faith. If it's included at all, it should be
  validated against actual historical data first (does a team's ATS
  performance actually shift in a documented lookahead spot, or not)
  rather than assumed and shipped. Leave OUT of v1 unless/until that
  validation happens.
- **Schedule scroll:** Infinite scroll through the full week, no
  pagination or day-tabs needed.

## Stat catalog (full scope — locked in)

**Team offense:**
- Yards/game (total, rush, pass) and yards/play (efficiency version,
  preferred over raw totals since it isn't inflated by pace)
- Points/game
- Run/pass rate (feeds directly into existing coordinator-tendency work)
- Third-down conversion %, red-zone TD % (specifically touchdown rate,
  not just "scored" — distinguishes efficient red-zone offenses from
  ones settling for field goals)
- Explosive play rate (20+ yard plays) — separates "efficient" from
  "explosive" offenses, which raw yardage totals blur together
- Turnovers given away
- Sacks/pressure allowed
- Time of possession, plays/game (tempo)
- Success rate (per-play efficiency, advanced/secondary — see below)

**Team defense:** mirrors offense, but allowed, broken out further per
earlier decision:
- Yards/play allowed, split into run D / pass D / red-zone D / third-down D
- Points allowed/game
- Sacks/TFLs generated, turnovers forced
- Explosive plays allowed, success rate allowed (advanced/secondary)
- Havoc rate (TFLs + forced fumbles + pass breakups, as a rate) — single
  number for defensive disruption/aggression

**Advanced/efficiency metrics** (SP+, success rate, PPA): included, but
visually secondary/clearly labeled as "advanced" — traditional counting
stats (yards, TDs, etc.) are the primary display; advanced metrics
supplement rather than lead.

**Player — offense only** (defensive player stats explicitly excluded —
player-level detail stays scoped to offense):
- QB: completion %, yards, TDs, INTs, yards/attempt, rushing stats if
  dual-threat, sacks taken
- RB: carries, yards, yards/carry, TDs, PLUS receiving stats (catches/
  yards) — pass-catching usage matters for prop relevance
- WR/TE: targets, receptions, yards, yards/reception, TDs, target share
  (target share is a better usage signal than raw catch counts)

## Stat comparison display — locked in
**Matchup-framed as the default view**: each team's offense stat is
paired against the OPPONENT's defense-allowed stat for that same
category (e.g. Team A's rush yards/play next to Team B's rush yards/play
ALLOWED) — this directly shows the tension the tool is built around,
rather than requiring the user to mentally cross-reference two separate
columns. A raw box-score toggle (same stat, both teams, side by side) is
also available as a secondary/alternate view.

## Strength of schedule / opponent adjustment (important addition)

**The problem identified:** Raw stats aren't comparable across teams with
different schedule difficulty — a team that padded stats against weak
opponents looks identical to one that earned them against strong
competition if only raw totals are shown. This matters MORE early in the
season, when small samples against weak or strong opponents are
especially misleading — connects directly to the sample-size/cold-start
concerns already documented above.

**The solution:** SP+ and opponent-adjusted PPA (already planned as
"advanced metrics") are specifically built to solve this — they're not
just extra flavor stats, they're the actual answer to "how good is this
team accounting for who they've played." Raw stats show what happened;
opponent-adjusted stats show how much to trust it.

**Display decision (revised from initial "secondary/advanced" framing):**
Raw and opponent-adjusted stats are shown TOGETHER in the same main
table, side by side — not separated into a primary/secondary split. Both
matter for different reasons (raw = intuitive, what a viewer understands;
adjusted = more predictive), so both stay equally visible rather than
burying the adjusted numbers behind a toggle.

**Additional element:** A plain-language strength-of-schedule line (e.g.
"opponents faced so far: average defensive SP+ rank 62nd nationally")
should accompany the stat tables — an intuitive gut-check on the raw
numbers without requiring the viewer to understand SP+ methodology.

## Model vs. market gap (new flag type — locked in)

**Mechanism:** SP+ (or another opponent-adjusted rating) gives each team
a number; the difference between two teams' ratings, adjusted for home
field, produces an implied point spread — "what the numbers say this
game should be." Comparing that against the actual posted market spread
surfaces cases like the user's example: a team with a brutal
schedule-adjusted profile sitting as a bigger underdog than the numbers
justify, because raw record/perception undersells them.

**Treatment:** Same guide-not-spoonfeed pattern as every other flag —
states the gap as a fact ("power rating implies TCU as a 3.5-point
underdog; market has them at +7.5 — a 4-point gap"), does not say "bet
this." The user then cross-references the matchup-level detail (tempo,
tendencies, injuries, etc.) already in the tool to judge whether the gap
is real signal or the market knows something the rating can't see
(injury, weather, etc.).

**Scope decisions:**
- Extends to totals as well as spreads (combined power-rating implied
  total vs. market total, same gap logic).
- Explicitly kept SEPARATE from the "top matchup" star logic — a big
  model-vs-market gap is its own standalone flag, not folded into what
  drives the star.

**Known limitation (team-level vs. player-level adjustment):**
Team-level SOS/opponent-adjustment (via SP+) is well-supported and
straightforward. Player-level opponent-adjustment (e.g., a RB's yards
adjusted for the specific run defenses faced) is NOT readily available
from CFBD and would require real custom modeling — out of scope for now.
Player stats stay raw/season-total, with team-level SOS context around
them, rather than a fully adjusted player number.

## Model vs. market gap — display decisions (continued)

- **Schedule row indicator:** Only for very large gaps — small/minor
  gaps stay inside the matchup detail, not surfaced on the schedule row.
  Ties into the already-planned adjustable flagging sensitivity (the
  threshold for "large" should be tunable, not hardcoded).
- **Confirmed as a taggable angle type** in the lightweight track-record
  system, alongside the other flag categories.

## Additional functionality decisions (round 12)

- **No team pinning/favoriting.** Search is sufficient when the user
  wants to check a specific team.
- **Broadcast/exposure level (national TV, primetime):** Nice-to-have,
  not essential — not a v1 requirement, low priority if built at all.
- **No "updated since you last viewed" flagging.** Not needed — user
  doesn't want change-tracking on individual games between visits.

## Additional functionality decisions (round 13)

- **Player props:** Yardage O/U and TD-scorer props matter equally — the
  props section shouldn't overweight one over the other.
- **Turnover luck / regression signal:** Include this — teams recovering
  fumbles (or otherwise running hot/cold on turnovers) at a rate unlikely
  to continue are flagged as a regression candidate. A legitimate,
  well-established predictive signal worth including as its own flag
  type.
- **Garbage time filtering:** No strong preference — use whichever
  approach (filtered or raw) is more statistically accurate; defer to
  data/implementation quality rather than a fixed rule.

## Additional functionality decisions (round 14)

- **Special teams:** NOT a standing full stat category — only surfaces
  as a flag when something is a genuine outlier (elite or terrible),
  consistent with the broader principle of not manufacturing signal
  where none exists.
- **Home/away splits:** Same pattern — not a standing displayed
  category, only surfaces when the split is notably large for a specific
  team.
- **Flag-type icons:** Include icons alongside text labels, never
  icon-only — user doesn't want to have to memorize icon meanings. Use
  icons for faster scanning WHEN there's room, but the text label always
  stays.

## Build-phase priority order (user-ranked)

When this moves into actual implementation, build in this order:
1. Schedule view + basic team/player stats browsing (the foundation)
2. Full flag system (tempo, weather, injuries, turnover luck, etc.)
3. SOS/opponent-adjusted stats
4. Model vs. market gap flagging
5. Coaching tendency blending (NOTE: this was already built and
   validated in the earlier Phase 1 session — ranked lower here not
   because it's less important conceptually, but because the user
   prioritizes breadth across many signal types over depth on any one
   mechanic, even one that's already working)
6. Notes + weekly export (lowest priority — nice workflow layer, not
   core analysis)

This ordering should directly inform how the rebuild is sequenced —
don't over-invest early in the coordinator-blend mechanic at the expense
of getting basic browsing + a broad (if simpler) flag system working
first.

## Additional functionality decisions (round 15)

- **Free data sources only** — no budget for paid odds/weather APIs.
  Confirmed feasible: CFBD (already in use) has a solid free tier, NWS
  provides free US weather data, and free-tier odds APIs exist within
  the expected usage volume.
- **Historical head-to-head result:** Only surfaced for notable
  rivalries/recurring matchups — not a standing factual line for every
  game. Distinct from the ATS-trend stuff already declined; this is
  purely factual context, shown sparingly.

## CRITICAL: timeline reality check
User's first video films THIS SATURDAY. This is a hard, near-term
deadline that the full spec built in this session cannot realistically
meet — the spec below is comprehensive (SOS adjustment, model-vs-market
gap engine, full multi-category flag system, cold-start blending) and
represents real, multi-week build effort, not a few days, especially
given the user has no coding background and needs to work through
Claude Code interactively.

**Realistic Saturday scope = priority #1 only** (from the build-phase
ranking above): a working schedule view with real team/player stats
pulled in and browsable. NO flags, NO SOS adjustment, NO model-vs-market
gap yet for the first version. Everything else layers in over subsequent
weeks — user has explicitly signed off on this incremental approach
("something working, with an understanding we will tune and adjust each
week"). Do not let the full spec's scope create pressure to over-deliver
before Saturday — a genuinely simple, working stats browser is the
correct v0, not a compromise.

## Open threads for next session
- **Possible weekly summary/overview page** — user raised this while
  thinking out loud in response to the model-vs-market gap discussion,
  specifically wondering if a larger summary page (beyond the schedule
  list) is worth building — e.g. a dedicated view surfacing the week's
  biggest gaps/flags in one place, separate from the game-by-game
  schedule. NOT a locked decision — this contradicts the earlier "no
  cross-game view, game-by-game is enough" call, so it's worth
  deliberately revisiting rather than assuming either answer. Good
  candidate for the next session once there's a real week of data to
  reason about concretely.
- Walk through what the click-through matchup screen should actually
  show, in what order, for one real example game
- Decide how "conflicting matchup" flags get generated — rules-based
  (if X stat vs Y stat crosses a threshold, flag it) is the realistic v1
  approach; anything fancier is later
- Revisit the existing Phase 1 codebase against this new direction —
  what's reusable as-is (data layer, coordinator blending) vs. what needs
  to be rebuilt (the UI, which was leaderboard-shaped, not matchup-shaped)
