# RouteWise – v1 (semester MVP)

Prioritized visit routes for the Jerusalem collection department's field surveyors. Built from `RouteWise-PDR-מתוקן.md`.
**Synthetic data only. No real resident data, and no login (per the PDR).**

## Run

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # macOS/Linux: .venv/bin/...
.venv/Scripts/python scripts/make_synthetic.py              # -> sample_data/properties.xlsx
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000. To start over, delete `routewise.db`.

Tests: `.venv/Scripts/python -m pytest -q`

## End-to-end flow
1. **Manager** (`/static/manager.html`): upload `sample_data/properties.xlsx` and review the validation report. Rows with a missing address, duplicates, or no location are excluded; non-numeric values are flagged as warnings.
2. Set each criterion's role (gap probability / amount ₪ / not used), weight, and direction, then recalculate the score. Click a property in the ranking to see why it got its score.
3. Assign a surveyor to each neighborhood, then approve. Weights and assignments are locked after approval.
4. **Surveyor** (`/static/surveyor.html`): pick a name and a route. The route is built on first open, starting from the surveyor's location (or the neighborhood centre if that location is unavailable or more than 5 km away). The screen shows the next property, Waze / Google Maps navigation, and done / not done (with a reason) / skip (moves it to the end), as a list and on a map.
5. **Report** (on the manager screen): done / not done / reason / timestamps / expected revenue of the visits, plus a CSV download.

## How the score and the route work
- **Score** (`app/scoring.py`): expected revenue = P(gap) × amount. P is a weighted average of the "probability" criteria after min-max normalization within the round. The amount is a weighted sum of the ₪ criteria. The score does not depend on the surveyor's location, so the manager sees one fixed ranking.
- **Route** (`app/routing.py`): maximizes Σ score × 0.5^(arrival time / 4h) − a travel-time cost. High value gets visited early, zig-zagging is penalized, and a nearby cluster can come before a single distant property. It uses greedy insertion followed by relocate and 2-opt improvement. Parameters are in `RouteParams`.

## Structure
`app/` server (FastAPI + SQLite) · `static/` screens (HTML/JS, Leaflet) · `scripts/make_synthetic.py` synthetic data · `tests/`

## Deferred to the next phase (per the PDR)
Real-time monitoring, offline mode, rebuilding the route from the current location, login, the AI assistant for weights, municipal GIS / systems integration, printable export.
