import time
import pytest
from rotas_medicas.domain import GAConfig
from rotas_medicas.genetic import BudgetedEvaluator,SearchBudgetStop,solve_genetic
from rotas_medicas.baselines import repair_routes
from rotas_medicas.datasets import make_euclidean_fixture


def test_repair_fitness_calls_consume_same_budget():
    scenario=make_euclidean_fixture(8,2,seed=7)
    scenario.vehicles[0].capacity=2
    config=GAConfig(population_size=4,max_evaluations=5)
    evaluator=BudgetedEvaluator(scenario,config,time.perf_counter())
    with pytest.raises(SearchBudgetStop,match="evaluation_budget"):
        repair_routes(evaluator,[list(range(1,9)),[]],max_moves=12)
    assert evaluator.evaluations==5
    assert len(evaluator.seen)>1


def test_global_budget_and_feasible_incumbent_survive_interruption():
    scenario=make_euclidean_fixture(12,3,seed=13)
    result=solve_genetic(scenario,GAConfig(population_size=80,max_evaluations=100,seed=42))
    assert result.metadata["evaluations"]<=100
    assert result.metadata["termination"] in {"evaluation_budget","candidate_attempt_budget"}
    assert result.status=="feasible" and result.verification.valid
    assert result.metadata["unique_fitness_evaluations"]<=result.metadata["evaluations"]
