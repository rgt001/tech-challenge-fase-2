"""Interface comum aos experimentos, à API e à validação."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .config import DATA_ROOT,OUTPUT_ROOT
from .domain import GAConfig
from .storage import load_scenario,write_json


def main(argv=None):
    parser=argparse.ArgumentParser(prog="tc2",description="Tech Challenge Fase 2 — Rotas médicas")
    subs=parser.add_subparsers(dest="command",required=True)
    opt=subs.add_parser("otimizar",help="Otimizar cenário salvo")
    opt.add_argument("cenario",help="Identificador em data/scenarios ou arquivo JSON")
    opt.add_argument("--algoritmo",choices=["genetic","greedy","ortools"],default="genetic")
    opt.add_argument("--semente",type=int,default=42)
    opt.add_argument("--avaliacoes",type=int,default=20_000)
    opt.add_argument("--mapa",action="store_true")
    serve=subs.add_parser("api",help="Iniciar a API local e Swagger")
    serve.add_argument("--porta",type=int,default=8000)
    exp=subs.add_parser("experimentos")
    exp.add_argument("--rapido",action="store_true")
    valid=subs.add_parser("validar")
    valid.add_argument("--perfil",choices=["desenvolvimento","entrega"],default="entrega")
    subs.add_parser("avaliar-llm")
    args=parser.parse_args(argv)
    if args.command=="api":
        import uvicorn
        uvicorn.run("rotas_medicas.api:app",host="127.0.0.1",port=args.porta)
    elif args.command=="experimentos":
        from .experiments import run_experiments
        run_experiments(not args.rapido)
    elif args.command=="validar":
        from .acceptance import validate_delivery
        report=validate_delivery(args.perfil)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report["status"]=="aprovado" else 1 if report["status"]=="falhou" else 2
    elif args.command=="avaliar-llm":
        from .llm_evaluation import evaluate_prompts
        print(json.dumps(evaluate_prompts(),ensure_ascii=False,indent=2))
    else:
        path=Path(args.cenario)
        scenario=load_scenario(path if path.is_file() else DATA_ROOT/"scenarios"/f"{args.cenario}.json")
        if args.algoritmo=="genetic":
            from .genetic import solve_genetic
            result=solve_genetic(scenario,GAConfig(seed=args.semente,max_evaluations=args.avaliacoes))
        elif args.algoritmo=="greedy":
            from .baselines import solve_greedy
            result=solve_greedy(scenario)
        else:
            from .baselines import solve_ortools
            result=solve_ortools(scenario)
        target=OUTPUT_ROOT/"solutions"/f"{scenario.id}_{args.algoritmo}_{args.semente}.json"
        write_json(target,result)
        print(json.dumps({"status":result.status,"solution":str(target),"metrics":result.metrics.model_dump() if result.metrics else None},ensure_ascii=False,indent=2))
        if args.mapa and result.status=="feasible":
            from .maps import export_map
            for p in export_map(scenario,result):print(p)
    return 0
