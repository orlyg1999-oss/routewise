"""Route engine: decides the ORDER of visits, separately from the value score.

Objective (maximize): sum(score_i * 0.5 ** (arrival_i / half_life)) - travel_cost * travel_minutes.
High-value properties are pulled early, but every minute of travel delays everything after it,
so zig-zagging across the neighborhood is penalized and a nearby cluster with high combined
value can come before a single distant property.
Construction: greedy insertion. Improvement: relocate (or-opt) + 2-opt until no gain.
"""
import math
from dataclasses import dataclass


@dataclass
class RouteParams:
    visit_minutes: float = 30.0        # time on site per property
    walk_threshold_m: float = 400.0    # shorter legs are walked
    walk_kmh: float = 4.5
    drive_kmh: float = 22.0            # city driving incl. parking
    drive_overhead_min: float = 4.0    # getting in/out of the car and parking
    road_factor: float = 1.3           # street distance vs straight line
    half_life_min: float = 240.0       # value of a visit halves every 4 hours of delay
    travel_penalty: float = 0.5        # cost of a travel minute, as a share of the average value per visit-minute


def haversine_m(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def travel_minutes(a, b, p: RouteParams) -> float:
    d = haversine_m(a, b) * p.road_factor
    if d <= p.walk_threshold_m * p.road_factor:
        return d / (p.walk_kmh * 1000 / 60)
    return p.drive_overhead_min + d / (p.drive_kmh * 1000 / 60)


class _Problem:
    def __init__(self, start, points, values, p: RouteParams):
        self.n = len(points)
        self.values = values
        self.p = p
        locs = [start] + list(points)  # index 0 = start
        self.t = [[travel_minutes(a, b, p) for b in locs] for a in locs]
        # travel time is time not spent visiting: it pushes the low-value tail out of the day
        mean_value = sum(values) / len(values) if values else 0.0
        self.cost_per_travel_min = p.travel_penalty * mean_value / p.visit_minutes

    def objective(self, order) -> float:
        total, time, travel, prev = 0.0, 0.0, 0.0, 0
        hl = self.p.half_life_min
        for i in order:
            leg = self.t[prev][i + 1]
            travel += leg
            time += leg
            total += self.values[i] * 0.5 ** (time / hl)
            time += self.p.visit_minutes
            prev = i + 1
        return total - self.cost_per_travel_min * travel


def build_route(start, points, values, params: RouteParams | None = None) -> list[int]:
    """start: (lat, lon); points: [(lat, lon)]; values: [score]. Returns indices in visit order."""
    p = params or RouteParams()
    n = len(points)
    if n <= 1:
        return list(range(n))
    prob = _Problem(start, points, values, p)

    # greedy insertion, most valuable first
    order: list[int] = []
    for i in sorted(range(n), key=lambda k: -values[k]):
        best, best_pos = None, 0
        for pos in range(len(order) + 1):
            val = prob.objective(order[:pos] + [i] + order[pos:])
            if best is None or val > best:
                best, best_pos = val, pos
        order.insert(best_pos, i)

    # local search
    best = prob.objective(order)
    for _ in range(50):                          # passes; each applies every improving move it finds
        improved = False
        for a in range(n):                       # relocate one stop
            for b in range(n):
                if b == a:
                    continue
                rest = order[:a] + order[a + 1:]
                cand = rest[:b] + [order[a]] + rest[b:]
                v = prob.objective(cand)
                if v > best + 1e-9:
                    order, best, improved = cand, v, True
        for a in range(n - 1):                   # 2-opt segment reversal
            for b in range(a + 2, n + 1):
                cand = order[:a] + order[a:b][::-1] + order[b:]
                v = prob.objective(cand)
                if v > best + 1e-9:
                    order, best, improved = cand, v, True
        if not improved:
            break
    return order


def route_stats(start, points, order, params: RouteParams | None = None) -> dict:
    p = params or RouteParams()
    prev, travel, legs = start, 0.0, []
    for i in order:
        m = travel_minutes(prev, points[i], p)
        travel += m
        legs.append(round(m, 1))
        prev = points[i]
    return {"travel_minutes": round(travel, 1), "legs": legs,
            "total_minutes": round(travel + p.visit_minutes * len(order), 1)}
