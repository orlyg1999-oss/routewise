"""End-to-end flow through the HTTP API on the synthetic file (no network: geocoding is stubbed)."""
import os
import tempfile

os.environ["ROUTEWISE_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import geocode  # noqa: E402
from app.main import app  # noqa: E402
from scripts.make_synthetic import main as make_file  # noqa: E402

geocode.geocode = lambda a: None  # the row without coordinates should be reported, not crash


def test_full_round():
    path = os.path.join(tempfile.mkdtemp(), "p.xlsx")
    make_file(path)
    c = TestClient(app)
    with open(path, "rb") as f:
        r = c.post("/api/rounds", data={"name": "סבב בדיקה"}, files={"file": ("p.xlsx", f.read())})
    assert r.status_code == 200, r.text
    rnd = r.json()
    kinds = sorted({i["kind"] for i in rnd["validation"]["issues"]})
    assert kinds == ["bad_number", "duplicate", "geocode_failed", "missing_address"]
    assert rnd["validation"]["summary"]["valid"] == 147
    rid = rnd["id"]

    ranking = c.get(f"/api/rounds/{rid}/ranking").json()
    assert ranking[0]["rank"] == 1 and ranking[0]["score"] >= ranking[-1]["score"]
    assert ranking[0]["breakdown"]

    crit = rnd["criteria"]
    for x in crit:
        if "תלונות" in x["name"]:
            x["weight"] = 5
    assert c.put(f"/api/rounds/{rid}/criteria", json=crit).status_code == 200

    hood = rnd["neighborhoods"][0]["neighborhood"]
    assert c.post(f"/api/rounds/{rid}/approve").status_code == 400  # no assignment yet
    c.put(f"/api/rounds/{rid}/assignments", json={hood: 1})
    assert c.post(f"/api/rounds/{rid}/approve").json()["status"] == "approved"
    assert c.put(f"/api/rounds/{rid}/criteria", json=crit).status_code == 409

    routes = c.get("/api/surveyor/1/routes").json()["routes"]
    route = c.post(f"/api/routes/{routes[0]['id']}/open", json={"lat": 0, "lon": 0}).json()
    assert route["start"]["source"] == "centroid" and len(route["stops"]) > 20
    s1, s2, s3 = (s["property_id"] for s in route["stops"][:3])
    url = f"/api/routes/{route['id']}/stops"
    c.post(f"{url}/{s1}", json={"action": "done"})
    assert c.post(f"{url}/{s2}", json={"action": "not_done"}).status_code == 400
    c.post(f"{url}/{s2}", json={"action": "not_done", "reason": "locked"})
    route = c.post(f"{url}/{s3}", json={"action": "skip"}).json()
    assert route["stops"][-1]["property_id"] == s3

    rep = c.get(f"/api/rounds/{rid}/report").json()["routes"][0]
    assert (rep["done"], rep["not_done"]) == (1, 1) and rep["visited_value"] > 0
    csv = c.get(f"/api/rounds/{rid}/report.csv")
    assert csv.status_code == 200 and "נעול" in csv.content.decode("utf-8-sig")
