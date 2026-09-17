# Handoff: estado persistido, limites e correções

Auditoria sobre a implementação do backend e os critérios do Book Mestre: destino humano por casa, registro da transferência e tempo até a primeira resposta. Não houve mensagens reais, cadastro de destinatários, aplicação em produção ou validação de recebimento humano nesta tarefa.

## Falhas encontradas e corrigidas

| Falha | Comportamento resultante |
| --- | --- |
| `send_to_customer` retornava silenciosamente sem Twilio; o painel salvava a resposta e avançava status | Ausência do provedor, SID inválido ou rejeição geram erro; nada é salvo como resposta aceita |
| Remetente vazio usava fallback global | Exige o remetente da unidade; não escolhe outra operação por ambiente |
| Destino humano podia ser o próprio sender | Normalização de número e bloqueio no envio, no cadastro de equipe e na seleção clínica; seleção também rejeita sender de outra unidade |
| Webhook podia processar eco do próprio número | Eco com `From` e `To` iguais após normalização recebe ACK sem LLM ou resposta |
| Toda criação inseria outra sessão aberta | Lock transacional por unidade/telefone e reutilização da sessão aberta; concorrência gera um registro e um conjunto de alertas |
| Resolver uma duplicata deixava outra aberta e mantinha o bot pausado | Resolve todas as sessões abertas da mesma unidade/telefone, preservando as linhas históricas; outras unidades não mudam |
| Kanban alterava status sem `resolved_at` | Kanban usa a mesma transição de estado e timestamps |
| Operador podia assumir durante geração e receber resposta automática logo depois | O agente relê o estado após a geração e suprime a resposta se houve assunção; mantém o custo observado |
| Aceitação de canais existia somente em logs | `notification_status` registra resultado observado por canal, sem afirmar entrega |
| Tempo até resolução era apresentado como tempo de resposta | Métrica adicional usa `first_human_response_at`; o campo legado conserva definição explícita |

A resposta ao cliente confirma somente o fato persistido: a solicitação foi registrada para a equipe. Não promete atendimento “agora”, tempo de retorno ou entrega do alerta.

## Persistência e transições

Migração aditiva gerada pelo Supabase CLI:

`files/restaurant-ai/migrations/20260917050154_handoff_reliability.sql`

Novos campos em `handoff_sessions`: `assumed_at`, `first_human_response_at`, `last_reply_message_sid` e `notification_status`. `conversations.provider_message_sid` registra o SID da resposta humana aceita, com índice único por unidade/SID. Nenhum histórico foi recalculado ou apagado. RLS e privilégios existentes permanecem intactos.

- `aguardando` e `em_atendimento` continuam pausando o bot; cada consulta lê o banco.
- Assumir grava `assumed_at`; não equivale a responder ou comprovar que o cliente recebeu mensagem.
- Resposta humana exige SID válido. Conversa, status, primeiro horário de resposta e último SID são gravados na mesma transação. Regravar o mesmo SID não duplica a conversa.
- Resolver preenche `resolved_at` e libera a conversa; uma nova solicitação posterior cria outra sessão. Repetir a resolução de um ID já resolvido não fecha essa nova sessão.
- Resolver pelo kanban segue a mesma lógica. IDs inexistentes não geram sucesso falso.
- Os caches de relatório são invalidados nas transições do painel. O estado do handoff não depende do cache de prompt ou do cache Anthropic.

A releitura antes da resposta reduz a disputa entre modelo e operador; não transforma a requisição ao provedor em uma transação atômica com o clique humano. Ferramentas que já terminaram durante a geração não são desfeitas.

## Aceitação não é entrega

`POST /api/handoff/{hid}/reply` mantém `ok` para compatibilidade e acrescenta:

```json
{
  "ok": true,
  "accepted": true,
  "delivery_confirmed": false,
  "provider_message_sid": "SM…",
  "provider_status": "queued"
}
```

SID válido significa que a API aceitou a mensagem. Entrega/leitura exigem status posterior da Twilio. Timeout ou aceitação não confirmada retornam 502 e não avançam o estado. Se a Twilio aceitar e a gravação local falhar, o endpoint retorna 503 com o SID e orienta conciliação antes de reenviar. Não há retry automático de resposta humana neste código.

Em `notification_status`, os canais guardam:

- `pending`: sessão persistida, resultado não gravado; processo pode ter sido interrompido.
- `accepted`: canal aceitou a solicitação; WhatsApp inclui SID/status quando observados.
- `unconfirmed`: não foi possível comprovar aceitação.
- `skipped`: falta configuração ou destino seguro; inclui motivo.

Sessão reutilizada não dispara de novo os alertas. `pending`/`unconfirmed` não provocam reenvio cego; exigem inspeção operacional. Discord é independente da tentativa clínica e falha de notificação não desfaz o handoff persistido. Não foi introduzida uma fila durável de retries nem um recibo de leitura humana.

## Cobertura real frente ao Book Mestre

| Caminho | Cobertura após o código | Evidência ainda necessária |
| --- | --- | --- |
| Painel humano por unidade | Sessão e mensagens persistidas, estados consistentes, autenticação existente por recurso/unidade | Operador assumir e responder em operação real |
| Discord | Canal primário existente; resultado de aceitação persistido | Webhook configurado e recebimento observado por responsável |
| Levvai `[LARA]` | Gerente ativo da própria unidade, sender da clínica, bloqueio de autoenvio, SID observado | Texto livre continua dependendo da janela válida; template aprovado para fora da janela e entrega posterior não foram comprovados |
| WhatsApp de handoff comum nas quatro casas | Continua explicitamente sem template de equipe configurado; painel/Discord preservados | Template aprovado, destino humano responsável e teste autorizado de recebimento |
| Meet | Fonte operacional da Vic foi confirmada na investigação anterior; nenhum cadastro modificado aqui | Configuração e recebimento reais, sem transformar a existência de um contato em prova de entrega |
| Madonna | Contato de gerente identificado; responsabilidade ainda pendente | Confirmação do responsável. O próprio número sender nunca é destino humano |

Portanto, o KR “100% das casas com destino que chega em humano” **não fica certificado por esta mudança**. Testes com mocks provam comportamento do código, não recebimento pelas pessoas.

Não foram criados templates ou SLAs. O limiar de duas horas já existente permanece identificado como `limiar_legado_minutos=120` e `sla_validado=false`. `tma_minutos` legado mede tempo até resolução; `tempo_primeira_resposta_minutos` usa somente primeiras respostas instrumentadas e fica nulo quando não há dados.

## Validação e integração

43 testes offline passaram: regressões de handoff, instrumentação e menu, mais resposta humana sem provedor/SID, autoenvio e assunção durante geração. Todos os transportes são simulados.

O hook `test_handoff_reliability_restore.py` executou sobre PostgreSQL descartável restaurado: migração aplicada duas vezes, criação concorrente, isolamento entre unidades, resolução das duplicatas sem exclusão, reabertura, SID idempotente, timestamps humanos, queries de métricas e rejeição de senders cadastrados como equipe.

Prova sanitizada: `VALIDACAO_CONFIABILIDADE.json`. O runner destruiu o banco local após o teste. Aplicar a migração antes do código; rollback de código pode preservar as colunas novas. A assinatura de `send_to_customer` é preservada, mas ausência de configuração deixa de ser sucesso silencioso, e o retorno agora contém o SID/status observados. Callers existentes que ignoram esse retorno continuam funcionando com remetente correto e Twilio disponível.
