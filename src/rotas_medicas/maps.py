"""Mapas vetoriais autossuficientes: ruas, percursos e JavaScript incluídos localmente."""
from __future__ import annotations
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import plotly.graph_objects as go
from .config import DATA_ROOT,OUTPUT_ROOT
from .storage import canonical_hash,write_json,utc_now
from .verification import verify_solution

COLORS=["#1565c0","#e65100","#00897b","#8e24aa","#c62828","#546e7a","#6d4c41","#3949ab","#558b2f","#d81b60"]


def route_segments(scenario,solution):
    certificate=verify_solution(scenario,solution)
    if solution.status!="feasible" or not certificate.valid:
        raise ValueError("Mapa operacional exige solução viável certificada")
    nodes=[scenario.depot,*scenario.deliveries]
    indices={n.id:i for i,n in enumerate(nodes)}
    result=[]
    for ri,route in enumerate(solution.routes):
        visits=[0,*[indices[p.delivery_id] for p in route.stops],0]
        segments=[]
        for a,b in zip(visits,visits[1:]):
            if a==b:continue
            if scenario.coordinates=="wgs84":
                points=scenario.path_geometry.get(f"{a}:{b}")
                if not points: raise ValueError(f"Geometria rodoviária ausente: {a}:{b}")
            else:points=[[nodes[a].x,nodes[a].y],[nodes[b].x,nodes[b].y]]
            segments.append(points)
        result.append((route,segments,COLORS[ri%len(COLORS)]))
    return result


def street_segments(data_root=None):
    path=(data_root or DATA_ROOT)/"sources"/"osm"/"streets.geojson"
    streets=json.loads(path.read_text(encoding="utf-8"))
    segments=[]
    for f in streets["features"]:
        g=f["geometry"]
        if g["type"]=="LineString":segments.append(g["coordinates"])
        elif g["type"]=="MultiLineString":segments.extend(g["coordinates"])
    return segments


def export_map(scenario,solution,output_dir=None,data_root=None):
    folder=output_dir or OUTPUT_ROOT/"maps"
    folder.mkdir(parents=True,exist_ok=True)
    segments=route_segments(scenario,solution)
    fig=go.Figure()
    streets=street_segments(data_root) if scenario.coordinates=="wgs84" else []
    if streets:
        x,y=[],[]
        for points in streets:
            x.extend([p[0] for p in points]+[None]);y.extend([p[1] for p in points]+[None])
        fig.add_trace(go.Scatter(x=x,y=y,mode="lines",line={"color":"#d1d6db","width":1},hoverinfo="skip",name="Ruas OSM",showlegend=False))
    for route,paths,color in segments:
        x,y=[],[]
        for points in paths:
            x.extend([p[0] for p in points]+[None]);y.extend([p[1] for p in points]+[None])
        if x:fig.add_trace(go.Scatter(x=x,y=y,mode="lines",line={"color":color,"width":3},name=route.vehicle_id))
    colors={"regular":"#1565c0","urgente":"#f57c00","critica":"#b71c1c"}
    fig.add_trace(go.Scatter(x=[d.x for d in scenario.deliveries],y=[d.y for d in scenario.deliveries],mode="markers",
        marker={"size":10,"color":[colors[d.priority.value] for d in scenario.deliveries],"line":{"color":"white","width":1}},
        text=[f"{d.id}: {d.name}<br>{d.priority.value}; carga {d.load:g} {scenario.load_unit}" for d in scenario.deliveries],
        hovertemplate="%{text}<extra></extra>",name="Entregas"))
    fig.add_trace(go.Scatter(x=[scenario.depot.x],y=[scenario.depot.y],mode="markers",marker={"size":16,"symbol":"star","color":"#172b4d"},name="Depósito"))
    ratio=1.09 if scenario.coordinates=="wgs84" else 1
    fig.update_layout(title={"text":f"Rotas certificadas — {scenario.id}<br><sup>Dados fictícios; retorno ao depósito incluído. © OpenStreetMap contributors, ODbL 1.0</sup>","font":{"size":19}},
        template="plotly_white",height=800,margin={"l":30,"r":30,"t":85,"b":50},
        xaxis={"title":"Longitude" if streets else "x","showgrid":False},
        yaxis={"title":"Latitude" if streets else "y","scaleanchor":"x","scaleratio":ratio,"showgrid":False},legend={"orientation":"h"})
    html=folder/f"{scenario.id}.html"
    fig.write_html(html,include_plotlyjs=True,full_html=True,config={"responsive":True,"displaylogo":False})
    static=folder/f"{scenario.id}.png"
    plot,ax=plt.subplots(figsize=(9,8))
    plot.subplots_adjust(left=.11,right=.98,top=.93,bottom=.12)
    if streets:ax.add_collection(LineCollection(streets,colors="#dce1e5",linewidths=.4,zorder=0))
    for route,paths,color in segments:
        if paths:ax.add_collection(LineCollection(paths,colors=color,linewidths=2,label=route.vehicle_id,zorder=2))
    ax.scatter([d.x for d in scenario.deliveries],[d.y for d in scenario.deliveries],c=[colors[d.priority.value] for d in scenario.deliveries],s=30,edgecolor="white",linewidth=.5,zorder=3)
    ax.scatter([scenario.depot.x],[scenario.depot.y],marker="*",s=180,c="#172b4d",label="Depósito",zorder=4)
    ax.autoscale();ax.set_aspect(ratio)
    # Centraliza a região percorrida, mantendo uma margem para contexto urbano.
    xs=[n.x for n in [scenario.depot,*scenario.deliveries]];ys=[n.y for n in [scenario.depot,*scenario.deliveries]]
    if xs and max(xs)>min(xs):ax.set_xlim(min(xs)-.005 if streets else min(xs)-10,max(xs)+.005 if streets else max(xs)+10)
    if ys and max(ys)>min(ys):ax.set_ylim(min(ys)-.005 if streets else min(ys)-10,max(ys)+.005 if streets else max(ys)+10)
    ax.set_title(f"{scenario.id}: {solution.metrics.deliveries_served} entregas, {solution.metrics.vehicles_used} veículos",fontsize=12)
    ax.set_xlabel("Longitude" if streets else "x");ax.set_ylabel("Latitude" if streets else "y")
    ax.legend(loc="upper left",fontsize=8)
    plot.text(.02,.012,"© OpenStreetMap contributors, ODbL 1.0 | Tempos estimados, sem trânsito em tempo real",fontsize=8)
    plot.savefig(static,dpi=180,bbox_inches="tight");plt.close(plot)
    write_json(folder/f"{scenario.id}.manifest.json",{"scenario_hash":canonical_hash(scenario),"solution_id":solution.id,
        "html":html.name,"png":static.name,"offline":True,"geometry":"saved directed OSM paths" if streets else "original Cartesian benchmark coordinates","created_at":utc_now()})
    return html,static
