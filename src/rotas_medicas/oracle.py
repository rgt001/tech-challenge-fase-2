"""Enumeração independente para problemas pequenos; não chama o avaliador do GA."""
from __future__ import annotations
from itertools import permutations, combinations_with_replacement
import math
from .domain import Scenario


def exact_small(scenario: Scenario) -> dict:
    n, k = len(scenario.deliveries), len(scenario.vehicles)
    if n > 7 or k > 3:
        raise ValueError("Oráculo limitado a 7 entregas e 3 veículos")
    best = math.inf
    best_routes = None
    examined = 0
    for order in permutations(range(1, n+1)):
        for cuts in combinations_with_replacement(range(n+1), k-1):
            bounds = (0, *cuts, n)
            candidate = [list(order[bounds[i]:bounds[i+1]]) for i in range(k)]
            distance_total = weighted = 0.0
            valid = True
            examined += 1
            for v, route in zip(scenario.vehicles, candidate):
                capacity = sum(scenario.deliveries[node-1].load for node in route)
                if capacity > v.capacity + 1e-8:
                    valid = False
                    break
                previous = 0
                length = time = 0.0
                for node in route:
                    edge = scenario.distance[previous][node]
                    seconds = scenario.duration_s[previous][node]
                    if edge is None or seconds is None:
                        valid = False
                        break
                    length += edge
                    time += seconds
                    delivery = scenario.deliveries[node-1]
                    weighted += scenario.priority_weights[delivery.priority] * time
                    time += delivery.service_s
                    previous = node
                if not valid:
                    break
                back = scenario.distance[previous][0]
                if back is None or scenario.duration_s[previous][0] is None:
                    valid = False
                    break
                length += back
                if v.max_distance is not None and length > v.max_distance + 1e-8:
                    valid = False
                    break
                distance_total += length
            if valid:
                cost_distance = distance_total/1000 if scenario.distance_unit == "m" else distance_total
                cost = cost_distance + scenario.priority_coefficient*weighted/60
                if cost < best - 1e-10:
                    best, best_routes = cost, candidate
    return {"feasible": best_routes is not None, "objective": best if best_routes is not None else None,
            "routes": best_routes, "examined": examined, "method": "independent_exhaustive_enumeration"}
