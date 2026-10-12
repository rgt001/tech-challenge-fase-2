"""Comparadores guloso e OR-Tools, sempre certificados antes da saída."""
from __future__ import annotations
import math
import time
from .domain import Scenario, Solution
from .evaluation import Evaluator, build_solution, failure_solution, infeasibility_proofs


def _route_violation(ev: Evaluator, route: list[int], vehicle_index: int) -> float:
    distance, _, load, _ = ev.route_values(route, vehicle_index)
    if not math.isfinite(distance):
        return math.inf
    vehicle = ev.scenario.vehicles[vehicle_index]
    violation = (load-vehicle.capacity)/vehicle.capacity if load > vehicle.capacity+1e-8 else 0
    if vehicle.max_distance is not None:
        if distance > vehicle.max_distance+1e-8:
            violation += (distance-vehicle.max_distance)/vehicle.max_distance
    return violation


def repair_routes(ev: Evaluator, routes: list[list[int]], max_moves: int = 4) -> list[list[int]]:
    """Realoca e, se necessário, troca pedidos. Preserva todas as visitas."""
    result = [list(r) for r in routes]
    for _ in range(max_moves):
        current = ev.score(result)
        if current.feasible or current.structural_errors:
            break
        best_key = current.key
        best_change = None
        for source in range(ev.k):
            if _route_violation(ev, result[source], source) == 0:
                continue
            for pos, node in enumerate(result[source]):
                reduced = result[source][:pos]+result[source][pos+1:]
                for dest in range(ev.k):
                    if source == dest:
                        continue
                    # Inserções são avaliadas por distância/duração reais, inclusive retorno.
                    for insert in range(len(result[dest])+1):
                        candidate = list(result)
                        candidate[source] = reduced
                        candidate[dest] = result[dest][:insert]+[node]+result[dest][insert:]
                        key = ev.score(candidate).key
                        if key < best_key:
                            best_key, best_change = key, candidate
                    if best_change is None:
                        for dest_pos, other in enumerate(result[dest]):
                            candidate = [list(r) for r in result]
                            candidate[source][pos], candidate[dest][dest_pos] = other, node
                            key = ev.score(candidate).key
                            if key < best_key:
                                best_key, best_change = key, candidate
        if best_change is None:
            break
        result = best_change
    return result


def greedy_routes(ev: Evaluator) -> list[list[int]]:
    orders = [
        sorted(range(1, ev.n+1), key=lambda n: (-ev.weights[n],
               ev.dist[0][n] if ev.dist[0][n] is not None else math.inf, -ev.loads[n])),
        sorted(range(1, ev.n+1), key=lambda n: (-ev.loads[n], -ev.weights[n], n)),
        sorted(range(1, ev.n+1), key=lambda n: (ev.dist[0][n] if ev.dist[0][n] is not None else math.inf, n)),
    ]
    candidates = []
    for order in orders:
        routes = [[] for _ in range(ev.k)]
        for node in order:
            best = None
            best_key = None
            for vehicle in range(ev.k):
                for position in range(len(routes[vehicle])+1):
                    modified = routes[vehicle][:position]+[node]+routes[vehicle][position:]
                    violation = _route_violation(ev, modified, vehicle)
                    distance, _, _, weighted = ev.route_values(modified, vehicle)
                    old_distance, _, _, old_weighted = ev.route_values(routes[vehicle], vehicle)
                    factor = 1000 if ev.scenario.distance_unit == "m" else 1
                    increment = (distance-old_distance)/factor + ev.scenario.priority_coefficient*(weighted-old_weighted)/60
                    key = (violation, increment, vehicle, position)
                    if best_key is None or key < best_key:
                        best_key, best = key, (vehicle, modified)
            routes[best[0]] = best[1]
        routes = repair_routes(ev, routes, max_moves=12)
        candidates.append(routes)
    return min(candidates, key=lambda r: ev.score(r).key)


def solve_greedy(scenario: Scenario) -> Solution:
    started = time.perf_counter()
    proofs = infeasibility_proofs(scenario)
    if proofs:
        return failure_solution(scenario, "greedy", proofs, proven=True)
    ev = Evaluator(scenario)
    routes = greedy_routes(ev)
    return build_solution(scenario, routes, "greedy", metadata={"elapsed_s": time.perf_counter()-started,
                          "construction": "best_of_priority_proximity_and_descending_load_insertions",
                          "repair_max_moves": 12})


def solve_ortools(scenario: Scenario, seconds: float = 5) -> Solution:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Orçamento de tempo deve ser positivo e finito")
    started = time.perf_counter()
    proofs = infeasibility_proofs(scenario)
    if proofs:
        return failure_solution(scenario, "ortools", proofs, proven=True)
    n, k = len(scenario.node_ids), len(scenario.vehicles)
    manager = pywrapcp.RoutingIndexManager(n, k, 0)
    routing = pywrapcp.RoutingModel(manager)
    ev = Evaluator(scenario)
    unreachable = 10**12
    cost_factor = 6_000_000

    def distance_cost(a, b):
        value = scenario.distance[manager.IndexToNode(a)][manager.IndexToNode(b)]
        if value is None:
            return unreachable
        unit = 1000 if scenario.distance_unit == "m" else 1
        return int(round(value/unit*cost_factor))

    cost_cb = routing.RegisterTransitCallback(distance_cost)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_cb)
    load_cb = routing.RegisterUnaryTransitCallback(
        lambda a: int(math.ceil(ev.loads[manager.IndexToNode(a)]*1000-1e-9)))
    routing.AddDimensionWithVehicleCapacity(load_cb, 0,
        [int(math.floor(v.capacity*1000+1e-9)) for v in scenario.vehicles], True, "Capacity")

    def distance_limit(a, b):
        value = scenario.distance[manager.IndexToNode(a)][manager.IndexToNode(b)]
        return unreachable if value is None else int(math.ceil(value*1000-1e-9))

    dist_cb = routing.RegisterTransitCallback(distance_limit)
    all_values = [x for row in scenario.distance for x in row if x is not None]
    unconstrained = int(math.ceil(max(all_values, default=0)*max(n, 1)*1000+1))
    routing.AddDimensionWithVehicleCapacity(dist_cb, 0,
        [int(math.floor(v.max_distance*1000+1e-9)) if v.max_distance is not None else unconstrained
         for v in scenario.vehicles], True, "Distance")

    def time_transit(a, b):
        i, j = manager.IndexToNode(a), manager.IndexToNode(b)
        value = scenario.duration_s[i][j]
        return unreachable if value is None else int(round((value+ev.services[i])*1000))

    time_cb = routing.RegisterTransitCallback(time_transit)
    max_time = max([x for row in scenario.duration_s for x in row if x is not None], default=0)
    horizon = int(math.ceil((max_time+max(ev.services, default=0))*max(n, 1)*1000+1))
    routing.AddDimension(time_cb, 0, horizon, True, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")
    for node in range(1, n):
        penalty = int(round(scenario.priority_coefficient*ev.weights[node]*cost_factor/60/1000))
        if penalty:
            time_dimension.SetCumulVarSoftUpperBound(manager.NodeToIndex(node), 0, penalty)
    # Remove arcos ausentes; custo grande sozinho não é uma restrição rígida.
    for index in range(routing.Size()):
        i = manager.IndexToNode(index)
        for target in range(routing.Size()+k):
            if routing.IsStart(target):
                continue
            j = manager.IndexToNode(target)
            if scenario.distance[i][j] is None:
                routing.NextVar(index).RemoveValue(target)
    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    parameters.time_limit.FromMilliseconds(max(1, int(seconds*1000)))
    parameters.log_search = False
    assignment = routing.SolveWithParameters(parameters)
    metadata = {"elapsed_s": time.perf_counter()-started, "time_budget_s": seconds,
                "routing_status": int(routing.status()), "distance_precision": 0.001,
                "load_precision": 0.001, "time_precision_s": 0.001,
                "priority_penalty_rounding": "integer penalty per millisecond"}
    if assignment is None:
        return failure_solution(scenario, "ortools", ["Busca não encontrou solução viável no orçamento"], **metadata)
    routes = []
    for v in range(k):
        index = routing.Start(v)
        route = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node:
                route.append(node)
            index = assignment.Value(routing.NextVar(index))
        routes.append(route)
    return build_solution(scenario, routes, "ortools", metadata=metadata)
