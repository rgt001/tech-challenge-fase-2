"""README deriva números da mesma tabela usada pelo relatório e pelos notebooks."""
from pathlib import Path
import json
from rotas_medicas.config import PROJECT_ROOT,OUTPUT_ROOT

analysis=json.loads((OUTPUT_ROOT/"analysis/summary.json").read_text(encoding="utf-8"))
selected=analysis["selected"]
rows=[]
for n in (12,30,60):
    line=[str(n)]
    for algo in ("greedy","genetic","ortools"):
        item=next(r for r in analysis["summaries"] if r["scenario"]==f"sp_evaluation_{n}" and r["algorithm"]==algo and (algo!="genetic" or r["configuration"]==selected))
        line.append(f"{item['objective_mean']:.3f}".replace(".",","))
    rows.append("| "+" | ".join(line)+" |")
evaluation=OUTPUT_ROOT/"llm/evaluation/summary.json"
llm=json.loads(evaluation.read_text(encoding="utf-8")) if evaluation.is_file() else None
llm_state=f"Avaliação real: **{llm['status']}**, prompt selecionado `{llm['selected']}`. Utilidade nos respondíveis: {100*llm['prompts'][llm['selected']]['answerable_useful_fraction']:.1f}%; dados ausentes corretos: {llm['prompts'][llm['selected']]['insufficient_correct']}/8. Compromisso conservador acumulado: US$ {llm['budget']['committed_upper_usd']:.6f}." if llm else "**Pendente:** configurar a chave específica e executar as chamadas reais ao Luna. Testes simulados não aprovam essa etapa."
text=f'''# Tech Challenge Fase 2

Otimização da distribuição fictícia de medicamentos e insumos com múltiplos
veículos, capacidade, autonomia e prioridades. A base FIAP evolui para um pacote
Python compartilhado por CLI, notebooks e FastAPI. O `gpt-6-luna` interpreta
soluções certificadas pela Responses API, com orçamento acumulado de US$ 1.

## Situação da entrega

{analysis['runs']} execuções estão tabuladas. Os dois notebooks foram executados,
e as soluções viáveis passaram pelo verificador independente. A comparação
mantém resultados desfavoráveis e falhas dos comparadores.

{llm_state}

O estado completo está em [outputs/validation/acceptance.json](outputs/validation/acceptance.json).
`aprovado`, `falhou` e `pendente` têm significados distintos; uma ausência de
acesso externo não conta como aprovação.

## Instalação reproduzível

Validado em Windows x64, CPU e Python 3.13. Outros ambientes não foram validados.
Na raiz da cópia do projeto:

```powershell
python -m venv .venv
.venv\\Scripts\\python -m pip install -r requirements-lock.txt
.venv\\Scripts\\python -m pip install -e . --no-deps
.venv\\Scripts\\python -m pip check
```

O pacote usa instalação editável junto aos dados do repositório. Não há caminhos
particulares da máquina nos contratos. A cópia para outra pasta e a execução
fora da raiz são conferidas em [outputs/validation/portability.json](outputs/validation/portability.json).

## Executar

```powershell
.venv\\Scripts\\tc2 otimizar sp_evaluation_12 --algoritmo genetic --mapa
.venv\\Scripts\\tc2 experimentos
.venv\\Scripts\\python scripts/gerar_analise.py
.venv\\Scripts\\tc2 api
.venv\\Scripts\\tc2 validar --perfil entrega
```

Swagger: `http://127.0.0.1:8000/docs`. A API escuta somente no endereço local.
Endpoints de saúde, cenários, otimização, solução persistida, instruções,
relatório diário/semanal e perguntas estão em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).
CLI e API não publicam rotas inválidas como utilizáveis. Falha da busca não é
prova de impossibilidade.

Experimentos usam checkpoints: dados e implementação precisam ter o mesmo hash,
e soluções viáveis são recertificadas antes do reaproveitamento. `--rapido` serve
somente para desenvolvimento e não aprova o perfil de entrega. Para forçar uma
execução nova, preservar os resultados antigos em outra pasta antes de executar.

## Resultados médicos

Configuração selecionada apenas nos dados de desenvolvimento: `{selected}`.
Valores médios de J, com dez sementes para cada configuração do GA:

| Entregas | Guloso | GA selecionado | OR-Tools |
|---|---|---|---|
{chr(10).join(rows)}

J combina distância em km e chegada ponderada; não representa apenas distância.
O GA inclui a reparação e a inicialização no teto de 20 mil chamadas de fitness,
com limites adicionais de tentativas e tempo. OR-Tools utiliza cinco segundos.
Esses orçamentos não são equivalentes. Nos cenários maiores, a reparação pode
consumir o orçamento antes de completar gerações; não atribuímos ganhos à
evolução quando eles não foram observados.

[Tabela completa](outputs/experiments/results.csv),
[resumos e dispersão](outputs/analysis/summary.csv) e
[gráficos comentados](outputs/analysis/summary.json).
SHA-256 da tabela: `{analysis['results_sha256']}`.

Os benchmarks A-n32-k5, A-n54-k7 e A-n80-k10 mantêm distâncias e capacidades
originais, com referências 784, 1167 e 1763. Seus gaps não são quilômetros.
A base FIAP é comparada apenas no TSP compatível de 15 pontos.

## Notebooks e artefatos

- [Otimização genética](notebooks/01_otimizacao_genetica.ipynb)
- [Aplicação hospitalar e LLM](notebooks/02_aplicacao_hospitalar_llm.ipynb)
- [Relatório técnico editável](Tech_Challenge_Fase2_Entrega.docx)
- [Relatório para leitura em PDF](outputs/report-pages/Tech_Challenge_Fase2_Entrega.pdf)
- [Roteiro de apresentação de 14:30](docs/ROTEIRO_VIDEO.md)
- [Mapa de 12 entregas](outputs/maps/sp_evaluation_12.html)
- [Mapa de 30 entregas](outputs/maps/sp_evaluation_30.html)
- [Mapa de 60 entregas](outputs/maps/sp_evaluation_60.html)

Os mapas HTML incluem ruas, trajetos e JavaScript localmente e abrem sem rede.
As figuras estáticas estão em `outputs/figures` e `outputs/maps`. A malha OSM,
matrizes e geometrias salvas usam os mesmos trajetos direcionados. Os tempos
são estimativas sem trânsito real. Os dados hospitalares, cargas, prioridades
e datas são fictícios. Detalhes e licenças: [data/README.md](data/README.md).

Para executar os notebooks do início ao fim:

```powershell
.venv\\Scripts\\python -m ipykernel install --prefix .venv --name python3
.venv\\Scripts\\python scripts/executar_notebooks.py
```

## Chave, avaliação e custo da LLM

Copiar `.env.example` para `.env` e configurar `OPENAI_API_KEY` localmente.
A chave não deve ser colocada em notebooks, commits, mensagens ou artefatos.
Usar exclusivamente `gpt-6-luna`; o preço conferido e os limites estão no ledger.

```powershell
.venv\\Scripts\\tc2 avaliar-llm
.venv\\Scripts\\python scripts/verificar_http_llm.py
```

São dois prompts e 30 casos fixos. A saída estruturada seleciona referências a
fatos e sequências; números e frases factuais são apresentados pelo Python.
Utilidade e clareza medem seleção e organização de fatos controlados, sem
pretender medir compreensão clínica. Dados ausentes exigem resposta explícita.
O contrato estruturado proíbe instruções em tipos diferentes de `instructions`.
A lista de referências fica restrita aos fatos existentes no contexto.
A primeira rodada falhou e foi preservada em `outputs/llm/attempts/initial-prompts`.
A segunda rodada reprovada está em `outputs/llm/attempts/contract-r2`.
A revisão do prompt usa os mesmos casos; as taxas finais não demonstram
generalização para perguntas novas. Todos os custos anteriores permanecem no ledger.
O segundo comando requer a API em execução na porta 8766 e verifica os quatro
endpoints por HTTP real. Reutiliza respostas da avaliação quando o cache tem
origem real. Os critérios estão em [docs/CRITERIOS_DE_ACEITE.md](docs/CRITERIOS_DE_ACEITE.md).

O ledger SQLite reserva o máximo antes de cada chamada, reconcilia o uso e
mantém a reserva quando o consumo é desconhecido. Não há retries automáticos.
O snapshot `outputs/llm/budget-summary.json` preserva o gasto acumulado ao
reconstruir o ambiente. **Não apagar o ledger ou seu snapshot para reiniciar
o orçamento.** Respostas de cache mantêm a origem original e são conferidas.
As novas chamadas solicitam explicitamente o nível de serviço `default`.
Hashes do prompt, esquema e contexto impedem reutilizar evidências de uma revisão
antiga. A conexão TLS usa certificados confiáveis do sistema, com validação ativa.

## Gerar a documentação

As tabelas e os números do relatório são derivados dos resultados salvos:

```powershell
.venv\\Scripts\\python scripts/gerar_relatorio.py
```

O DOCX permite edição e o PDF permite leitura direta no GitHub. Depois de alterar
o relatório, exportar novamente para PDF e revisar todas as páginas. As imagens
PNG de revisão são temporárias e não fazem parte do repositório. O registro de
inspeção mantém os hashes dos documentos finais; gerar o DOCX não aprova sua
apresentação automaticamente.

## Estrutura e referência

Arquitetura: [docs/ARQUITETURA.md](docs/ARQUITETURA.md). Aceite: [docs/CRITERIOS_DE_ACEITE.md](docs/CRITERIOS_DE_ACEITE.md).
Adaptação do algoritmo: [docs/EVOLUCAO_FIAP.md](docs/EVOLUCAO_FIAP.md).
Os resultados da contagem inicial incompleta foram invalidados e não integram a
comparação final.
O repositório contém dados, código e evidências da entrega final. Rodadas reprovadas
dos prompts permanecem documentadas pelos resumos, com seus custos incluídos no ledger.

Equipe: Lucas dos Santos Batista (RM 376835), Eduardo Fagner Costalonga Ribeiro
(RM 376780) e Renan Gonçalves Micheletti (RM 376743).
Gravação do vídeo e submissão ficam com a equipe.
'''
(PROJECT_ROOT/"README.md").write_text(text,encoding="utf-8")
print("README atualizado a partir das evidências.")
