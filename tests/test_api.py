from fastapi.testclient import TestClient
from rotas_medicas.api import create_app


def test_http_optimization_roundtrip_and_swagger(tiny,tmp_path,monkeypatch):
    client=TestClient(create_app(tmp_path/"data",tmp_path/"outputs"))
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200
    schema=client.get("/openapi.json").json()
    assert "/v1/optimizations" in schema["paths"]
    r=client.post("/v1/optimizations",json={"scenario":tiny.model_dump(mode="json"),"algorithm":"greedy"})
    assert r.status_code == 200,r.text
    solution=r.json()
    assert solution["verification"]["valid"]
    assert client.get(f"/v1/solutions/{solution['id']}").json()["metrics"]["objective"] == 3.6
    assert client.post("/v1/optimizations",json={}).status_code == 422
    assert client.get("/v1/scenarios/not_found").status_code == 404
    assert client.get("/v1/solutions/../../secret").status_code in (404,422)
    # Avaliação incompleta não pode transformar ausência de chave em erro interno.
    import dotenv
    from rotas_medicas.storage import write_json
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    monkeypatch.setattr(dotenv,"load_dotenv",lambda *args,**kwargs:False)
    write_json(tmp_path/"outputs/llm/evaluation/summary.json",{"status":"pendente","completed":0})
    for endpoint,body in [("instructions",None),("daily-report",None),("questions",{"question":"Qual a distância?"})]:
        missing=client.post(f"/v1/solutions/{solution['id']}/{endpoint}",json=body)
        assert missing.status_code==503
        assert missing.json()["detail"]["reason"]=="missing_credentials"
    assert client.post("/v1/reports/weekly",json={"solution_ids":[solution["id"]]}).status_code==503


def test_persisted_tampering_is_rejected(tiny,tmp_path):
    from rotas_medicas.storage import load_solution,write_json
    outputs=tmp_path/"outputs"
    client=TestClient(create_app(tmp_path/"data",outputs))
    result=client.post("/v1/optimizations",json={"scenario":tiny.model_dump(mode="json"),"algorithm":"greedy"}).json()
    path=outputs/"runtime"/"solutions"/f"{result['id']}.json"
    solution=load_solution(path)
    solution.routes[0].distance=1
    write_json(path,solution)
    assert client.get(f"/v1/solutions/{solution.id}").status_code == 409
