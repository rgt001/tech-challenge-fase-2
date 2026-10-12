# Dados, unidades e fontes

Os pontos de entrega representam unidades fictícias, sem cadastro de hospitais,
pacientes ou medicamentos reais. As ruas são reais, obtidas do OpenStreetMap.
A região escolhida é delimitada por longitudes -46,69 a -46,61 e latitudes
-23,59 a -23,52. A componente fortemente conexa retida contém 7.029 nós e
14.036 arestas direcionadas; isso permite ida e retorno entre os pontos sorteados.

`sources/osm` preserva a malha GraphML compactada, as geometrias vetoriais das
ruas e o manifesto da obtenção. A licença e atribuição são
[© OpenStreetMap contributors, ODbL 1.0](https://www.openstreetmap.org/copyright).
O recorte e as matrizes derivadas devem conservar essa atribuição e as condições
da licença quando redistribuídos.

Cada matriz usa o caminho de menor tempo estimado na malha direcionada. Distância,
duração e geometria são calculadas sobre as mesmas arestas. A velocidade usa
`maxspeed` do OSM quando disponível, imputação por tipo de rua e fallback de
30 km/h. Não representa trânsito atual. Restrições de conversão e condições
operacionais temporárias não são modeladas. A preparação usa
[OSMnx](https://osmnx.readthedocs.io/en/stable/user-reference.html).

| Campo | Interpretação |
|---|---|
| `depot`, `deliveries` | Nós na ordem usada pelas matrizes |
| `id` | Identificador único; localização não é identidade |
| `x`, `y` | Longitude e latitude, ou coordenadas cartesianas do benchmark |
| `load` | Carga entregue em kg no cenário médico |
| `priority` | Regular, urgente ou crítica; classificação simulada |
| `service_s` | Atendimento simulado em segundos |
| `capacity` | Carga máxima inicial do veículo |
| `max_distance` | Autonomia, incluindo o retorno ao depósito |
| `distance` | Metros no cenário médico; unidades originais nos benchmarks |
| `duration_s` | Tempo dirigido de deslocamento em segundos |
| `path_geometry` | Polilinha do mesmo trajeto da matriz, indexada por `i:j` |
| `source` | Semente, malha e premissas de origem |
| `split` | Desenvolvimento, avaliação ou caso de teste |

As sementes de desenvolvimento são 617+n e as de avaliação são 2026+n.
As escalas são 12 entregas/2 veículos, 30/3 e 60/5. Cargas são inteiros de 2 a
10 kg. Prioridades são sorteadas com proporções 55%, 30% e 15%; o atendimento
usa 180, 300 ou 420 segundos. Capacidade nominal é o teto de
1,35 × carga total / número de veículos, com autonomia de 50 km. Sete dias
simulados usam sementes 5000 a 5006 e datas de 5 a 11 de outubro de 2026.
Essas datas não comprovam operações ocorridas.

As variações de prioridade usam coeficientes 0, 0,01, 0,05 e 0,10. As variações
de restrições reduzem a capacidade nominal para 82%, arredondando para cima,
ou a autonomia para 25 km. Não se altera a matriz viária para favorecer um método.

## CVRPLIB e fonte FIAP

As instâncias A-n32-k5, A-n54-k7 e A-n80-k10 e suas soluções publicadas estão em
`sources/cvrplib`. O objetivo é exclusivamente a distância EUC_2D com arredondamento
original `floor(d+0,5)`, capacidades e números de veículos originais. Tempo,
autonomia e prioridades médicas não são adicionados ao benchmark. Os custos
de referência são 784, 1167 e 1763 unidades, respectivamente.

O endereço público da [CVRPLIB](https://galgos.inf.puc-rio.br/cvrplib/en/instances)
apresentou certificado TLS expirado na obtenção. A transferência usou o
[espelho mantido pelo autor](https://github.com/vidalt/CVRPLIB), com commit e hashes
registrados no manifesto; a verificação TLS permaneceu ativa. A URL original e a
URL efetivamente usada estão registradas para cada arquivo.

A base FIAP é preservada no commit indicado em `docs/EVOLUCAO_FIAP.md`.
Os scripts `baixar_fontes.py` e `preparar_dados.py` permitem refazer a preparação.
Uma nova obtenção do OSM pode refletir mudanças da fonte; os experimentos desta
entrega usam o snapshot salvo e seu hash.
