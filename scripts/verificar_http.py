"""Evidência de integração por HTTP real, sem TestClient."""
from pathlib import Path
import sys
import httpx
from rotas_medicas.config import OUTPUT_ROOT
from rotas_medicas.storage import write_json,utc_now,canonical_hash
from rotas_medicas.domain import Scenario,Solution
from rotas_medicas.verification import verify_solution
from rotas_medicas.experiments import implementation_hash

base=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8766"
checks=[]
with httpx.Client(base_url=base,timeout=45) as client:
    health=client.get("/health");health.raise_for_status()
    checks.append({"name":"health","passed":health.json()["status"]=="ok" and health.json().get("implementation_hash")==implementation_hash(),"http_status":health.status_code})
    swagger=client.get("/docs");swagger.raise_for_status()
    schema=client.get("/openapi.json");schema.raise_for_status()
    checks.append({"name":"swagger","passed":"/v1/optimizations" in schema.json()["paths"],"http_status":swagger.status_code})
    scenario_response=client.get("/v1/scenarios/sp_evaluation_12");scenario_response.raise_for_status()
    scenario=Scenario.model_validate(scenario_response.json())
    response=client.post("/v1/optimizations",json={"scenario_id":scenario.id,"algorithm":"genetic","configuration":{"seed":42,"population_size":80,"mutation_probability":.1,"max_evaluations":20000}})
    response.raise_for_status();solution=Solution.model_validate(response.json())
    checks.append({"name":"optimization","passed":solution.status=="feasible" and verify_solution(scenario,solution).valid,"http_status":response.status_code})
    fetched=client.get(f"/v1/solutions/{solution.id}");fetched.raise_for_status()
    checks.append({"name":"saved_solution","passed":fetched.json()==response.json(),"http_status":fetched.status_code})
    unknown=client.get("/v1/solutions/"+"0"*32)
    checks.append({"name":"unknown_solution","passed":unknown.status_code==404,"http_status":unknown.status_code})
    bad=client.post("/v1/optimizations",json={})
    checks.append({"name":"invalid_request","passed":bad.status_code==422,"http_status":bad.status_code})
    instruction=client.post(f"/v1/solutions/{solution.id}/instructions")
    checks.append({"name":"llm_dependency","passed":instruction.status_code in (200,503),"http_status":instruction.status_code,"real_llm_passed":instruction.status_code==200})
report={"status":"aprovado" if all(c["passed"] for c in checks) else "falhou","transport":"real_http_loopback",
        "executed_at":utc_now(),"checks":checks,"scenario_hash":canonical_hash(scenario),"solution_id":solution.id,"implementation_hash":health.json().get("implementation_hash"),
        "note":"A integração LLM tem seu próprio critério; HTTP 503 não aprova chamadas reais ao modelo."}
write_json(OUTPUT_ROOT/"validation"/"http.json",report)
print(report)
raise SystemExit(0 if report["status"]=="aprovado" else 1)
