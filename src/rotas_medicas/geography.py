"""Malha viária fixada, caminhos direcionados e cenário hospitalar fictício."""
from __future__ import annotations
from datetime import date, timedelta
import hashlib
import math
from pathlib import Path
import random
import networkx as nx
from .config import DATA_ROOT
from .domain import Delivery, Location, Scenario, Vehicle
from .storage import write_json, utc_now

BBOX = (-46.69, -23.59, -46.61, -23.52)  # oeste, sul, leste, norte
ATTRIBUTION = "© OpenStreetMap contributors, ODbL 1.0"


def prepare_graph():
    import osmnx as ox
    directory = DATA_ROOT / "sources" / "osm"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "sao_paulo_drive.graphml.gz"
    ox.settings.cache_folder = str(directory / "cache")
    ox.settings.requests_timeout = 90
    ox.settings.log_console = True
    if path.exists():
        graph = ox.load_graphml(path)
        return graph
    graph = ox.graph_from_bbox(BBOX, network_type="drive", simplify=True, retain_all=True)
    # Uma componente fortemente conexa garante ida e volta entre os pontos escolhidos.
    largest = max(nx.strongly_connected_components(graph), key=len)
    original_nodes = len(graph)
    graph = graph.subgraph(largest).copy()
    graph = ox.routing.add_edge_speeds(graph, fallback=30)
    graph = ox.routing.add_edge_travel_times(graph)
    ox.save_graphml(graph, path)
    write_json(directory / "manifest.json", {
        "retrieved_at": utc_now(), "bbox": list(BBOX), "network_type": "drive",
        "original_nodes": original_nodes, "retained_nodes": len(graph), "edges": graph.number_of_edges(),
        "component": "largest_strongly_connected", "attribution": ATTRIBUTION,
        "graph_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "speed_model": "OSM maxspeed or mean by highway type; fallback 30 km/h",
        "travel_time": "free_flow_estimate_not_live_traffic", "path_weight": "travel_time",
        "url": "https://www.openstreetmap.org/", "prepared_with_osmnx": ox.__version__,
        "limitations": ["Trânsito, restrições de conversão e horários de operação não são modelados"]})
    return graph


def edge_coordinates(graph, u, v, edge):
    if "geometry" in edge:
        coordinates = [list(c) for c in edge["geometry"].coords]
        start = (graph.nodes[u]["x"], graph.nodes[u]["y"])
        if math.dist(coordinates[-1], start) < math.dist(coordinates[0], start):
            coordinates.reverse()
        return coordinates
    return [[graph.nodes[u]["x"], graph.nodes[u]["y"]], [graph.nodes[v]["x"], graph.nodes[v]["y"]]]


def route_matrices(graph, osm_nodes: list[int]):
    n = len(osm_nodes)
    distances, durations = [[0.0]*n for _ in range(n)], [[0.0]*n for _ in range(n)]
    geometry = {}
    for i, origin in enumerate(osm_nodes):
        _, paths = nx.single_source_dijkstra(graph, origin, weight="travel_time")
        for j, destination in enumerate(osm_nodes):
            if i == j:
                geometry[f"{i}:{j}"] = [[graph.nodes[origin]["x"], graph.nodes[origin]["y"]]]
                continue
            if destination not in paths:
                raise ValueError("Ponto fora da componente viária alcançável")
            distance = duration = 0.0
            points = []
            path = paths[destination]
            for u, v in zip(path, path[1:]):
                edge = min(graph[u][v].values(), key=lambda e: e["travel_time"])
                distance += edge["length"]
                duration += edge["travel_time"]
                coords = edge_coordinates(graph, u, v, edge)
                points.extend(coords if not points else coords[1:])
            distances[i][j], durations[i][j] = distance, duration
            geometry[f"{i}:{j}"] = points
    return distances, durations, geometry


def medical_scenario(graph, n: int, k: int, seed: int, split: str = "evaluation",
                     scenario_id: str | None = None, day: date | None = None) -> Scenario:
    rng = random.Random(seed)
    # Seleção determinística por IDs ordenados; não consulta hospitais/pacientes reais.
    available = sorted(graph.nodes)
    depot_node = min(available, key=lambda node: (graph.nodes[node]["x"]+46.65)**2 +
                                               (graph.nodes[node]["y"]+23.55)**2)
    selected = rng.sample([node for node in available if node != depot_node], n)
    osm_nodes = [depot_node, *selected]
    distances, durations, geometries = route_matrices(graph, osm_nodes)
    deliveries = []
    for i, node in enumerate(selected, 1):
        priority = rng.choices(["regular","urgente","critica"], weights=[55,30,15])[0]
        deliveries.append(Delivery(id=f"ENT_{i:03d}", name=f"Unidade simulada {i:03d}",
                                  x=graph.nodes[node]["x"], y=graph.nodes[node]["y"],
                                  load=rng.randint(2,10), priority=priority,
                                  service_s=rng.choice([180,300,420])))
    # Folga nominal declarada, não determinada por resultados da otimização.
    capacity = math.ceil(sum(d.load for d in deliveries)/k*1.35)
    manifest_path = DATA_ROOT / "sources" / "osm" / "manifest.json"
    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenario = Scenario(id=scenario_id or f"sp_{split}_{n}",
        description=f"Distribuição hospitalar fictícia em São Paulo, {n} pedidos e {k} veículos",
        depot=Location(id="DEPOT", name="Centro de distribuição simulado",
                       x=graph.nodes[depot_node]["x"], y=graph.nodes[depot_node]["y"]),
        deliveries=deliveries, vehicles=[Vehicle(id=f"VEI_{i+1:02d}", capacity=capacity,
                                               max_distance=50_000) for i in range(k)],
        distance=distances, duration_s=durations, path_geometry=geometries,
        day=day, split=split, source={"kind": "simulated_medical_on_real_osm", "seed": seed,
            "osm_nodes": osm_nodes, "graph_sha256": manifest["graph_sha256"],
            "source": "OpenStreetMap", "attribution": ATTRIBUTION,
            "geography_retrieved_at": manifest["retrieved_at"],
            "capacity_premise": "ceil(total_load / vehicle_count * 1.35)",
            "range_premise_m": 50_000, "time_model": manifest["travel_time"]})
    return scenario


def prepare_medical_data():
    graph = prepare_graph()
    paths = []
    for split, base_seed in (("development", 617), ("evaluation", 2026)):
        for n, k in ((12,2),(30,3),(60,5)):
            scenario = medical_scenario(graph,n,k,base_seed+n,split)
            path = DATA_ROOT / "scenarios" / f"{scenario.id}.json"
            write_json(path,scenario)
            paths.append(path)
            print(f"Cenário salvo: {scenario.id}", flush=True)
    for i in range(7):
        day = date(2026,10,5)+timedelta(days=i)
        scenario = medical_scenario(graph,12,2,5000+i,"evaluation",f"sp_day_{i+1}",day)
        path = DATA_ROOT / "scenarios" / f"{scenario.id}.json"
        write_json(path,scenario)
        paths.append(path)
        print(f"Dia simulado salvo: {scenario.id}", flush=True)
    # Fundo vetorial do mapa, autossuficiente e com atribuição.
    features = []
    for u,v,key,edge in graph.edges(keys=True,data=True):
        features.append({"type":"Feature","geometry":{"type":"LineString",
                        "coordinates":edge_coordinates(graph,u,v,edge)},
                         "properties":{"u":u,"v":v,"key":key,"name":edge.get("name","")}})
    write_json(DATA_ROOT / "sources" / "osm" / "streets.geojson",
               {"type":"FeatureCollection","attribution":ATTRIBUTION,"features":features})
    return paths
