# A prorrogação mudou o resultado? — 2º turno de 2026 (Presidente)

Gerado automaticamente a partir dos logs de todas as urnas e dos Boletins de Urna publicados pelo TSE (`pipeline/late_votes_table.py`, `pipeline/analyze_extension.py`). Horários de Brasília.

## Resposta curta

**Não.** Depois das 17:00 foram registrados **34.050 votos** (0,027% dos votos no Brasil); outros 318 votos, de 4 urnas com log incompleto, não têm horário e foram tratados como se pudessem ser posteriores. Mesmo se **todos** esses 34.368 votos tivessem sido do mesmo candidato, a diferença final entre Lula e Flávio Bolsonaro (+4.430.191) ficaria entre **+4.395.956** e **+4.464.401**. Nenhum estado muda de vencedor em nenhum horário de corte; nenhum município muda de vencedor (no corte das 17:00, 1 município poderia terminar empatado).

> **Limite dos dados:** nenhum arquivo liga o horário de um voto ao candidato. O log da urna registra *quando*; o RDV registra *em quem*, embaralhado para proteger o sigilo. Por isso este relatório usa contagens e limites exatos, e marca como estimativa o que depende de hipótese.

## Se a votação parasse em cada horário (limites exatos)

| Corte | Votos depois* | Diferença Lula − Flávio possível | Lula % válidos possível | Vencedor muda? |
|---|---:|---|---|---|
| 17:00 | 34.368 | +4.395.956 a +4.464.401 | 51,77% a 51,80% | não |
| 17:01 | 20.508 | +4.409.816 a +4.450.544 | 51,78% a 51,79% | não |
| 17:05 | 5.631 | +4.424.693 a +4.435.672 | 51,78% a 51,79% | não |
| 17:10 | 4.515 | +4.425.809 a +4.434.557 | 51,78% a 51,79% | não |
| 17:30 | 3.536 | +4.426.788 a +4.433.578 | 51,78% a 51,79% | não |
| 18:00 | 2.311 | +4.428.013 a +4.432.355 | 51,78% a 51,79% | não |
| 18:30 | 1.016 | +4.429.308 a +4.431.064 | 51,78% a 51,79% | não |
| 19:00 | 329 | +4.429.995 a +4.430.377 | 51,79% a 51,79% | não |

\* inclui os 318 votos sem horário. Resultado oficial: Lula 64.256.232 (51,79%), Flávio Bolsonaro 59.826.041. O exterior entra inteiro: não houve prorrogação lá (todas as urnas encerraram até 18:15, hora local).

## Quantas urnas ficaram abertas, e onde

Às 17:01, 368.835 urnas ainda não tinham encerrado (filas e procedimento de encerramento); 6.714 ficaram abertas até 18:55 ou mais (grupo D). Dessas, **3.545 não receberam nenhum voto depois das 17:00** e 4.034 nenhum depois das 17:10; o último voto foi, na mediana, às 16:58. No total, o grupo D recebeu 4.710 votos depois das 17:00 (0,24% dos seus votos), 1.952 depois das 18:00 e 11 depois das 19:00.

| Grupo (encerramento no BU) | Urnas | Votos após 17:00 | Após 17:10 | Lula % (urnas do grupo) |
|---|---:|---:|---:|---:|
| A · encerrou até 17:01 | 125.624 | 302 | 0 | 49,0% |
| B · encerrou 17:01–17:10 (filas normais) | 358.891 | 27.114 | 0 | 52,5% |
| C · encerrou 17:10–18:55 | 6.668 | 1.924 | 518 | 58,9% |
| D · encerrou a partir de 18:55 ("mais duas horas") | 6.714 | 4.710 | 3.679 | 55,0% |

| Região | Urnas | Grupo D | Votos após 17:00 | Após 17:10 | Lula % (região) |
|---|---:|---:|---:|---:|---:|
| Centro-Oeste | 38.048 | 27 | 3.016 | 52 | 40,0% |
| Norte | 43.769 | 10 | 3.511 | 31 | 50,0% |
| Nordeste | 140.828 | 2.041 | 9.911 | 1.110 | 69,4% |
| Sul | 72.015 | 3 | 2.182 | 20 | 37,4% |
| Sudeste | 203.237 | 4.633 | 15.430 | 2.984 | 47,2% |

| UF | Grupo D | % das urnas | Votos após 17:00 | Lula % estado | Lula % urnas D | Diferença oficial | Parada às 17:00 |
|---|---:|---:|---:|---:|---:|---:|---|
| RJ | 2.981 | 7,9% | 4.126 | 46,9% | 45,7% | −603.640 | −607.766 a −599.514 |
| SP | 1.649 | 1,6% | 9.055 | 46,2% | 57,2% | −2.019.904 | −2.028.826 a −2.010.992 |
| BA | 973 | 2,7% | 4.180 | 71,3% | 72,3% | +3.876.497 | +3.872.317 a +3.880.677 |
| PE | 691 | 3,2% | 1.625 | 69,2% | 65,8% | +2.284.959 | +2.283.334 a +2.286.584 |
| PB | 309 | 2,9% | 465 | 67,5% | 52,8% | +928.849 | +928.384 a +929.314 |
| SE | 53 | 0,9% | 284 | 69,5% | 65,7% | +555.687 | +555.403 a +555.971 |
| DF | 17 | 0,2% | 976 | 45,7% | 46,3% | −154.318 | −155.294 a −153.342 |
| MT | 9 | 0,1% | 896 | 33,9% | 29,5% | −656.932 | −657.828 a −656.036 |
| PA | 9 | 0,0% | 1.299 | 55,0% | 55,5% | +490.509 | +489.210 a +491.807 |
| PI | 7 | 0,1% | 334 | 75,9% | 73,7% | +1.128.130 | +1.127.796 a +1.128.464 |
| MA | 3 | 0,0% | 951 | 69,5% | 83,3% | +1.578.260 | +1.577.309 a +1.579.202 |
| RN | 3 | 0,0% | 412 | 65,7% | 60,4% | +676.187 | +675.775 a +676.599 |
| AL | 2 | 0,0% | 640 | 60,8% | 70,2% | +408.481 | +407.841 a +409.121 |
| ES | 2 | 0,0% | 289 | 43,6% | 33,1% | −292.539 | −292.828 a −292.250 |
| RS | 2 | 0,0% | 820 | 42,2% | 48,8% | −1.049.826 | −1.050.646 a −1.049.006 |
| AC | 1 | 0,0% | 157 | 33,4% | 22,0% | −143.202 | −143.359 a −143.046 |
| GO | 1 | 0,0% | 725 | 40,3% | 26,8% | −759.779 | −760.504 a −759.054 |
| MG | 1 | 0,0% | 2.228 | 50,4% | 81,2% | +109.313 | +107.085 a +111.541 |
| PR | 1 | 0,0% | 909 | 37,4% | 34,1% | −1.724.940 | −1.725.849 a −1.724.031 |
| AM | 0 | 0,0% | 999 | 54,0% | — | +170.538 | +169.539 a +171.535 |
| CE | 0 | 0,0% | 1.069 | 68,9% | — | +2.216.646 | +2.215.577 a +2.217.713 |
| RO | 0 | 0,0% | 552 | 30,4% | — | −379.936 | −380.488 a −379.384 |

As urnas do grupo D estavam sobretudo no Sudeste (RJ e SP) e, dentro dos estados, nas capitais e grandes cidades: 5.862 das 6.714 em municípios onde Lula venceu. No conjunto deram 55,0% a Lula (Brasil: 51,8%) — percentual que inclui todos os votos dessas urnas, a maioria dados antes das 17:00.

## Biometria dos eleitores depois das 17:00

*Sem biometria* = leitura da digital falhou e o mesário liberou o eleitor, **mais** eleitores para quem a urna não pediu a digital. Referência: votos entre 16:00 e 17:00 nas mesmas urnas.

| Recorte | Sem biometria depois | 16:00–17:00 | Diferença | Votos depois |
|---|---:|---:|---:|---:|
| Todas as urnas, depois das 17:00 | 15,9% | 12,4% | 3,57 p.p. | 34.050 |
| Todas as urnas, depois das 17:10 | 12,9% | 12,4% | 0,52 p.p. | 4.197 |
| Todas as urnas, depois das 18:00 | 12,1% | 12,4% | -0,28 p.p. | 1.993 |
| Grupo D, depois das 17:00 | 12,8% | 12,2% | 0,64 p.p. | 4.710 |
| Grupo D, depois das 17:10 | 12,0% | 12,2% | -0,15 p.p. | 3.679 |
| Grupo D, depois das 18:00 | 12,1% | 12,2% | -0,10 p.p. | 1.952 |

A diferença logo depois das 17:00 vem da fila de encerramento (mais falhas de leitura); depois das 17:10, e nas urnas da prorrogação, a proporção é a mesma da última hora regular.

## Em quem votaram? (estimativas, não contagens)

- Se cada eleitor tardio tivesse votado como o restante da própria urna: 54,4% Lula — descreve onde houve voto tardio, não como esses eleitores votaram.
- Dentro do mesmo local de votação (63.794 locais), a fatia de Lula entre os eleitores depois das 17:00 é estimada em **48,6%** (IC 95%: 36,0% a 61,3%), contra 55,5% entre os demais eleitores desses locais. A hipótese "80% Lula" fica 4,9 erros-padrão abaixo do observado (rejeitada); "65%", 2,5. Conferências: sem pesos -7,3 p.p.; placebo (horários embaralhados no local) -1,2 ± 4,7 p.p.
- Depois das 17:10 há só 4.197 votos — poucos demais para estimar (IC 95%: 28,8% a 92,0%). Para eles vale o limite exato: no máximo 4.382 votos de diferença.
- Urnas da prorrogação vs vizinhas do mesmo local que fecharam no horário (763 locais): -0,35 p.p. na fatia de Lula (IC 95%: -0,69 a -0,02).

## Qualidade dos dados

- Totais conferem com o resultado oficial (Lula 64.256.232, Flávio Bolsonaro 59.826.041); 127.854.631 votos no Brasil, dos quais 127.854.313 com horário no log.
- Urnas com voto registrado depois do próprio encerramento: 0. Urnas com voto antes das 08:00: 0. Urnas sem log: 1.
- A urna que encerrou por último (Chapada Gaúcha/MG, zona 320, seção 185, às 23:04) teve o último voto às 16:27.
- Fuso de cada município deduzido do horário de abertura no BU (todas as urnas abrem às 08:00 de Brasília).

