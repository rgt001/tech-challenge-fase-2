"""Execução sem Pygame da referência FIAP, preservando o comportamento original."""
from __future__ import annotations
import ast
import copy
import hashlib
import json
import math
import random
import time
from typing import List, Tuple
from .config import DATA_ROOT
from .domain import Delivery, Location, Scenario, Vehicle
from .evaluation import build_solution


def original_functions(seed: int):
    path = DATA_ROOT / "sources" / "fiap" / "genetic_algorithm.py"
    manifest = json.loads((DATA_ROOT / "sources" / "manifest.json").read_text(encoding="utf-8"))
    record = next(r for r in manifest["files"] if r["path"].endswith("fiap/genetic_algorithm.py"))
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError("Snapshot FIAP não corresponde ao hash preservado")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {"generate_random_population","calculate_distance","calculate_fitness","order_crossover","mutate"}
    definitions = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
    namespace = {"random":random.Random(seed),"math":math,"copy":copy,"List":List,"Tuple":Tuple}
    exec(compile(ast.Module(body=definitions,type_ignores=[]),"fiap_pinned_functions","exec"),namespace)
    points = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id == "default_problems" for t in n.targets))
    return namespace, points, record


def reference_scenario(n: int = 15) -> Scenario:
    _,problems,record = original_functions(42)
    points = problems[n]
    matrix = [[math.dist(a,b) for b in points] for a in points]
    return Scenario(id=f"fiap_tsp_{n}",description=f"TSP original FIAP, {n} cidades em coordenadas de tela",
        depot=Location(id="city_0",name="Cidade 0",x=points[0][0],y=points[0][1]),
        deliveries=[Delivery(id=f"city_{i}",name=f"Cidade {i}",x=p[0],y=p[1],load=1,service_s=0)
                    for i,p in enumerate(points[1:],1)],
        vehicles=[Vehicle(id="V1",capacity=n)], distance=matrix,
        duration_s=[[0.0]*n for _ in range(n)],distance_unit="benchmark_unit",load_unit="benchmark_unit",
        coordinates="cartesian",priority_coefficient=0,source={"kind":"FIAP_TSP_reference",
            "commit":record["commit"],"sha256":record["sha256"],"distance":"unrounded_Euclidean_screen_units"})


def solve_fiap_reference(scenario: Scenario, seed: int = 42, max_evaluations: int = 20_000):
    if len(scenario.vehicles) != 1 or scenario.priority_coefficient != 0:
        raise ValueError("Referência FIAP só é comparável ao TSP de distância com um veículo")
    points = [(scenario.depot.x,scenario.depot.y),*((d.x,d.y) for d in scenario.deliveries)]
    if len(set(points)) != len(points):
        raise ValueError("Referência original perde identidade de coordenadas repetidas")
    ns,_,record = original_functions(seed)
    rng = ns["random"]
    size = min(100,max_evaluations)
    if size < 2:
        raise ValueError("Orçamento da referência deve permitir ao menos dois indivíduos")
    population = ns["generate_random_population"](points,size)
    evaluations = 0
    best_route, best_cost = None, math.inf
    started = time.perf_counter()
    while evaluations+size <= max_evaluations:
        costs = [ns["calculate_fitness"](p) for p in population]
        evaluations += size
        ordered = sorted(zip(costs,population),key=lambda t:t[0])
        if ordered[0][0] < best_cost:
            best_cost,best_route = ordered[0]
        new = [ordered[0][1]]
        while len(new) < size:
            parent1,parent2 = rng.choices(population,weights=[1/max(c,1e-9) for c in costs],k=2)
            # Reprodução de tsp.py: crossover(parent1,parent1), bug mantido no comparador.
            child = ns["order_crossover"](parent1,parent1)
            child = ns["mutate"](child,0.5)
            new.append(child)
        population = new
    depot_position = best_route.index(points[0])
    rotated = best_route[depot_position+1:]+best_route[:depot_position]
    route = [points.index(point) for point in rotated]
    return build_solution(scenario,[route],"fiap_original",seed,{
        "elapsed_s":time.perf_counter()-started,"evaluations":evaluations,"population_size":size,
        "mutation_probability":0.5,"same_parent_crossover_preserved":True,
        "source_commit":record["commit"],"source_sha256":record["sha256"]})
