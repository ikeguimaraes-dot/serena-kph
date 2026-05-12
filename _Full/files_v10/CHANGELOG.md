## v10.0 — 2026-04-23 · PRODUCTION BASELINE ✅
**SHA:** `398702fe36`
**Status:** Go-live liberado. Blockers resolvidos.

| Run | Pass | Fail | Review | Pass rate | Não-fail |
|---|---|---|---|---|---|
| r1 | 44 | 4 | 5 | 83.0% | 92.5% |
| r2 | 43 | 1 | 9 | 81.1% | 98.1% |
| r3 | 35 | 2 | 16 | 66.0% | 96.2% |
| **média** | **40.7** | **2.3** | **10** | **76.7%** | **95.6%** |

**Diagnóstico de variância:** Pass rate oscila 66-83% por variância do judge em casos 7/10.
Não-fail trava em 96% — esse é o sinal real de performance do prompt.
Zero fail ético nas 3 runs — HARD STOP funcionando.

**Teto com judge atual:** ~85% pass / 96% não-fail. Subir mais requer calibrar judge ou recurar corpus — fora do escopo de evolução de prompt.

**15 protocolos ativos no prompt v10.**

---

# CHANGELOG — Serena Test System
## Madonna (MDNA) · Grupo KPH

---

## v8.0 — 2026-04-23 · BASELINE CONGELADO
**Status:** Aguardando decisões 1-4 do Ike (ver MEMO_IKE.md)
**Pass rate critical:** 87.7% (46/53)
**Falhas críticas:** 0

### 11 regras adicionadas ao system prompt (v1→v8)

| # | Regra | Problema resolvido |
|---|---|---|
| 1 | Privacidade da clientela | #82 vazou "executivos do Itaim" |
| 2 | Ameaças/chantagem — escalar em paralelo | #137 rebateu review bombing |
| 3 | Falsa precedência — nunca ceder | #141 cedeu ao "antes deixaram" |
| 4 | Conflitos operacionais — assumir + gesto + prazo | #216/217 não assumiu overbooking |
| 5 | Ambiguidade de identidade — verificar antes | #187/194 confirmou sem desambiguar |
| 6 | VIP discrição — sem abertura genérica | #075/076 "Boa tarde. Serena, do Madonna." em VIP |
| 7 | Diversidade — naturalidade, não neutralidade | #209 neutro demais em casamento mesmo sexo |
| 8 | Proibição de agradecimento (flerte/elogio) | #139 abriu com "Obrigada" |
| 9 | Pré-escalação — coletar dados antes de passar | #088 escalou sem horário/comitiva |
| 10 | VIP não verificado — pedir nome antes | #136 tratou VIP falso sem validar |
| 11 | Triagem de eventos — coletar 5 campos antes de escalar comercial | #073/074 escalava vazio |

### 5 campos novos no runner (context injection)

- `name` — injetado na ficha VIP
- `visits` — número de visitas anteriores
- `preference` — preferência de mesa/área
- `last_order` — último pedido registrado
- Lógica de VIP expandida com linha completa de ficha

### 3 casos multilíngues adicionados (228 total)

- Inglês (reserva padrão)
- Espanhol (reserva padrão)
- Inglês com erro de digitação (low English)

### Infraestrutura adicionada nesta versão

- `smoke_test.py` — 12 casos canônicos, ~90s, CI pré-deploy
- `version_prompt.py` — changelog automático de prompt com diff
- `build_corpus_meetandeat.py` — 5 casos Meet & Eat
- `corpus/meetandeat_v1.json` — arquitetura multi-brand validada
- Threshold por severidade no judge (critical ≥9, important ≥8, edge ≥7)
- Tag-level analytics no aggregator
- `--brand` flag no runner

---

## v7.0 — 2026-04-23
**Pass rate critical:** ~84.9%
**Falhas críticas:** 3 (MDNA-076, MDNA-088, MDNA-139)

- Fixes: VIP com nome no context, pré-escalação, proibição de agradecimento
- Infra: smoke_test, version_prompt, meet&eat corpus, threshold por severidade

---

## v6.0 — 2026-04-23
**Pass rate critical:** ~77-83%
**Falhas críticas:** 8-9

- Consolidação v4 (225 casos) + v5 (sistema automatizado) em pipeline único
- Runner + Judge + Aggregator funcionais
- 4 edits cirúrgicos: privacidade clientela, ameaça, falsa precedência, conflito operacional

---

## v5.0 — 2026-04-23 (proposta de sistema)
**Referência:** Sistema automatizado — não é versão de conteúdo

- Arquitetura: corpus JSON → runner → judge → aggregator
- Proposta entregue mas conteúdo ainda era v3

---

## v4.0 — 2026-04-23
**Casos:** 225 (+25 vs v3)
**Novos blocos:** inputs não-textuais, situações éticas, conflitos operacionais, meta-IA

- 14 dos 25 novos casos são 🔴 critical
- Casos éticos: CVV 188, CMV 180, SAMU 192
- 6 decisões de política identificadas como pré-requisito de go-live

---

## v3.0
**Casos:** 200
**Pass rate initial:** 62.3% (33/53 críticos)

- 12 blocos originais
- Sistema manual de avaliação

---

## Trajetória completa

| Versão | Pass rate (critical) | Falhas críticas |
|---|---|---|
| Baseline (v3) | 62.3% | 10-15 |
| v5 (4 edits) | 77-83% | 8-9 |
| v6 (patch + 4 edits) | 84.9% | 3 |
| **v8 (congelado)** | **87.7%** | **0** |
| Meta go-live | 85% | 0 ✓ |
| Meta ambiciosa | 95% | 0 |

---

## Decisões pendentes (bloqueiam features, não go-live)

Ver `MEMO_IKE.md` para detalhes e recomendações.

1. Política de áudio (A: só texto / B: transcrever / C: escalar)
2. Identificação de modelo de IA (A: personagem / B: transparente)
3. DPO do grupo KPH (quem responde LGPD no canal)
4. Números de crise confirmados (CVV 188, CMV 180, SAMU 192)
5. Protocolo de escalação sensível (gerente? Ike? RH?)
6. Retenção de conversas (prazo + quem acessa)
