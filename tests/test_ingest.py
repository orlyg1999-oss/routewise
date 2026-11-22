from app.ingest import validate

H = ["מזהה נכס", "כתובת", "שכונה", "lat", "lon", "שימוש רשום", "פער", "חוב (₪)"]


def row(i, addr, lat=31.77, lon=35.21, gap=1, debt=100):
    return [f"P{i}", addr, "רחביה", lat, lon, "מגורים", gap, debt]


def test_missing_and_duplicates_are_excluded():
    data = [row(1, "עזה 1"), row(2, ""), row(3, "עזה 2"), row(3, "עזה 9"), row(4, "עזה, 1")]
    res = validate(H, data)
    assert [p["ext_id"] for p in res["properties"]] == ["P1", "P3"]
    kinds = sorted(i["kind"] for i in res["issues"] if i["level"] == "error")
    assert kinds == ["duplicate", "duplicate", "missing_address"]
    assert res["criteria"] == ["פער", "חוב (₪)"] and res["info_columns"] == ["שימוש רשום"]


def test_non_numeric_is_warning_and_geocode_fallback():
    data = [row(1, "עזה 1", gap="לא ידוע"), row(2, "עזה 2", lat=None, lon=None), row(3, "עזה 3", lat=None, lon=None)]
    data += [row(i, f"עזה {i}") for i in range(4, 9)]  # enough numeric values to keep "פער" a criterion
    res = validate(H, data, geocode=lambda a: (31.0, 35.0) if a == "עזה 2" else None)
    assert res["properties"][0]["values"]["פער"] is None
    assert res["properties"][1]["lat"] == 31.0
    assert len(res["properties"]) == 7
    assert {i["kind"] for i in res["issues"]} == {"bad_number", "geocoded", "geocode_failed"}
