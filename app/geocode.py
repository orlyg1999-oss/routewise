"""Address -> (lat, lon). Used only when the uploaded file lacks coordinates.

Uses OpenStreetMap Nominatim (max 1 request/second, results cached in SQLite).
"""
import time

import httpx

from .db import get_conn

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "RouteWise-prototype/0.1"
_last_call = [0.0]


def geocode(address: str) -> tuple[float, float] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT lat, lon FROM geocache WHERE address = ?", (address,)).fetchone()
        if row:
            return (row["lat"], row["lon"]) if row["lat"] is not None else None
    wait = 1.0 - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    try:
        r = httpx.get(NOMINATIM, params={"q": address, "format": "json", "limit": 1, "countrycodes": "il"},
                      headers={"User-Agent": USER_AGENT}, timeout=10)
        r.raise_for_status()
        hits = r.json()
        loc = (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None
    except Exception:
        return None  # network problem: do not cache, report as failed
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO geocache(address, lat, lon) VALUES (?, ?, ?)",
                     (address, loc[0] if loc else None, loc[1] if loc else None))
    return loc
