import pytest
from rotas_medicas.domain import Delivery, Location, Scenario, Vehicle


@pytest.fixture
def tiny():
    return Scenario(id="tiny", description="Duas entregas em triângulo de lados iguais",
        depot=Location(id="dep", name="Depósito", x=0, y=0), coordinates="cartesian",
        deliveries=[Delivery(id="A", name="Crítica", x=1, y=0, load=1, priority="critica", service_s=0),
                    Delivery(id="B", name="Regular", x=0, y=1, load=1, service_s=0)],
        vehicles=[Vehicle(id="V", capacity=2, max_distance=3000)],
        distance=[[0,1000,1000],[1000,0,1000],[1000,1000,0]],
        duration_s=[[0,60,60],[60,0,60],[60,60,0]], split="fixture")
