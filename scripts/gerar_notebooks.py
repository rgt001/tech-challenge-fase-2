"""Constrói dois notebooks narrativos; resultados experimentais permanecem rastreáveis."""
from pathlib import Path
import nbformat as nbf
from rotas_medicas.config import PROJECT_ROOT


def md(text):return nbf.v4.new_markdown_cell(text.strip())
def code(text):return nbf.v4.new_code_cell(text.strip())
def save(name,cells):
    nb=nbf.v4.new_notebook(cells=cells,metadata={"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.13"}})
    path=PROJECT_ROOT/"notebooks"/name;path.parent.mkdir(parents=True,exist_ok=True)
    nbf.write(nb,path);print(path.name)


setup='''
from pathlib import Path
import json
import pandas as pd
from IPython.display import display, Image, Markdown
from rotas_medicas.config import PROJECT_ROOT as ROOT
from rotas_medicas.storage import load_scenario, load_solution, canonical_hash
from rotas_medicas.verification import verify_solution
results = pd.read_csv(ROOT / "outputs/experiments/results.csv")
analysis = json.loads((ROOT / "outputs/analysis/summary.json").read_text(encoding="utf-8"))
selected = analysis["selected"]
METHOD_LABELS = {"greedy":"Guloso", "ortools":"OR-Tools", "genetic":"Algoritmo genético", "fiap_original":"Referência FIAP"}
CONFIGURATION_LABELS = {"pop80_mut10":"80 / 0,10", "pop160_mut20":"160 / 0,20", "pop240_mut30":"240 / 0,30", "baseline":"Comparador", "reference":"Referência original"}
TERMINATION_LABELS = {"evaluation_budget":"Limite de avaliações de fitness", "candidate_attempt_budget":"Limite de tentativas de candidatos", "time_limit":"Limite de tempo"}
presentation = results.assign(método=results.algorithm.replace(METHOD_LABELS),
    configuração=results.configuration.replace(CONFIGURATION_LABELS)).rename(columns={"scenario":"cenário"})
print("Configuração escolhida apenas no desenvolvimento (população / mutação):", CONFIGURATION_LABELS[selected])
print("Execuções tabuladas:", len(results))
print("SHA-256 da tabela:", analysis["results_sha256"])
'''
save("01_otimizacao_genetica.ipynb",[
md("""# Tech Challenge Fase 2 — Otimização de rotas médicas

Este notebook apresenta a representação, os operadores, a conferência das restrições e a comparação experimental. Os pontos de entrega são fictícios e os tempos são estimados sobre ruas reais. A função objetivo representa uma preferência de planejamento; seus pesos não foram validados clinicamente.

O núcleo está no pacote `rotas_medicas`, também utilizado pela API e pela CLI. Para reproduzir a análise completa, executar antes `tc2 experimentos` e `python scripts/gerar_analise.py`. As células abaixo executam novamente um exemplo e analisam os registros completos, com a origem de cada resultado explícita."""),
code(setup),
md("""## 1. Dados e problema

Cada veículo sai do mesmo depósito com toda a carga da sua rota e retorna ao final. As entregas devem ser visitadas exatamente uma vez. A carga inicial não pode ultrapassar a capacidade e a distância completa deve respeitar a autonomia. Dois pedidos no mesmo endereço continuam sendo duas entregas distintas.

A distância é medida em metros nos dados médicos. A duração é medida em segundos e pode ser assimétrica, pois as ruas têm sentidos de circulação. A carga é expressa em kg. Cada par da matriz conserva a geometria do mesmo percurso usado para calcular distância e tempo."""),
code('''
scenario = load_scenario(ROOT / "data/scenarios/sp_evaluation_30.json")
display(pd.DataFrame([d.model_dump() for d in scenario.deliveries]).drop(columns=["x","y"]).head(10))
display(pd.DataFrame([v.model_dump() for v in scenario.vehicles]))
print("Distribuição das prioridades:", pd.Series([d.priority.value for d in scenario.deliveries]).value_counts().to_dict())
print("Matriz assimétrica:", any(abs(scenario.distance[i][j]-scenario.distance[j][i])>1e-6 for i in range(31) for j in range(31)))
'''),
md("""## 2. Objetivo e resposta conhecida

Entre soluções viáveis, minimizamos **J = distância em km + α × soma dos minutos de chegada ponderados**. Usamos α = 0,05 km/min e pesos 1, 3 e 10 para prioridades regular, urgente e crítica. Cada veículo tem um relógio próprio, iniciado na saída comum. O atendimento de uma parada atrasa as seguintes.

Antes de interpretar cenários grandes, conferimos um caso pequeno. Num triângulo com três lados de 1 km e viagens de um minuto, visitar primeiro a entrega crítica produz J = 3 + 0,05 × (10 × 1 + 1 × 2) = 3,6. A ordem inversa produz 4,05. O oráculo abaixo enumera as alternativas sem utilizar a avaliação do genético."""),
code('''
from rotas_medicas.domain import Scenario,Location,Delivery,Vehicle,GAConfig
from rotas_medicas.oracle import exact_small
tiny = Scenario(id="notebook_oracle",description="Caso independente de duas entregas",coordinates="cartesian",
    depot=Location(id="D",name="Depósito",x=0,y=0),
    deliveries=[Delivery(id="A",name="Crítica",x=1,y=0,load=1,priority="critica",service_s=0),Delivery(id="B",name="Regular",x=0,y=1,load=1,service_s=0)],
    vehicles=[Vehicle(id="V1",capacity=2,max_distance=3000)],
    distance=[[0,1000,1000],[1000,0,1000],[1000,1000,0]],duration_s=[[0,60,60],[60,0,60],[60,60,0]])
oracle = exact_small(tiny)
display(oracle)
assert abs(oracle["objective"]-3.6)<1e-9
'''),
md("""## 3. Representação e adaptação do algoritmo genético

A base usa coordenadas como genes e chama OX com o mesmo pai; isso reduz a recombinação e não conserva a identidade de pedidos em coordenadas repetidas. A nova representação usa identificadores únicos, convertidos em índices internos positivos, com separadores negativos para dividir a frota.

A seleção usa torneio de três indivíduos, crossover OX com probabilidade 0,90, mutação por troca ou inversão e dois elites. Primeiro se comparam as restrições; só depois, o objetivo. Um candidato curto e inválido não supera uma solução viável.

**Reparação não significa executar mais gerações.** A função examina uma solução candidata e testa transferir entregas de uma rota que viola capacidade ou autonomia para posições nas rotas de outros veículos. Quando necessário, testa trocas entre veículos. Ela prefere reduzir o total de violações; em caso de empate, compara J. Todas as entregas são preservadas.

Por exemplo, dois veículos com capacidade de 10 kg recebem 12 kg e 6 kg. Transferir uma entrega de 3 kg deixa ambos com 9 kg, mas ainda é necessário conferir a distância completa e a autonomia. A função para quando a solução fica válida, não encontra uma mudança melhor ou atinge seu limite. Ela pode terminar sem corrigir todas as violações.

Nos candidatos do GA que recebem reparação, cada chamada permite até duas mudanças aceitas. A construção gulosa pode usar até 12. Para escolher uma mudança, o código pode avaliar muitas alternativas; duas mudanças não significam apenas duas avaliações. A reparação ocorre na inicialização e também em parte dos descendentes durante a evolução."""),
code('''
import random
from rotas_medicas.genetic import encode,decode,order_crossover,mutate,solve_genetic
parent1 = encode([[1,2],[3,4]])
parent2 = encode([[4,2,1],[3]])
rng = random.Random(42)
child = mutate(order_crossover(parent1,parent2,rng),rng,1.0)
print("Pais:",parent1,parent2)
print("Filho:",child,"Rotas:",decode(child,2))
assert sorted(child)==sorted(parent1)
'''),
md("""## 4. Execução e certificação

Este exemplo é uma execução nova do núcleo. O teto de 20 mil chamadas de fitness inclui a inicialização e os candidatos avaliados pela reparação. Também se limitam as tentativas da população para encerrar a repetição de indivíduos já conhecidos. A melhor solução viável observada é preservada quando o orçamento termina. Custos de inserção de rotas parciais são registrados separadamente; a certificação final não é uma avaliação de busca."""),
code('''
small = load_scenario(ROOT / "data/scenarios/sp_evaluation_12.json")
demo = solve_genetic(small,GAConfig(population_size=80,mutation_probability=.10,max_evaluations=20000,seed=42))
certificate = verify_solution(small,demo)
assert demo.status=="feasible" and certificate.valid
display(demo.metrics.model_dump())
print("Avaliações de fitness:",demo.metadata["evaluations"],"Tentativas:",demo.metadata["candidate_attempts"],"Término:",TERMINATION_LABELS[demo.metadata["termination"]])
saved = load_solution(ROOT / "outputs/experiments/runs/sp_evaluation_12" / "genetic_pop80_mut10_42.json")
assert abs(saved.metrics.objective-demo.metrics.objective)<1e-9
adulterated = demo.model_copy(deep=True)
adulterated.routes[0].stops.pop()
print("Adulteração rejeitada:",not verify_solution(small,adulterated).valid)
'''),
md("""## 5. Desenho experimental

Três configurações combinam populações 80/160/240 com mutações 0,10/0,20/0,30. Variamos os dois parâmetros juntos; esta comparação não isola o efeito da população nem da mutação. Cada configuração é avaliada com dez sementes nos cenários finais. O ajuste usa apenas três cenários de desenvolvimento, com três sementes por configuração. O resultado da seleção é salvo antes da avaliação final.

**Guloso** insere cada entrega considerando primeiro as violações e depois o aumento imediato de J. Escolhe a melhor entre três construções com ordens por prioridade/proximidade, carga decrescente e proximidade, seguidas de reparação. **OR-Tools** é a biblioteca de otimização do Google; usamos seu solucionador de roteamento com cinco segundos de busca e as mesmas restrições. **GA** significa algoritmo genético. **GA selecionado** identifica a configuração escolhida no desenvolvimento, 80 indivíduos e 10% de probabilidade de mutação por descendente; esse rótulo não significa que ele supera os demais métodos.

O GA usa limites de avaliações, tentativas e tempo. Esses orçamentos não são equivalentes: registramos os tempos e evitamos atribuir toda diferença ao algoritmo. Há atividades locais em paralelo durante a execução; os tempos não são um benchmark de hardware isolado. Nas tabelas, traduzimos os nomes dos métodos. Identificadores de cenários e valores do contrato da API são mantidos para localizar os registros originais."""),
code('''
development = json.loads((ROOT / "outputs/experiments/selection.json").read_text(encoding="utf-8"))
display(pd.DataFrame.from_dict(development["mean_ratios"],orient="index",columns=["razão média GA/guloso em desenvolvimento"]).rename(index=CONFIGURATION_LABELS))
medical = presentation[presentation["cenário"].isin(["sp_evaluation_12","sp_evaluation_30","sp_evaluation_60"])]
display(medical.groupby(["cenário","método","configuração"]).agg(execuções=("status","size"),J_médio=("objective","mean"),J_desvio=("objective","std"),J_mínimo=("objective","min"),J_máximo=("objective","max"),tempo_médio_s=("elapsed_s","mean")))
'''),
code('display(Image(filename=str(ROOT / "outputs/figures/medical_objective.png")))'),
md("""Os pontos mantêm a dispersão entre sementes. A comparação de J considera simultaneamente distância e chegada ponderada. Mesmo quando duas soluções têm quilômetros próximos, uma pode chegar mais cedo às entregas prioritárias. O gráfico preserva situações em que o GA não melhora o guloso ou fica atrás de OR-Tools. Nas tabelas, o desvio amostral aparece como `NaN` para comparadores com uma única execução: não existe amostra suficiente para estimá-lo. O gerador do relatório preenche esse campo com zero nesses casos, por convenção de apresentação. Esse zero não é uma estimativa de variabilidade nem comprova estabilidade entre execuções. O `NaN` do notebook não representa falha de execução."""),
code('display(Image(filename=str(ROOT / "outputs/figures/runtime_critical.png")))'),
md("""## 6. Benchmarks e referência original

Na CVRPLIB, mantemos as capacidades, a frota e o arredondamento EUC_2D original: `floor(distância + 0,5)`. Os custos de referência são 784, 1167 e 1763. Nessas instâncias, o objetivo é somente a distância original; não adicionamos tempo ou prioridade. O gap é 100 × (custo / ótimo publicado − 1).

A base FIAP é comparada apenas no TSP compatível de 15 pontos. Sua reprodução conserva o crossover com o mesmo pai e um elite. Não comparamos sua distância de tela diretamente com quilômetros das rotas hospitalares.

Nesse TSP, o novo GA coincide com o resultado do guloso. A diferença em relação à reprodução FIAP não isola o efeito da correção do crossover: mudaram também a inicialização, a seleção, a mutação e o elitismo. O resultado não permite atribuir a melhora exclusivamente à evolução genética."""),
code('''
bench = presentation[presentation["cenário"].str.startswith("A-n")]
display(bench.groupby(["cenário","método","configuração"]).agg(gap_médio_pct=("gap_percent","mean"),gap_mínimo_pct=("gap_percent","min"),gap_máximo_pct=("gap_percent","max"),viáveis=("status",lambda s:(s=="feasible").sum())))
display(Image(filename=str(ROOT / "outputs/figures/benchmark_gap.png")))
display(Image(filename=str(ROOT / "outputs/figures/fiap_tsp.png")))
'''),
md("""## 7. Convergência, sensibilidade e limitações

A figura mostra o melhor J de uma solução válida já observado. Nos seis registros da semente 42 apresentados abaixo, a solução inicial do guloso já respeitava as restrições. Candidatos inválidos podem existir na população, mas não são os valores mostrados nessa curva.

Com 30 entregas, 80/10% registra 38 gerações e reduz J de 181,929 para 180,967, aproximadamente 0,53%. A configuração 160/20% avalia a população inicial, mas não completa uma geração seguinte; 240/30% não conclui a inicialização. As duas retornam a solução inicial válida. Com 60 entregas, as três interrompem a inicialização e também conservam uma solução válida. Zero gerações completas não significa que o programa não executou ou que nenhuma tentativa parcial ocorreu.

Linhas representam evolução registrada; marcadores distinguem observações inicial/final e resultados sobrepostos. O teto de 20 mil avaliações foi atingido nas seis execuções. Os tempos salvos são inferiores a um segundo, com limite de 120 segundos: o término ocorreu por avaliações, não por falta de capacidade da máquina. Um computador mais rápido não altera o número permitido de avaliações.

A inicialização e a reparação consomem parte do orçamento da busca como um todo. Esses resultados não demonstram otimização eficaz nas configurações sem evolução suficiente. Tornar essas etapas mais eficientes ou ampliar o orçamento exige novos experimentos; não há garantia de melhora. Uma redução de J também não implica necessariamente redução de quilômetros, pois J inclui a chegada ponderada por prioridade.

A análise de prioridade varia o coeficiente em um cenário de 30 entregas e uma semente. É uma exploração da premissa, sem alegação causal nem definição de pesos clínicos. A autonomia corresponde a distância, sem modelo de combustível ou bateria dependente da carga."""),
code('''
convergence_rows=[]
for delivery_count in (30,60):
    current_scenario=load_scenario(ROOT / f"data/scenarios/sp_evaluation_{delivery_count}.json")
    for configuration in ("pop80_mut10","pop160_mut20","pop240_mut30"):
        current_solution=load_solution(ROOT / f"outputs/experiments/runs/sp_evaluation_{delivery_count}" / f"genetic_{configuration}_42.json")
        assert current_solution.status=="feasible" and verify_solution(current_scenario,current_solution).valid
        metadata=current_solution.metadata
        assert metadata["termination"]=="evaluation_budget"
        initial_objective=metadata["initial_greedy_objective"]
        assert initial_objective is not None
        stage="Evolução registrada" if metadata["generations"] else ("População inicial avaliada" if metadata["history"] else "Inicialização incompleta")
        convergence_rows.append({"Entregas":delivery_count,"População / mutação":CONFIGURATION_LABELS[configuration],
            "Etapa ao parar":stage,"Gerações completas":metadata["generations"],"J inicial (guloso)":initial_objective,
            "J final":current_solution.metrics.objective,"Melhora de J (%)":100*(initial_objective-current_solution.metrics.objective)/initial_objective})
display(pd.DataFrame(convergence_rows).round(3))
display(Image(filename=str(ROOT / "outputs/figures/convergence.png")))
display(Image(filename=str(ROOT / "outputs/figures/priority_sensitivity.png")))
sensitivity=results[results.scenario.str.startswith("sp_sensitivity_")].copy()
sensitivity["Distância (km)"]=sensitivity.distance/1000
sensitivity["Chegada média das críticas (min)"]=sensitivity.critical_arrival_mean_s/60
sensitivity["Condição de término"]=sensitivity.termination.replace(TERMINATION_LABELS)
display(sensitivity.rename(columns={"scenario":"Cenário","objective":"J"})[["Cenário","Distância (km)","Chegada média das críticas (min)","J","Condição de término"]])
print("Términos do GA:",{TERMINATION_LABELS.get(key,key):value for key,value in analysis["termination_counts"].items()})
'''),
md("""## 8. Reprodução e conclusão

As soluções finais são certificadas independentemente. Uma busca sem solução viável retorna diagnóstico e não libera rotas. As tabelas, os gráficos e o relatório derivam dos mesmos registros, identificados por hash. O comando `tc2 validar --perfil entrega` reúne as verificações e mantém pendências externas explícitas.

O valor acadêmico do experimento está na formulação, na extensão da base, na comparação controlada e na análise dos limites. Superar todos os concorrentes não é condição de conclusão. Estes resultados não validam uso clínico ou operacional real.

Fontes: [FIAP](https://github.com/FIAP/genetic_algorithm_tsp), [CVRPLIB](https://galgos.inf.puc-rio.br/cvrplib/en/instances), [OSMnx](https://osmnx.readthedocs.io/en/stable/user-reference.html), [OR-Tools](https://developers.google.com/optimization/routing/vrp).""")
])

save("02_aplicacao_hospitalar_llm.ipynb",[
md("""# Tech Challenge Fase 2 — Aplicação hospitalar, mapas e LLM

Este notebook acompanha uma solução desde a certificação até as instruções e os relatórios. As métricas são calculadas pelo Python. O modelo `gpt-6-luna` organiza referências a fatos, preservando os valores e a sequência de paradas. Todas as respostas reais, de cache e de teste mantêm sua origem identificada.

O uso hospitalar é uma simulação. Não há pacientes, cadastros reais, estoque ou prazo clínico nos dados. O sistema não inventa esses campos quando uma pergunta os solicita."""),
code(setup),
md("""## 1. Solução operacional e horários

Uma rota só pode ser apresentada como utilizável depois de conferir todas as visitas, capacidade, autonomia e retorno. Os tempos abaixo são estimativas, acrescidas do atendimento simulado. A soma de durações dos veículos não corresponde ao tempo transcorrido de toda a operação, pois os veículos saem em paralelo."""),
code('''
scenario = load_scenario(ROOT / "data/scenarios/sp_evaluation_12.json")
solution = load_solution(ROOT / "outputs/experiments/runs/sp_evaluation_12" / f"genetic_{selected}_42.json")
assert verify_solution(scenario,solution).valid
from datetime import datetime,timedelta
initial = datetime.strptime(scenario.start_time,"%H:%M")
rows=[]
for route in solution.routes:
    for stop in route.stops:
        rows.append({"veículo":route.vehicle_id,"ordem":stop.order,"entrega":stop.delivery_id,"prioridade":stop.priority.value,
                     "chegada_estimada":(initial+timedelta(seconds=stop.arrival_s)).strftime("%H:%M:%S"),"carga_kg":stop.load})
display(pd.DataFrame(rows))
display(solution.metrics.model_dump())
'''),
md("""## 2. Mapas e utilização da frota

O HTML contém as ruas, os percursos e o JavaScript necessário para interação local. As linhas seguem os mesmos caminhos direcionados das matrizes; não são segmentos retos entre endereços. As figuras estáticas permitem a leitura sem executar JavaScript.

Abrir os arquivos em `outputs/maps/sp_evaluation_12.html`, `sp_evaluation_30.html` e `sp_evaluation_60.html`. Os marcadores usam azul para regular, laranja para urgente e vermelho para crítica; as cores das linhas distinguem os veículos."""),
code('''
display(Image(filename=str(ROOT / "outputs/maps/sp_evaluation_12.png")))
display(Image(filename=str(ROOT / "outputs/figures/fleet_capacity.png")))
'''),
md("""## 3. API e persistência

O teste abaixo exercita a aplicação em memória para ser executável sem iniciar outro processo. A evidência separada em `outputs/validation/http.json` registra a execução com Uvicorn e HTTP real. O Swagger fica em `/docs` após `tc2 api`.

A API salva cenários por hash e soluções por identificador. Uma consulta faz nova conferência da solução persistida. IDs inexistentes e pedidos inválidos têm respostas específicas. Os endpoints de linguagem usam a mesma certificação e o mesmo orçamento do pacote.

No JSON, `algorithm: "greedy"` é o identificador exigido pela API para o método **Guloso**. Traduzimos o nome na apresentação, mas preservamos o valor do contrato na requisição."""),
code('''
import tempfile,warnings
from starlette.exceptions import StarletteDeprecationWarning
warnings.filterwarnings("ignore",category=StarletteDeprecationWarning)
from fastapi.testclient import TestClient
from rotas_medicas.api import create_app
with tempfile.TemporaryDirectory() as temporary:
    with TestClient(create_app(output_root=Path(temporary))) as client:
        health=client.get("/health")
        response=client.post("/v1/optimizations",json={"scenario_id":"sp_evaluation_12","algorithm":"greedy"})
        assert response.status_code==200
        fetched=client.get("/v1/solutions/"+response.json()["id"])
        assert fetched.status_code==200
        print("Saúde:",health.json(),"Otimização:",response.status_code,"Consulta:",fetched.status_code)
http_evidence=json.loads((ROOT / "outputs/validation/http.json").read_text(encoding="utf-8"))
display(pd.DataFrame(http_evidence["checks"]))
'''),
md("""## 4. Relatório diário e semanal

Os sete dias são cenários simulados com 12 entregas cada. O relatório semanal soma distâncias e entregas e utiliza veículos-dia para não confundir o uso diário com veículos distintos da frota. A LLM não recalcula esses totais."""),
code('''
from rotas_medicas.llm_evaluation import evaluation_pairs
datasets=evaluation_pairs()
weekly_rows=[]
for day,day_solution in datasets["week"]:
    assert verify_solution(day,day_solution).valid
    weekly_rows.append({"dia":str(day.day),"entregas":day_solution.metrics.deliveries_served,"distância_km":day_solution.metrics.total_distance/1000,"veículos":day_solution.metrics.vehicles_used})
display(pd.DataFrame(weekly_rows))
print("Distância acumulada (km):",round(sum(r["distância_km"] for r in weekly_rows),3))
print("Entregas no período:",sum(r["entregas"] for r in weekly_rows))
display(Image(filename=str(ROOT / "outputs/figures/weekly_distance.png")))
'''),
md("""## 5. Integração fundamentada com Luna

A saída estruturada inclui referências a fatos, seções, sequências por veículo e sugestões autorizadas. A seleção da LLM é conferida antes de renderizar. Identificadores desconhecidos, paradas ausentes ou invertidas e referências inexistentes são rejeitados. Os textos factuais e seus números vêm do Python; a LLM escolhe o que é pertinente e como agrupar.

Essa escolha limita a liberdade de redação e facilita a conferência factual. A validação de estrutura, por si só, não prova que uma resposta é útil: os casos de avaliação também exigem fatos pertinentes ao pedido. Não é permitido inferir dados de pacientes, trânsito atual ou efeito clínico."""),
code('''
from rotas_medicas.llm import build_context
context=build_context("daily_report",[(scenario,solution)])
display(pd.DataFrame([{"referência":key,"valor":value["value"],"texto":value["text"]} for key,value in context["facts"].items() if key in {"s0.distance","s0.deliveries","s0.vehicles","s0.critical_arrival","s0.time_basis"}]))
evaluation_root=ROOT / "outputs/llm/evaluation"
demo_path=evaluation_root / "v2_c01.json"
if demo_path.exists():
    record=json.loads(demo_path.read_text(encoding="utf-8"))
    display(record.get("answer",{"status":"rejeitada","reason":record.get("error_reason")}))
else:
    print("PENDENTE: a chamada real ao Luna ainda não possui evidência. Nenhuma resposta de teste foi apresentada como real.")
'''),
md("""## 6. Dois prompts e 30 casos

Os casos fixos cobrem instruções, relatórios diários e semanais, perguntas respondíveis, oito solicitações de dados ausentes e duas tentativas de indução. Cada prompt é executado sobre o mesmo conjunto, totalizando 60 casos.

A rubrica mede correspondência do status, presença dos fatos necessários e preservação integral da ordem das instruções. A clareza da apresentação controlada considera duplicações, excesso de seções e volume de fatos numa pergunta direta. Ela não mede empatia, compreensão clínica ou qualidade de prosa livre.

Exigimos consistência factual em todas as respostas aceitas e utilidade de pelo menos 90% nos casos respondíveis. Respostas rejeitadas e falhas continuam registradas e entram na taxa de utilidade."""),
code('''
from rotas_medicas.llm_evaluation import fixed_cases
display(pd.DataFrame(fixed_cases())[["id","kind","question","category","expected_status"]])
summary_path=evaluation_root / "summary.json"
if summary_path.exists():
    evaluation=json.loads(summary_path.read_text(encoding="utf-8"))
    display(pd.DataFrame.from_dict(evaluation["prompts"],orient="index"))
    print("Aceite da LLM:",evaluation["status"],"Prompt selecionado:",evaluation["selected"])
    initial_path=ROOT / "outputs/llm/attempts/initial-prompts/summary.json"
    if initial_path.exists():
        initial=json.loads(initial_path.read_text(encoding="utf-8"))
        print("Rodada inicial preservada:",initial["status"])
        display(pd.DataFrame.from_dict(initial["prompts"],orient="index"))
        print("A revisão usa os mesmos casos; estas taxas não estimam generalização para perguntas novas.")
else:
    print("PENDENTE: avaliação real dos dois prompts. A execução deste notebook não substitui esse critério de aceite.")
'''),
md("""## 7. Custo, falhas e origem

Antes da chamada, a entrada é contada pela API de tokens. O ledger SQLite reserva atomicamente o custo máximo de entrada e saída, dentro de US$ 1 acumulado. Não há retry automático. Respostas incompletas são contabilizadas; timeouts sem consumo conhecido conservam a reserva. O snapshot JSON permite preservar o gasto ao reconstruir o ambiente.

Os testes simulados verificam concorrência, falta de provedor, resposta incompleta, referência inexistente, ordem adulterada e identificação do cache. Eles não comprovam disponibilidade do serviço real. A chave fica em variável de ambiente ou `.env` ignorado pelo Git e nunca é gravada em uma célula."""),
code('''
budget_path=ROOT / "outputs/llm/budget-summary.json"
if budget_path.exists():
    budget=json.loads(budget_path.read_text(encoding="utf-8"))
    print("Teto (USD):",budget["limit_usd"],"Compromisso conservador (USD):",budget["committed_upper_usd"],"Chamadas:",len(budget["calls"]))
else:
    print("Não há chamada real contabilizada neste projeto.")
acceptance_path=ROOT / "outputs/validation/acceptance.json"
if acceptance_path.exists():
    print("Consultar o aceite atualizado em outputs/validation/acceptance.json e executar tc2 validar --perfil entrega.")
'''),
md("""## 8. Limitações e apresentação

A distribuição é fictícia; os tempos ignoram trânsito, restrições de conversão e mudanças temporárias das vias. Os pesos de prioridade são premissas, não recomendações clínicas. O GA pode terminar sem melhorar a construção inicial, mesmo quando essa solução já é válida. Como explicado no notebook de otimização, reparar é ajustar um candidato; não significa executar mais gerações. O teto de avaliações inclui esse trabalho e pode limitar a evolução. As sugestões da LLM não demonstram que uma nova rota seria melhor: uma alteração operacional precisa de nova simulação e certificação.

O roteiro em `docs/ROTEIRO_VIDEO.md` organiza a apresentação em até 14 minutos e 30 segundos. Gravação, publicação e submissão ficam com a equipe. O projeto só recebe aprovação integral quando `tc2 validar --perfil entrega` não retorna falhas nem pendências.

Fontes: [Responses API](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), [gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [contagem de tokens](https://developers.openai.com/api/docs/guides/token-counting), [OpenStreetMap](https://www.openstreetmap.org/copyright).""")
])
