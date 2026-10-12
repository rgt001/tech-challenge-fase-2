"""Recomputa todas as matrizes sobre o snapshot; não usa o preparador de matrizes."""
import hashlib
import json
import math
import networkx as nx
import osmnx as ox
from rotas_medicas.config import DATA_ROOT,OUTPUT_ROOT
from rotas_medicas.storage import load_scenario,write_json,utc_now,canonical_hash

path=DATA_ROOT/"sources"/"osm"/"sao_paulo_drive.graphml.gz"
graph=ox.load_graphml(path)
graph_hash=hashlib.sha256(path.read_bytes()).hexdigest()
records=[]
for scenario_path in sorted((DATA_ROOT/"scenarios").glob("sp_*.json")):
    s=load_scenario(scenario_path)
    nodes=s.source["osm_nodes"]
    failures=[];checked=0
    if s.source["graph_sha256"]!=graph_hash:failures.append("graph hash mismatch")
    for i,origin in enumerate(nodes):
        times,paths=nx.single_source_dijkstra(graph,origin,weight="travel_time")
        for j,destination in enumerate(nodes):
            checked+=1
            if i==j:continue
            distance=0.0;geometry=[]
            for u,v in zip(paths[destination],paths[destination][1:]):
                edge=min(graph[u][v].values(),key=lambda e:e["travel_time"])
                distance+=edge["length"]
                coords=[list(p) for p in edge["geometry"].coords] if "geometry" in edge else [[graph.nodes[u]["x"],graph.nodes[u]["y"]],[graph.nodes[v]["x"],graph.nodes[v]["y"]]]
                start=[graph.nodes[u]["x"],graph.nodes[u]["y"]]
                if math.dist(coords[-1],start)<math.dist(coords[0],start):coords=list(reversed(coords))
                geometry.extend(coords if not geometry else coords[1:])
            if not math.isclose(distance,s.distance[i][j],rel_tol=1e-10,abs_tol=1e-6):failures.append(f"distance {i}:{j}")
            if not math.isclose(times[destination],s.duration_s[i][j],rel_tol=1e-10,abs_tol=1e-6):failures.append(f"duration {i}:{j}")
            if geometry!=s.path_geometry[f"{i}:{j}"]:failures.append(f"geometry {i}:{j}")
    records.append({"scenario":s.id,"scenario_hash":canonical_hash(s),"pairs_checked":checked,"failures":failures,"directed":graph.is_directed()})
    print(f"{s.id}: {checked} pares, {len(failures)} divergências",flush=True)
report={"status":"aprovado" if all(not r["failures"] for r in records) else "falhou","created_at":utc_now(),"graph_sha256":graph_hash,"scenarios":records,"method":"independent reconstruction using saved graph and directed Dijkstra paths"}
write_json(OUTPUT_ROOT/"validation"/"geography.json",report)
raise SystemExit(0 if report["status"]=="aprovado" else 1)
