# Onboarding Nova Casa — Serena

Checklist completo para adicionar uma nova marca/unidade à plataforma.
Siga os passos em ordem — cada etapa depende da anterior.

**Estimativa total hoje:** ~3h30 (manual) | **Com automação futura:** ~25 min

---

## Pré-requisitos

- Acesso ao Supabase (service key)
- Acesso ao Railway (`railway link` já configurado)
- Número WhatsApp Business registrado na Twilio (ou reutilizável)
- Aprovação da marca: nome do agente, personalidade, cardápio resumido, FAQ

---

## Passo 1 — Banco de Dados (Supabase) `~20 min`

### 1.1 Inserir restaurante na tabela `restaurants`

```sql
INSERT INTO restaurants (
    id,
    nome,
    whatsapp_number,
    endereco,
    descricao,
    capacidade_maxima_reserva,
    antecedencia_minima_horas,
    capacidade_total,
    ativo
) VALUES (
    'meet_eat',                          -- slug único, snake_case, sem espaços
    'Meet & Eat',                        -- nome de exibição
    '+5511XXXXXXXXX',                    -- número WhatsApp Business (E.164)
    'Rua Exemplo, 123 — Pinheiros, SP',
    'Bistrô contemporâneo com foco em fermentados e sazonalidade.',
    8,                                   -- máx. pessoas via WhatsApp/widget
    2,                                   -- antecedência mínima em horas
    80,                                  -- capacidade total do salão
    true
);
```

> **Checklist:**
> - [ ] `id` é único e igual ao `restaurant_id` usado em todas as outras tabelas
> - [ ] `whatsapp_number` está em formato E.164 (`+55...`)
> - [ ] `ativo = true`

### 1.2 Inserir turnos (`agenda_turnos`)

```sql
-- Exemplo: Jantar único, Seg–Dom
INSERT INTO agenda_turnos (restaurant_id, nome, hora_inicio, hora_fim, dias_semana, capacidade)
VALUES
    ('meet_eat', 'Jantar', '19:00', '23:00', ARRAY[0,1,2,3,4,5,6], 80),
    ('meet_eat', 'Almoço', '12:00', '15:00', ARRAY[0,5,6], 40);   -- só fim de semana + dom
```

> Dias: PostgreSQL DOW — 0=Dom, 1=Seg, ..., 6=Sáb

**Tempo estimado: 15–20 min**

---

## Passo 2 — Prompt e Personalidade da Marca `~40 min`

### 2.1 Criar arquivo de personalidade

Crie `prompts/<restaurant_id>_v1.txt` com o seguinte template:

```
IDENTIDADE
Você é [nome_agente], a voz digital do [nome_restaurante].
[2–3 linhas sobre background e arquétipo da marca]

VOZ — REGRAS INVIOLÁVEIS
[copiar bloco de VOZ do _FALLBACK_BODY em agent_prompt.py e adaptar tom]

CARDÁPIO RESUMIDO
[especialidades + faixa de preço]

FAQ DA CASA
- pagamento: [formas aceitas]
- estacionamento: [info]
- dress_code: [info]
- crianças: [info]
- cancelamento: [política]
```

### 2.2 Fazer upload do prompt via API

```bash
# Após editar upload_prompt_v10.py com os dados da nova casa:
BACKEND_URL=https://restaurant-ai-production-bb5d.up.railway.app
curl -s -X POST "$BACKEND_URL/api/serena/prompts" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Secret: kph@serena2026" \
  -d '{
    "nome": "meet-eat-v1",
    "versao": "1",
    "restaurant_id": "meet_eat",
    "prompt_completo": "<conteúdo do arquivo .txt>",
    "ativar": true
  }'
```

Ou use o script `upload_prompt_v10.py` como modelo — duplicar e adaptar para a nova casa.

### 2.3 Registrar `nome_agente` no banco

```sql
-- Se a tabela restaurants tiver campo nome_agente (verifique schema atual):
UPDATE restaurants SET nome_agente = 'Bia', personalidade = '' WHERE id = 'meet_eat';
```

Se não existir o campo, adicione no `agent_prompt.py` como fallback manual até ser incluído no schema.

**Tempo estimado: 30–40 min**

---

## Passo 3 — Twilio: Registrar Sender WhatsApp `~45 min (excluindo aprovação Meta)`

### Opção A — Reutilizar número existente (recomendado para MVP)

Não é necessário: o `TWILIO_FROM_NUMBER` atual já envia para qualquer número opt-in.
Apenas registre o `whatsapp_number` da nova casa no banco (Passo 1) e o backend
roteará corretamente.

### Opção B — Número dedicado por marca

1. No Twilio Console → Messaging → Senders → WhatsApp Senders
2. Clique **Register a number** → escolha número existente ou compre novo
3. Preencha business display name, category, sample messages
4. Aguarde aprovação Meta (1–5 dias úteis)
5. Após aprovação, definir variável de ambiente (Passo 4)

> **Regra crítica:** o valor de `TWILIO_FROM_NUMBER` nunca deve ter prefixo `whatsapp:`.
> Correto: `+5511988302367` | Errado: `whatsapp:+5511988302367`

**Tempo estimado:** 15 min (configuração) + 1–5 dias úteis (aprovação Meta se novo número)

---

## Passo 4 — Railway: Variáveis de Ambiente `~15 min`

Adicione ou confirme as variáveis necessárias:

```bash
# Verifique valores atuais
railway variables

# Adicione se necessário (sem prefix whatsapp:)
railway variables --set "TWILIO_FROM_NUMBER=+5511988302367"

# Se o novo restaurante usar número Twilio dedicado:
# railway variables --set "TWILIO_FROM_<RESTAURANT_ID>=+5511XXXXXXXXX"
```

> **Nota:** `railway variables --set` pode dar timeout — verifique com `railway variables`
> logo após. O valor é persistido mesmo com timeout na CLI.

### Variáveis que devem existir

| Variável | Obrigatória | Descrição |
|---|---|---|
| `ANTHROPIC_API_KEY` | Sim | Chave Anthropic |
| `DATABASE_URL` | Sim | URI Supabase (modo Session) |
| `WEBHOOK_SECRET` | Sim | HMAC secret do webhook Twilio |
| `TWILIO_ACCOUNT_SID` | Sim (WhatsApp) | SID da conta Twilio |
| `TWILIO_AUTH_TOKEN` | Sim (WhatsApp) | Token Twilio |
| `TWILIO_FROM_NUMBER` | Sim (WhatsApp) | Número sender (sem prefixo) |

**Tempo estimado: 10–15 min**

---

## Passo 5 — Configurar Webhook Twilio `~10 min`

No Twilio Console → Phone Numbers (ou WhatsApp Senders) → novo número → Messaging:

- **When a message comes in:** `POST https://restaurant-ai-production-bb5d.up.railway.app/webhook/whatsapp`

Para validar que o HMAC está funcionando:
```bash
curl -s https://restaurant-ai-production-bb5d.up.railway.app/health
# Esperado: {"status":"ok"}
```

**Tempo estimado: 5–10 min**

---

## Passo 6 — Painel: Isolamento por restaurant_id `~10 min`

### 6.1 Verificar guard no middleware

O painel filtra dados por `restaurant_id` via query params e RLS Supabase.
Confirme que o novo `restaurant_id` está no guard list se houver lista de permissões
em `painel/middleware.js`.

```bash
grep -n "restaurant_id\|allowed\|guard" painel/src/middleware.js | head -20
```

### 6.2 Criar usuário operador para a nova casa

```bash
# Edite setup_operadora.py com os dados da nova casa
USER_EMAIL = "operadora@meeteat.com.br"
USER_PASSWORD = "meeteat@2026"
USER_NOME = "Operadora Meet & Eat"
USER_ROLE = "operador"

# Execute com a service key do Supabase
SUPABASE_SERVICE_KEY=eyJ... python3 setup_operadora.py
```

### 6.3 Testar acesso isolado

- Login com operadora nova no painel
- Confirmar que `/conversas`, `/reservas`, `/os` mostram apenas dados de `meet_eat`
- Confirmar que `/admin` e `/orkestri` estão bloqueados para role `operador`

**Tempo estimado: 10 min**

---

## Passo 7 — Widget de Reservas `~5 min`

O widget está disponível em:

```
https://madonna-painel.vercel.app/widget/reserva?rid=<restaurant_id>
```

Para uso em site externo (iframe):

```html
<iframe
  src="https://madonna-painel.vercel.app/widget/reserva?rid=meet_eat"
  width="420"
  height="600"
  frameborder="0"
  style="border-radius:12px;"
></iframe>
```

> Se o painel tiver `NEXT_PUBLIC_RESTAURANT_ID` hardcoded (verificar `.env.production`),
> será necessário parametrizar por query string ou criar deploy separado por marca.

**Tempo estimado: 5 min**

---

## Passo 8 — Smoke Test `~15 min`

Execute o smoke test completo após todas as etapas:

```bash
BACKEND_URL=https://restaurant-ai-production-bb5d.up.railway.app \
TWILIO_FROM_NUMBER=+5511988302367 \
python3 smoke_test.py
```

### Checklist manual de go-live

- [ ] `GET /health` → `{"status":"ok"}`
- [ ] `GET /api/agenda/meet_eat/disponibilidade?data=YYYY-MM-DD&pessoas=2` → retorna turnos
- [ ] POST reserva via API:
  ```bash
  curl -s -X POST "https://restaurant-ai-production-bb5d.up.railway.app/api/agenda/meet_eat/reservas" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Secret: kph@serena2026" \
    -d '{"nome":"Teste","telefone":"11999999999","data":"2026-06-20","hora_inicio":"19:00","pessoas":2}'
  # Esperado: 201 + objeto da reserva
  ```
- [ ] Webhook responde mensagem de teste via WhatsApp real (send "oi" para o número)
- [ ] Painel `/conversas` mostra a conversa de teste
- [ ] Handoff: enviar mensagem que aciona handoff → verificar notificação no WhatsApp da equipe
- [ ] Widget de reserva abre e conclui reserva de teste
- [ ] Deletar reservas de teste do banco

**Tempo estimado: 15 min**

---

## Resumo de Tempo

| Passo | Etapa | Hoje (manual) | Com automação futura |
|---|---|---|---|
| 1 | Banco de dados | 20 min | 2 min (script) |
| 2 | Prompt e personalidade | 40 min | 10 min (template assistido) |
| 3 | Twilio sender | 15 min + aprovação Meta | 5 min (reutilizando número) |
| 4 | Railway env vars | 15 min | 2 min (script) |
| 5 | Webhook Twilio | 10 min | 2 min |
| 6 | Painel + operador | 10 min | 3 min (script) |
| 7 | URL widget | 5 min | 1 min |
| 8 | Smoke test | 15 min | 5 min (automatizado) |
| **Total** | | **~3h30** | **~30 min** |

> O gargalo real é a aprovação da Meta para números Twilio dedicados (1–5 dias úteis).
> Usando o número existente já aprovado, o onboarding técnico fica em **~2h** hoje.

---

## Automação Futura (roadmap)

- `scripts/onboarding_casa.py` — cria registro no banco + turnos a partir de YAML
- Template de prompt por categoria (bistrô, italiana, rodízio) com variáveis preenchíveis
- `setup_operadora.py` já genérico — apenas parametrizar email/nome/restaurante
- CI smoke test automático pós-merge com novo `restaurant_id`
