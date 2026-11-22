# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is
RouteWise: prioritized visit routes for field surveyors of the Jerusalem municipality's collection department (אגף הגבייה).
Two users: the assessment manager (מנהל השומה), who uploads properties, sets weights, approves, and reads the report, and the field surveyor (סוקר השטח), who follows the route and marks visits.

- **Source of truth for requirements:** `RouteWise-PDR-מתוקן.md` (the corrected PDR). `PRD.md` is the older version; where they differ, follow the corrected PDR.
- v1 is a semester MVP. **Synthetic data only, no login.** Do not add real resident data.
- Deferred to the next phase, so don't build unless asked: real-time dashboard, offline mode, rerouting from the current location, auth, the AI weights assistant, municipal GIS/system integration, printable export.

## Stack
- Python 3.13, FastAPI, stdlib `sqlite3` (`routewise.db`, git-ignored), openpyxl.
- Frontend: plain HTML/JS in `static/`, Hebrew RTL, Leaflet 1.9.4 from cdnjs with OSM tiles. No Node and no build step.
- Geocoding: lat/lon from the file; otherwise OSM Nominatim (1 req/s, cached in the `geocache` table).

## Commands
```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python scripts/make_synthetic.py           # sample_data/properties.xlsx
.venv/Scripts/python -m uvicorn app.main:app --port 8000  # http://localhost:8000
.venv/Scripts/python -m pytest -q
```
Delete `routewise.db` to reset the data. `.claude/launch.json` defines the `routewise` dev server for the browser preview.

## Layout
- `app/ingest.py`: Excel/CSV parsing and validation. Errors (missing address/neighborhood, duplicate id or address, failed geocode) exclude the row. A non-numeric value is a warning. A numeric column becomes a criterion when at least 80% of its values are numeric.
- `app/scoring.py`: score = expected revenue = P(gap) × amount. Probability criteria are min-max normalized within the round and averaged by weight (optionally inverted). Amount criteria are a weighted ₪ sum. Each property keeps a per-criterion breakdown. The score must stay **independent of the surveyor's location**.
- `app/routing.py`: visit order, kept separate from the score. Maximizes Σ score·0.5^(arrival/half_life) − travel_penalty·travel_minutes. Greedy insertion, then relocate + 2-opt. Tunables are in `RouteParams`; they are unvalidated guesses pending the department's input (e.g. ~7 visits/day).
- `app/api/manager.py`: rounds, upload, criteria (rescore), ranking, assignments, approve, report (+ CSV).
- `app/api/surveyor.py`: a route is built on first `open`, from the surveyor's GPS (falls back to the neighborhood centroid if it is more than 5 km away). Stop actions: `done`, `not_done` + reason (`locked|no_answer|refused|other`), `skip` (moves the stop to the end), `undo`.
- `static/manager.*`, `static/surveyor.*`, `static/common.js`, `static/style.css`.

## Branches
- `main` is the stable version; `dev` is for ongoing work.
- Commit to `dev`. Merge into `main` only when `pytest` passes and the flow works.

## Conventions
- UI text is Hebrew (RTL); code, identifiers, and comments are English.
- After approval, the round's weights and assignments are locked (HTTP 409).
- Keep the surveyor UI one-handed and glanceable: big buttons, no findings entry (findings stay on paper).
- Add or adjust tests in `tests/` for any scoring, routing, validation, or API-flow change. `tests/test_api.py` stubs geocoding and uses a temp DB.
