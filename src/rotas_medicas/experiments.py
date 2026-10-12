"""Experimentos com parâmetros fixados, checkpoint por execução e proveniência."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import statistics
import time
from .baselines import solve_greedy, solve_ortools
from .config import DATA_ROOT, OUTPUT_ROOT
from .domain import GAConfig, Scenario
from .fiap_reference import reference_scenario, solve_fiap_reference
from .genetic import solve_genetic
from .storage import canonical_hash, load_scenario, load_solution, write_json, utc_now
from .verification import verify_solution

SEEDS = [42,73,101,127,151,181,211,241,271,307]
CONFIGURATIONS = [("pop80_mut10",80,0.10),("pop160_mut20",160,0.20),("pop240_mut30",240,0.30)]


def implementation_hash():
    root = Path(__file__).parent
    names = ["domain.py","evaluation.py","verification.py","genetic.py","baselines.py","fiap_reference.py"]
    return hashlib.sha256(b"".join((root/name).read_bytes() for name in names)).hexdigest()


def run_one(scenario: Scenario, algorithm: str, config_name: str, seed: int,
            population=160, mutation=0.2, evaluations=20_000, ortools_seconds=5):
    path = OUTPUT_ROOT / "experiments" / "runs" / scenario.id / f"{algorithm}_{config_name}_{seed}.json"
    fingerprint = {"scenario_hash":canonical_hash(scenario),"implementation_hash":implementation_hash(),
        "algorithm":algorithm,"configuration":config_name,"seed":seed,"population":population,
        "mutation":mutation,"evaluations":evaluations,"ortools_seconds":ortools_seconds}
    if path.exists():
        saved = load_solution(path)
        if saved.metadata.get("experiment_fingerprint") == fingerprint:
            if saved.status != "feasible" or verify_solution(scenario,saved).valid:
                return saved
    if algorithm == "genetic":
        config = GAConfig(population_size=population,mutation_probability=mutation,
                          max_evaluations=evaluations,seed=seed)
        solution = solve_genetic(scenario,config)
    elif algorithm == "greedy": solution = solve_greedy(scenario)
    elif algorithm == "ortools": solution = solve_ortools(scenario,ortools_seconds)
    elif algorithm == "fiap_original": solution = solve_fiap_reference(scenario,seed,evaluations)
    else: raise ValueError("Algoritmo desconhecido")
    solution.metadata["experiment_fingerprint"] = fingerprint
    solution.metadata["executed_at"] = utc_now()
    write_json(path,solution)
    value = round(solution.metrics.objective,4) if solution.metrics else solution.status
    print(f"{scenario.id} | {algorithm} | {config_name} | seed {seed} | {value} | "
          f"{solution.metadata.get('elapsed_s',0):.2f}s",flush=True)
    return solution


def table_row(scenario,solution):
    metric = solution.metrics
    return {"scenario":scenario.id,"split":scenario.split,"algorithm":solution.algorithm,
        "configuration":solution.metadata["experiment_fingerprint"]["configuration"],"seed":solution.seed,
        "status":solution.status,"objective":metric.objective if metric else None,
        "distance":metric.total_distance if metric else None,"distance_unit":scenario.distance_unit,
        "critical_arrival_mean_s":metric.critical_arrival_mean_s if metric else None,
        "vehicles_used":metric.vehicles_used if metric else None,
        "elapsed_s":solution.metadata.get("elapsed_s"),"evaluations":solution.metadata.get("evaluations"),
        "unique_fitness_evaluations":solution.metadata.get("unique_fitness_evaluations"),
        "termination":solution.metadata.get("termination"),"solution_id":solution.id,
        "scenario_hash":solution.scenario_hash,"implementation_hash":implementation_hash(),
        "known_optimum":scenario.known_optimum,
        "gap_percent":100*(metric.total_distance/scenario.known_optimum-1)
            if metric and scenario.known_optimum else None}


def run_experiments(full: bool = True):
    import pandas as pd
    budget = 20_000 if full else 1000
    seeds = SEEDS if full else SEEDS[:1]
    rows = []
    development_scores = {name:[] for name,_,_ in CONFIGURATIONS}
    for n in (12,30,60):
        scenario = load_scenario(DATA_ROOT/"scenarios"/f"sp_development_{n}.json")
        greedy = run_one(scenario,"greedy","baseline",0,evaluations=budget)
        for name,population,mutation in CONFIGURATIONS:
            for seed in ([11,23,37] if full else [11]):
                result = run_one(scenario,"genetic",name,seed,population,mutation,budget)
                rows.append(table_row(scenario,result))
                if result.metrics and greedy.metrics:
                    development_scores[name].append(result.metrics.objective/greedy.metrics.objective)
    # Escolha usa somente desenvolvimento e recebe seu próprio registro.
    eligible = {name:statistics.mean(values) for name,values in development_scores.items()
                if len(values) == (9 if full else 3)}
    if not eligible:
        raise RuntimeError("Nenhuma configuração completou os cenários de desenvolvimento")
    chosen_name = min(eligible,key=eligible.get)
    chosen = next(c for c in CONFIGURATIONS if c[0] == chosen_name)
    write_json(OUTPUT_ROOT/"experiments"/"selection.json",{
        "criterion":"mean GA/greedy objective ratio on development scenarios only",
        "development_scores":development_scores,"mean_ratios":eligible,"selected":chosen_name,
        "split":"development","profile":"full" if full else "quick",
        "implementation_hash":implementation_hash(),"executed_at":utc_now()})
    scenarios = [load_scenario(DATA_ROOT/"scenarios"/f"{name}.json") for name in
                 ["sp_evaluation_12","sp_evaluation_30","sp_evaluation_60",
                  "A-n32-k5","A-n54-k7","A-n80-k10"]]
    fiap = reference_scenario(15)
    write_json(DATA_ROOT/"scenarios"/f"{fiap.id}.json",fiap)
    scenarios.append(fiap)
    for scenario in scenarios:
        for algorithm in ("greedy","ortools"):
            result = run_one(scenario,algorithm,"baseline",0,evaluations=budget,ortools_seconds=5 if full else 0.5)
            rows.append(table_row(scenario,result))
        if scenario.id.startswith("fiap"):
            for seed in seeds:
                result = run_one(scenario,"fiap_original","reference",seed,evaluations=budget)
                rows.append(table_row(scenario,result))
        for name,population,mutation in CONFIGURATIONS:
            for seed in seeds:
                result = run_one(scenario,"genetic",name,seed,population,mutation,budget)
                rows.append(table_row(scenario,result))
        pd.DataFrame(rows).to_csv(OUTPUT_ROOT/"experiments"/"results_partial.csv",index=False,encoding="utf-8")
    for coefficient in (0,0.01,0.05,0.10):
        base = load_scenario(DATA_ROOT/"scenarios"/"sp_evaluation_30.json")
        base.priority_coefficient = coefficient
        base.id = f"sp_sensitivity_{str(coefficient).replace('.','_')}"
        base.source["variation"] = f"priority_coefficient={coefficient}"
        write_json(DATA_ROOT/"scenarios"/f"{base.id}.json",base)
        result = run_one(base,"genetic",chosen[0],42,chosen[1],chosen[2],budget)
        rows.append(table_row(base,result))
    for variant in ("capacity","range"):
        base = load_scenario(DATA_ROOT/"scenarios"/"sp_evaluation_30.json")
        base.id = f"sp_stress_{variant}"
        for vehicle in base.vehicles:
            if variant == "capacity": vehicle.capacity = math.ceil(vehicle.capacity*0.82)
            else: vehicle.max_distance = 25_000
        base.source["variation"] = "capacity * 0.82 rounded up" if variant == "capacity" else "range 25000 m"
        write_json(DATA_ROOT/"scenarios"/f"{base.id}.json",base)
        for algorithm in ("greedy","ortools","genetic"):
            result = run_one(base,algorithm,chosen[0] if algorithm == "genetic" else "baseline",
                             42,chosen[1],chosen[2],budget,5 if full else 0.5)
            rows.append(table_row(base,result))
    for i in range(1,8):
        scenario = load_scenario(DATA_ROOT/"scenarios"/f"sp_day_{i}.json")
        result = run_one(scenario,"genetic",chosen[0],42,chosen[1],chosen[2],budget)
        rows.append(table_row(scenario,result))
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT_ROOT/"experiments"/"results.csv",index=False,encoding="utf-8")
    write_json(OUTPUT_ROOT/"experiments"/"manifest.json",{
        "executed_at":utc_now(),"profile":"full" if full else "quick","runs":len(rows),
        "seeds":seeds,"configurations":CONFIGURATIONS,"evaluations_budget":budget,
        "ortools_time_budget_s":5 if full else 0.5,"implementation_hash":implementation_hash(),
        "results_sha256":hashlib.sha256((OUTPUT_ROOT/"experiments"/"results.csv").read_bytes()).hexdigest(),
        "selected_configuration":chosen_name,
        "comparison_caveat":"GA fixed candidate-evaluation budget; OR-Tools fixed time budget; times reported separately"})
    return table


import math
