import argparse
from rotas_medicas.experiments import run_experiments

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--rapido",action="store_true")
    args=p.parse_args()
    result=run_experiments(full=not args.rapido)
    print(f"Experimentos finalizados: {len(result)} execuções",flush=True)
