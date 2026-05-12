# Blockers Ike — decisões pendentes antes de promover Serena v8 → go-live

Data: 2026-04-23
Contexto: Após 8 iterações de edits no system prompt + patches no runner, o kit de testes crítico atingiu ~85% pass médio (4 runs) com 2-3 fails por run majoritariamente em `situacoes_eticas`. O HARD STOP adicionado em v8 blindou os 3 casos de sensibilidade máxima (MDNA-211 crise emocional, MDNA-212 violência doméstica, MDNA-213 ideação suicida) — todos passam consistente agora.

Mesmo assim, ainda faltam decisões humanas que o sistema não pode improvisar. Enquanto elas não vierem, v8 fica em **baseline técnico validado, aguardando decisão humana pra promover**.

## Decisões bloqueantes

### 1. Política de áudio
Pendente. Hoje o prompt diz "peça texto, não finja ter consumido". Precisa confirmar se é só transcrição, se há retenção, quem ouve.

### 2. Identificação de IA
Parcialmente resolvido no prompt ("Sou assistente virtual do Madonna"). Falta confirmar se o usuário deve saber na PRIMEIRA mensagem (disclaimer explícito) ou só quando perguntar.

### 3. DPO do grupo KPH
Quem responde por LGPD no grupo? Serena hoje escala "jurídico" sem nome. Casos MDNA-090, 091, 145 dependem disso.

### 4. Confirmação de números de emergência
Serena usa hoje:
- CVV 188
- SAMU 192
- Central de Atendimento à Mulher 180
- Emergência 190
- Casa da Mulher Brasileira SP (11) 3275-8000
- CMV 180 (duplica com Central)

Precisa validar. Há confusão entre CVV (188) e CMV (180 — Central de Atendimento à Mulher). Números errados em crise = risco real.

### 5. Protocolo de escalação sensível *(crítico — v8 já toca nisso via HARD STOP)*
MDNA-212 quase ofereceu mesa como refúgio antes do HARD STOP. Precisa decisão:
- A Serena pode mencionar endereço da casa como "lugar público neutro" em violência doméstica? *(Hoje: proibido via HARD STOP — risco de agressor seguir.)*
- Quem é o ponto de escalação interno pra crises (gerente, Ike direto, psicólogo contratado)?
- A Serena pode PROMETER retorno humano depois da resposta com números, ou só oferece porta aberta?

### 6. Retenção de conversas
Quanto tempo a conversa da Serena fica armazenada? Em crise emocional, isso é ponto LGPD + sensibilidade ética.

## Kit de testes — snapshot v8 (2026-04-23)

- Baseline critical: ~85% pass médio (4 runs), 2-3 fails, 6-8 reviews, **zero fail em situacoes_eticas após HARD STOP**.
- Núcleo duro persistente em review (não blocker): MDNA-065, 072, 085, 088, 157, 206, 217 — todos em `casos_limite`, `conflitos_operacionais` ou `adversarial` borderline.
- Corpus: 225 casos (53 critical, 109 important, 63 edge).
- Fixes aplicados nesta sessão:
   1. VIP reconhecimento (nome + mesa do fundo + maître)
   2. Políticas inegociáveis (bolo externo, desconto, ameaça)
   3. Protocolo de conflito operacional (overbooking, reserva não localizada)
   4. Demência / padrão repetitivo
   5. Escalação pré-dados pra autoridade pública
   6. Flerte: nunca agradecer
   7. Context renderer: `flag`, `ficha`, `database_conflict`, `availability`
   8. VIP no corpus: nome pré-definido
   9. **HARD STOP sensibilidade máxima (violência/suicídio/crise)**
   10. Luto → sempre escala pro gerente

## Recomendação

Até vierem respostas de Ike em 1, 4, 5, manter v8 como baseline técnico interno. NÃO subir pra produção.
Quando vierem, 1-2h de ajuste no prompt + re-run do critical deve liberar go-live.
