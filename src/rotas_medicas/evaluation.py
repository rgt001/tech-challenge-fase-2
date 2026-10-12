"""Avaliação rápida de candidatos, separada do certificador de entrega."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
import math
import uuid
from .domain import Metrics, Priority, Route, Scenario, Solution, Stop
from .storage import canonical_hash


@dataclass(slots=True)
class CandidateScore:
    structural_errors: int
    violation: float
    objective: float
    distance: float
    weighted_arrival_s: float

    @property
    def key(self) -> tuple[int, float, float]:
        return self.structural_errors, self.violation, self.objective

    @property
    def feasible(self) -> bool:
        return self.structural_errors == 0 and self.violation == 0


class Evaluator:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.n = len(scenario.deliveries)
        self.k = len(scenario.vehicles)
        self.dist = scenario.distance
        self.time = scenario.duration_s
        self.loads = [0.0, *(d.load for d in scenario.deliveries)]
        self.services = [0.0, *(d.service_s for d in scenario.deliveries)]
        self.weights = [0.0, *(scenario.priority_weights[d.priority] for d in scenario.deliveries)]

    def route_values(self, route: list[int], vehicle_index: int) -> tuple[float, float, float, float]:
        distance = arrival = load = weighted = 0.0
        previous = 0
        for node in route:
            edge = self.dist[previous][node]
            duration = self.time[previous][node]
            if edge is None or duration is None:
                return math.inf, math.inf, math.inf, math.inf
            distance += edge
            arrival += duration
            weighted += self.weights[node] * arrival
            arrival += self.services[node]
            load += self.loads[node]
            previous = node
        edge, duration = self.dist[previous][0], self.time[previous][0]
        if edge is None or duration is None:
            return math.inf, math.inf, math.inf, math.inf
        return distance + edge, arrival + duration, load, weighted

    def score(self, routes: list[list[int]]) -> CandidateScore:
        seen = Counter(node for r in routes for node in r)
        structural = sum(abs(seen[i] - 1) for i in range(1, self.n + 1))
        structural += sum(c for i, c in seen.items() if not 1 <= i <= self.n)
        structural += abs(len(routes) - self.k)
        if structural:
            return CandidateScore(structural, math.inf, math.inf, math.inf, math.inf)
        total_distance = total_weighted = violation = 0.0
        for i, route in enumerate(routes):
            distance, _, load, weighted = self.route_values(route, i)
            if not math.isfinite(distance):
                return CandidateScore(0, math.inf, math.inf, math.inf, math.inf)
            vehicle = self.scenario.vehicles[i]
            if load > vehicle.capacity + 1e-8:
                violation += (load - vehicle.capacity) / vehicle.capacity
            if vehicle.max_distance is not None:
                if distance > vehicle.max_distance + 1e-8:
                    violation += (distance - vehicle.max_distance) / vehicle.max_distance
            total_distance += distance
            total_weighted += weighted
        distance_cost = total_distance / 1000 if self.scenario.distance_unit == "m" else total_distance
        objective = distance_cost + self.scenario.priority_coefficient * total_weighted / 60
        return CandidateScore(0, violation, objective, total_distance, total_weighted)


def infeasibility_proofs(scenario: Scenario) -> list[str]:
    """Somente condições necessárias cuja falha prova impossibilidade."""
    reasons = []
    if sum(d.load for d in scenario.deliveries) > sum(v.capacity for v in scenario.vehicles) + 1e-8:
        reasons.append("Carga total excede a capacidade total da frota, sem reabastecimento")
    for i, delivery in enumerate(scenario.deliveries, 1):
        if all(delivery.load > v.capacity + 1e-8 for v in scenario.vehicles):
            reasons.append(f"Carga de {delivery.id} excede todos os veículos")
        # Não usar distância direta como limite inferior: matriz arbitrária pode não ser métrica.
        # Ausência total de arcos de entrada/saída, porém, prova impossibilidade.
        if all(scenario.distance[j][i] is None for j in range(len(scenario.node_ids)) if j != i):
            reasons.append(f"Entrega {delivery.id} sem arco de entrada")
        if all(scenario.distance[i][j] is None for j in range(len(scenario.node_ids)) if j != i):
            reasons.append(f"Entrega {delivery.id} sem arco de saída")
    return reasons


def failure_solution(scenario: Scenario, algorithm: str, diagnostics: list[str],
                     proven: bool = False, **metadata) -> Solution:
    return Solution(id=uuid.uuid4().hex, scenario_id=scenario.id, scenario_hash=canonical_hash(scenario),
                    algorithm=algorithm, status="infeasible_proven" if proven else "no_feasible_solution",
                    routes=[], metrics=None, diagnostics=diagnostics, metadata=metadata)


def build_solution(scenario: Scenario, routes: list[list[int]], algorithm: str,
                   seed: int | None = None, metadata: dict | None = None) -> Solution:
    evaluator = Evaluator(scenario)
    score = evaluator.score(routes)
    if not score.feasible:
        return failure_solution(scenario, algorithm, ["Candidato final não satisfaz todas as restrições"],
                                candidate_violation=str(score.violation), **(metadata or {}))
    result_routes = []
    critical = []
    total_duration = 0.0
    for i, route in enumerate(routes):
        stops = []
        clock = 0.0
        previous = 0
        for order, node in enumerate(route, 1):
            delivery = scenario.deliveries[node - 1]
            clock += scenario.duration_s[previous][node]
            arrival = clock
            if delivery.priority == Priority.CRITICAL:
                critical.append(arrival)
            clock += delivery.service_s
            stops.append(Stop(delivery_id=delivery.id, order=order, arrival_s=arrival,
                              departure_s=clock, load=delivery.load, priority=delivery.priority))
            previous = node
        distance, duration, load, _ = evaluator.route_values(route, i)
        total_duration += duration
        result_routes.append(Route(vehicle_id=scenario.vehicles[i].id, stops=stops,
                                   distance=distance, duration_s=duration, initial_load=load))
    solution = Solution(id=uuid.uuid4().hex, scenario_id=scenario.id, scenario_hash=canonical_hash(scenario),
                        algorithm=algorithm, seed=seed, status="feasible", routes=result_routes,
                        metrics=Metrics(total_distance=score.distance, total_duration_s=total_duration,
                                        weighted_arrival_s=score.weighted_arrival_s,
                                        critical_arrival_mean_s=sum(critical)/len(critical) if critical else None,
                                        vehicles_used=sum(bool(r) for r in routes), deliveries_served=evaluator.n,
                                        objective=score.objective), metadata=metadata or {})
    from .verification import verify_solution
    solution.verification = verify_solution(scenario, solution)
    if not solution.verification.valid:
        raise RuntimeError("Certificador independente rejeitou a construção: " +
                           "; ".join(solution.verification.errors))
    return solution
