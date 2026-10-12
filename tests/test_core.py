import copy
import math
import random
from collections import Counter
import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError
from rotas_medicas.domain import GAConfig, Scenario
from rotas_medicas.datasets import make_euclidean_fixture
from rotas_medicas.evaluation import Evaluator, build_solution
from rotas_medicas.genetic import order_crossover, mutate, encode, decode, solve_genetic
from rotas_medicas.baselines import repair_routes, solve_greedy, solve_ortools
from rotas_medicas.oracle import exact_small
from rotas_medicas.verification import verify_solution


def test_known_priority_and_distance(tiny):
    # Valores calculados à mão: 3 km + 0,05*(10*1+1*2) = 3,6.
    score = Evaluator(tiny).score([[1,2]])
    assert score.feasible
    assert score.distance == 3000
    assert score.objective == pytest.approx(3.6)
    assert Evaluator(tiny).score([[2,1]]).objective == pytest.approx(4.05)
    oracle = exact_small(tiny)
    assert oracle["objective"] == pytest.approx(3.6)
    assert oracle["routes"] == [[1,2]]


@pytest.mark.parametrize("solver", [solve_greedy, solve_genetic, solve_ortools])
def test_solvers_match_small_optimum(tiny, solver):
    if solver is solve_genetic:
        result = solver(tiny, GAConfig(population_size=20, max_evaluations=400, seed=42))
    elif solver is solve_ortools:
        result = solver(tiny, seconds=0.15)
    else:
        result = solver(tiny)
    assert result.status == "feasible"
    assert verify_solution(tiny, result).valid
    assert result.metrics.objective == pytest.approx(3.6)


@given(st.integers(min_value=2, max_value=25), st.integers(min_value=0, max_value=10000))
def test_genetic_operators_preserve_deliveries_and_separators(n, seed):
    rng = random.Random(seed)
    p1 = tuple(range(1,n+1))+(-1,-2)
    p2 = tuple(rng.sample(p1,len(p1)))
    child = order_crossover(p1,p2,rng)
    changed = mutate(child,rng,1)
    assert Counter(child) == Counter(p1) == Counter(changed)
    assert encode(decode(changed,3)) == changed
    assert p1 == tuple(range(1,n+1))+(-1,-2)


def test_empty_and_single_gene_operators():
    rng = random.Random(1)
    assert order_crossover((),(),rng) == ()
    assert order_crossover((1,),(1,),rng) == (1,)
    assert mutate((1,),rng,1) == (1,)
    with pytest.raises(ValueError):
        order_crossover((1,1),(1,2),rng)


def test_seed_reproduction_and_elitism():
    scenario = make_euclidean_fixture()
    config = GAConfig(population_size=30,max_evaluations=1200,seed=73)
    a,b = solve_genetic(scenario,config), solve_genetic(scenario,config)
    assert a.routes == b.routes
    assert a.metrics == b.metrics
    objectives = [h["best_objective"] for h in a.metadata["history"] if h["best_objective"] is not None]
    assert objectives == sorted(objectives,reverse=True)
    assert a.metrics.objective <= a.metadata["initial_greedy_objective"]+1e-9
    assert a.metrics.objective == pytest.approx(exact_small(scenario)["objective"])


@pytest.mark.parametrize("edit", ["missing","duplicate","vehicle","load","distance","arrival","metrics","return","hash"])
def test_independent_checker_rejects_tampering(tiny, edit):
    solution = build_solution(tiny,[[1,2]],"manual")
    if edit == "missing": solution.routes[0].stops.pop()
    elif edit == "duplicate": solution.routes[0].stops.append(copy.deepcopy(solution.routes[0].stops[0]))
    elif edit == "vehicle": solution.routes[0].vehicle_id = "unknown"
    elif edit == "load": solution.routes[0].stops[0].load = 0.5
    elif edit == "distance": solution.routes[0].distance = 2000
    elif edit == "arrival": solution.routes[0].stops[0].arrival_s = 30
    elif edit == "metrics": solution.metrics.objective = 0
    elif edit == "return": solution.routes[0].return_to_depot = False
    elif edit == "hash": solution.scenario_hash = "wrong"
    assert not verify_solution(tiny,solution).valid


def test_checker_recalculates_actual_capacity(tiny):
    solution = build_solution(tiny,[[1,2]],"manual")
    tiny.vehicles[0].capacity = 1.5
    from rotas_medicas.storage import canonical_hash
    solution.scenario_hash = canonical_hash(tiny)
    assert any("Capacidade" in e for e in verify_solution(tiny,solution).errors)


def test_autonomy_includes_return(tiny):
    tiny.vehicles[0].max_distance = 2000
    assert not exact_small(tiny)["feasible"]
    result = solve_genetic(tiny,GAConfig(population_size=10,max_evaluations=50))
    assert result.status == "no_feasible_solution" # busca não é prova de impossibilidade
    assert result.routes == [] and result.metrics is None


def test_total_capacity_proves_impossibility(tiny):
    tiny.vehicles[0].capacity = 1
    result = solve_genetic(tiny,GAConfig(population_size=10,max_evaluations=50))
    assert result.status == "infeasible_proven"
    assert not result.routes


def test_deliveries_at_same_address_are_distinct(tiny):
    tiny.deliveries[1].x, tiny.deliveries[1].y = tiny.deliveries[0].x, tiny.deliveries[0].y
    tiny.distance = [[0,1000,1000],[1000,0,0],[1000,0,0]]
    tiny.duration_s = [[0,60,60],[60,0,0],[60,0,0]]
    result = solve_genetic(tiny,GAConfig(population_size=10,max_evaluations=100))
    assert result.verification.valid
    assert result.metrics.deliveries_served == 2
    assert result.metrics.total_distance == 2000


def test_asymmetric_matrix(tiny):
    tiny.priority_coefficient = 0
    tiny.distance = [[0,100,300],[300,0,100],[100,300,0]]
    assert Evaluator(tiny).score([[1,2]]).distance == 300
    assert Evaluator(tiny).score([[2,1]]).distance == 900
    solution = solve_genetic(tiny,GAConfig(population_size=10,max_evaluations=200))
    assert solution.metrics.total_distance == 300


def test_unreachable_is_not_a_zero_distance(tiny):
    for j in (0,1):
        tiny.distance[j][2] = tiny.distance[2][j] = None
        tiny.duration_s[j][2] = tiny.duration_s[2][j] = None
    assert not exact_small(tiny)["feasible"]
    assert solve_genetic(tiny).status == "infeasible_proven"


def test_repair_preserves_visits_and_capacity():
    s = make_euclidean_fixture(n=4,k=2)
    for v in s.vehicles: v.capacity=2
    routes = repair_routes(Evaluator(s),[[1,2,3,4],[]])
    assert Evaluator(s).score(routes).feasible
    assert Counter(n for r in routes for n in r) == Counter([1,2,3,4])


@pytest.mark.parametrize("edit", ["duplicate_id","nan","negative","dimension","diagonal","reachable_mismatch","weights"])
def test_invalid_inputs_rejected(tiny, edit):
    data = tiny.model_dump(mode="json")
    if edit == "duplicate_id": data["deliveries"][1]["id"] = "A"
    elif edit == "nan": data["distance"][0][1] = math.nan
    elif edit == "negative": data["distance"][0][1] = -1
    elif edit == "dimension": data["distance"].pop()
    elif edit == "diagonal": data["distance"][0][0] = 1
    elif edit == "reachable_mismatch": data["distance"][0][1] = None
    elif edit == "weights": data["priority_weights"]["critica"] = 0
    with pytest.raises(ValidationError): Scenario.model_validate(data)
