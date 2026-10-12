"""API local: nenhuma rota é disponibilizada sem recertificação."""
from __future__ import annotations
import re
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import Field, model_validator
from typing import Literal
from .config import DATA_ROOT, OUTPUT_ROOT
from .domain import Contract, GAConfig, Scenario, Solution
from .baselines import solve_greedy,solve_ortools
from .genetic import solve_genetic
from .storage import load_scenario,load_solution,write_json,canonical_hash
from .verification import verify_solution
from .experiments import implementation_hash

APPLICATION_BUILD=implementation_hash()


class OptimizationRequest(Contract):
    scenario_id: str | None = None
    scenario: Scenario | None = None
    algorithm: Literal["genetic","greedy","ortools"] = "genetic"
    configuration: GAConfig = Field(default_factory=GAConfig)
    ortools_seconds: float = Field(default=5,gt=0,le=120)

    @model_validator(mode="after")
    def one_source(self):
        if (self.scenario_id is None) == (self.scenario is None):
            raise ValueError("Informar cenário completo ou scenario_id, exclusivamente")
        return self


class QuestionRequest(Contract):
    question: str = Field(min_length=1,max_length=2000)


class WeeklyRequest(Contract):
    solution_ids: list[str] = Field(min_length=1,max_length=7)


def create_app(data_root: Path | None = None, output_root: Path | None = None):
    data_root,output_root = data_root or DATA_ROOT,output_root or OUTPUT_ROOT
    app=FastAPI(title="Rotas médicas - Tech Challenge Fase 2",version="0.1.0",
                description="Otimização local com certificação das rotas e interpretação por LLM")

    def scenario_by_id(scenario_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}",scenario_id):
            raise HTTPException(422,"Identificador inválido")
        path=data_root/"scenarios"/f"{scenario_id}.json"
        if not path.is_file(): raise HTTPException(404,"Cenário não encontrado")
        return load_scenario(path)

    def get_pair(solution_id):
        if not re.fullmatch(r"[a-f0-9]{32}",solution_id):
            raise HTTPException(422,"Identificador de solução inválido")
        path=output_root/"runtime"/"solutions"/f"{solution_id}.json"
        if not path.is_file(): raise HTTPException(404,"Solução não encontrada")
        solution=load_solution(path)
        scenario=load_scenario(output_root/"runtime"/"scenarios"/f"{solution.scenario_hash}.json")
        if solution.status == "feasible":
            certification=verify_solution(scenario,solution)
            if not certification.valid: raise HTTPException(409,{"message":"Solução persistida inválida","errors":certification.errors})
            solution.verification=certification
        return scenario,solution

    def language(kind,pairs,question=None):
        try:
            from .llm import generate_grounded
            return generate_grounded(kind,pairs,question=question,output_root=output_root)
        except ImportError:
            raise HTTPException(503,"Integração LLM ainda em preparação")
        except Exception as exc:
            from .llm import LLMError
            if isinstance(exc,LLMError):
                raise HTTPException(503,{"message":str(exc),"reason":exc.reason})
            raise

    @app.get("/health")
    def health(): return {"status":"ok","version":"0.1.0","implementation_hash":APPLICATION_BUILD}

    @app.get("/v1/scenarios")
    def scenarios():
        return [{"id":p.stem} for p in sorted((data_root/"scenarios").glob("*.json"))]

    @app.get("/v1/scenarios/{scenario_id}",response_model=Scenario)
    def scenario_endpoint(scenario_id:str): return scenario_by_id(scenario_id)

    @app.post("/v1/optimizations",response_model=Solution)
    def optimize(request:OptimizationRequest):
        scenario=request.scenario or scenario_by_id(request.scenario_id)
        if request.algorithm == "genetic": result=solve_genetic(scenario,request.configuration)
        elif request.algorithm == "greedy": result=solve_greedy(scenario)
        else: result=solve_ortools(scenario,request.ortools_seconds)
        write_json(output_root/"runtime"/"scenarios"/f"{canonical_hash(scenario)}.json",scenario)
        write_json(output_root/"runtime"/"solutions"/f"{result.id}.json",result)
        return result

    @app.get("/v1/solutions/{solution_id}",response_model=Solution)
    def solution_endpoint(solution_id:str): return get_pair(solution_id)[1]

    @app.post("/v1/solutions/{solution_id}/instructions")
    def instructions(solution_id:str): return language("instructions",[get_pair(solution_id)])

    @app.post("/v1/solutions/{solution_id}/daily-report")
    def daily(solution_id:str): return language("daily_report",[get_pair(solution_id)])

    @app.post("/v1/solutions/{solution_id}/questions")
    def question(solution_id:str,request:QuestionRequest):
        return language("qa",[get_pair(solution_id)],request.question)

    @app.post("/v1/reports/weekly")
    def weekly(request:WeeklyRequest):
        if len(set(request.solution_ids)) != len(request.solution_ids):
            raise HTTPException(422,"Soluções repetidas no relatório semanal")
        return language("weekly_report",[get_pair(i) for i in request.solution_ids])
    return app


app=create_app()
