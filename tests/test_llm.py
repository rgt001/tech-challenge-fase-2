import json
import copy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
import pytest
from rotas_medicas.budget import BudgetLedger,BudgetExceeded,cost_micro
from rotas_medicas.baselines import solve_greedy
from rotas_medicas.llm import build_context,validate_selection,generate_grounded,LLMError


def selection(context):
    return copy.deepcopy({"status":"answered","reason":"none","sections":[{"heading":"overview","fact_ids":["s0.distance"]}],
            "instructions":context["active_routes"] and [{k:r[k] for k in ("vehicle_id","solution_id","delivery_ids")} for r in context["active_routes"]] if context["kind"]=="instructions" else [],"suggestions":[]})


def fake_client(body,*,status="completed",failure=False,usage=True):
    def create(**kwargs):
        if failure: raise TimeoutError("simulado")
        return NS(id="test_response",status=status,output_text=json.dumps(body),
                  usage=NS(input_tokens=100,output_tokens=100,input_tokens_details=NS(cached_tokens=0)) if usage else None)
    return NS(responses=NS(input_tokens=NS(count=lambda **kwargs:NS(input_tokens=100)),create=create))


def test_ledger_atomic_cap_and_reconciliation(tmp_path):
    ledger=BudgetLedger(tmp_path/"budget.db")
    def reserve(_):
        try:return ledger.reserve(0,400_000)
        except BudgetExceeded:return None
    with ThreadPoolExecutor(max_workers=8) as pool: ids=list(pool.map(reserve,range(20)))
    accepted=[i for i in ids if i]
    assert len(accepted)==5
    assert ledger.summary()["committed_upper_usd"]==1
    ledger.settle(accepted[0],input_tokens=0,output_tokens=10)
    assert ledger.summary()["remaining_usd"]==pytest.approx(.199995)
    with pytest.raises(ValueError):ledger.settle(accepted[0],input_tokens=0,output_tokens=0)
    assert cost_micro(1000,1000)==625


def test_known_facts_and_instruction_order(tiny):
    result=solve_greedy(tiny)
    context=build_context("instructions",[(tiny,result)])
    body=selection(context)
    assert validate_selection(body,context).status=="answered"
    body["instructions"][0]["delivery_ids"].reverse()
    with pytest.raises(LLMError,match="ordem"):validate_selection(body,context)


def test_exported_budget_survives_database_reconstruction(tmp_path):
    original=BudgetLedger(tmp_path/"budget.db")
    identifier=original.reserve(0,1_800_000)
    original.mark_unknown(identifier,"timeout")
    reconstructed=BudgetLedger(tmp_path/"reconstructed.db")
    assert reconstructed.summary()["committed_upper_usd"]==.9
    with pytest.raises(BudgetExceeded):reconstructed.reserve(0,300_000)


@pytest.mark.parametrize("change",["unknown_fact","unknown_vehicle","missing_stop","duplicate_route","unverified"])
def test_reject_adulterated_selection(tiny,change):
    context=build_context("instructions",[(tiny,solve_greedy(tiny))])
    body=selection(context)
    if change=="unknown_fact":body["sections"][0]["fact_ids"]=["inventado"]
    elif change=="unknown_vehicle":body["instructions"][0]["vehicle_id"]="ambulancia_inexistente"
    elif change=="missing_stop":body["instructions"][0]["delivery_ids"].pop()
    elif change=="duplicate_route":body["instructions"].append(body["instructions"][0])
    else:context["verified"]=False
    with pytest.raises(LLMError):validate_selection(body,context)


def test_cache_has_explicit_test_provenance(tiny,tmp_path):
    pair=(tiny,solve_greedy(tiny))
    context=build_context("daily_report",[pair])
    body=selection(context)
    result=generate_grounded("daily_report",[pair],output_root=tmp_path,client=fake_client(body),origin="test")
    assert result["sections"][0]["facts"][0]["value"]==pytest.approx(3)
    assert result["provenance"]["origin"]=="test"
    cached=generate_grounded("daily_report",[pair],output_root=tmp_path)
    assert cached["provenance"]["origin"]=="cache" and cached["provenance"]["original_origin"]=="test"
    assert len(BudgetLedger(tmp_path/"llm"/"budget.sqlite3").summary()["calls"])==1


def test_changed_prompt_cannot_reuse_old_response(tiny,tmp_path,monkeypatch):
    from rotas_medicas.llm import PROMPTS
    pair=(tiny,solve_greedy(tiny))
    body=selection(build_context("daily_report",[pair]))
    first=generate_grounded("daily_report",[pair],output_root=tmp_path,client=fake_client(body),prompt_version="v2")
    monkeypatch.setitem(PROMPTS,"v2",PROMPTS["v2"]+" Nova revisão.")
    second=generate_grounded("daily_report",[pair],output_root=tmp_path,client=fake_client(body),prompt_version="v2")
    assert first["provenance"]["contract_hash"]!=second["provenance"]["contract_hash"]
    assert len(BudgetLedger(tmp_path/"llm"/"budget.sqlite3").summary()["calls"])==2


@pytest.mark.parametrize("problem,reason",[("timeout","provider_unavailable"),("partial","incomplete_response"),("usage","incomplete_response"),("fact","inconsistent_response")])
def test_failures_preserve_accounting(tiny,tmp_path,problem,reason):
    pair=(tiny,solve_greedy(tiny))
    body=selection(build_context("daily_report",[pair]))
    if problem=="fact":body["sections"][0]["fact_ids"]=["falso"]
    client=fake_client(body,status="incomplete" if problem=="partial" else "completed",failure=problem=="timeout",usage=problem!="usage")
    with pytest.raises(LLMError) as exc:
        generate_grounded("daily_report",[pair],output_root=tmp_path,client=client,origin="test")
    assert exc.value.reason==reason
    summary=BudgetLedger(tmp_path/"llm"/"budget.sqlite3").summary()
    assert summary["committed_upper_usd"]>0
    assert not list((tmp_path/"llm"/"cache").glob("*.json"))
