# Roteiro de apresentação

Duração planejada: **14:30**, com 30 segundos de margem até o limite de 15 minutos.
Gravação, publicação e submissão serão feitas pela equipe. Ensaiar os comandos
antes de gravar e usar as soluções salvas para evitar espera durante o vídeo.

| Tempo | Apresentador sugerido | Conteúdo e evidência |
|---|---|---|
| 00:00–01:00 | Lucas | Problema, entregas fictícias, ruas reais e objetivo do projeto |
| 01:00–03:00 | Lucas | Contrato, capacidade, autonomia com retorno e prioridades; caso conhecido J=3,6 |
| 03:00–05:00 | Eduardo | Evolução FIAP, IDs/separadores, OX, torneio, mutação, elitismo e reparação |
| 05:00–07:30 | Eduardo | Definir Guloso, OR-Tools e GA selecionado; três configurações, dez sementes e resultados favoráveis/desfavoráveis |
| 07:30–09:00 | Renan | Mapas de 12/30/60, ruas direcionadas, retorno e utilização da frota |
| 09:00–11:00 | Renan | API no Swagger, otimização, recuperação e rejeição de entrada inválida |
| 11:00–13:00 | Renan | Exemplo real do Luna: instruções, relatório semanal e pergunta sem suporte |
| 13:00–14:30 | Equipe | Controle factual, teto US$ 1, validação, limitações e conclusão |

## Preparação

Abrir os dois notebooks executados e as figuras `medical_objective.png`,
`benchmark_gap.png` e `convergence.png`. Separar os três mapas HTML. Iniciar
`tc2 api` e abrir `http://127.0.0.1:8000/docs`. Usar a configuração selecionada
em `outputs/experiments/selection.json` e conferir o último aceite.

```powershell
tc2 validar --perfil entrega
tc2 api
```

## Demonstração da API

Em `POST /v1/optimizations`, enviar:

```json
{
  "scenario_id": "sp_evaluation_12",
  "algorithm": "genetic",
  "configuration": {
    "seed": 42,
    "population_size": 80,
    "mutation_probability": 0.1,
    "max_evaluations": 20000
  }
}
```

Mostrar `status`, métricas e certificação. Copiar o ID para
`GET /v1/solutions/{id}` e para `POST /v1/solutions/{id}/instructions`.
Na pergunta, usar “Qual é a distância total planejada?” e depois
“Qual paciente recebe cada medicamento?”. A segunda deve reconhecer dados
insuficientes. O relatório semanal pode usar as sete soluções salvas na evidência
da avaliação. Evitar repetir chamadas reais desnecessariamente; o teto é acumulado.

## Fala sobre a representação e a reparação

No bloco de 03:00–05:00, explicar os identificadores, os separadores e os
operadores. Reservar aproximadamente 45 segundos para o exemplo de reparação:

“Reparar é ajustar uma solução candidata que ultrapassou capacidade ou autonomia.
O código testa transferir uma entrega para outro veículo e, quando necessário,
trocar entregas. Dois veículos com capacidade de dez quilos receberam doze e seis.
Transferir uma entrega de três quilos deixa ambos com nove, mas ainda precisamos
conferir a distância e o retorno. O reparador pode falhar. Nos candidatos do GA,
cada chamada aceita até duas mudanças, mas pode avaliar muitas alternativas
para escolhê-las. Esse trabalho já pode ocorrer antes da primeira geração.”

Ao citar a correção do crossover, dizer que OX agora pode combinar pais distintos.
A comparação com o TSP FIAP avalia a implementação completa: outras etapas também
mudaram, e o novo GA coincide com a construção gulosa nesse caso. Não atribuir a
diferença observada exclusivamente ao crossover ou à evolução genética.

## Fala sobre os métodos e os resultados

No bloco de 05:00–07:30, reservar os primeiros 45 segundos para explicar os
métodos, antes de mostrar os gráficos. Usar os 105 segundos restantes para a
seleção da configuração e os principais resultados; a duração total permanece
em 14:30.

“Guloso constrói as rotas considerando primeiro as restrições e depois o aumento
imediato do custo J em cada inserção.
Testamos ordens por prioridade, carga e proximidade. OR-Tools é a biblioteca de
otimização do Google; usamos seu solucionador de rotas com cinco segundos de
busca. GA significa algoritmo genético: várias soluções evoluem por seleção,
cruzamento e mutação. GA selecionado é a configuração escolhida no ajuste:
80 indivíduos e 10% de probabilidade de mutação por descendente. Selecionado
indica a escolha entre configurações do genético, sem garantir que ele vença
os outros métodos.”

Ao apontar a tabela, esclarecer que a escolha usou somente os cenários de
desenvolvimento, com três sementes por configuração. Na avaliação final,
cada configuração foi executada com dez sementes em dados separados.
População e mutação variam juntas; a comparação não isola o efeito de cada uma.

“Conferimos todas as restrições antes de apresentar rotas. Comparamos as três
configurações e mantivemos também os resultados em que o genético não melhorou
a construção gulosa ou ficou atrás de OR-Tools. A reparação consome parte do
orçamento e pode limitar a evolução nos problemas maiores.”

Ao mostrar a figura de evolução, apontar os registros da **semente 42**, sem
apresentar essa execução como a média das dez sementes:

“A linha azul parte de uma rota já válida e reduz J de 181,929 para 180,967,
aproximadamente 0,53%. J combina distância e chegada ponderada; a queda não
significa necessariamente menos quilômetros. O 80/10% completou 38 gerações.
O 160/20% avaliou a população inicial, mas não completou a geração seguinte.
O 240/30% e as três configurações com sessenta entregas interromperam a
inicialização e devolveram rotas iniciais válidas. Acabaram as vinte mil
avaliações permitidas; não foi o limite de tempo nem falta de capacidade da
máquina. Mais velocidade de processamento não aumenta esse teto.”

Círculo, quadrado e cruz distinguem resultados na mesma coordenada. Reforçar que
zero gerações completas não significa ausência de execução e que testes dos
operadores aprovados não comprovam eficácia da busca nas configurações sem
evolução suficiente. Para melhorar essa busca, seria necessário alterar a
inicialização ou a reparação, ou ampliar o orçamento, e repetir os experimentos.

Na tabela do notebook, o desvio `NaN` nos comparadores com uma única execução
significa que não há amostra suficiente para estimar dispersão; não é falha.
O relatório preenche esse campo com zero por convenção de apresentação.
Não apresentar esse zero como uma estimativa de variabilidade ou prova de
estabilidade entre execuções.

Manter as falas sobre dados e LLM abaixo nos seus blocos de mapa e integração,
respectivamente. Ensaiar o bloco de resultados em 02:30, priorizando a figura
médica e a curva de evolução; os detalhes dos benchmarks ficam disponíveis no
notebook e no relatório.

“Os dados hospitalares são fictícios. A malha de ruas é real, mas os tempos não
consideram trânsito em tempo real. Os pesos de prioridade são premissas do
experimento, sem validação clínica.”

“A LLM organiza fatos calculados em Python. Conferimos referências e sequência
de entregas, identificamos a origem do cache e contabilizamos as chamadas dentro
de US$ 1. A avaliação de dois prompts usa os mesmos 30 casos.”

## Condição antes de gravar

O vídeo final deve mostrar evidência real do Luna e o aceite integral aprovado.
Se a chave ainda estiver ausente, ensaiar as outras partes e manter a etapa da
LLM pendente. Não gravar uma resposta de teste como se viesse do serviço real.
Confirmar a divisão entre integrantes e ajustar a fala ao tempo de cada bloco.
