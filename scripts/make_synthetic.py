"""Generate a synthetic property list (no real residents) for RouteWise demos.

Output: sample_data/properties.xlsx
Contains a few deliberate problems so upload validation can be demonstrated:
missing address, duplicate property, a non-numeric value, and rows without coordinates.
"""
import os
import random
import sys

from openpyxl import Workbook

NEIGHBORHOODS = {
    "רחביה": ((31.7735, 35.2115), ["רמב\"ן", "עזה", "אבן גבירול", "אלפסי", "קרן קיימת לישראל", "אברבנאל"]),
    "בקעה": ((31.7570, 35.2215), ["דרך בית לחם", "יהודה", "רחל אמנו", "יהושע בן נון", "גדעון"]),
    "קטמון": ((31.7625, 35.2070), ["הפלמ\"ח", "טשרניחובסקי", "ההגנה", "שמואל הנגיד", "רחל אמנו"]),
    "גילה": ((31.7290, 35.1865), ["הגנן", "אנה פרנק", "הרוזמרין", "המעיין", "ניצנה"]),
    "רמות": ((31.8155, 35.1955), ["גולדה מאיר", "רב אשי", "סולם יעקב", "אידלסון", "מיטב"]),
}
USES = ["מגורים", "מגורים", "מגורים", "מסחר", "משרד"]

HEADERS = [
    "מזהה נכס", "כתובת", "שכונה", "lat", "lon", "שימוש רשום",
    "שטח רשום (מ\"ר)", "שנים מאז ביקור אחרון", "פער שטח לפי צילום אוויר (מ\"ר)",
    "פניות ותלונות", "חוב פוטנציאלי שנתי (₪)",
]


def make_rows(per_neighborhood: int = 30, seed: int = 7):
    rnd = random.Random(seed)
    rows, n = [], 0
    for hood, ((clat, clon), streets) in NEIGHBORHOODS.items():
        used = set()
        for _ in range(per_neighborhood):
            n += 1
            while True:
                street, num = rnd.choice(streets), rnd.randint(1, 60)
                if (street, num) not in used:
                    used.add((street, num))
                    break
            area = rnd.randint(45, 220)
            gap = max(0, round(rnd.gauss(8, 14)))
            years = rnd.randint(0, 15)
            complaints = rnd.choice([0, 0, 0, 0, 1, 1, 2, 3])
            use = rnd.choice(USES)
            rate = 95 if use == "מגורים" else 320
            debt = round((gap + rnd.randint(0, 25)) * rate * rnd.uniform(0.6, 1.4), -1)
            rows.append([
                f"P{n:04d}", f"{street} {num}, ירושלים", hood,
                round(clat + rnd.gauss(0, 0.0035), 6), round(clon + rnd.gauss(0, 0.0035), 6),
                use, area, years, gap, complaints, debt,
            ])
    # deliberate problems for the validation demo
    rows[3][1] = ""                         # missing address
    rows[40][1] = None                      # missing address
    rows.append(list(rows[10]))             # exact duplicate row
    dup = list(rows[70]); dup[0] = "P9999"; rows.append(dup)   # same address, new id
    rows[55][9] = "לא ידוע"                 # non-numeric criterion
    rows[20][3] = rows[20][4] = None        # no coordinates -> geocoding fallback
    return rows


def main(out_path: str):
    wb = Workbook()
    ws = wb.active
    ws.title = "נכסים"
    ws.sheet_view.rightToLeft = True
    ws.append(HEADERS)
    for r in make_rows():
        ws.append(r)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    wb.save(out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "sample_data", "properties.xlsx"))
