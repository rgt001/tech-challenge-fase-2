"""GA de permutações e separadores: evolução rastreável da base FIAP."""
from __future__ import annotations
import random
import time
from .baselines import greedy_routes, repair_routes
from .domain import GAConfig, Scenario, Solution
from .evaluation import Evaluator, build_solution, failure_solution, infeasibility_proofs


def decode(genome: tuple[int, ...] | list[int], k: int) -> list[list[int]]:
    routes = [[]]
    for gene in genome:
        if gene < 0:
            routes.append([])
        else:
            routes[-1].append(gene)
    if len(routes) != k:
        raise ValueError("Quantidade incorreta de separadores")
    return routes


def encode(routes: list[list[int]]) -> tuple[int, ...]:
    genes = []
    for i, route in enumerate(routes):
        if i:
            genes.append(-i)
        genes.extend(route)
    return tuple(genes)


def canonical(genome: tuple[int, ...] | list[int]) -> tuple[int, ...]:
    separator = 0
    out = []
    for gene in genome:
        if gene < 0:
            separator -= 1
            out.append(separator)
        else:
            out.append(gene)
    return tuple(out)


def order_crossover(parent1: tuple[int, ...], parent2: tuple[int, ...], rng: random.Random) -> tuple[int, ...]:
    if len(parent1) != len(parent2) or set(parent1) != set(parent2) or len(set(parent1)) != len(parent1):
        raise ValueError("Pais devem ser permutações do mesmo conjunto de genes únicos")
    n = len(parent1)
    if n < 2:
        return parent1
    start, end = sorted(rng.sample(range(n+1), 2))
    child: list[int | None] = [None]*n
    child[start:end] = parent1[start:end]
    kept = set(parent1[start:end])
    remaining = [parent2[(end+i) % n] for i in range(n) if parent2[(end+i) % n] not in kept]
    positions = [i % n for i in range(end, end+n) if child[i % n] is None]
    for i, gene in zip(positions, remaining):
        child[i] = gene
    return canonical(tuple(child))


def mutate(genome: tuple[int, ...], rng: random.Random, probability: float) -> tuple[int, ...]:
    if len(genome) < 2 or rng.random() >= probability:
        return genome
    a, b = sorted(rng.sample(range(len(genome)), 2))
    child = list(genome)
    if rng.random() < 0.5:
        child[a], child[b] = child[b], child[a]
    else:
        child[a:b+1] = reversed(child[a:b+1])
    return canonical(tuple(child))


class SearchBudgetStop(RuntimeError):
    pass


class BudgetedEvaluator(Evaluator):
    """Conta também fitness da inicialização e da reparação, sem extrapolar o teto."""
    def __init__(self,scenario,config,started):
        super().__init__(scenario)
        self.config,self.started=config,started
        self.evaluations=0
        self.route_cost_calls=0
        self.seen=set()
        self.best_routes=None
        self.best_score=None

    def check_time(self):
        if time.perf_counter()-self.started>=self.config.max_seconds:
            raise SearchBudgetStop("time_limit")

    def route_values(self,route,vehicle_index):
        self.check_time()
        self.route_cost_calls+=1
        return super().route_values(route,vehicle_index)

    def score(self,routes):
        self.check_time()
        if self.evaluations>=self.config.max_evaluations:
            raise SearchBudgetStop("evaluation_budget")
        self.evaluations+=1
        self.seen.add(tuple(tuple(r) for r in routes))
        value=super().score(routes)
        if value.feasible and (self.best_score is None or value.key<self.best_score.key):
            self.best_score=value
            self.best_routes=[list(r) for r in routes]
        return value


def solve_genetic(scenario: Scenario, config: GAConfig | None = None) -> Solution:
    config = config or GAConfig()
    started = time.perf_counter()
    proofs = infeasibility_proofs(scenario)
    if proofs:
        return failure_solution(scenario, "genetic", proofs, proven=True, configuration=config.model_dump())
    ev = BudgetedEvaluator(scenario,config,started)
    if ev.n == 0:
        return build_solution(scenario, [[] for _ in range(ev.k)], "genetic", config.seed,
                              {"elapsed_s": time.perf_counter()-started, "evaluations": 1,
                               "termination": "empty_problem", "configuration": config.model_dump()})
    rng = random.Random(config.seed)
    genes = tuple([*range(1, ev.n+1), *(-i for i in range(1, ev.k))])
    cache = {}
    attempts = 0
    generations = 0
    history = []
    best_genome = None
    best_key = (10**9, float("inf"), float("inf"))
    termination = "evaluation_budget"
    seed_objective=None

    def evaluate(genome):
        nonlocal attempts
        attempts += 1
        if genome not in cache:
            cache[genome] = ev.score(decode(genome, ev.k))
        return cache[genome].key

    try:
        seed_routes = greedy_routes(ev)
        seed_score=ev.score(seed_routes)
        seed_objective=seed_score.objective if seed_score.feasible else None
        seed_genome = encode(seed_routes)
        population = [seed_genome]
        while len(population) < config.population_size:
            if len(population) < config.population_size*0.6:
                child = seed_genome
                for _ in range(rng.randint(1, 4)):
                    child = mutate(child, rng, 1.0)
                routes = repair_routes(ev, decode(child, ev.k), max_moves=2)
                population.append(encode(routes))
            else:
                population.append(canonical(tuple(rng.sample(genes, len(genes)))))
        while attempts < config.max_evaluations:
            ev.check_time()
            ranked = []
            for genome in population:
                if attempts >= config.max_evaluations: break
                key = evaluate(genome)
                ranked.append((key, genome))
                if key < best_key: best_key, best_genome = key, genome
            if not ranked: break
            ranked.sort(key=lambda pair: pair[0])
            best_score = cache[ranked[0][1]]
            history.append({"generation": generations, "evaluations": ev.evaluations,
                            "candidate_attempts":attempts,
                            "best_objective": ev.best_score.objective if ev.best_score else None,
                            "best_violation": best_score.violation if best_score.violation != float("inf") else None,
                            "feasible_fraction": sum(cache[g].feasible for _, g in ranked)/len(ranked),
                            "unique_fraction": len(set(g for _, g in ranked))/len(ranked)})
            if attempts >= config.max_evaluations:
                termination="candidate_attempt_budget"
                break
            new_population = [g for _, g in ranked[:config.elites]]

            def select():
                return min(rng.sample(ranked, min(config.tournament_size, len(ranked))), key=lambda p: p[0])[1]

            while len(new_population) < config.population_size:
                parent1, parent2 = select(), select()
                if parent1 == parent2:
                    alternatives = [g for _, g in ranked if g != parent1]
                    if alternatives: parent2 = rng.choice(alternatives)
                child = order_crossover(parent1, parent2, rng) if rng.random() < config.crossover_probability else parent1
                child = mutate(child, rng, config.mutation_probability)
                if rng.random() < config.repair_probability:
                    child = encode(repair_routes(ev, decode(child, ev.k), max_moves=2))
                new_population.append(child)
            population = new_population
            generations += 1
    except SearchBudgetStop as exc:
        termination=str(exc)
    metadata = {"elapsed_s": time.perf_counter()-started, "evaluations": ev.evaluations,
                "candidate_attempts":attempts,"route_cost_calls":ev.route_cost_calls,
                "unique_fitness_evaluations": len(ev.seen), "generations": generations,
                "termination": termination, "configuration": config.model_dump(), "history": history,
                "initial_greedy_objective": seed_objective,
                "budget_scope":"all full fitness calls including greedy initialization and repair; route insertion costs counted separately",
                "fitness_order": "structural_errors, normalized_hard_violation, distance_plus_weighted_arrival"}
    if ev.best_routes is None:
        return failure_solution(scenario, "genetic", ["Busca não encontrou solução viável no orçamento"], **metadata)
    return build_solution(scenario, ev.best_routes, "genetic", config.seed, metadata)
