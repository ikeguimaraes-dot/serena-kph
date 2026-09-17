# Régua com consentimento e outbox por unidade

## Comportamento

A régua mantém as etapas pós-evento existentes: D+1 (20–30h), D+3 (68–80h, após D+1), D+7 (7–8d, após D+3) e D+30 (30–32d, após D+7). Usa OS `realizado` e `evento_realizado_em`, sem criar conclusão fictícia. Timestamps antigos impedem repetir etapas já marcadas, mas não são transformados em prova de entrega ou novos SIDs.

Nurture usa a última mensagem **inbound** do mesmo contato/unidade, entre 3 e 90 dias, e o lead score `morno`. Reservas `pendente`/`confirmada` da mesma unidade impedem o nurture. Alterar notas, consentimento ou cadastro não muda a data dessa interação. O ID da última mensagem é a identidade do evento: uma nova mensagem recebida pode originar outro evento, nunca apenas a execução repetida do cron.

Os joins de CRM, reserva, consentimento, configuração e remetente usam a mesma `restaurant_id`. Não há fallback para o remetente de Madonna. O remetente vem do cadastro ativo da unidade. Telefones devem estar em formato E.164; não há aproximação entre números.

## Portas de ativação

Nenhum envio fica ativo pela migração ou pelo deploy. Para disparar, todas estas condições devem existir:

1. Chamada explícita com `dry_run=false` (padrão: `true`).
2. Ambiente `SERENA_OUTREACH_SEND_ENABLED=true` (padrão: desativado).
3. Regra da unidade/etapa `enabled=true`.
4. Consentimento explícito auditado, último evento concedido, sem revogação posterior, e flag CRM ainda habilitada.
5. Evento elegível, unidade ativa, remetente/destinatário válidos e nenhuma tentativa anterior para a mesma chave.
6. Template com aprovação `approved` verificada na Twilio ao habilitar a regra **e novamente antes de cada tentativa**.

Não se infere consentimento por conversa, reserva, evento, CTWA ou pelo booleano legado. Não se infere aprovação pelos SIDs antigos. Os quatro SIDs existentes permanecem como referência `legacy_content_sid` na prévia de configuração; precisam ser verificados e configurados expressamente. Não há envio livre como fallback.

Referências oficiais consultadas em 17/09/2026: [templates WhatsApp](https://www.twilio.com/docs/whatsapp/tutorial/send-whatsapp-notification-messages-templates), [Content API e consulta de aprovação](https://www.twilio.com/docs/content/content-api-resources), [recurso Message e SID](https://www.twilio.com/docs/messaging/api/message-resource). O sistema usa `ContentSid`/`ContentVariables` e registra aceitação do provedor separadamente da entrega.

## Consentimento auditável

`GET /api/restaurants/{restaurant_id}/contacts/{phone}/outreach-consent`

Retorna `{current, history, eligible, legacy_opt_in}`. `current=null` e `eligible=false` significam que não há prova suficiente, mesmo se o booleano antigo for verdadeiro. `history` contém os últimos 50 eventos.

`PUT` no mesmo caminho:

```json
{
  "granted": true,
  "source": "whatsapp_explicit",
  "occurred_at": "2026-09-17T10:00:00-03:00",
  "evidence": "Referência da mensagem/formulário em que o cliente autorizou este contato."
}
```

- `source`: `form`, `whatsapp_explicit`, `paper`, `import_documented` ou `revocation`.
- `occurred_at`: data com timezone, sem futuro.
- `evidence`: texto ou referência da prova, entre 8 e 2.000 caracteres. Não deve conter credenciais.
- Operador obtido de `request.state.operator`, nunca aceito do payload. Chamadas de serviço autenticadas ficam identificadas como `authenticated_service`.
- Cada alteração insere um evento com fonte, momento observado, momento do registro e operador. A API não modifica eventos anteriores.
- Revogar: `granted=false`, com origem/data/evidência. A mesma transação desativa `contacts.opt_in_marketing` na unidade.
- Uma concessão datada antes da última alteração é recusada com 409; importação antiga não desfaz revogação.
- Alterar somente o booleano antigo para verdadeiro não cria evidência. Alterá-lo para falso bloqueia envio.

## Configuração e execução

- `GET /api/restaurants/{restaurant_id}/outreach/config`
- `PUT /api/restaurants/{restaurant_id}/outreach/config/{stage}` com `{enabled, content_sid, messaging_service_sid?}`. Etapas: `nurture_d3`, `d1`, `d3`, `d7`, `d30`. Habilitação falha se a consulta ao provedor não comprovar aprovação.
- `POST /api/restaurants/{restaurant_id}/outreach/{family}/run?dry_run=true`. Famílias: `nurture` e `pos_evento`.
- `GET /api/restaurants/{restaurant_id}/outreach/outbox?limit=100` para auditar tentativas.

Todas as rotas reutilizam autenticação privilegiada do backend e a autorização por unidade já existente. As rotas antigas `/api/serena/nurture` e `/api/serena/pos-evento` continuam existindo, agora exigem `rid` explícito e também usam `dry_run=true` por padrão. A prévia apenas lê o banco, apresenta motivos de bloqueio e não grava tentativas. Cada rodada examina no máximo 100 contatos/OS; não é um relatório exaustivo de toda a base.

## Idempotência e estados

Chave única: `(restaurant_id, object_type, object_id, stage)`.

Antes da chamada HTTP, o banco revalida evento, opt-in e regra e persiste `dispatching`. O lock no contato serializa esse momento com a gravação de revogação. A tentativa guarda consentimento utilizado, remetente, template, variáveis e data do evento. Duas execuções concorrentes não enviam duas vezes para a mesma chave.

- `sent`: a Twilio aceitou a criação e retornou SID válido. **Não significa entregue/lido.** Só então o timestamp legado da etapa é atualizado, na mesma transação que conclui a outbox.
- `failed`: rejeição explícita ou indisponibilidade antes do envio. Não marca timestamp.
- `unknown`: timeout, erro de transporte, HTTP 5xx ou resposta sem SID. Não marca timestamp.
- `dispatching`: processo interrompido ou conclusão ainda não persistida. Pode ter sido aceito pelo provedor.

Nenhum estado já persistido é reenviado automaticamente, incluindo `failed`, `unknown` e `dispatching`. Falha após aceitação e antes da confirmação no banco permanece visível para conciliação manual nos logs Twilio. Não apagar a linha nem gerar nova chave para repetir uma tentativa ambígua. Não há afirmação de entrega exatamente uma vez; há uma única tentativa de criação por evento e reconhecimento explícito das ambiguidades de rede.

O cliente HTTP faz uma única requisição de envio, sem política automática de retries. Regras, consentimento e evento são um snapshot no momento do claim; revogação concluída antes desse momento bloqueia. Revogação após a requisição ter sido iniciada não consegue cancelar retroativamente a chamada já aceita.

## Migração e testes

`files/restaurant-ai/migrations/20260917044853_consented_outreach_outbox.sql` criada pelo Supabase CLI. Três tabelas novas, RLS habilitada e sem privilégios `anon`/`authenticated`. Acesso apenas via backend. Sem backfill de consentimento e sem remover colunas legadas.

Aplicar a migração antes do código. Reverter somente o código antigo reintroduziria os disparos inseguros; em rollback, manter as rotas de régua desativadas e as tabelas preservadas. Não foi ativado `SERENA_OUTREACH_SEND_ENABLED` em produção por este trabalho.

- `test_outreach.py`: contratos de consentimento/operador, rota privada, defaults sem envio, templates pausados/rejeitados, SID obrigatório, timeout e ausência de credenciais. HTTP totalmente simulado.
- `test_outreach_restore.py`: aplica/reaplica migração sobre restore isolado, RLS/ACL, opt-in legado sem prova, isolamento de remetente/reserva/consentimento, concorrência da mesma chave, revogação, estados ambíguos e timestamps somente após SID.

Nenhum teste carrega `.env`, envia mensagens reais ou modifica produção. O hook recusa qualquer alvo fora do socket privado do runner de restore.
