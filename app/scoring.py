"""Transparent value score per property: expected revenue = P(gap) x revenue if gap is found.

Each criterion has a role:
  - "prob":   a signal that a gap exists. Min-max normalized within the round to 0..1,
              optionally inverted, combined as a weighted average -> probability 0..1.
  - "amount": money (or money-like) columns. Weighted sum -> revenue if the gap is found (₪).
  - "ignore": not used.
The score does not depend on the surveyor's location, so the manager sees one fixed ranking.
"""

DEFAULT_ROLE_HINTS = (
    ("₪", "amount", 1.0),
    ("חוב", "amount", 1.0),
    ("הכנסה", "amount", 1.0),
    ("פער", "prob", 2.0),
    ("תלונ", "prob", 1.0),
    ("פניות", "prob", 1.0),
    ("שנים", "prob", 1.0),
)


def default_criteria(names: list[str]) -> list[dict]:
    out = []
    for name in names:
        role, weight = "ignore", 1.0
        for hint, r, w in DEFAULT_ROLE_HINTS:
            if hint in name:
                role, weight = r, w
                break
        out.append({"name": name, "role": role, "weight": weight, "invert": False})
    return out


def score_properties(props: list[dict], criteria: list[dict]) -> list[dict]:
    """props: [{"id":..., "values": {name: float|None}}]. Returns [{id, prob, amount, score, breakdown}]."""
    prob_c = [c for c in criteria if c["role"] == "prob" and c["weight"] > 0]
    amt_c = [c for c in criteria if c["role"] == "amount" and c["weight"] > 0]

    ranges = {}
    for c in prob_c:
        vals = [p["values"].get(c["name"]) for p in props if p["values"].get(c["name"]) is not None]
        ranges[c["name"]] = (min(vals), max(vals)) if vals else (0.0, 0.0)
    wsum = sum(c["weight"] for c in prob_c)

    results = []
    for p in props:
        breakdown = []
        prob = 0.0 if prob_c else 1.0  # no probability criteria -> rank by amount alone
        for c in prob_c:
            v = p["values"].get(c["name"])
            lo, hi = ranges[c["name"]]
            norm = 0.0 if v is None or hi == lo else (v - lo) / (hi - lo)
            if c.get("invert") and v is not None:
                norm = 1.0 - norm
            contrib = c["weight"] * norm / wsum
            prob += contrib
            breakdown.append({"name": c["name"], "role": "prob", "value": v, "normalized": round(norm, 3),
                              "weight": c["weight"], "contribution": round(contrib, 4)})
        prob = min(max(prob, 0.0), 1.0)
        amount = 0.0
        for c in amt_c:
            v = p["values"].get(c["name"]) or 0.0
            contrib = c["weight"] * v
            amount += contrib
            breakdown.append({"name": c["name"], "role": "amount", "value": p["values"].get(c["name"]),
                              "weight": c["weight"], "contribution": round(contrib, 2)})
        results.append({"id": p["id"], "prob": round(prob, 4), "amount": round(amount, 2),
                        "score": round(prob * amount, 2), "breakdown": breakdown})
    results.sort(key=lambda r: -r["score"])
    for i, r in enumerate(results, start=1):
        r["rank"] = i
    return results
