import json
import hashlib
import math
from pathlib import Path
import pytest
from rotas_medicas.config import DATA_ROOT
from rotas_medicas.datasets import read_cvrplib
from rotas_medicas.evaluation import build_solution
from rotas_medicas.verification import verify_solution
from rotas_medicas.fiap_reference import reference_scenario,solve_fiap_reference


@pytest.mark.parametrize("name,optimum",[("A-n32-k5",784),("A-n54-k7",1167),("A-n80-k10",1763)])
def test_public_optimal_solution_matches_original_rules(name,optimum):
    path = DATA_ROOT / "sources" / "cvrplib" / f"{name}.vrp"
    scenario = read_cvrplib(path,optimum)
    routes = []
    for line in path.with_suffix(".sol").read_text().splitlines():
        if line.startswith("Route"):
            routes.append([int(n) for n in line.split(":",1)[1].split()])
    # Referência externa publicada, não uma rota produzida por nosso otimizador.
    solution = build_solution(scenario,routes,"published_optimum")
    assert solution.metrics.total_distance == optimum
    assert verify_solution(scenario,solution).valid
    assert scenario.priority_coefficient == 0
    assert scenario.distance_unit == "benchmark_unit"


def test_all_pinned_sources_match_manifest():
    root = DATA_ROOT.parent
    manifest = json.loads((DATA_ROOT/"sources"/"manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 14
    for record in manifest["files"]:
        assert hashlib.sha256((root/record["path"]).read_bytes()).hexdigest() == record["sha256"]


def test_fiap_reference_is_a_valid_closed_tsp():
    scenario = reference_scenario(10)
    solution = solve_fiap_reference(scenario,max_evaluations=500)
    assert solution.verification.valid
    assert solution.metadata["same_parent_crossover_preserved"] is True
    assert solution.metadata["source_commit"] == "d236a2ae6a08fefdb8ee9f1ca3f8201223a92da3"
