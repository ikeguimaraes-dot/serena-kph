# Confirmação, lembrete e execução periódica

Implementação de 17/09/2026. Nenhuma regra, variável de ambiente ou mensagem de
produção foi ativada por esta entrega. A ativação é uma etapa operacional separada.

## Contrato por unidade

Família API `reservation`, em
`POST /api/restaurants/{restaurant_id}/outreach/reservation/run?dry_run=true`.
O endpoint usa a mesma autenticação administrativa e escopo de unidade das réguas
existentes. A consulta de regras inclui duas novas etapas, inicialmente desativadas:

| Etapa | Evento e elegibilidade |
|---|---|
| `reservation_confirmation` | Reserva atualmente `confirmada`, data/hora futura, com evento real em `reservation_status_events` (`created` ou `status_changed`, `new_status=confirmada`) ocorrido após `outreach_rules.updated_at`. Ativar uma regra não dispara confirmações antigas. |
| `reservation_reminder` | Reserva atualmente `confirmada`, entre 20 e 24 horas antes da data/hora, usando `America/Sao_Paulo`. Pendente, cancelada, no-show, realizada e horário ausente ficam fora. |

O lembrete usa `reminder_hours_before=24` e `reminder_window_minutes=240`. São
campos por unidade/regra; a janela precisa terminar antes da reserva. O padrão
permite recuperar até quatro horas de interrupção do worker. Fora da janela não
há envio tardio. Esta janela precisa ser aceita pelo responsável operacional e
corresponder à redação do template antes da ativação.

Mudar uma regra atualiza seu corte de confirmação; eventos anteriores à edição
não são recuperados automaticamente. Remarcações não geram uma segunda mensagem
da mesma etapa: a chave única continua unidade + reserva + etapa. Alterações após
uma tentativa exigem comunicação humana, evitando duplicidade ou confirmação de
uma data antiga. Reserva confirmada antes da ativação pode receber o lembrete se
entrar na janela e satisfizer todos os requisitos de consentimento e template.

## Template, variáveis e consentimento

Cada regra armazena o próprio `content_sid` e `template_variables`. Não há template
global nem significado implícito para `{{1}}`. O mapa deve cobrir **nome, data,
hora e unidade**, corresponder a todas as variáveis declaradas na Content API e
ser verificado no momento de habilitar e novamente antes de cada tentativa.
Nome/unidade vêm do registro da mesma reserva/unidade; data e hora têm formatos
`dd/mm/aaaa` e `HH:MM`. Dados ausentes impedem a tentativa.

Exemplo de corpo para configurar uma regra **desativada**, sem envio:

```json
{
  "enabled": false,
  "content_sid": "PREENCHER_SID_HX_DO_TEMPLATE_DA_UNIDADE",
  "template_variables": {"1": "nome", "2": "unidade", "3": "data", "4": "hora"},
  "reminder_hours_before": 24,
  "reminder_window_minutes": 240
}
```

Destino: `PUT /api/restaurants/{restaurant_id}/outreach/config/{stage}`.
O marcador do exemplo precisa ser substituído por um SID real válido antes do PUT.
`enabled=true` exige resposta `approved` da verificação WhatsApp; `received` não basta.

Templates submetidos pelo responsável da execução, conforme prova separada
`reservation-template-proof-20260917.json`:

- Confirmação: `HXc5378a3bd3fab82c4e1e7c289a054326`.
- Lembrete: `HXf0e4708a7b1c5762397573fdcacecc85`.
- Mapa declarado: 1 nome, 2 unidade, 3 data, 4 hora. Estado informado nesta etapa:
  `received` na submissão; nova leitura em 17/09 às 11:06 UTC confirmou **approved**
  nos dois. Seis regras foram salvas desativadas; não são disparos ativos.

A mesma evidência explícita de consentimento `whatsapp_followup` e flag de contato
das réguas existentes é exigida; uma reserva recebida não concede consentimento.
Revogação e status/data da reserva são relidos sob transação antes da criação da
tentativa. As linhas da reserva e do contato são bloqueadas nessa etapa. Como em
qualquer integração externa, cancelamento posterior à tentativa já aceita pelo
provedor não pode desfazer a mensagem; isso fica sujeito a acompanhamento humano.

As variáveis são conferidas usando os contratos oficiais de
[variáveis da Twilio](https://www.twilio.com/docs/content/using-variables-with-content-api)
e [consulta de Content](https://www.twilio.com/docs/content/content-api-resources).

## Agendamento e controles

`outreach_scheduler.py` agenda uma consulta a cada 15 minutos, somente quando
`SERENA_OUTREACH_SCHEDULER_ENABLED=true`. A inicialização é independente do WBR.
O worker consulta apenas unidades ativas com regras habilitadas e executa as
famílias `nurture`, `pos_evento` e `reservation` presentes nessas regras. Falha em
uma família/unidade é registrada sem interromper as demais.

Além do scheduler, **todos** os requisitos de envio permanecem necessários:

1. `SERENA_OUTREACH_SEND_ENABLED=true`.
2. Regra habilitada, template atualmente aprovado e remetente válido da unidade.
3. Consentimento com evidência, sem revogação posterior.
4. Evento elegível e ausência de tentativa anterior.
5. Credenciais do provedor disponíveis.

Com scheduler ligado e envio desligado, só há prévia: nenhuma outbox é criada.
Com ambos ausentes, nenhum worker de régua é iniciado. Não há criação de serviço
pago, envio livre como fallback nem tentativas repetidas de resposta ambígua.
Vários workers podem disputar o mesmo evento: a unicidade na outbox permite
somente uma tentativa. `sent` significa aceite com SID, nunca prova de entrega.

O scheduler roda dentro do backend e depende de sua disponibilidade. Reinício
fora da janela não reproduz lembretes vencidos. Confirmações elegíveis desde a
última ativação podem ser recuperadas enquanto a reserva ainda for futura.

## Implantação e reversão

1. Aplicar, em ordem, as migrações de outbox/consentimento, histórico CRM e
   `20260917050855_reservation_outreach_schedule.sql`. A nova migração apenas
   amplia enums/checks e adiciona campos; não cria regras nem consentimentos.
2. Publicar o código mantendo os dois controles globais desligados.
3. Conferir cada unidade, aprovação do template, mapa, janela e evidência de
   consentimento; usar prévia antes da ativação coordenada.
4. Para interromper novos disparos, desligar o envio global e/ou as regras.
   Desligar o scheduler interrompe também as consultas periódicas. Preservar
   outbox e histórico para reconciliação; não apagar tentativas para forçar retry.

Não há ensaio por mensagem real nesta entrega. Testes offline simulam a Content API
e o envio; o hook restaurado usa apenas o Postgres descartável do backup runner,
com fixtures sintéticas fora de produção. Ele verifica as réguas anteriores e as
novas, limites de horário BRT, eventos posteriores à ativação, status, isolamento,
cancelamento/revogação antes do claim, concorrência e remarcação sem duplicidade.

```bash
cd files/restaurant-ai
python3.11 -m unittest test_outreach -v
# Restore hook (executado pelo runner com PGHOST privado e PGDATABASE=serena_restore):
# files/restaurant-ai/test_reservation_outreach_restore.py
```
