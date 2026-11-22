"""Parse the manager's Excel/CSV and validate it before anything enters a route."""
import csv
import io
import re
from typing import Callable

from openpyxl import load_workbook

ID_COLS = {"מזהה נכס", "מזהה", "id", "property_id"}
ADDR_COLS = {"כתובת", "address"}
HOOD_COLS = {"שכונה", "neighborhood"}
LAT_COLS = {"lat", "latitude", "קו רוחב"}
LON_COLS = {"lon", "lng", "longitude", "קו אורך"}


def read_table(filename: str, content: bytes) -> tuple[list[str], list[list]]:
    """Return headers and data rows from .xlsx or .csv bytes."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    elif filename.lower().endswith(".csv"):
        text = content.decode("utf-8-sig")
        rows = [list(r) for r in csv.reader(io.StringIO(text))]
    else:
        raise ValueError("סוג קובץ לא נתמך. יש להעלות קובץ xlsx או csv")
    rows = [r for r in rows if any(c not in (None, "") for c in r)]
    if not rows:
        raise ValueError("הקובץ ריק")
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    return headers, rows[1:]


def to_number(v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("₪", "").strip()
    try:
        return float(s)
    except ValueError:
        raise ValueError(s)


def _find(headers, names):
    for i, h in enumerate(headers):
        if h.strip().lower() in {n.lower() for n in names}:
            return i
    return None


def norm_address(a: str) -> str:
    return re.sub(r"[\s,\"'״׳]+", " ", a).strip().lower()


def validate(headers: list[str], data: list[list],
             geocode: Callable[[str], tuple[float, float] | None] | None = None) -> dict:
    """Validate rows. Returns valid properties, issues, and detected criterion columns."""
    idx_id, idx_addr, idx_hood = _find(headers, ID_COLS), _find(headers, ADDR_COLS), _find(headers, HOOD_COLS)
    idx_lat, idx_lon = _find(headers, LAT_COLS), _find(headers, LON_COLS)
    missing = [name for name, i in (("כתובת", idx_addr), ("שכונה", idx_hood)) if i is None]
    if missing:
        raise ValueError("חסרות עמודות חובה: " + ", ".join(missing))

    special = {i for i in (idx_id, idx_addr, idx_hood, idx_lat, idx_lon) if i is not None}
    other = [i for i, h in enumerate(headers) if i not in special and h]

    # a column is a criterion if at least 80% of its non-empty values are numeric
    criteria_idx, info_idx = [], []
    for i in other:
        vals = [r[i] for r in data if i < len(r) and r[i] not in (None, "")]
        ok = 0
        for v in vals:
            try:
                to_number(v)
                ok += 1
            except ValueError:
                pass
        (criteria_idx if vals and ok / len(vals) >= 0.8 else info_idx).append(i)

    issues, props = [], []
    seen_ids, seen_addr = {}, {}
    for n, r in enumerate(data, start=2):  # Excel row number (header is row 1)
        r = list(r) + [None] * (len(headers) - len(r))
        def issue(kind, msg, level="error"):
            issues.append({"row": n, "level": level, "kind": kind, "message": msg})

        addr = str(r[idx_addr]).strip() if r[idx_addr] not in (None, "") else ""
        hood = str(r[idx_hood]).strip() if r[idx_hood] not in (None, "") else ""
        ext_id = str(r[idx_id]).strip() if idx_id is not None and r[idx_id] not in (None, "") else None
        if not addr:
            issue("missing_address", "כתובת חסרה – השורה לא תיכנס למסלול")
            continue
        if not hood:
            issue("missing_neighborhood", f"שכונה חסרה ({addr}) – השורה לא תיכנס למסלול")
            continue
        if ext_id and ext_id in seen_ids:
            issue("duplicate", f"מזהה נכס {ext_id} כפול (מופיע גם בשורה {seen_ids[ext_id]}) – השורה הושמטה")
            continue
        na = norm_address(addr)
        if na in seen_addr:
            issue("duplicate", f"הכתובת \"{addr}\" כפולה (מופיעה גם בשורה {seen_addr[na]}) – השורה הושמטה")
            continue

        values = {}
        for i in criteria_idx:
            try:
                values[headers[i]] = to_number(r[i])
            except ValueError as e:
                values[headers[i]] = None
                issue("bad_number", f"ערך לא מספרי \"{e}\" בעמודה \"{headers[i]}\" – יחושב כחסר", "warning")
        info = {headers[i]: r[i] for i in info_idx if r[i] not in (None, "")}

        lat = lon = None
        try:
            if idx_lat is not None and idx_lon is not None:
                lat, lon = to_number(r[idx_lat]), to_number(r[idx_lon])
        except ValueError:
            lat = lon = None
        if lat is None or lon is None:
            loc = geocode(addr) if geocode else None
            if not loc:
                issue("geocode_failed", f"לא נמצא מיקום לכתובת \"{addr}\" – השורה לא תיכנס למסלול")
                continue
            lat, lon = loc
            issue("geocoded", f"מיקום חושב מהכתובת \"{addr}\"", "info")

        if ext_id:
            seen_ids[ext_id] = n
        seen_addr[na] = n
        props.append({"ext_id": ext_id, "address": addr, "neighborhood": hood, "lat": lat, "lon": lon,
                      "values": values, "info": info})

    return {
        "properties": props,
        "issues": issues,
        "criteria": [headers[i] for i in criteria_idx],
        "info_columns": [headers[i] for i in info_idx],
        "summary": {
            "rows": len(data),
            "valid": len(props),
            "errors": sum(1 for i in issues if i["level"] == "error"),
            "warnings": sum(1 for i in issues if i["level"] == "warning"),
        },
    }
