"""Field-surveyor endpoints: get today's route, mark done / not done / skip."""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_conn, jloads
from ..routing import build_route, haversine_m, route_stats

router = APIRouter(prefix="/api")

MAX_GPS_DISTANCE_M = 5000  # farther than this from the neighborhood -> start from its center


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@router.get("/surveyor/{sid}/routes")
def my_routes(sid: int):
    with get_conn() as conn:
        s = conn.execute("SELECT * FROM surveyors WHERE id = ?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "סוקר לא נמצא")
        rows = conn.execute("""SELECT rt.id, rt.neighborhood, rt.built_at, r.name AS round_name, r.id AS round_id,
                                      (SELECT COUNT(*) FROM route_stops st WHERE st.route_id = rt.id AND st.status = 'pending') AS pending
                               FROM routes rt JOIN rounds r ON r.id = rt.round_id
                               WHERE rt.surveyor_id = ? ORDER BY rt.id DESC""", (sid,)).fetchall()
        return {"surveyor": dict(s), "routes": [dict(r) for r in rows]}


class OpenRequest(BaseModel):
    lat: float | None = None
    lon: float | None = None


def _get_route(conn, rid: int):
    rt = conn.execute("SELECT * FROM routes WHERE id = ?", (rid,)).fetchone()
    if not rt:
        raise HTTPException(404, "מסלול לא נמצא")
    return rt


@router.post("/routes/{rid}/open")
def open_route(rid: int, req: OpenRequest):
    """Build the route on first open, starting from where the surveyor is."""
    with get_conn() as conn:
        rt = _get_route(conn, rid)
        if rt["built_at"] is None:
            props = conn.execute("SELECT id, lat, lon, score FROM properties WHERE round_id = ? AND neighborhood = ?",
                                 (rt["round_id"], rt["neighborhood"])).fetchall()
            points = [(p["lat"], p["lon"]) for p in props]
            center = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
            start, source = center, "centroid"
            if req.lat is not None and req.lon is not None and \
                    haversine_m((req.lat, req.lon), center) <= MAX_GPS_DISTANCE_M:
                start, source = (req.lat, req.lon), "gps"
            order = build_route(start, points, [p["score"] or 0.0 for p in props])
            conn.executemany("INSERT INTO route_stops(route_id, property_id, seq, planned_seq) VALUES (?,?,?,?)",
                             [(rid, props[i]["id"], n, n) for n, i in enumerate(order, start=1)])
            conn.execute("UPDATE routes SET start_lat=?, start_lon=?, start_source=?, built_at=? WHERE id=?",
                         (start[0], start[1], source, now(), rid))
    return get_route(rid)


@router.get("/routes/{rid}")
def get_route(rid: int):
    with get_conn() as conn:
        rt = _get_route(conn, rid)
        stops = conn.execute("""SELECT st.*, p.address, p.ext_id, p.lat, p.lon, p.score, p.rank, p.data_json
                                FROM route_stops st JOIN properties p ON p.id = st.property_id
                                WHERE st.route_id = ? ORDER BY st.seq""", (rid,)).fetchall()
        out = []
        for s in stops:
            d = dict(s)
            d["info"] = jloads(d.pop("data_json")).get("info", {})
            out.append(d)
        pending = [s for s in out if s["status"] == "pending"]
        stats = None
        if rt["built_at"] and pending:
            stats = route_stats((rt["start_lat"], rt["start_lon"]), [(s["lat"], s["lon"]) for s in pending],
                                list(range(len(pending))))
        return {"id": rt["id"], "neighborhood": rt["neighborhood"], "built": rt["built_at"] is not None,
                "start": {"lat": rt["start_lat"], "lon": rt["start_lon"], "source": rt["start_source"]},
                "stops": out, "remaining": stats,
                "counts": {k: sum(1 for s in out if s["status"] == k) for k in ("pending", "done", "not_done")}}


class Mark(BaseModel):
    action: str            # done | not_done | skip | undo
    reason: str | None = None


@router.post("/routes/{rid}/stops/{pid}")
def mark(rid: int, pid: int, m: Mark):
    with get_conn() as conn:
        _get_route(conn, rid)
        st = conn.execute("SELECT * FROM route_stops WHERE route_id = ? AND property_id = ?", (rid, pid)).fetchone()
        if not st:
            raise HTTPException(404, "הנכס לא נמצא במסלול")
        ts = now()
        if m.action == "done":
            conn.execute("UPDATE route_stops SET status='done', reason=NULL, updated_at=? WHERE route_id=? AND property_id=?",
                         (ts, rid, pid))
        elif m.action == "not_done":
            if m.reason not in ("locked", "no_answer", "refused", "other"):
                raise HTTPException(400, "יש לבחור סיבה")
            conn.execute("UPDATE route_stops SET status='not_done', reason=?, updated_at=? WHERE route_id=? AND property_id=?",
                         (m.reason, ts, rid, pid))
        elif m.action == "skip":
            if st["status"] != "pending":
                raise HTTPException(400, "אפשר לדלג רק על נכס שממתין")
            last = conn.execute("SELECT MAX(seq) FROM route_stops WHERE route_id = ?", (rid,)).fetchone()[0]
            conn.execute("UPDATE route_stops SET seq=?, skips=skips+1, updated_at=? WHERE route_id=? AND property_id=?",
                         (last + 1, ts, rid, pid))
        elif m.action == "undo":
            conn.execute("UPDATE route_stops SET status='pending', reason=NULL, updated_at=? WHERE route_id=? AND property_id=?",
                         (ts, rid, pid))
        else:
            raise HTTPException(400, "פעולה לא מוכרת")
        conn.execute("INSERT INTO visit_events(route_id, property_id, action, reason, ts) VALUES (?,?,?,?,?)",
                     (rid, pid, m.action, m.reason, ts))
    return get_route(rid)
