# Evolução da base FIAP

A referência é o commit `d236a2ae6a08fefdb8ee9f1ca3f8201223a92da3` do
[repositório FIAP](https://github.com/FIAP/genetic_algorithm_tsp).
Os oito arquivos originais usados na análise estão preservados em
`data/sources/fiap`, com hashes em `data/sources/manifest.json`.

| Aspecto | Base preservada | Implementação deste projeto |
|---|---|---|
| Problema | TSP, um circuito | Múltiplos veículos com capacidade e autonomia |
| Gene | Tupla de coordenadas | Identificador exclusivo de entrega |
| Divisão de rotas | Um percurso | Separadores para os veículos |
| Seleção | Roleta | Torneio de três indivíduos |
| Crossover | Chamada com o mesmo pai em `tsp.py` | OX entre pais distintos quando há diversidade |
| Mutação | Troca de vizinhos, apesar da descrição de inversão | Troca e inversão, escolhidas aleatoriamente |
| Elitismo | Um indivíduo no laço original | Dois indivíduos |
| Restrições | Distância de um ciclo | Precedência das restrições e reparação determinística |
| Métricas | Comprimento do circuito | Distância, chegadas, carga, frota, orçamento e certificação |
| Uso | Visualização com Pygame | Pacote, CLI, API, mapas e notebooks |

O crossover baseado em coordenadas distingue valores, mas não identifica pedidos.
Entregas diferentes no mesmo endereço podem ser eliminadas pelo teste de
pertencimento do OX original. Identificadores exclusivos resolvem essa ambiguidade.
O erro de passar o mesmo pai reduz a recombinação; corrigi-lo exige preservar as
restrições da representação e verificar a descendência.

A comparação com a base original usa somente um TSP compatível: 15 pontos
predefinidos, distância euclidiana original, sem carga, tempo ou prioridade.
`fiap_reference.py` reproduz os operadores e o erro do laço original a partir das
funções do arquivo preservado; remove apenas a dependência de interface gráfica.
As mesmas coordenadas e o mesmo orçamento de avaliações são usados pelo genético
novo. Essa comparação não mistura o TSP original com o problema hospitalar.

O arquivo `LICENSE` preservado declara CC0 1.0. O README original menciona MIT;
essa divergência é registrada, e o arquivo de licença efetivamente presente no
commit não foi substituído. A autoria FIAP permanece identificada.
