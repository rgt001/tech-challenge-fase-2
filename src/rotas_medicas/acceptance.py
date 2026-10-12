"""Aceite por evidências, com pendências externas explícitas e saída para automação."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
from .config import PROJECT_ROOT,DATA_ROOT,OUTPUT_ROOT,relative_path
from .storage import load_scenario,load_solution,write_json,utc_now,canonical_hash
from .verification import verify_solution
from .experiments import implementation_hash,SEEDS,CONFIGURATIONS


def file_hash(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_delivery(profile="entrega"):
    gates=[]
    folder=OUTPUT_ROOT/"validation"
    folder.mkdir(parents=True,exist_ok=True)
    def gate(identifier,state,evidence,detail):
        gates.append({"id":identifier,"status":state,"evidence":evidence,"detail":detail})
        print(f"{identifier}: {state} — {detail}",flush=True)
    def existing_report(identifier,path,extra=None):
        if not path.is_file():gate(identifier,"pendente",[relative_path(path)],"Evidência ainda não produzida");return None
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("status")=="pendente":
            gate(identifier,"pendente",[relative_path(path)],data.get("reason","Evidência ainda incompleta"))
            return data
        ok=data.get("status")=="aprovado" and (extra(data) if extra else True)
        gate(identifier,"aprovado" if ok else "falhou",[relative_path(path)],"Evidência conferida" if ok else "Evidência não atende ao contrato")
        return data
    junit=folder/"pytest.xml"
    run=subprocess.run([sys.executable,"-m","pytest","--junitxml",str(junit)],cwd=PROJECT_ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace")
    test_log=run.stdout+run.stderr
    for prefix,label in [(PROJECT_ROOT,"<project>"),(Path.home(),"<user>")]:
        for spelling in [str(prefix),prefix.as_posix()]:
            test_log=re.sub(re.escape(spelling),lambda _:label,test_log,flags=re.IGNORECASE)
    (folder/"pytest.log").write_text(test_log,encoding="utf-8")
    cases=ET.parse(junit).findall(".//testcase") if junit.is_file() else []
    ok=run.returncode==0 and bool(cases) and not any(c.find("skipped") is not None for c in cases)
    # Os critérios não dependem apenas da quantidade total de testes.
    names=" ".join(c.attrib.get("name","") for c in cases)
    required=["test_known_priority_and_distance","test_solvers_match_small_optimum","test_genetic_operators_preserve_deliveries_and_separators",
        "test_independent_checker_rejects_tampering","test_autonomy_includes_return","test_asymmetric_matrix","test_deliveries_at_same_address_are_distinct",
        "test_repair_fitness_calls_consume_same_budget","test_ledger_atomic_cap_and_reconciliation","test_failures_preserve_accounting"]
    ok &= all(n in names for n in required)
    for identifier in ["DOM","GA","ORACLE","ADV","TAMPER","FAIL"]:
        gate(identifier,"aprovado" if ok else "falhou",["outputs/validation/pytest.xml","outputs/validation/pytest.log"],f"{len(cases)} testes; grupos obrigatórios presentes: {ok}")
    sources=json.loads((DATA_ROOT/"sources"/"manifest.json").read_text(encoding="utf-8"))
    mismatches=[r["path"] for r in sources["files"] if not (PROJECT_ROOT/r["path"]).is_file() or file_hash(PROJECT_ROOT/r["path"])!=r["sha256"]]
    gate("BASE","aprovado" if not mismatches and (PROJECT_ROOT/"docs"/"EVOLUCAO_FIAP.md").is_file() else "falhou",["data/sources/manifest.json","docs/EVOLUCAO_FIAP.md"],f"{len(sources['files'])} fontes; divergências: {mismatches}")
    gate("CVRP","aprovado" if ok and "test_public_optimal_solution_matches_original_rules" in names else "falhou",["outputs/validation/pytest.xml"],"Soluções publicadas conferidas com distância e capacidade originais")
    existing_report("GEO",folder/"geography.json",lambda d:all((DATA_ROOT/"scenarios"/f"{r['scenario']}.json").is_file() and canonical_hash(load_scenario(DATA_ROOT/"scenarios"/f"{r['scenario']}.json"))==r["scenario_hash"] for r in d["scenarios"]))
    required_scenarios=[f"sp_{split}_{n}" for split in ("development","evaluation") for n in (12,30,60)]+[f"sp_day_{i}" for i in range(1,8)]+["sp_stress_capacity","sp_stress_range","sp_sensitivity_0","sp_sensitivity_0_01","sp_sensitivity_0_05","sp_sensitivity_0_1"]
    missing=[s for s in required_scenarios if not (DATA_ROOT/"scenarios"/f"{s}.json").is_file()]
    gate("SCEN","pendente" if missing else "aprovado",["data/README.md"],f"Cenários ausentes: {missing}")
    manifest_path=OUTPUT_ROOT/"experiments"/"manifest.json"
    if not manifest_path.is_file():
        for identifier in ["EXP","VALID","BASELINE","PRI"]:gate(identifier,"pendente",[relative_path(manifest_path)],"Experimentos finais incompletos")
    else:
        import pandas as pd
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"));table=pd.read_csv(OUTPUT_ROOT/"experiments"/"results.csv")
        fingerprint=implementation_hash()
        complete=manifest["profile"]=="full" and manifest["results_sha256"]==file_hash(OUTPUT_ROOT/"experiments"/"results.csv") and manifest["implementation_hash"]==fingerprint
        final=[f"sp_evaluation_{n}" for n in (12,30,60)]+["A-n32-k5","A-n54-k7","A-n80-k10","fiap_tsp_15"]
        for name in final:
            for config,_,_ in CONFIGURATIONS:
                subset=table[(table.scenario==name)&(table.algorithm=="genetic")&(table.configuration==config)]
                complete &= len(subset)==10 and set(subset.seed)==set(SEEDS)
        invalid=[];budgets=[];solution_rows=[]
        scenarios={}
        for path in sorted((OUTPUT_ROOT/"experiments"/"runs").rglob("*.json")):
            result=load_solution(path)
            if result.scenario_id not in scenarios:scenarios[result.scenario_id]=load_scenario(DATA_ROOT/"scenarios"/f"{result.scenario_id}.json")
            scenario=scenarios[result.scenario_id]
            if result.metadata["experiment_fingerprint"]["implementation_hash"]!=fingerprint:invalid.append(relative_path(path)+": implementation")
            if result.status=="feasible" and not verify_solution(scenario,result).valid:invalid.append(relative_path(path)+": constraints")
            if result.status!="feasible" and result.routes:invalid.append(relative_path(path)+": invalid route published")
            if result.algorithm=="genetic" and result.metadata.get("evaluations",0)>20000:budgets.append(relative_path(path))
            solution_rows.append({"id":result.id,"scenario":result.scenario_id,"status":result.status,"evaluations":result.metadata.get("evaluations"),"termination":result.metadata.get("termination")})
        write_json(folder/"solutions.json",{"status":"aprovado" if not invalid and not budgets else "falhou","checked":len(solution_rows),"solutions":solution_rows,"errors":invalid,"budget_errors":budgets,"implementation_hash":fingerprint})
        gate("EXP","aprovado" if complete and not budgets else "falhou",["outputs/experiments/manifest.json","outputs/validation/solutions.json"],f"{len(table)} execuções tabuladas; todos os grupos 3 × 10 conferidos: {bool(complete)}")
        gate("VALID","aprovado" if not invalid else "falhou",["outputs/validation/solutions.json"],f"{len(solution_rows)} soluções conferidas; divergências: {len(invalid)}")
        baseline_ok=all(all(a in set(table[table.scenario==s].algorithm) for a in ("greedy","ortools")) for s in final) and len(table[(table.scenario=="fiap_tsp_15")&(table.algorithm=="fiap_original")])==10
        gate("BASELINE","aprovado" if baseline_ok else "falhou",["outputs/experiments/results.csv"],"Comparadores por cenário e referência FIAP no TSP")
        gate("PRI","aprovado" if len(table[table.scenario.str.startswith("sp_sensitivity_")])==4 and ok else "falhou",["outputs/experiments/results.csv","outputs/validation/pytest.xml"],"Caso conhecido e quatro coeficientes de sensibilidade")
    existing_report("API",folder/"http.json",lambda d:d.get("implementation_hash")==implementation_hash())
    existing_report("API_LLM",folder/"http-llm.json",lambda d:d.get("transport")=="real_http_loopback" and {r["kind"] for r in d.get("checks",[])}=={"instructions","daily_report","qa","weekly_report"} and all(r.get("passed") and r.get("real_origin") for r in d["checks"]))
    existing_report("MAP",folder/"maps-browser.json",lambda d:len(d.get("maps",[]))>=3 and len(d.get("static_maps",[]))>=3 and all((PROJECT_ROOT/r["path"]).is_file() and file_hash(PROJECT_ROOT/r["path"])==r["sha256"] for r in d["maps"]+d["static_maps"]))
    llm_path=OUTPUT_ROOT/"llm"/"evaluation"/"summary.json"
    llm=existing_report("EVAL",llm_path,lambda d:d.get("completed")==60)
    if not llm:gate("LLM","pendente",[relative_path(llm_path)],"Chamadas reais ainda não comprovadas")
    elif llm.get("status")=="pendente":gate("LLM","pendente",[relative_path(llm_path)],"Avaliação real ainda incompleta")
    else:
        records=[json.loads(p.read_text(encoding="utf-8")) for p in (OUTPUT_ROOT/"llm"/"evaluation").glob("v?_c??.json")]
        real=[r for r in records if r.get("accepted") and (r["answer"]["provenance"]["origin"]=="api" or r["answer"]["provenance"].get("original_origin")=="api")]
        from .llm_evaluation import fixed_cases,evaluation_pairs,assess
        from .llm import build_context,contract_hash,PROMPTS
        from .budget import BudgetLedger
        ledger_rows={r["id"]:r for r in BudgetLedger(OUTPUT_ROOT/"llm/budget.sqlite3").summary()["calls"]} if real else {}
        cases_by_id={c["id"]:c for c in fixed_cases()}
        pairs=evaluation_pairs()
        expected={(version,case_id) for version in PROMPTS for case_id in cases_by_id}
        observed={(r.get("prompt_version"),r.get("case_id")) for r in records}
        coherent=len(records)==60 and observed==expected and llm.get("cases_sha256")==canonical_hash(fixed_cases())
        raw_rows=[json.loads(p.read_text(encoding="utf-8")) for p in (OUTPUT_ROOT/"llm/responses").glob("*.json")]
        for record in records:
            case=cases_by_id.get(record.get("case_id"))
            if case is None:coherent=False;continue
            context=build_context(case["kind"],pairs[case["dataset"]],case["question"])
            coherent &= record.get("context_hash")==canonical_hash(context) and record.get("case_hash")==canonical_hash(case)
            coherent &= record.get("contract_hash")==contract_hash(case["kind"],record["prompt_version"],context)
            # Também uma resposta rejeitada precisa provar execução real e custo.
            attempts=[r for r in raw_rows if r.get("origin")=="api" and r.get("context_hash")==record.get("context_hash") and r.get("contract_hash")==record.get("contract_hash") and r.get("prompt_version")==record.get("prompt_version")]
            coherent &= any(ledger_rows.get(r.get("reservation_id"),{}).get("state")=="settled" and ledger_rows[r["reservation_id"]].get("response_id")==r.get("response_id") and (r.get("response_model")=="gpt-6-luna" or str(r.get("response_model","")).startswith("gpt-6-luna-")) for r in attempts)
        for record in real:
            case=cases_by_id[record["case_id"]]
            context=build_context(case["kind"],pairs[case["dataset"]],case["question"])
            coherent &= record["context_hash"]==canonical_hash(context) and record["case_hash"]==canonical_hash(case)
            coherent &= record.get("contract_hash")==contract_hash(case["kind"],record["prompt_version"],context)
            coherent &= assess(record["answer"],case,context)==record["assessment"] and record["assessment"]["factual_consistency"]
            provenance=record["answer"]["provenance"]
            coherent &= provenance.get("contract_hash")==record.get("contract_hash")
            response_model=provenance.get("response_model","")
            coherent &= bool(response_model and (response_model=="gpt-6-luna" or response_model.startswith("gpt-6-luna-")))
            row=ledger_rows.get(provenance.get("reservation_id"),{})
            coherent &= row.get("state")=="settled" and row.get("response_id")==provenance.get("response_id")
            raw_path=OUTPUT_ROOT/"llm/responses"/f"{provenance.get('reservation_id')}.json"
            if not raw_path.is_file():coherent=False;continue
            raw=json.loads(raw_path.read_text(encoding="utf-8"))
            coherent &= raw.get("origin")=="api" and raw.get("context_hash")==canonical_hash(context) and raw.get("response_id")==provenance.get("response_id")
        gate("LLM","aprovado" if llm["status"]=="aprovado" and coherent and len(real)>0 else "falhou",[relative_path(llm_path)],f"{len(real)} respostas reais aceitas e recertificadas")
    budget_path=OUTPUT_ROOT/"llm"/"budget-summary.json"
    if budget_path.exists():
        from .budget import BudgetLedger
        budget=BudgetLedger(OUTPUT_ROOT/"llm"/"budget.sqlite3").summary()
        gate("COST","aprovado" if budget["committed_upper_usd"]<=1 and ok else "falhou",[relative_path(budget_path)],f"Compromisso conservador acumulado: US$ {budget['committed_upper_usd']:.6f}")
    else:gate("COST","pendente",[relative_path(budget_path)],"Nenhuma chamada real contabilizada ainda")
    for identifier,path in [("NB",folder/"notebooks.json"),("DOC",folder/"document-visual.json"),("REPRO",folder/"portability.json"),("CONSIST",folder/"consistency.json")]:
        existing_report(identifier,path,lambda d:all((PROJECT_ROOT/r["path"]).is_file() and file_hash(PROJECT_ROOT/r["path"])==r["sha256"] for r in d.get("artifacts",[])))
    video=PROJECT_ROOT/"docs"/"ROTEIRO_VIDEO.md"
    gate("VIDEO","aprovado" if video.is_file() and "14:30" in video.read_text(encoding="utf-8") else "pendente",[relative_path(video)],"Roteiro cronometrado em até 15 minutos")
    # Arquivos ignorados não fazem parte da entrega; a inspeção cobre todas as fontes e artefatos textuais rastreáveis.
    listed=subprocess.run(["git","ls-files","--cached","--others","--exclude-standard"],cwd=PROJECT_ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace")
    suspect=[]
    for name in listed.stdout.splitlines():
        p=PROJECT_ROOT/name
        if p.suffix.lower() not in {".py",".md",".json",".toml",".ipynb",".html",".txt",".csv",".ps1",".example"}:continue
        text=p.read_text(encoding="utf-8",errors="replace")
        if re.search(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}",text):suspect.append(name)
    secret_ok=not suspect and subprocess.run(["git","check-ignore",".env"],cwd=PROJECT_ROOT,capture_output=True).returncode==0
    gate("SECRET","aprovado" if secret_ok else "falhou",[".gitignore"],f"Chave fora dos artefatos; arquivos suspeitos: {suspect}")
    considered=gates if profile=="entrega" else [g for g in gates if g["id"] in {"DOM","GA","ORACLE","ADV","TAMPER","FAIL","BASE","CVRP","SECRET"}]
    status="falhou" if any(g["status"]=="falhou" for g in considered) else "pendente" if any(g["status"]=="pendente" for g in considered) else "aprovado"
    report={"status":status,"profile":profile,"created_at":utc_now(),"gates":gates,"pending":[g["id"] for g in considered if g["status"]=="pendente"],"failed":[g["id"] for g in considered if g["status"]=="falhou"]}
    write_json(folder/"acceptance.json",report)
    return report
