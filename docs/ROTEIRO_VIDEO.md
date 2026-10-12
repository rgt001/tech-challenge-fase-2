# Roteiro de apresentação

Duração planejada: **14:30**, com 30 segundos de margem até o limite de 15 minutos.
Gravação, publicação e submissão serão feitas pela equipe. Ensaiar os comandos
antes de gravar e usar as soluções salvas para evitar espera durante o vídeo.

| Tempo | Apresentador sugerido | Conteúdo e evidência |
|---|---|---|
| 00:00–01:00 | Lucas | Problema, entregas fictícias, ruas reais e objetivo do projeto |
| 01:00–03:00 | Lucas | Contrato, capacidade, autonomia com retorno e prioridades; caso conhecido J=3,6 |
| 03:00–05:00 | Eduardo | Evolução FIAP, IDs/separadores, OX, torneio, mutação, elitismo e reparação |
| 05:00–07:30 | Eduardo | Três configurações, dez sementes, dados separados e resultados favoráveis/desfavoráveis |
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

## Fala sobre os resultados

“Conferimos todas as restrições antes de apresentar rotas. Comparamos as três
configurações e mantivemos também os resultados em que o genético não melhorou
a construção gulosa ou ficou atrás de OR-Tools. A reparação consome parte do
orçamento e pode limitar a evolução nos problemas maiores.”

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
