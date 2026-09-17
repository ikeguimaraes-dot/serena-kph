# Tagme: fonte de turnos e exportação do legado

Auditoria somente leitura em 17/09/2026, 01:40 BRT. Nenhum dado de produção,
reserva, fila, configuração ou mensagem foi alterado. Evidência resumida:
[`tagme-audit-proof-20260917.json`](tagme-audit-proof-20260917.json).

## Resultado comprovado

| Campo | Meet & Eat | Frêneze |
|---|---|---|
| Venue confirmado | `62ffd74ddaf31500126b3e29` | `6a73919fef73b2f5d86824de` |
| Origem do ID | `restaurants.tagme_venue_id` e prompt ativo | URL no prompt ativo; campo no banco vazio |
| Identidade pública | Meet & Eat, Vila Olímpia, São Paulo/SP | Frêneze, Vila Olimpia, São Paulo/SP |
| Antecedência mínima | 60 minutos | 180 minutos |
| Janela máxima | 90 dias | 90 dias |
| Tolerância de atraso | 15 minutos | 15 minutos |
| Configuração de grupos | habilitada, 9–12 pessoas | habilitada, 7–15 pessoas |
| Datas retornadas | 17/09–15/12/2026, 90 dias | 17/09–15/12/2026, 90 dias |
| Combinações data/ambiente/tamanho/horário | 29.650 | 14.454 |
| Turnos na agenda própria | 0 | 0 |
| Capacidade física em pessoas | não determinada | não determinada |

Os endpoints oficiais usados são somente os que o widget público utiliza:
`https://public.tagme.com.br/venues/{id}`, `/apps-availability` e
`/availability-for-app/reservationWidget`. As seis leituras retornaram HTTP 200.
Nome e ID foram conferidos antes de ler a disponibilidade; nenhum segredo Tagme
foi enviado. Reservas estavam habilitadas/disponíveis; fila habilitada, porém não
disponível naquele instante. Isso não informa se existe histórico de fila.

`tablesQuantity` e `freeTablesQuantity` variam por tamanho de grupo e horário.
As mesmas mesas podem compor mais de uma configuração. Somar esses valores ou
transformá-los em capacidade fixa causaria dupla contagem. Os limites de grupos
também não são automaticamente o limite geral da casa.

### Amostra verificável de horários

Horários retornados para duas pessoas, na semana de 17–23/09/2026; intervalos
abaixo avançam a cada 30 minutos. São disponibilidade observada, não regra
semanal permanente nem prova de horário de funcionamento.

| Data | Meet — Salão Principal | Frêneze — Salão Principal e Deck |
|---|---|---|
| 17 e 18/09 | 12:00, 12:30, 14:00–22:00 | 12:00–23:00 |
| 19/09 | 12:00–13:00 e 17:00–22:00 | 12:00–15:00 e 17:00–23:00 |
| 20/09 | 12:00–13:00 e 17:00–21:00 | nenhum ambiente retornado |
| 21/09 | 12:00, 12:30, 14:00 e 19:00–21:00 | 12:00–14:00 e 19:00–22:00 |
| 22 e 23/09 | 12:00, 12:30, 14:00 e 19:00–22:00 | 12:00–14:00 e 19:00–22:00 |

Ausência de ambiente no dia 20 não autoriza afirmar que a Frêneze está fechada.
A matriz completa por data, ambiente e tamanho está no artefato privado; antes
de configurar a agenda própria faltam a planta/capacidade real, política de
compartilhamento das mesas, duração/ocupação, bloqueios e aprovação operacional.

## Links oficiais para continuidade

- Meet: https://reservation-widget.tagme.com.br/reservation/schedule/62ffd74ddaf31500126b3e29/reservationWidget
- Frêneze: https://reservation-widget.tagme.com.br/smartlink/6a73919fef73b2f5d86824de
- Madonna: https://usetag.me/madonnacucina — origem `TAGME_WIDGET_URL` da produção;
  HTTP 200 após redirecionar para o widget do venue `691377229337bdf1ad07625f`.

## Histórico de reservas e fila: pendente de acesso específico

**Nenhuma linha de histórico foi exportada.** Não significa histórico vazio.
Data mais recente e contagem existente continuam desconhecidas. Foi possível
auditar configuração pública, não acessar dados pessoais de clientes.

- A [entrada oficial](https://tagme.com.br/entrar) encaminha a gestão para
  [login da Tagme](https://waitlist.tagme.com.br/login); não há sessão autenticada
  disponível neste procedimento.
- `https://api.tagme.com.br/swagger/index.html` retornou **401**. A tentativa foi
  encerrada, sem contornar autenticação nem tentar endpoints protegidos alternativos.
- Há `TAGME_API_KEY` e `TAGME_PARTNER_APP_ID` nas variáveis Railway, porém não há
  contrato de API de exportação comprovado. O cliente legado local contém consulta
  por telefone sem filtro de venue; não foi executada, pois não delimita o tenant.

### Entrega necessária para concluir a migração

Responsável operacional: Ike ou operador designado com acesso ao painel Tagme.
Responsável técnico: engenharia Serena. Obter exportação autorizada **por venue**
ou documentação/acesso da API correspondente. Manter reservas e fila separadas.

Campos a solicitar, caso disponibilizados pelo fornecedor:

| Entidade | Identidade e campos mínimos para revisão |
|---|---|
| Reserva | ID legado, venue ID, criação/atualização, data/hora e fuso, tamanho do grupo, status/desfecho, origem, ambiente, nome/telefone do titular |
| Fila | ID legado, venue ID, entrada/chamada/saída e fuso, tamanho do grupo, status, nome/telefone do titular |
| Consentimento | finalidade, estado, data e fonte, quando houver; ausência nunca vira consentimento |

Antes de importar: contar linhas, registrar colunas, menor/maior data e SHA-256;
conferir identidade do venue; mapear status sem inventar comparecimento; chave
de deduplicação `(fonte, venue_id, id_legado)`, preservando o ID original. Se não
houver ID, gerar candidatos a duplicidade e pedir revisão; telefone+horário não
é chave garantidamente única. Validar em banco restaurado isolado, apresentar
diff por tenant, revisar colisões e só então coordenar importação com o responsável.

## Reprodução e armazenamento

```bash
/usr/local/bin/python3.11 scripts/tagme_readonly_audit.py \
  --railway-cwd /caminho/da/pasta/vinculada/ao/Railway \
  --allow-active-prompt-link
```

Requer Python 3.11, asyncpg e Railway CLI autenticada. O script carrega variáveis
apenas em memória, usa transação SQL somente leitura e limita os venues a Meet e
Frêneze. Não faz login, não envia mensagem, não cria reserva e não exporta clientes.

Artefatos: `~/.local/share/serena-recovery/export-legado-20260917`, diretório 0700,
arquivos 0600, fora de Git. Incluem respostas JSON brutas, padrões por data e
manifesto de hashes. O repositório contém somente resumo de configuração pública.
Essa pasta também é o destino previsto para futuro legado privado autorizado;
dados pessoais nunca devem entrar no repositório.
