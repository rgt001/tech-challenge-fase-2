"""Contratos de dados; unidades e premissas são explícitas no cenário."""
from __future__ import annotations
from datetime import date
from enum import StrEnum
import math
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Priority(StrEnum):
    REGULAR = "regular"
    URGENT = "urgente"
    CRITICAL = "critica"


DEFAULT_WEIGHTS = {Priority.REGULAR: 1.0, Priority.URGENT: 3.0, Priority.CRITICAL: 10.0}


class Location(Contract):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    x: float
    y: float


class Delivery(Location):
    load: float = Field(gt=0)
    priority: Priority = Priority.REGULAR
    service_s: float = Field(default=300, ge=0)


class Vehicle(Contract):
    id: str = Field(min_length=1, max_length=100)
    capacity: float = Field(gt=0)
    max_distance: float | None = Field(default=None, gt=0)


class Scenario(Contract):
    schema_version: str = "1.0"
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    description: str
    depot: Location
    deliveries: list[Delivery]
    vehicles: list[Vehicle] = Field(min_length=1, max_length=30)
    distance: list[list[float | None]]
    duration_s: list[list[float | None]]
    distance_unit: Literal["m", "benchmark_unit"] = "m"
    load_unit: Literal["kg", "benchmark_unit"] = "kg"
    coordinates: Literal["wgs84", "cartesian"] = "wgs84"
    priority_coefficient: float = Field(default=0.05, ge=0)
    priority_weights: dict[Priority, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    start_time: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    day: date | None = None
    split: Literal["development", "evaluation", "fixture"] = "evaluation"
    source: dict[str, Any] = Field(default_factory=dict)
    known_optimum: float | None = Field(default=None, ge=0)
    path_geometry: dict[str, list[list[float]]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_problem(self) -> Scenario:
        ids = [self.depot.id] + [d.id for d in self.deliveries]
        if len(set(ids)) != len(ids):
            raise ValueError("Identificadores do depósito e das entregas devem ser únicos")
        if len({v.id for v in self.vehicles}) != len(self.vehicles):
            raise ValueError("Identificadores dos veículos devem ser únicos")
        if any(i.startswith("__separator") for i in ids):
            raise ValueError("Prefixo reservado para representação genética")
        n = len(ids)
        for label, matrix in (("distance", self.distance), ("duration_s", self.duration_s)):
            if len(matrix) != n or any(len(row) != n for row in matrix):
                raise ValueError(f"{label}: dimensão deve ser {n} x {n}")
            for i, row in enumerate(matrix):
                if row[i] != 0:
                    raise ValueError(f"{label}: diagonal deve ser zero")
                for value in row:
                    if value is not None and (not math.isfinite(value) or value < 0):
                        raise ValueError(f"{label}: valores devem ser finitos e não negativos")
        for i in range(n):
            for j in range(n):
                if (self.distance[i][j] is None) != (self.duration_s[i][j] is None):
                    raise ValueError("Distância e duração devem indicar os mesmos pares inalcançáveis")
        if set(self.priority_weights) != set(Priority):
            raise ValueError("Informar pesos para todas as prioridades")
        if any(not math.isfinite(w) or w <= 0 for w in self.priority_weights.values()):
            raise ValueError("Pesos de prioridade devem ser positivos e finitos")
        if self.coordinates == "wgs84":
            for node in [self.depot, *self.deliveries]:
                if not -180 <= node.x <= 180 or not -90 <= node.y <= 90:
                    raise ValueError("Coordenada geográfica inválida")
        if self.distance_unit == "benchmark_unit" and self.priority_coefficient != 0:
            raise ValueError("Benchmark usa objetivo original de distância, coeficiente deve ser zero")
        return self

    @property
    def node_ids(self) -> list[str]:
        return [self.depot.id, *(d.id for d in self.deliveries)]


class GAConfig(Contract):
    population_size: int = Field(default=160, ge=4, le=2000)
    mutation_probability: float = Field(default=0.2, ge=0, le=1)
    crossover_probability: float = Field(default=0.9, ge=0, le=1)
    tournament_size: int = Field(default=3, ge=2)
    elites: int = Field(default=2, ge=1)
    max_evaluations: int = Field(default=20_000, ge=4, le=2_000_000)
    max_seconds: float = Field(default=120, gt=0)
    repair_probability: float = Field(default=0.15, ge=0, le=1)
    seed: int = 42

    @model_validator(mode="after")
    def check_sizes(self) -> GAConfig:
        if self.elites >= self.population_size or self.tournament_size > self.population_size:
            raise ValueError("Elitismo/torneio incompatíveis com população")
        if self.max_evaluations < self.population_size:
            raise ValueError("Orçamento deve permitir avaliar a população inicial")
        return self


class Stop(Contract):
    delivery_id: str
    order: int = Field(ge=1)
    arrival_s: float = Field(ge=0)
    departure_s: float = Field(ge=0)
    load: float = Field(gt=0)
    priority: Priority


class Route(Contract):
    vehicle_id: str
    stops: list[Stop]
    distance: float = Field(ge=0)
    duration_s: float = Field(ge=0)
    initial_load: float = Field(ge=0)
    return_to_depot: bool = True


class Metrics(Contract):
    total_distance: float = Field(ge=0)
    total_duration_s: float = Field(ge=0)
    weighted_arrival_s: float = Field(ge=0)
    critical_arrival_mean_s: float | None = Field(default=None, ge=0)
    vehicles_used: int = Field(ge=0)
    deliveries_served: int = Field(ge=0)
    objective: float = Field(ge=0)


class Verification(Contract):
    valid: bool
    errors: list[str]
    checked_deliveries: int
    recomputed: dict[str, Any] = Field(default_factory=dict)


class Solution(Contract):
    schema_version: str = "1.0"
    id: str
    scenario_id: str
    scenario_hash: str
    algorithm: str
    seed: int | None = None
    status: Literal["feasible", "no_feasible_solution", "infeasible_proven"]
    routes: list[Route]
    metrics: Metrics | None
    verification: Verification | None = None
    diagnostics: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
