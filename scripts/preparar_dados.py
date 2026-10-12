from pathlib import Path
from rotas_medicas.config import DATA_ROOT
from rotas_medicas.datasets import read_cvrplib
from rotas_medicas.geography import prepare_medical_data
from rotas_medicas.storage import write_json

if __name__ == "__main__":
    for name,optimum in (("A-n32-k5",784),("A-n54-k7",1167),("A-n80-k10",1763)):
        scenario = read_cvrplib(DATA_ROOT / "sources" / "cvrplib" / f"{name}.vrp",optimum)
        write_json(DATA_ROOT / "scenarios" / f"{name}.json",scenario)
        print(f"Benchmark preparado: {name}",flush=True)
    prepare_medical_data()
