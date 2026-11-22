"""Assessment-manager endpoints: upload, weights, scoring, ranking, assignment, approval, report."""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import geocode as geo
from ..db import get_conn, jdumps, jloads
from ..ingest import read_table, validate
from ..scoring import default_criteria, score_properties

router = APIRouter(prefix="/api")

REASONS = {"locked": "נעול", "no_answer": "אין מענה", "refused": "סירוב", "other": "אחר"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _round(conn, rid: int):
    r = conn.execute("SELECT * FROM rounds WHERE id = ?", (rid,)).fetchone()
    if not r:
        raise HTTPException(404, "סבב לא נמצא")
    return r


@router.get("/surveyors")
def surveyors():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT id, name FROM surveyors ORDER BY id")]


@router.get("/rounds")
def list_rounds():
    with get_conn() as conn:
        rows = conn.execute("""SELECT r.id, r.name, r.created_at, r.status, COUNT(p.id) AS properties
                               FROM rounds r LEFT JOIN properties p ON p.round_id = r.id
                               GROUP BY r.id ORDER BY r.id DESC""").fetchall()
        return [dict(r) for r in rows]


@router.post("/rounds")
async def create_round(name: str = Form(...), file: UploadFile = File(...)):
    content = await file.read()
    try:
        headers, data = read_table(file.filename or "", content)
        report = validate(headers, data, geocode=geo.geocode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not report["properties"]:
        raise HTTPException(400, "אין בקובץ אף שורה תקינה")
    criteria = default_criteria(report["criteria"])
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO rounds(name, created_at, criteria_json, validation_json) VALUES (?,?,?,?)",
                           (name.strip() or file.filename, now(), jdumps(criteria),
                            jdumps({"issues": report["issues"], "summary": report["summary"],
                                    "info_columns": report["info_columns"], "filename": file.filename})))
        rid = cur.lastrowid
        conn.executemany(
            "INSERT INTO properties(round_id, ext_id, address, neighborhood, lat, lon, data_json) VALUES (?,?,?,?,?,?,?)",
            [(rid, p["ext_id"], p["address"], p["neighborhood"], p["lat"], p["lon"],
              jdumps({"values": p["values"], "info": p["info"]})) for p in report["properties"]])
        _score(conn, rid, criteria)
    return get_round(rid)


@router.get("/rounds/{rid}")
def get_round(rid: int):
    with get_conn() as conn:
        r = _round(conn, rid)
        hoods = conn.execute("""SELECT neighborhood, COUNT(*) AS n, SUM(score) AS total, AVG(lat) AS lat, AVG(lon) AS lon
                                FROM properties WHERE round_id = ? GROUP BY neighborhood
                                ORDER BY SUM(score) DESC""", (rid,)).fetchall()
        assigns = {a["neighborhood"]: a["surveyor_id"] for a in
                   conn.execute("SELECT * FROM assignments WHERE round_id = ?", (rid,))}
        return {
            "id": r["id"], "name": r["name"], "created_at": r["created_at"], "status": r["status"],
            "criteria": jloads(r["criteria_json"], []),
            "validation": jloads(r["validation_json"], {}),
            "neighborhoods": [{**dict(h), "surveyor_id": assigns.get(h["neighborhood"])} for h in hoods],
        }


class Criterion(BaseModel):
    name: str
    role: str  # prob | amount | ignore
    weight: float = 1.0
    invert: bool = False


def _score(conn, rid: int, criteria: list[dict]):
    rows = conn.execute("SELECT id, data_json FROM properties WHERE round_id = ?", (rid,)).fetchall()
    props = [{"id": r["id"], "values": jloads(r["data_json"])["values"]} for r in rows]
    results = score_properties(props, criteria)
    conn.executemany("UPDATE properties SET score=?, prob=?, amount=?, breakdown_json=?, rank=? WHERE id=?",
                     [(x["score"], x["prob"], x["amount"], jdumps(x["breakdown"]), x["rank"], x["id"]) for x in results])
    conn.execute("UPDATE rounds SET criteria_json = ?, status = 'scored' WHERE id = ?", (jdumps(criteria), rid))


@router.put("/rounds/{rid}/criteria")
def set_criteria(rid: int, criteria: list[Criterion]):
    for c in criteria:
        if c.role not in ("prob", "amount", "ignore") or c.weight < 0:
            raise HTTPException(400, f"הגדרה לא תקינה לקריטריון {c.name}")
    if not any(c.role == "amount" and c.weight > 0 for c in criteria):
        raise HTTPException(400, "צריך לפחות קריטריון אחד מסוג 'סכום' (₪) – אחרת הציון תמיד 0")
    with get_conn() as conn:
        if _round(conn, rid)["status"] == "approved":
            raise HTTPException(409, "הסבב כבר אושר ונשלח לסוקרים – אי אפשר לשנות משקלים")
        _score(conn, rid, [c.model_dump() for c in criteria])
    return get_round(rid)


@router.get("/rounds/{rid}/ranking")
def ranking(rid: int, neighborhood: str | None = None):
    with get_conn() as conn:
        _round(conn, rid)
        q = "SELECT * FROM properties WHERE round_id = ?"
        args: list = [rid]
        if neighborhood:
            q += " AND neighborhood = ?"
            args.append(neighborhood)
        rows = conn.execute(q + " ORDER BY rank", args).fetchall()
        out = []
        for r in rows:
            d = jloads(r["data_json"])
            out.append({"id": r["id"], "ext_id": r["ext_id"], "address": r["address"],
                        "neighborhood": r["neighborhood"], "lat": r["lat"], "lon": r["lon"],
                        "rank": r["rank"], "score": r["score"], "prob": r["prob"], "amount": r["amount"],
                        "breakdown": jloads(r["breakdown_json"], []), "info": d.get("info", {})})
        return out


@router.put("/rounds/{rid}/assignments")
def set_assignments(rid: int, assignments: dict[str, int | None]):
    with get_conn() as conn:
        if _round(conn, rid)["status"] == "approved":
            raise HTTPException(409, "הסבב כבר אושר – אי אפשר לשנות שיבוץ")
        conn.execute("DELETE FROM assignments WHERE round_id = ?", (rid,))
        conn.executemany("INSERT INTO assignments(round_id, neighborhood, surveyor_id) VALUES (?,?,?)",
                         [(rid, h, s) for h, s in assignments.items() if s])
    return get_round(rid)


@router.post("/rounds/{rid}/approve")
def approve(rid: int):
    with get_conn() as conn:
        r = _round(conn, rid)
        if r["status"] == "approved":
            raise HTTPException(409, "הסבב כבר אושר")
        assigns = conn.execute("SELECT * FROM assignments WHERE round_id = ? AND surveyor_id IS NOT NULL",
                               (rid,)).fetchall()
        if not assigns:
            raise HTTPException(400, "צריך לשבץ סוקר לפחות לשכונה אחת לפני האישור")
        for a in assigns:
            # the route itself is built when the surveyor opens it, from where they stand
            conn.execute("INSERT INTO routes(round_id, surveyor_id, neighborhood) VALUES (?,?,?)",
                         (rid, a["surveyor_id"], a["neighborhood"]))
        conn.execute("UPDATE rounds SET status = 'approved' WHERE id = ?", (rid,))
    return get_round(rid)


def _report(conn, rid: int) -> dict:
    _round(conn, rid)
    routes = conn.execute("""SELECT rt.*, s.name AS surveyor FROM routes rt JOIN surveyors s ON s.id = rt.surveyor_id
                             WHERE rt.round_id = ? ORDER BY rt.neighborhood""", (rid,)).fetchall()
    out = []
    for rt in routes:
        stops = conn.execute("""SELECT st.*, p.address, p.ext_id, p.score, p.rank FROM route_stops st
                                JOIN properties p ON p.id = st.property_id
                                WHERE st.route_id = ? ORDER BY st.planned_seq""", (rt["id"],)).fetchall()
        stops = [dict(s) | {"reason_label": REASONS.get(s["reason"], s["reason"])} for s in stops]
        done = [s for s in stops if s["status"] == "done"]
        times = sorted(s["updated_at"] for s in stops if s["status"] != "pending" and s["updated_at"])
        days = {t[:10] for t in times}
        out.append({
            "route_id": rt["id"], "neighborhood": rt["neighborhood"], "surveyor": rt["surveyor"],
            "opened": rt["built_at"] is not None, "built_at": rt["built_at"],
            "done": len(done), "not_done": sum(1 for s in stops if s["status"] == "not_done"),
            "pending": sum(1 for s in stops if s["status"] == "pending"), "total": len(stops),
            "visited_value": round(sum(s["score"] or 0 for s in done), 2),
            "visits_per_day": round(len(done) / len(days), 1) if days else 0,
            "first_mark": times[0] if times else None, "last_mark": times[-1] if times else None,
            "stops": stops,
        })
    return {"round_id": rid, "routes": out}


@router.get("/rounds/{rid}/report")
def report(rid: int):
    with get_conn() as conn:
        return _report(conn, rid)


@router.get("/rounds/{rid}/report.csv")
def report_csv(rid: int):
    with get_conn() as conn:
        rep = _report(conn, rid)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["שכונה", "סוקר", "סדר מתוכנן", "מזהה נכס", "כתובת", "דירוג", "ציון (₪ צפוי)",
                "סטטוס", "סיבה", "דילוגים", "זמן סימון"])
    status = {"done": "בוצע", "not_done": "לא בוצע", "pending": "ממתין"}
    for rt in rep["routes"]:
        for s in rt["stops"]:
            w.writerow([rt["neighborhood"], rt["surveyor"], s["planned_seq"], s["ext_id"], s["address"], s["rank"],
                        s["score"], status.get(s["status"], s["status"]), s["reason_label"] or "", s["skips"],
                        s["updated_at"] if s["status"] != "pending" else ""])
    data = "﻿" + buf.getvalue()  # BOM so Excel shows Hebrew correctly
    return StreamingResponse(iter([data.encode("utf-8")]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename=routewise-report-{rid}.csv"})
