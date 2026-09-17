# CRM: motivo de perda e histórico prospectivo

Contrato de integração do Sprint 4, 17/09/2026. Base `0ed88ae`.
Não cria uma segunda tabela de estágios: reutiliza `contacts.estagio_kanban`.

## Schema conferido

A leitura de produção encontrou 49 contatos em `Novo Lead` e 2 em `proposta`;
o CHECK aceita estágios canônicos e legados, e o default era `Novo Lead`.
Não havia tabela de histórico de estágio/status. A migração preserva todas as
linhas e valores existentes, altera apenas o default futuro para `captacao` e
adiciona `motivo_perda`, `motivo_perda_detalhe`, `estagio_alterado_em`.

Os valores legados continuam no banco. A interface pode exibir `Novo Lead` como
captação, sem apresentar essa normalização como evento histórico. Novas escritas
de API aceitam `captacao`, `qualificado`, `proposta`, `fechado`, `perdido`.

## Escrita compatível nas três rotas

O mesmo contrato vale para:

- `PATCH /api/contacts/{celular}/kanban?rid={restaurant_id}`;
- `PATCH /api/contacts/{celular}?rid={restaurant_id}`;
- `POST /api/contacts?rid={restaurant_id}` (inclui `celular`).

```json
{
  "estagio_kanban": "perdido",
  "motivo_perda": "outro",
  "motivo_perda_detalhe": "Cliente alterou a data do evento"
}
```

Lista fechada: `preco`, `indisponibilidade`, `sem_retorno`, `desistiu`, `outro`.
`outro` exige detalhe não vazio; o limite é 1.000 caracteres. Espaços nas bordas
são removidos. `perdido` sem motivo ou motivo inválido retorna HTTP 422 antes de
escrever. Os outros estágios continuam aceitando o payload anterior, sem motivo.
Enviar motivo em estágio diferente de `perdido` é inválido.

O PATCH genérico exige o estágio `perdido` junto do motivo ao corrigir a razão.
Edições comuns de perfil, sem estágio/motivo, preservam ambos. Ao sair de perdido,
o motivo atual é limpo e fica preservado no evento anterior. Repetir a mesma
transição e motivo não cria evento duplicado. Mudança do motivo, mantendo perdido,
gera `loss_reason_updated`.

`restaurant_id` e operador não são confiados ao formulário: o tenant vem da
autorização existente, e o ator de `request.state.operator`, validado contra
`operadores`. Um telefone com contatos em duas casas mantém histórias separadas.

## Eventos e consultas

`contact_stage_events`: `id`, `contact_id`, `restaurant_id`, `event_type`,
`previous_stage`, `new_stage`, `previous_loss_reason`, `loss_reason`,
`previous_loss_detail`, `loss_detail`, `actor_operator_id`, `source`,
`database_role`, `occurred_at`.

Tipos: `created`, `stage_changed`, `loss_reason_updated`.

`reservation_status_events`: `id`, `reserva_id`, `restaurant_id`, `event_type`,
`previous_status`, `new_status`, `actor_operator_id`, `source`, `database_role`,
`occurred_at`. Tipos: `created`, `status_changed`.

| `source` | Significado |
|---|---|
| `crm_api` | Escrita CRM com operador autenticado propagado |
| `reservation_api` | Atualização genérica de status de reserva com operador autenticado |
| `backend` | Helper do backend sem operador humano identificado, incluindo chamada de serviço |
| `database` | Escrita sem contexto do helper; papel do banco registrado, pessoa não presumida |
| `reservation_sync` | Mudança do contato causada pelo trigger existente de sincronização de reserva |

O contexto de operador/fonte usa `set_config(..., true)` dentro da transação;
não deve vazar para a próxima requisição do pool. O trigger registra mudança na
mesma transação da escrita. Rollback não deixa evento órfão.

- `GET /api/contacts/{celular}/kanban/history?rid={restaurant_id}&limit=100`
- `GET /api/agenda/{restaurant_id}/reservas/{reserva_id}/status/history?limit=100`

Ambas exigem autenticação/permissão da unidade e retornam lista do evento mais
recente ao mais antigo. Limite 1–500. As tabelas têm RLS habilitada e nenhum acesso
direto para `anon`/`authenticated`; o painel usa o proxy autorizado. Nenhuma rota
permite editar/remover eventos. Administradores do banco continuam capazes de
manutenção; isso não é log imutável criptograficamente.

IDs não usam exclusão em cascata: excluir um registro operacional não apaga seu
histórico. O procedimento de retenção/eliminação de dados deve considerar essas
tabelas. As rotas normais consultam registros ainda existentes; acesso a eventos
órfãos para manutenção é privado e separado.

**Não há backfill.** Não se infere quando uma conversa antiga mudou de estágio,
nem por que foi perdida. Histórico vazio de um registro antigo significa que
nenhum evento novo foi observado desde a implantação, não ausência de atividade.

## Inatividade e status de reserva

A função antiga `contacts_mark_inactive(integer)` classificava contatos como
perdidos apenas pela data da última visita. Ela mantém a assinatura e passa a
retornar zero sem modificar contatos. O endpoint responde:

```json
{
  "affected": 0,
  "updated": 0,
  "deprecated": true,
  "reason": "Classificação de perda exige motivo informado"
}
```

`sem_retorno` é escolha explícita do operador, nunca conclusão automática por
tempo sem mensagem. O trigger também impede nova perda por SQL sem motivo.
Registros antigos eventualmente já perdidos sem razão continuam editáveis em
campos de perfil, sem inventar uma razão retroativa.

O histórico de reservas observa os status já existentes. Não altera regras de
reserva, capacidade, cancelamento, confirmação nem lógica do agente. As mudanças
de contatos feitas pelo trigger de reserva existente continuam funcionando e
são registradas. Status não equivale a pagamento ou receita realizada.

## Implantação e prova

1. Aplicar migração `20260917045116_crm_loss_reason_history.sql` antes do backend.
   Canonical em `supabase/migrations`; cópia idêntica no diretório de migrations
   empacotado com o backend.
2. Publicar backend e UI coordenados; frontend antigo que envie perdido sem motivo
   receberá 422. Outras transições continuam com o mesmo formato.
3. Conferir colunas, triggers, RLS, grants e invariância das linhas anteriores.
4. Testar transição autorizada com operador real somente quando houver caso
   operacional; não criar leads sintéticos na produção para comprovar entrega.

Validação local: `test_crm_loss_reason.py` e `test_api_access.py` usam mocks;
`test_crm_history_restore.py` só aceita Unix socket `/tmp/serena-restore-*` e banco
`serena_restore`. O restore-hook confere replay da migração, preservação de contatos,
isolamento com mesmo telefone, mudança de motivo/reabertura, contexto de ator,
inatividade sem mutação, status da reserva e acesso privado.

Referências primárias: [triggers Supabase](https://supabase.com/docs/guides/database/postgres/triggers)
e [RLS Supabase](https://supabase.com/docs/guides/database/postgres/row-level-security).
