"""Certificador independente: não importa o avaliador, GA ou reparador."""
from __future__ import annotations
from collections import Counter
import math
from .domain import Priority, Scenario, Solution, Verification
from .storage import canonical_hash


def verify_solution(scenario: Scenario, solution: Solution) -> Verification:
    errors: list[str] = []
    nodes = {node_id: i for i, node_id in enumerate(scenario.node_ids)}
    deliveries = {d.id: d for d in scenario.deliveries}
    vehicles = {v.id: v for v in scenario.vehicles}
    visits: Counter[str] = Counter()
    vehicle_visits: Counter[str] = Counter()
    distances, durations, weighted, critical = [], [], [], []

    def equal(label: str, reported: float, actual: float) -> None:
        if not math.isclose(reported, actual, rel_tol=1e-9, abs_tol=1e-6):
            errors.append(f"{label}: informado {reported}, recalculado {actual}")

    if solution.scenario_id != scenario.id or solution.scenario_hash != canonical_hash(scenario):
        errors.append("Solução pertence a outro cenário ou versão dos dados")
    if solution.status != "feasible":
        errors.append("Solução não está liberada como viável")
    for route in solution.routes:
        vehicle_visits[route.vehicle_id] += 1
        if route.vehicle_id not in vehicles:
            errors.append(f"Veículo desconhecido: {route.vehicle_id}")
            continue
        vehicle = vehicles[route.vehicle_id]
        previous = 0
        length = clock = cargo = route_weighted = 0.0
        for position, stop in enumerate(route.stops, 1):
            visits[stop.delivery_id] += 1
            if stop.delivery_id not in deliveries:
                errors.append(f"Entrega desconhecida: {stop.delivery_id}")
                continue
            delivery = deliveries[stop.delivery_id]
            current = nodes[stop.delivery_id]
            distance = scenario.distance[previous][current]
            duration = scenario.duration_s[previous][current]
            if distance is None or duration is None:
                errors.append(f"Trecho inalcançável na entrega {stop.delivery_id}")
                previous = current
                continue
            length += distance
            clock += duration
            equal(f"Chegada {stop.delivery_id}", stop.arrival_s, clock)
            if stop.order != position:
                errors.append(f"Ordem incorreta em {stop.delivery_id}")
            if stop.priority != delivery.priority:
                errors.append(f"Prioridade incorreta em {stop.delivery_id}")
            equal(f"Carga {stop.delivery_id}", stop.load, delivery.load)
            cargo += delivery.load
            route_weighted += scenario.priority_weights[delivery.priority] * clock
            if delivery.priority == Priority.CRITICAL:
                critical.append(clock)
            clock += delivery.service_s
            equal(f"Saída {stop.delivery_id}", stop.departure_s, clock)
            previous = current
        back_distance = scenario.distance[previous][0]
        back_duration = scenario.duration_s[previous][0]
        if back_distance is None or back_duration is None:
            errors.append(f"Retorno inalcançável: {route.vehicle_id}")
        else:
            length += back_distance
            clock += back_duration
        if not route.return_to_depot:
            errors.append(f"Retorno ao depósito não declarado: {route.vehicle_id}")
        equal(f"Distância {route.vehicle_id}", route.distance, length)
        equal(f"Duração {route.vehicle_id}", route.duration_s, clock)
        equal(f"Carga inicial {route.vehicle_id}", route.initial_load, cargo)
        if cargo > vehicle.capacity + 1e-8:
            errors.append(f"Capacidade excedida: {route.vehicle_id}")
        if vehicle.max_distance is not None and length > vehicle.max_distance + 1e-8:
            errors.append(f"Autonomia excedida incluindo retorno: {route.vehicle_id}")
        distances.append(length)
        durations.append(clock)
        weighted.append(route_weighted)
    for vehicle_id, count in vehicle_visits.items():
        if count > 1:
            errors.append(f"Veículo usado em mais de uma rota: {vehicle_id}")
    for delivery_id in deliveries:
        if visits[delivery_id] != 1:
            errors.append(f"Entrega {delivery_id}: {visits[delivery_id]} visitas, esperado 1")
    total_distance = sum(distances)
    distance_objective = total_distance / 1000 if scenario.distance_unit == "m" else total_distance
    recomputed = {
        "total_distance": total_distance,
        "total_duration_s": sum(durations),
        "weighted_arrival_s": sum(weighted),
        "critical_arrival_mean_s": sum(critical) / len(critical) if critical else None,
        "vehicles_used": sum(bool(r.stops) for r in solution.routes),
        "deliveries_served": sum(visits.values()),
        "objective": distance_objective + scenario.priority_coefficient * sum(weighted) / 60,
    }
    if solution.metrics is None:
        errors.append("Métricas ausentes")
    else:
        for label, actual in recomputed.items():
            reported = getattr(solution.metrics, label)
            if actual is None:
                if reported is not None:
                    errors.append(f"{label}: deveria ser ausente")
            elif reported is None:
                errors.append(f"{label}: valor ausente")
            else:
                equal(label, reported, actual)
    return Verification(valid=not errors, errors=errors,
                        checked_deliveries=len(deliveries), recomputed=recomputed)
