"""Endpoints de linguagem em processo HTTP real, reutilizando dados da avaliação.

Caches só aprovam a integração quando têm origem comprovada na Responses API.
Sem chave, as respostas 503 ficam registradas como pendentes.
"""
import sys
import httpx
from rotas_medicas.config import OUTPUT_ROOT
from rotas_medicas.storage import write_json,utc_now,canonical_hash
from rotas_medicas.verification import verify_solution
from rotas_medicas.llm import build_context,MODEL
from rotas_medicas.llm_evaluation import fixed_cases,evaluation_pairs,assess
from rotas_medicas.budget import BudgetLedger

base=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8766"
datasets=evaluation_pairs()
for pairs in datasets.values():
    for scenario,solution in pairs:
        if not verify_solution(scenario,solution).valid:
            raise ValueError("Solução da avaliação não certificada")
        write_json(OUTPUT_ROOT/"runtime/scenarios"/f"{solution.scenario_hash}.json",scenario)
        write_json(OUTPUT_ROOT/"runtime/solutions"/f"{solution.id}.json",solution)
small_id=datasets["small"][0][1].id
cases={c["id"]:c for c in fixed_cases()}
requests=[
    ("c01",f"/v1/solutions/{small_id}/instructions",None),
    ("c02",f"/v1/solutions/{small_id}/daily-report",None),
    ("c07",f"/v1/solutions/{small_id}/questions",{"question":cases["c07"]["question"]}),
    ("c04","/v1/reports/weekly",{"solution_ids":[s.id for _,s in datasets["week"]]}),
]
checks=[]
with httpx.Client(base_url=base,timeout=60) as client:
    for case_id,url,body in requests:
        case=cases[case_id]
        context=build_context(case["kind"],datasets[case["dataset"]],case["question"])
        response=client.post(url,json=body)
        row={"case_id":case_id,"kind":case["kind"],"http_status":response.status_code,
             "context_hash":canonical_hash(context),"passed":False,"real_origin":False}
        if response.status_code==503:
            row.update(status="pendente",detail=response.json())
        elif response.status_code!=200:
            row.update(status="falhou",detail=response.text[:1000])
        else:
            answer=response.json()
            provenance=answer.get("provenance",{})
            origin=provenance.get("origin")
            real=origin=="api" or (origin=="cache" and provenance.get("original_origin")=="api")
            response_model=provenance.get("response_model","")
            model_ok=response_model==MODEL or response_model.startswith(MODEL+"-")
            evaluation=assess(answer,case,context)
            order_ok=True
            if case["kind"]=="instructions":
                expected=[{k:r[k] for k in ("solution_id","vehicle_id","delivery_ids")} for r in context["active_routes"]]
                order_ok=sorted(answer["instructions"],key=lambda r:(r["solution_id"],r["vehicle_id"]))==sorted(expected,key=lambda r:(r["solution_id"],r["vehicle_id"]))
            ledger=BudgetLedger(OUTPUT_ROOT/"llm/budget.sqlite3").summary()
            accounted=any(r["id"]==provenance.get("reservation_id") and r["response_id"]==provenance.get("response_id") and r["state"]=="settled" for r in ledger["calls"])
            passed=bool(real and model_ok and provenance.get("model")==MODEL and provenance.get("context_hash")==canonical_hash(context)
                        and accounted and order_ok and evaluation["factual_consistency"] and evaluation["useful"])
            row.update(status="aprovado" if passed else "falhou",passed=passed,real_origin=real,
                       assessment=evaluation,accounted=accounted,answer=answer)
        checks.append(row)
        print(case["kind"],row["status"],response.status_code,flush=True)
status="falhou" if any(r["status"]=="falhou" for r in checks) else "pendente" if any(r["status"]=="pendente" for r in checks) else "aprovado"
write_json(OUTPUT_ROOT/"validation/http-llm.json",{"status":status,"transport":"real_http_loopback",
           "created_at":utc_now(),"checks":checks,"reason":"Endpoints LLM aguardam resposta real conferida" if status=="pendente" else None})
raise SystemExit({"aprovado":0,"falhou":1,"pendente":2}[status])
