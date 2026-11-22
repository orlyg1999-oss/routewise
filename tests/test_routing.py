import itertools
import random

from app.routing import build_route, haversine_m, RouteParams, _Problem

START = (31.7700, 35.2100)


def offset(lat_m, lon_m, base=START):
    return (base[0] + lat_m / 111_000, base[1] + lon_m / 94_500)


def test_high_value_comes_first_when_distances_similar():
    pts = [offset(200, 0), offset(0, 200), offset(-200, 0)]
    order = build_route(START, pts, [10, 1000, 10])
    assert order[0] == 1


def test_nearby_cluster_beats_single_distant_property():
    cluster = [offset(150, 0), offset(200, 60), offset(150, 120), offset(220, 180)]
    far = offset(-4000, -3000)
    order = build_route(START, cluster + [far], [100, 100, 100, 100, 150])
    assert order[-1] == 4  # the distant one, though individually most valuable, is last


def test_no_zigzag_between_two_clusters():
    a = [offset(100, 0), offset(150, 50), offset(100, 100)]
    b = [offset(-2500, 0), offset(-2550, 50), offset(-2500, 100)]
    # values alternate between clusters; a naive sort-by-value would zigzag
    order = build_route(START, a + b, [100, 80, 60, 95, 75, 55])
    sides = ["A" if i < 3 else "B" for i in order]
    assert sides in (["A"] * 3 + ["B"] * 3, ["B"] * 3 + ["A"] * 3)


def test_matches_brute_force_on_small_instances():
    rnd = random.Random(1)
    for _ in range(5):
        pts = [offset(rnd.uniform(-1500, 1500), rnd.uniform(-1500, 1500)) for _ in range(6)]
        vals = [rnd.uniform(100, 5000) for _ in range(6)]
        prob = _Problem(START, pts, vals, RouteParams())
        best = max(prob.objective(list(p)) for p in itertools.permutations(range(6)))
        got = prob.objective(build_route(START, pts, vals))
        assert got >= best * 0.995


def test_haversine():
    assert abs(haversine_m((31.77, 35.21), (31.78, 35.21)) - 1112) < 5
