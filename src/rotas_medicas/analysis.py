"""Tabelas e gráficos derivados exclusivamente dos resultados registrados."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from .config import DATA_ROOT,OUTPUT_ROOT
from .storage import load_scenario,load_solution,write_json,utc_now
from .maps import export_map

LABELS={"pop80_mut10":"80 / 0,10","pop160_mut20":"160 / 0,20","pop240_mut30":"240 / 0,30"}


def make_analysis():
    folder=OUTPUT_ROOT/"figures"
    folder.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(OUTPUT_ROOT/"experiments"/"results.csv")
    selection=json.loads((OUTPUT_ROOT/"experiments"/"selection.json").read_text(encoding="utf-8"))["selected"]
    configs=list(LABELS)
    summaries=[]
    for keys,group in df.groupby(["scenario","algorithm","configuration"],sort=False):
        valid=group[group.status=="feasible"]
        summaries.append({"scenario":keys[0],"algorithm":keys[1],"configuration":keys[2],"runs":len(group),"feasible":len(valid),
            "objective_mean":float(valid.objective.mean()) if len(valid) else None,
            "objective_std":float(valid.objective.std(ddof=1)) if len(valid)>1 else 0,
            "objective_min":float(valid.objective.min()) if len(valid) else None,
            "objective_max":float(valid.objective.max()) if len(valid) else None,
            "distance_mean":float(valid.distance.mean()) if len(valid) else None,
            "critical_arrival_mean_min":float(valid.critical_arrival_mean_s.mean()/60) if valid.critical_arrival_mean_s.notna().any() else None,
            "elapsed_mean_s":float(group.elapsed_s.mean()),"gap_mean_percent":float(valid.gap_percent.mean()) if valid.gap_percent.notna().any() else None})
    figure_records=[]
    def save(fig,name,caption):
        path=folder/f"{name}.png"
        fig.savefig(path,dpi=170,bbox_inches="tight");plt.close(fig)
        figure_records.append({"name":name,"path":f"outputs/figures/{name}.png","caption":caption,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    fig,axes=plt.subplots(1,3,figsize=(12,4),layout="constrained")
    for ax,n in zip(axes,(12,30,60)):
        sub=df[df.scenario==f"sp_evaluation_{n}"]
        values=[sub[(sub.algorithm=="genetic")&(sub.configuration==c)].objective.dropna().tolist() for c in configs]
        ax.boxplot(values,tick_labels=[LABELS[c] for c in configs],showfliers=True)
        for i,data in enumerate(values,1):ax.scatter(np.full(len(data),i),data,s=13,alpha=.6,color="#1565c0")
        for algo,color,label in [("greedy","#e65100","Guloso"),("ortools","#00897b","OR-Tools")]:
            row=sub[sub.algorithm==algo]
            if len(row) and row.objective.notna().any():ax.axhline(row.objective.iloc[0],color=color,ls="--",label=label)
        ax.set_title(f"{n} entregas");ax.set_xlabel("População / mutação");ax.set_ylabel("J: km + prioridade × chegada");ax.grid(alpha=.2);ax.legend(fontsize=8)
    save(fig,"medical_objective","Cada ponto representa uma semente; as linhas são os comparadores. A dispersão e resultados piores são preservados. J combina distância e chegada ponderada; não é apenas quilômetros.")
    fig,axes=plt.subplots(1,3,figsize=(12,4),layout="constrained")
    for ax,name in zip(axes,("A-n32-k5","A-n54-k7","A-n80-k10")):
        sub=df[df.scenario==name]
        values=[sub[(sub.algorithm=="genetic")&(sub.configuration==c)].gap_percent.dropna().tolist() for c in configs]
        ax.boxplot(values,tick_labels=[LABELS[c] for c in configs])
        for i,data in enumerate(values,1):ax.scatter(np.full(len(data),i),data,s=13,alpha=.6,color="#1565c0")
        for algo,color,label in [("greedy","#e65100","Guloso"),("ortools","#00897b","OR-Tools")]:
            row=sub[sub.algorithm==algo]
            if len(row) and row.gap_percent.notna().any():ax.axhline(row.gap_percent.iloc[0],color=color,ls="--",label=label)
        ax.axhline(0,color="black",lw=.8);ax.set_title(name);ax.set_ylabel("Distância ao ótimo publicado (%)");ax.set_xlabel("População / mutação");ax.legend(fontsize=8);ax.grid(alpha=.2)
    save(fig,"benchmark_gap","O gap usa o custo publicado e a distância EUC_2D original. Não se convertem essas unidades em quilômetros nem se incluem prioridades médicas.")
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout="constrained")
    for algo,label,color in [("greedy","Guloso","#e65100"),("ortools","OR-Tools","#00897b"),("genetic","Genético selecionado","#1565c0")]:
        med=df[df.scenario.isin([f"sp_evaluation_{n}" for n in (12,30,60)])&(df.algorithm==algo)]
        if algo=="genetic":med=med[med.configuration==selection]
        grouped=med.groupby("scenario")
        times=[grouped.get_group(f"sp_evaluation_{n}").elapsed_s.mean() for n in (12,30,60)]
        crit=[grouped.get_group(f"sp_evaluation_{n}").critical_arrival_mean_s.mean()/60 for n in (12,30,60)]
        axes[0].plot([12,30,60],times,"o-",label=label,color=color)
        axes[1].plot([12,30,60],crit,"o-",label=label,color=color)
    axes[0].set_ylabel("Tempo de execução (s)");axes[1].set_ylabel("Chegada média das críticas (min)")
    for ax in axes:ax.set_xlabel("Número de entregas");ax.grid(alpha=.2);ax.legend(fontsize=8)
    save(fig,"runtime_critical","O GA tem teto de fitness e tentativas; OR-Tools tem cinco segundos. As curvas de tempo não demonstram igualdade de orçamento. Chegadas são minutos após a saída de cada veículo.")
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout="constrained")
    for config,color in zip(configs,("#1565c0","#e65100","#00897b")):
        for n,ax in zip((30,60),axes):
            solution=load_solution(OUTPUT_ROOT/"experiments"/"runs"/f"sp_evaluation_{n}"/f"genetic_{config}_42.json")
            history=solution.metadata["history"]
            if history:ax.step([h["evaluations"] for h in history],[h["best_objective"] for h in history],where="post",label=LABELS[config],color=color)
            else:ax.scatter([solution.metadata["evaluations"]],[solution.metrics.objective],label=f"{LABELS[config]}: encerrou na inicialização",color=color,s=25)
            ax.set_title(f"{n} entregas, semente 42")
    for ax in axes:ax.set_xlabel("Chamadas de fitness, incluindo reparação");ax.set_ylabel("Melhor J viável observado");ax.grid(alpha=.2);ax.legend(fontsize=7)
    save(fig,"convergence","A reparação pode consumir grande parte do orçamento. Um ponto isolado indica interrupção antes de completar gerações; isso não é uma curva de convergência.")
    sensitivity=df[df.scenario.str.startswith("sp_sensitivity_")].copy()
    coefficients=[]
    for name in sensitivity.scenario:coefficients.append(load_scenario(DATA_ROOT/"scenarios"/f"{name}.json").priority_coefficient)
    sensitivity["coefficient"]=coefficients;sensitivity=sensitivity.sort_values("coefficient")
    fig,ax=plt.subplots(figsize=(7,4),layout="constrained");right=ax.twinx()
    ax.plot(sensitivity.coefficient,sensitivity.distance/1000,"o-",color="#1565c0",label="Distância")
    right.plot(sensitivity.coefficient,sensitivity.critical_arrival_mean_s/60,"s--",color="#c62828",label="Chegada crítica")
    ax.set_xlabel("Coeficiente de prioridade (km/min)");ax.set_ylabel("Distância (km)",color="#1565c0");right.set_ylabel("Chegada crítica média (min)",color="#c62828");ax.grid(alpha=.2)
    save(fig,"priority_sensitivity","Sensibilidade exploratória de uma semente e um cenário de 30 entregas. Não estima causalidade nem estabelece pesos clínicos; os valores são premissas de modelagem.")
    weekly=df[df.scenario.str.startswith("sp_day_")].sort_values("scenario")
    fig,ax=plt.subplots(figsize=(8,4),layout="constrained")
    ax.bar(range(1,8),weekly.distance/1000,color="#1565c0");ax.set_xticks(range(1,8));ax.set_xlabel("Dia simulado");ax.set_ylabel("Distância total (km)");ax.grid(axis="y",alpha=.2)
    save(fig,"weekly_distance","Sete cenários fictícios de 12 entregas. A variação resulta das localizações, cargas e prioridades sorteadas; não representa histórico operacional de hospitais.")
    fiap=df[df.scenario=="fiap_tsp_15"]
    fig,ax=plt.subplots(figsize=(8,4),layout="constrained")
    names=[("fiap_original","reference","FIAP original"),("genetic",selection,"GA selecionado"),("ortools","baseline","OR-Tools"),("greedy","baseline","Guloso")]
    values=[fiap[(fiap.algorithm==a)&(fiap.configuration==c)].distance.dropna().tolist() for a,c,_ in names]
    ax.boxplot(values,tick_labels=[label for _,_,label in names]);ax.set_ylabel("Comprimento euclidiano original");ax.grid(axis="y",alpha=.2)
    save(fig,"fiap_tsp","Comparação restrita ao TSP de 15 pontos, com objetivo euclidiano e sem restrições hospitalares. A reprodução preserva o crossover com o mesmo pai da base original.")
    sample=load_solution(OUTPUT_ROOT/"experiments"/"runs"/"sp_evaluation_60"/f"genetic_{selection}_42.json")
    scenario=load_scenario(DATA_ROOT/"scenarios"/"sp_evaluation_60.json")
    capacities={v.id:v.capacity for v in scenario.vehicles}
    fig,ax=plt.subplots(figsize=(7,4),layout="constrained")
    ax.bar([r.vehicle_id for r in sample.routes],[100*r.initial_load/capacities[r.vehicle_id] for r in sample.routes],color="#1565c0")
    ax.axhline(100,color="#c62828",ls="--");ax.set_ylim(0,110);ax.set_ylabel("Utilização da capacidade (%)");ax.set_title("60 entregas, configuração selecionada, semente 42");ax.grid(axis="y",alpha=.2)
    save(fig,"fleet_capacity","Carga inicial de cada veículo em relação à capacidade. A carga diminui a cada entrega; não há coleta nem reposição durante a rota.")
    map_records=[]
    for n in (12,30,60):
        scenario=load_scenario(DATA_ROOT/"scenarios"/f"sp_evaluation_{n}.json")
        solution=load_solution(OUTPUT_ROOT/"experiments"/"runs"/scenario.id/f"genetic_{selection}_42.json")
        html,png=export_map(scenario,solution)
        map_records.append({"scenario":scenario.id,"html":f"outputs/maps/{html.name}","png":f"outputs/maps/{png.name}","solution_id":solution.id})
    report={"created_at":utc_now(),"selected":selection,"runs":len(df),"summaries":summaries,
            "figures":figure_records,"maps":map_records,"results_sha256":hashlib.sha256((OUTPUT_ROOT/"experiments"/"results.csv").read_bytes()).hexdigest(),
            "weekly_distance_km":float(weekly.distance.sum()/1000),"weekly_deliveries":sum(load_solution(OUTPUT_ROOT/"experiments"/"runs"/f"sp_day_{i}"/f"genetic_{selection}_42.json").metrics.deliveries_served for i in range(1,8)),
            "termination_counts":df[df.algorithm=="genetic"].termination.value_counts().to_dict()}
    write_json(OUTPUT_ROOT/"analysis"/"summary.json",report)
    pd.DataFrame(summaries).to_csv(OUTPUT_ROOT/"analysis"/"summary.csv",index=False,encoding="utf-8")
    return report
