from app.scoring import default_criteria, score_properties

CRIT = [
    {"name": "gap", "role": "prob", "weight": 1, "invert": False},
    {"name": "debt", "role": "amount", "weight": 1, "invert": False},
]


def test_expected_revenue_medium_chance_big_gap_beats_high_chance_small_gap():
    props = [
        {"id": 1, "values": {"gap": 10, "debt": 1000}},    # high chance, small money
        {"id": 2, "values": {"gap": 5, "debt": 10000}},    # medium chance, big money
        {"id": 3, "values": {"gap": 0, "debt": 50000}},    # no signal at all
    ]
    res = {r["id"]: r for r in score_properties(props, CRIT)}
    assert res[1]["prob"] == 1.0 and res[1]["score"] == 1000
    assert res[2]["prob"] == 0.5 and res[2]["score"] == 5000
    assert res[3]["score"] == 0
    assert res[2]["rank"] == 1


def test_breakdown_explains_score_and_weights_change_ranking():
    props = [{"id": 1, "values": {"a": 10, "b": 0, "debt": 100}},
             {"id": 2, "values": {"a": 0, "b": 10, "debt": 100}}]
    crit = [{"name": "a", "role": "prob", "weight": 3}, {"name": "b", "role": "prob", "weight": 1},
            {"name": "debt", "role": "amount", "weight": 1}]
    res = score_properties(props, crit)
    assert res[0]["id"] == 1
    top = res[0]
    assert abs(sum(b["contribution"] for b in top["breakdown"] if b["role"] == "prob") - top["prob"]) < 1e-3
    crit[0]["weight"], crit[1]["weight"] = 1, 3
    assert score_properties(props, crit)[0]["id"] == 2


def test_invert_and_missing_values():
    props = [{"id": 1, "values": {"x": 0, "debt": 10}}, {"id": 2, "values": {"x": None, "debt": 10}},
             {"id": 3, "values": {"x": 10, "debt": 10}}]
    crit = [{"name": "x", "role": "prob", "weight": 1, "invert": True}, {"name": "debt", "role": "amount", "weight": 1}]
    res = {r["id"]: r for r in score_properties(props, crit)}
    assert res[1]["prob"] == 1.0 and res[3]["prob"] == 0.0 and res[2]["prob"] == 0.0


def test_default_roles():
    c = {x["name"]: x["role"] for x in default_criteria(["חוב פוטנציאלי שנתי (₪)", "פניות ותלונות", "שטח רשום"])}
    assert c == {"חוב פוטנציאלי שנתי (₪)": "amount", "פניות ותלונות": "prob", "שטח רשום": "ignore"}
