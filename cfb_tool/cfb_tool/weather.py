"""
Live game-day weather via the National Weather Service's free API
(api.weather.gov — US-government data, no key required).

Weather is inherently time-sensitive, so unlike everything else in this
app it's NOT batch-ingested into the database — it's fetched live on each
matchup-card view. That satisfies the spec's "auto-update if feasible"
call outright, so the "~24h before kickoff" fallback isn't needed: we
just gate display to whatever NWS's own hourly forecast horizon actually
covers (about a week out) and label it plainly as a forecast, not a fact.

Skipped entirely for: dome venues (not a factor), games without a known
venue/coordinates, games too far out for NWS to forecast, and non-US
venues (NWS has no international coverage — e.g. Dublin's Aviva Stadium).
"""
import time
import requests

USER_AGENT = "cfb-research-tool (personal project, contact via CFBD account)"
FORECAST_HORIZON_HOURS = 168  # ~7 days — NWS hourly forecasts aren't meaningful past this
_GRID_CACHE = {}       # (lat, lon) -> forecastHourly URL, doesn't change
_FORECAST_CACHE = {}   # forecastHourly URL -> (fetched_at, periods)
_FORECAST_TTL = 1800   # 30 min — avoid hammering NWS on repeat page loads


def _get(url):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
    if resp.status_code != 200:
        return None
    return resp.json()


def _forecast_hourly_url(lat, lon):
    key = (round(lat, 3), round(lon, 3))
    if key in _GRID_CACHE:
        return _GRID_CACHE[key]
    data = _get(f"https://api.weather.gov/points/{lat},{lon}")
    url = (data.get("properties") or {}).get("forecastHourly") if data else None
    _GRID_CACHE[key] = url
    return url


def _hourly_periods(url):
    cached = _FORECAST_CACHE.get(url)
    if cached and (time.time() - cached[0]) < _FORECAST_TTL:
        return cached[1]
    data = _get(url)
    periods = (data.get("properties") or {}).get("periods", []) if data else []
    _FORECAST_CACHE[url] = (time.time(), periods)
    return periods


def game_forecast(venue, kickoff_iso, now):
    """Returns a plain dict describing forecast conditions at kickoff, or
    None if weather isn't applicable/available (dome, no coordinates,
    outside the forecast horizon, non-US venue, or the API's unreachable)."""
    if not venue or venue["dome"] or venue["latitude"] is None or venue["longitude"] is None:
        return None
    if not kickoff_iso:
        return None

    from datetime import datetime, timezone
    kickoff = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
    hours_out = (kickoff - now).total_seconds() / 3600
    if hours_out < 0 or hours_out > FORECAST_HORIZON_HOURS:
        return None

    try:
        hourly_url = _forecast_hourly_url(venue["latitude"], venue["longitude"])
        if not hourly_url:
            return None
        periods = _hourly_periods(hourly_url)
    except requests.exceptions.RequestException:
        return None
    if not periods:
        return None

    closest = min(
        periods,
        key=lambda p: abs((datetime.fromisoformat(p["startTime"]) - kickoff).total_seconds()),
    )
    wind_mph = _parse_wind_mph(closest.get("windSpeed"))
    return {
        "temperature": closest.get("temperature"),
        "temperature_unit": closest.get("temperatureUnit"),
        "wind_mph": wind_mph,
        "wind_direction": closest.get("windDirection"),
        "short_forecast": closest.get("shortForecast"),
        "precip_pct": (closest.get("probabilityOfPrecipitation") or {}).get("value"),
        "forecast_time": closest.get("startTime"),
    }


def _parse_wind_mph(wind_speed_str):
    """NWS returns wind as a string like '10 mph' or '10 to 15 mph' — take
    the highest number mentioned (the gustier end, more relevant for a
    passing-game/kicking flag than the low end of a range)."""
    if not wind_speed_str:
        return None
    nums = [int(tok) for tok in wind_speed_str.replace("mph", "").split() if tok.isdigit()]
    return max(nums) if nums else None
