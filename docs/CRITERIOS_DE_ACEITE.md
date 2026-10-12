# Critérios de aceite

Cada requisito possui evidência verificável. `pendente` e `falhou` impedem aprovação global.

| ID | Requisito | Evidência exigida |
|---|---|---|
| BASE | Adaptação do código FIAP | Código de referência e descrição das mudanças |
| DOM | Dados e contratos válidos | Testes de IDs, unidades, matrizes, parâmetros e entradas inválidas |
| GA | Representação e operadores | Permutações preservadas, seleção, OX, troca/inversão, elitismo, reparação |
| PRI | Prioridade influencia fitness | Caso conhecido e análise de sensibilidade de pesos |
| VALID | Soluções verificadas independentemente | Visitas, capacidade, autonomia incluindo retorno, horários e métricas recalculados |
| ORACLE | Casos pequenos com ótimo conhecido | Enumeração independente e comparação com o núcleo |
| ADV | Casos adversos | Mesmo endereço, assimetria, limites, inalcançáveis e impossíveis |
| TAMPER | Certificador rejeita adulterações | Entrega ausente/duplicada, veículo desconhecido, carga/distância/horários falsos |
| GEO | Dados reais de ruas | OSM salvo, matrizes/traçados coerentes, fonte/data/hash |
| SCEN | Cenários médicos | Escalas 12/30/60, variações e sete dias; ajuste separado de avaliação |
| CVRP | Benchmarks públicos | Três instâncias originais, regras de distância e ótimo conhecido preservados |
| EXP | Comparações reproduzíveis | 3 configurações x 10 sementes, parâmetros, tempos, interrupções e dispersão |
| BASELINE | Comparadores | Guloso, OR-Tools e FIAP no TSP compatível, soluções certificadas |
| MAP | Mapas e gráficos | HTML autossuficiente aberto no navegador e PNGs inspecionados |
| API | API real documentada | Processo HTTP real, rotas de otimização/consulta/LLM e Swagger |
| API_LLM | Endpoints de linguagem por HTTP real | Instruções, relatório diário/semanal e pergunta com respostas da API real ou cache de origem real, conferidas contra os fatos |
| LLM | Integração real Luna | Responses API real, origem/modelo/uso e respostas fundamentadas |
| COST | Teto US$ 1 | Ledger persistente, reservas atômicas e retries contabilizados |
| EVAL | Avaliação dos prompts | 30 casos, 2 prompts, respostas aceitas consistentes e utilidade >=90% |
| FAIL | Falhas da LLM | Timeout, indisponibilidade, incompleta/inconsistente, cache identificado |
| NB | Dois notebooks | Execução integral em kernel novo e saídas coerentes com evidências |
| DOC | Relatório técnico | Conteúdo completo e todas as páginas renderizadas/inspecionadas |
| VIDEO | Roteiro <=15 min | Agenda cronometrada, comandos, mapas e exemplo real da LLM |
| REPRO | Reprodução/portabilidade | Instalação limpa, dependências fixadas, comandos, caminhos portáveis |
| CONSIST | Consistência da entrega | Dados e métricas iguais em outputs, notebooks, README e relatório |
| SECRET | Segredos fora da entrega | Varredura de fontes/artefatos e exclusões Git |

O verificador não reutiliza fitness/reparação para provar validade. Casos de referência
e testes de adulteração impedem que validação apenas confirme a própria implementação.
Ausência de chave não aprova a integração; ausência de renderização não aprova o relatório.

As páginas PNG usadas na inspeção visual são temporárias. A versão publicada
conserva o DOCX, o PDF e o registro de inspeção com os hashes dos documentos finais.
Os resumos das rodadas reprovadas da LLM preservam seus resultados e custos;
as respostas individuais da comparação final permitem a conferência factual.
