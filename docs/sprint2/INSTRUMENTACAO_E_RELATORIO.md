# CTWA, custo observado e relatório comercial

Implementação em branch isolada; nenhuma migração aplicada em produção e nenhum deploy ou envio de mensagem executado por este trabalho.

## O que muda

1. O webhook recebe os campos reais `MessageSid` e `ReferralCtwaClid` enviados pela Twilio e os encaminha ao agente. A documentação oficial define esses campos: [Twilio incoming-message webhook](https://www.twilio.com/docs/messaging/guides/webhook-request).
2. A mensagem inbound guarda `source_message_sid` e `ctwa_clid` em `conversations`. Mensagens em handoff também preservam esses metadados. A gravação ocorre antes das ferramentas do LLM, para uma reserva criada no mesmo turno já enxergar a origem.
3. O custo Anthropic guarda modelo observado, tokens de cache, componentes de custo e versão de tarifa. O campo histórico `custo_usd` não foi recalculado nem substituído.
4. Um endpoint privado de leitura retorna um relatório comercial determinístico por unidade. A coleta semanal existente incorpora esse objeto; a narrativa semanal por LLM permanece separada.

## Persistência idempotente e histórico

Índice único parcial em `(restaurant_id, source_message_sid)` apenas para mensagens `role='user'` com SID presente. A mesma mensagem reentregue não duplica a linha. Texto repetido com outro SID é outra mensagem. Sem SID, cada envio continua sendo aceito. Respostas do agente não usam o SID inbound como sua identidade.

O histórico é lido antes da gravação e exclui o SID atual nas tentativas repetidas; o turno atual é adicionado ao contexto uma única vez. A mera presença da linha inbound **não suprime o processamento de uma entrega**, pois ela pode ter sido salva antes de uma falha do LLM. Essa alteração garante idempotência da persistência, não processamento exatamente uma vez. O webhook mantém o reconhecimento imediato e o processamento em background já existentes. Fila durável/outbox e deduplicação de efeitos externos continuam sendo trabalho separado.

O caminho de captura NPS já existente antecede o agente e não passa por essa gravação. Mensagens vazias sem mídia e limite de tamanho mantêm o comportamento atual do webhook. Não se deve usar a cobertura deste relatório como prova de que todos os eventos da Twilio foram faturados ou persistidos.

## Regra de atribuição de reserva

Trigger `BEFORE INSERT` em `reservas`, invoker sem privilégios adicionais:

- Mesma `restaurant_id` e igualdade exata entre `cliente_phone` e `conversations.user_phone`.
- Apenas mensagem de usuário com CTWA não vazio.
- Último referral recebido nos **sete dias anteriores** à criação da reserva, nunca posterior.
- Mensagens orgânicas posteriores não apagam o último referral elegível.
- Snapshot na criação: `ctwa_clid`, `ctwa_source_message_sid`, `ctwa_source_created_at` e `ctwa_attribution_rule`.
- Sem preenchimento retroativo de reservas antigas e sem alteração quando chega um clique posterior.

A janela de sete dias é regra interna explícita, não uma afirmação de atribuição ou receita validada pela Meta. A igualdade de telefone evita relacionar pessoas por nome; formatos de telefone diferentes não são unidos por aproximação.

## Custo Anthropic

Fonte: [preços oficiais da Claude API](https://platform.claude.com/docs/en/about-claude/pricing), consultados em 17/09/2026. Versão gravada: `anthropic-global-standard-2026-09-17`. Valores USD por milhão de tokens, API first-party global padrão:

| Modelo | Entrada | Saída | Escrita cache 5 min | Escrita cache 1 h | Leitura cache |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sonnet 4.6 / 4.5 | 3 | 15 | 3,75 | 6 | 0,30 |
| Haiku 4.5 | 1 | 5 | 1,25 | 2 | 0,10 |

`response.model` e `response.usage` são registrados para **cada iteração** do agente. Os componentes são somados sem arredondamento intermediário. A escrita de cache é dividida por TTL quando a API informa o detalhamento; na ausência desse detalhamento, o código usa os cinco minutos explicitamente solicitados pelo cache ephemeral padrão deste agente. Cache read não é cobrado novamente como entrada normal.

Modelo desconhecido, uso ausente, contadores de cache ausentes ou detalhamento inconsistente deixam o custo completo **nulo**, com status de incompletude. Não existe fallback silencioso para tarifa de outro modelo. Aliases datados dos modelos conhecidos são aceitos; o modelo observado permanece registrado.

Esse custo é cálculo sobre uso observado, não fatura conciliada. Turnos que falhem antes da gravação, classificador de handoff, narrativa semanal, outras integrações e Twilio não estão incluídos. O relatório declara essas lacunas. Não houve chamadas cobradas ao modelo nos testes.

## Relatório privado

`GET /api/restaurants/{restaurant_id}/reports/commercial?inicio=2026-09-01&fim=2026-09-08`

Reutiliza a dependência privilegiada `require_admin`; não cria um novo esquema de autenticação. `inicio` é inclusivo, `fim` exclusivo, em `America/Sao_Paulo`. Limite de 366 dias. Consultas em snapshot read-only e filtradas pela mesma unidade.

- **Conversa:** contato com mensagem inbound no período/unidade, não sessão de 24 horas.
- **Intenção:** classificação existente `reserva_nova` ou `evento`, após a primeira mensagem do contato no período. Usa o horário da mensagem inbound vinculada pelo SID, porque a métrica é gravada depois das ferramentas de reserva. Sem SID vinculado, usa o horário da métrica; isso pode omitir uma reserva criada antes de sua gravação.
- **Confirmação ou desfecho:** reserva criada após a intenção e antes do fim do período, com status atual `confirmada`, `realizada`, `concluida` legado ou `no_show`.
- **Realização/no-show:** status atual dessas reservas. Um contato pode ter reservas com desfechos diferentes.
- **Reservas totais:** contagem separada de todas as reservas criadas no período, por status atual, inclusive as sem conversa/intenção observada.
- **Custos:** agrupados por modelo/versão observados, separados de `custo_usd` legado e com número de turnos sem custo completo.
- **Receita realizada, custo Twilio e ROI:** nulos enquanto não houver as fontes necessárias. Pagamentos marcados como pagos em reservas são um agregado identificado, sem tratá-lo como faturamento total nem somá-lo a OS sem conciliação.

Não há histórico de transições de status. Portanto, confirmação passada de reserva hoje cancelada e estado histórico em outra data não podem ser reconstruídos. O relatório usa os dados atuais com essa limitação explícita.

### Correções encontradas na validação

- A query semanal consultava `messages`, tabela inexistente. Passa a consultar `conversations`, limita inbound e relaciona unidade/cliente/ordem temporal.
- O ranking LTV podia selecionar o CRM de outra unidade pelo mesmo telefone. Agora o contato e as relações são da mesma unidade.
- No restore real, `reservas_status_check` aceitava `concluida`, mas o aplicativo já tentava gravar `realizada`. A migração amplia a constraint para aceitar ambos, preservando todos os valores antigos. Não cria coluna de desfecho e não reclassifica histórico.

## Aplicação e validação

Migração gerada com Supabase CLI 2.101.0:

`files/restaurant-ai/migrations/20260917043459_ctwa_cache_commercial_reporting.sql`

Aplicar a migração antes do código de captura. É aditiva; a única substituição é a ampliação compatível da constraint de status. `lock_timeout=5s` evita aguardar indefinidamente por locks. Rollback de código pode deixar as novas colunas e o trigger intactos sem excluir evidência. Não há backfill.

Testes locais:

- `python3.11 -m unittest test_instrumentation -v`: custos com cache 5 min/1 h, modelos desconhecidos, histórico sem repetição, gravação antes de ferramentas, handoff, múltiplas chamadas, campos Twilio e endpoint privado somente leitura.
- `test_instrumentation_restore.py`: hook que recusa alvos fora do socket isolado do restore. Aplica e reaplica a migração, confere custos históricos, SIDs iguais/diferentes/ausentes, atribuição entre unidades, janela temporal, origem futura, não retroatividade, desfechos existentes e queries comerciais/semanais.

O hook não lê `.env`, não recebe URL arbitrária de banco e não envia mensagens. O runner destrói a instância local após o teste. A prova sanitizada fica junto desta documentação quando a execução termina.
