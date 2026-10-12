"""Leitura das bases públicas respeitando as convenções originais."""
from __future__ import annotations
import hashlib
import math
from pathlib import Path
import re
from .domain import Delivery, Location, Scenario, Vehicle


def read_cvrplib(path: Path, optimum: float | None = None) -> Scenario:
    text = path.read_text(encoding="utf-8")
    headers, coords, demands, depot_ids = {}, {}, {}, []
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == "EOF":
            continue
        if line.endswith("_SECTION"):
            section = line
            continue
        if section is None:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
        elif section == "NODE_COORD_SECTION":
            node, x, y = line.split()
            coords[int(node)] = (float(x), float(y))
        elif section == "DEMAND_SECTION":
            node, demand = line.split()
            demands[int(node)] = float(demand)
        elif section == "DEPOT_SECTION" and int(line) != -1:
            depot_ids.append(int(line))
    if headers.get("EDGE_WEIGHT_TYPE") != "EUC_2D":
        raise ValueError("Leitor suporta EUC_2D; não substituir outras regras por distância comum")
    if len(depot_ids) != 1 or len(coords) != int(headers["DIMENSION"]):
        raise ValueError("Base incompleta ou múltiplos depósitos")
    name = headers["NAME"]
    k = int(re.search(r"-k(\d+)$", name).group(1))
    depot_id = depot_ids[0]
    order = [depot_id, *sorted(set(coords) - {depot_id})]
    points = [coords[node] for node in order]
    # TSPLIB nint(x)=floor(x+0.5), não round() de Python (empate bancário).
    matrix = [[float(math.floor(math.dist(a, b)+0.5)) for b in points] for a in points]
    depot = Location(id="depot", name="Depósito do benchmark", x=points[0][0], y=points[0][1])
    deliveries = [Delivery(id=f"node_{node}", name=f"Cliente {node}", x=coords[node][0],
                           y=coords[node][1], load=demands[node], service_s=0) for node in order[1:]]
    return Scenario(id=name, description=f"Benchmark CVRPLIB {name}, regras originais EUC_2D",
                    depot=depot, deliveries=deliveries,
                    vehicles=[Vehicle(id=f"V{i+1}", capacity=float(headers["CAPACITY"])) for i in range(k)],
                    distance=matrix, duration_s=[[0.0]*len(order) for _ in order],
                    coordinates="cartesian", distance_unit="benchmark_unit", load_unit="benchmark_unit",
                    priority_coefficient=0, known_optimum=optimum,
                    source={"kind": "CVRPLIB", "file": path.name,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "edge_weight_type": "EUC_2D", "duration": "not_applicable",
                            "url": "https://galgos.inf.puc-rio.br/cvrplib/en/instances"})


def make_euclidean_fixture(n: int = 5, k: int = 2, seed: int = 42) -> Scenario:
    import random
    rng = random.Random(seed)
    points = [(0.0, 0.0)] + [(float(rng.randint(1, 20)), float(rng.randint(1, 20))) for _ in range(n)]
    matrix = [[math.dist(a, b)*100 for b in points] for a in points]
    return Scenario(id=f"fixture_{n}_{k}_{seed}", description="Caso artificial para verificação independente",
                    depot=Location(id="depot", name="Depósito", x=0, y=0),
                    deliveries=[Delivery(id=f"D{i}", name=f"Entrega {i}", x=points[i][0], y=points[i][1],
                                         load=1, priority="critica" if i == 1 else "regular", service_s=60)
                                for i in range(1, n+1)],
                    vehicles=[Vehicle(id=f"V{i}", capacity=math.ceil(n/k)+1, max_distance=30_000)
                              for i in range(k)],
                    distance=matrix, duration_s=[[d/10 for d in row] for row in matrix],
                    coordinates="cartesian", split="fixture", source={"kind": "synthetic_fixture", "seed": seed})
