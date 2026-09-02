"""
"New OC/DC" context for the flag engine — the original seed idea for
this whole tool. Finds any coordinator on a team's CURRENT roster of
coaches who's new this season (didn't hold that role at that team last
year), then reuses blend.py's already-validated math to blend their
historical tendency (from prior stops, weighted by games coached) with
whatever this season's actual tendency looks like so far.

Needs data/coordinator_hires.csv hand-maintained (see load_coordinators.py
and the README) — CFBD's own /coaches endpoint only reliably covers head
coaches, not OC/DC hires, and there's no free API for that gap. Until
real hires are entered there (and compute_tendencies.py has been run),
this simply finds nothing to report — it never guesses at a hire.
"""
import blend as coordinator_blend


def _current_coordinators(conn, team_id, season):
    return conn.execute(
        """SELECT cs.coach_id, cs.role, c.first_name, c.last_name
           FROM coach_stints cs JOIN coaches c ON cs.coach_id = c.coach_id
           WHERE cs.team_id = ? AND cs.season = ? AND cs.role IN ('OC', 'DC')""",
        (team_id, season),
    ).fetchall()


def _is_new_hire(conn, coach_id, team_id, season):
    """True if this coach did NOT hold this role at this team last season."""
    row = conn.execute(
        "SELECT 1 FROM coach_stints WHERE coach_id = ? AND team_id = ? AND season = ?",
        (coach_id, team_id, season - 1),
    ).fetchone()
    return row is None


def _prior_stop(conn, coach_id, team_id, season):
    """Where this coach coached most recently before this team/season."""
    return conn.execute(
        """SELECT t.school FROM coach_stints cs JOIN teams t ON cs.team_id = t.team_id
           WHERE cs.coach_id = ? AND NOT (cs.team_id = ? AND cs.season >= ?)
           ORDER BY cs.season DESC LIMIT 1""",
        (coach_id, team_id, season),
    ).fetchone()


def new_coordinator_context(conn, team_id, season):
    """List of {coach_name, role, prior_team, ...blend.py's blend() dict}
    for each confirmed new OC/DC hire on this team this season. Empty
    list means either no new hires, or no coordinator_hires.csv data —
    those look the same from here, which is the correct behavior (no
    data in means no claim out)."""
    results = []
    for stint in _current_coordinators(conn, team_id, season):
        coach_id = stint["coach_id"]
        if not _is_new_hire(conn, coach_id, team_id, season):
            continue
        prior = coordinator_blend.get_prior(conn, coach_id, team_id, season)
        current = coordinator_blend.get_current(conn, coach_id, team_id, season)
        blended = coordinator_blend.blend(prior, current)
        if "blended_run_rate" not in blended:
            continue  # no tendency data at all for this coach yet
        prior_stop = _prior_stop(conn, coach_id, team_id, season)
        results.append({
            "coach_name": f"{stint['first_name']} {stint['last_name']}",
            "role": stint["role"],
            "prior_team": prior_stop["school"] if prior_stop else None,
            **blended,
        })
    return results
