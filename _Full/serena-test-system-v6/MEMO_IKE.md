# Memo — Serena v8: 6 decisões pra liberar go-live

**Para:** Ike
**De:** Claude Code (assistente de desenvolvimento)
**Data:** 2026-04-23
**Objetivo:** consolidar as 6 decisões humanas pendentes e propor caminho pra cada uma. Com 1-4 resolvidos, v8 vai pra produção. 5 e 6 podem ser release 1.1.

---

## Status técnico da Serena v8

- **Critical pass rate:** 87.7% médio (2 runs), zero fail em ética após HARD STOP, 0.5 fail médio por rodada (todos em casos borderline).
- **Multilíngue validado:** PT + EN, ES, IT, FR (cases MDNA-035, 151, 226, 227, 228).
- **Protocolos cobertos no prompt:** VIP, flerte, ameaça, bolo externo, overbooking, crise emocional (HARD STOP), luto, demência, autoridade pública, **eventos/buyout com triagem**.
- **Casos de sensibilidade máxima** (211 crise, 212 violência, 213 suicídio): resposta padrão agora é (a) números oficiais no topo, (b) pergunta curta de segurança, (c) porta aberta neutra. **Nunca oferecer mesa/refúgio físico.**

---

## Decisão 1 — Números de emergência *(go-live blocker, 10min de decisão)*

**Situação:** o prompt hoje mistura "CMV" (não existe como número único — confusão com 180, Central de Atendimento à Mulher). Números errados em crise = risco real.

**Indico padronizar 4 canais federais estáveis:**
- **188** — CVV (crise emocional, suicídio)
- **180** — Central de Atendimento à Mulher
- **190** — emergência/polícia
- **192** — SAMU/saúde

Remover "CMV". Manter *Casa da Mulher Brasileira SP (11) 3275-8000* como rede local opcional, com revisão trimestral (orçamento municipal muda e números caducam).

**Ação:** confirma e ajusto o prompt.

---

## Decisão 2 — DPO do grupo KPH *(go-live blocker, 30min com jurídico)*

**Situação:** Serena hoje escala "jurídico" sem destinatário. Escalação vira teatro se não houver canal real. LGPD exige designar DPO.

**Indico:**
- Você assume DPO **interino** até crescer pra designar externo (LGPD permite em empresa pequena-média).
- Criar `dpo@kph.com.br` — entra você + jurídico.
- Serena passa a dizer: *"Deixo o DPO do grupo falar direto com você — ele retorna em até 48h."*

**Ação:** confirma e ajusto o prompt + fluxo de e-mail.

---

## Decisão 3 — Identificação de IA *(recomendável pré-launch)*

**Situação:** hoje Serena só se identifica quando perguntada ("Você é humana ou robô?" → "Sou assistente virtual do Madonna"). CONAR e PL de IA em tramitação caminham pra transparência obrigatória.

**Indico disclaimer sutil na primeira mensagem:**
- Contato novo: *"Boa tarde. Aqui é a Serena — assistente virtual do Madonna. Como posso ajudar?"*
- Cliente recorrente (3+ reservas): não repete.

**Trade-off:** perde micro-encanto do "Maître Invisível" no primeiro contato. Ganha defensibilidade legal e confiança construída sobre verdade.

**Ação:** confirma abordagem e ajusto 1 linha no prompt.

---

## Decisão 4 — Retenção de conversas *(LGPD + infraestrutura)*

**Indico estrutura LGPD mínima:**
- **Reservas operacionais:** 90 dias (janela de chargeback/disputa).
- **Situações éticas (MDNA-211/212/213) e reclamações graves:** expurgar em 7 dias após fechamento. **Não treinar modelo com crise individual.**
- **Agregados anonimizados** (sem nome/telefone): mantém indefinido pra evolução da Serena.
- **Opt-out claro** no início de cada nova conversa: *"Seus dados são apagados em 90 dias. Responda SAIR pra expurgo imediato."*

**Trade-off:** perde histórico rico de treino mas defensível em auditoria.

**Ação:** decide janela (90 dias vs outra) + aprova opt-out.

---

## Decisão 5 — Protocolo de escalação sensível *(pode ir como release 1.1)*

**Situação:** HARD STOP já bloqueia o pior (oferecer mesa em violência). Falta **quem recebe a escalação** quando ela é necessária (luto, emergência médica, autoridade pública).

**Indico plantão sensível separado do salão:**
- **Horário comercial:** gerente sênior designado, SLA 30min.
- **Fora de horário:** Serena **não escala**. Entrega números oficiais + "retomamos amanhã às 9h". Exceção absoluta: risco iminente → SAMU direto.
- **Pós-crise:** você revisa transcript em 24h e decide follow-up humano (liga, manda flor, carta). **Não automatizar esse gesto.**

**Trade-off:** protege o cliente (não empurra pra funcionário despreparado de madrugada) e protege a casa (nenhuma promessa não-cumprível).

**Ação:** nomear plantonista sênior + validar SLA.

---

## Decisão 6 — Política de áudio *(fase 2, pós-launch)*

**Situação:** prompt hoje diz "peça texto". Funciona como default mas é fricção (Brasil é país do áudio no WhatsApp).

**Indico meio-termo pra fase 2:**
- Aceita áudio **apenas em reservas simples** (data, horário, pessoas) com transcrição automática + **confirmação em texto** antes de efetivar.
- **Qualquer tema sensível** (reclamação, crise, LGPD, disputa de cobrança) → pede texto e ponto.

**Trade-off:** 80% da conveniência, risco de transcrição errada em contexto sensível fica blindado.

**Ação:** fase 2. Pode lançar v8 sem isso.

---

## Ordem recomendada pra você decidir

| Ordem | Decisão | Esforço | Libera |
|---|---|---|---|
| 1 | Números (decisão 1) | 10min | go-live |
| 2 | DPO (decisão 2) | 30min | go-live |
| 3 | Identificação IA (decisão 3) | 5min | defensibilidade legal |
| 4 | Retenção (decisão 4) | infra + jurídico | LGPD |
| 5 | Escalação sensível (decisão 5) | 1h com gerente | release 1.1 |
| 6 | Áudio (decisão 6) | fase 2 | melhoria |

**Com 1–4 resolvidos (≈ 2h de trabalho consolidado), v8 vai pra produção.**

---

## Resumo do que já está entregue

- 10 regras/protocolos aplicados ao prompt desde a baseline
- Runner com 5 campos de `context` novos (flag, ficha, database_conflict, availability, name)
- Corpus expandido: 225 → 228 casos (3 multilíngue)
- Suite de testes: smoke + critical + adversarial + situacoes_eticas + cultural_linguistico
- Dados atualizados em CLAUDE.md e sincronizados entre os 2 diretórios
- Eventos agora disparam triagem mínima (data, horário, pessoas, nome, contato) antes de escalar ao comercial

Qualquer dúvida, `BLOCKERS_IKE.md` tem o histórico técnico curto; este `MEMO_IKE.md` é o executivo.
