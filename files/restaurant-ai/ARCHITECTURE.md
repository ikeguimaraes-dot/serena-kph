# Restaurant AI — Arquitetura

Visão sistêmica do produto Madonna Cucina (KPH). Para o sistema de testes da Serena, ver `README.md`.

## Componentes

```
                              ┌─────────────────────────┐
                              │   Painel (Next.js 16)   │
                              │  madonna-painel.vercel  │
                              └────────────┬────────────┘
                                           │ HTTPS
                                           ▼
                ┌──────────────────────────────────────────────┐
                │        Backend FastAPI (Railway)             │
                │   restaurant-ai-production-bb5d.up.railway   │
                └─┬──────────────────────────────────┬─────────┘
                  │                                  │
                  │ Anthropic SDK                    │ asyncpg
                  ▼                                  ▼
        ┌─────────────────┐              ┌──────────────────────┐
        │  Claude API     │              │  Supabase Postgres   │
        │  (Sonnet 4.5)   │              │  (managed)           │
        └─────────────────┘              └──────────────────────┘
                  ▲
                  │ webhook
                  │
        ┌─────────────────┐
        │  Twilio (WhatsApp) │
        └─────────────────┘
```

## Repositórios e paths

| Componente | Path local | Deploy | Repo |
|---|---|---|---|
| Painel (frontend) | `painel/` | Vercel auto-deploy via git push | github.com/ikeguimaraes-dot/restaurant-ai-painel |
| Backend API | `./` (main.py, agent.py, database.py) | Railway via `railway up` | (não em git — deploy direto via CLI) |
| Test system Serena | `./` (run.py, src/, corpus/) | Local | (não em git) |

## Stack

**Frontend** — Next.js 16, React 19, Tailwind v4, Recharts 3, Lucide React, PostHog (env-driven)

**Backend** — FastAPI 0.115+, asyncpg 0.30+, anthropic ≥0.40, cachetools (memória), GZip middleware

**DB** — Supabase Postgres com 3 grupos de tabelas:
- Operacional: `restaurants`, `business_hours`, `menu_items`, `faq_items`, `reservations`, `handoff_sessions`, `conversations`, `team_members`
- CRM: `contacts`
- Serena (Onda 8): `serena_metrics`, `serena_prompt_versions`, `serena_weekly_reports`

**Externo** — Twilio (WhatsApp Business), Tagme (widget de reservas — link), Anthropic Claude API.

## Fluxo de mensagens

1. Cliente envia WhatsApp ao número Madonna
2. Twilio entrega webhook em `POST /webhook/whatsapp`
3. `RestaurantAgent.process()`:
   - `ensure_contact()` — cria contato seed se novo
   - Verifica `is_in_handoff()` — se sim, só persiste msg e retorna sem responder
   - Carrega histórico (últimas 20 msgs) + system prompt da `serena_prompt_versions WHERE ativa=TRUE`
   - Loop até 6 iterações de tool_use ou end_turn
   - Captura tokens, latência, tools chamadas
   - Detecta intent + fricções via regex
   - Persiste em `serena_metrics`
   - Se handoff: cria handoff_session, notifica equipe via Twilio, dispara categorização async via Haiku
4. Painel polla `/api/restaurants/{rid}/handoff` (20s) e `/api/restaurants/{rid}/conversations` (8s)
5. Operador responde via `POST /api/handoff/{hid}/reply` → Twilio

## Endpoints principais

### Operacional
- `GET /api/restaurants` — lista
- `GET /api/restaurants/{rid}` — slim (sem menu)
- `GET /api/restaurants/{rid}/menu` — separado
- `GET /api/restaurants/{rid}/reservations`
- `GET /api/restaurants/{rid}/handoff`
- `POST /api/handoff/{hid}/{reply,assume,resolve}`
- `GET /api/restaurants/{rid}/conversations`
- `GET /api/conversations/{user_phone}?rid={rid}`
- `GET /api/reports?rid={rid}&days={n}` — agregado, **cache 60s**

### CRM
- `GET /api/contacts` (filtros: tier, estagio, ocasiao, opt_in)
- `GET /api/contacts/search?q=`
- `GET /api/contacts/{celular}` + `/reservations` + `/conversations`
- `PATCH /api/contacts/{celular}` + `/kanban`
- `POST /api/contacts/mark-inactive` — exige `x-admin-secret`

### Serena (Onda 8)
- `GET /api/serena/metrics?periodo=7d|30d|mtd`
- `GET /api/serena/handoffs/categorizados`
- `GET /api/serena/intencoes`
- `GET /api/serena/friccoes?periodo=14d&limit=30`
- `GET /api/serena/tools/stats`
- `GET /api/serena/custo?periodo=mtd`
- `GET /api/serena/recent?only_handoffs=true`
- `GET /api/serena/training-export?formato=jsonl|json`
- `GET /api/serena/prompts` + `/{id}` + `/active`
- `POST /api/serena/prompts` (cria) — admin
- `POST /api/serena/prompts/{id}/ativar` — admin
- `POST /api/serena/prompts/seed-v1` — admin
- `POST /api/serena/weekly-report` — gera via Claude — admin
- `GET /api/serena/weekly-report` — lista
- `GET /api/insights?rid={rid}` — **cache 1h**

## Variáveis de ambiente

### Backend (Railway)

| Var | Obrigatória | Descrição |
|---|---|---|
| `ANTHROPIC_API_KEY` | sim | Claude API key (sk-ant-…) |
| `DATABASE_URL` | sim | Postgres URL (Supabase) — exige `?sslmode=require` |
| `TWILIO_ACCOUNT_SID` | sim | Conta Twilio |
| `TWILIO_AUTH_TOKEN` | sim | Token Twilio |
| `TWILIO_FROM_NUMBER` | sim | `whatsapp:+551199…` (remetente Madonna) |
| `CORS_ORIGINS` | não | CSV de origens (default inclui madonna-painel.vercel.app + localhost:3000) |
| `ADMIN_SECRET` | recomendado | Header `x-admin-secret` para endpoints sensíveis (cron, prompt mgmt, weekly-report) |
| `PORT` | não | Default 8000 |

### Frontend (Vercel)

| Var | Obrigatória | Descrição |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | sim | URL do backend Railway (ex: `https://restaurant-ai-production-bb5d.up.railway.app`) |
| `NEXT_PUBLIC_POSTHOG_KEY` | não | Ativa tracking — `phc_…` (sem isso, o módulo é no-op) |
| `NEXT_PUBLIC_POSTHOG_HOST` | não | Default `https://app.posthog.com` |

## Como rodar local

### Backend

```bash
cd restaurant-ai/
cp .env.example .env  # preencha as vars acima
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd painel/
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev  # http://localhost:3000
```

## Como deployar

### Backend (Railway)

```bash
railway up --detach
```

A primeira vez exige `railway link` para conectar ao projeto `restaurant-ai`. Variáveis de ambiente são gerenciadas via Railway dashboard ou `railway variables`.

### Frontend (Vercel)

```bash
cd painel/
git push origin main
```

Vercel detecta o push automaticamente e faz build+deploy. Branch principal `main`.

## Multi-tenant

Toda tabela com dado de negócio carrega `restaurant_id TEXT` apontando para `restaurants(id)`. Não há `tenant_id` separado — `restaurant_id` é a unidade de isolamento.

**Provado em prod (Hotfix 6, 2026-04-26):** rodando 2 unidades (`madonna_cucina` + `meet_and_eat`) na mesma instância Railway. `GET /api/restaurants` devolve as ativas, o painel mostra todas no seletor da topbar, e cada endpoint `/api/restaurants/<rid>/<recurso>` é filtrado por `rid` na query — `meet_and_eat` retorna listas vazias enquanto `madonna_cucina` mantém seus dados.

### Cadastrar uma casa nova de verdade

1. **Banco:** `INSERT` em `restaurants` (id slug, nome, whatsapp_number, endereco, ativo=true) + 7 linhas em `business_hours` (uma por dia da semana). Ver `migrations/2026_04_26_meet_and_eat.sql` como template.
2. **WhatsApp:** o `whatsapp_number` no banco precisa bater com um sender autorizado na Twilio. Ou (a) cada casa tem seu próprio número, configurado como sender adicional na Twilio; ou (b) todas as casas compartilham o mesmo `TWILIO_FROM_NUMBER` — nesse caso o roteamento depende do número que o cliente discou (campo `To` do webhook), e o backend faz `get_restaurant_by_whatsapp(To)` pra achar o `restaurant_id` correto.
3. **Serena:** zero código novo. Cada conversa carrega o restaurant correspondente via webhook → `agent.process()` → `_dynamic_header(restaurant)` injeta cardápio/horário/datas especiais daquela casa. Prompt body é compartilhado (versionado por brand no futuro, ver KPH OS plano).
4. **Painel:** sem deploy. O seletor de unidade puxa `GET /api/restaurants` ao mount.

### O que ainda NÃO está pronto pra multi-brand de verdade

- Prompt da Serena é único para todo o sistema (`serena_prompt_versions` sem coluna `brand`). Para Meet & Eat de verdade: adicionar coluna ou usar `restaurant_id` na lookup. Ver KPH OS plano §3.2.
- Identidade "Madonna Cucina" hardcoded no logo/header da Sidebar do painel — vira o `unit.nome` em iteração futura.
- Datas especiais e cardápio são por unidade já (✓), mas FAQ vive em `faq_items` por unidade também (✓). Voz da marca não está separada.

## Migrations

Migrations vivem em `migrations/*.sql`. Aplicar manualmente:

```bash
DATABASE_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2- | tr -d '"')
psql "$DATABASE_URL" -f migrations/2026_04_25_serena_metrics.sql
```

São idempotentes (`CREATE TABLE IF NOT EXISTS`).

## Eventos PostHog ativos no painel

(Ativos quando `NEXT_PUBLIC_POSTHOG_KEY` setado)

| Evento | Origem | Props |
|---|---|---|
| `page_viewed` | toda navegação | path |
| `conversation_opened` | ConversasView | phone, operator, type |
| `handoff_assumed` | Dashboard | id, phone, seconds_since_created |
| `message_sent` | ConversasView | phone, length, duration_ms |
| `contact_edited` | Contatos | celular, fields[] |
| `kanban_card_moved` | Kanban | celular, from, to |
| `search_performed` | Cmd+K | where, query, results |
| `export_clicked` | Relatórios | where, range |

## Caches e camadas de performance

| Camada | TTL | Onde |
|---|---|---|
| Frontend `api.js` request cache | 2.5s + dedupe inflight | painel/src/lib/api.js |
| Backend `/api/reports` | 60s | TTLCache(64) em main.py |
| Backend `/api/insights` | 60min | TTLCache(8) em main.py |
| Backend `/api/serena/metrics` overview | 2min | TTLCache(32) em main.py |
| Prompt ativo da Serena | 5min | _prompt_cache em database.py |
| Vercel CDN | edge cache | rotas estáticas (○ Static) |
| GZip middleware | n/a | resposta >1KB |

## Fluxo de evolução do prompt da Serena

1. Toda segunda manhã: gerar relatório via `POST /api/serena/weekly-report` (ou no painel `/admin/serena` aba "Insights Semanais")
2. Claude gera análise em PT-BR com 3 sugestões de ajuste
3. Aplicar uma sugestão criando nova versão: `POST /api/serena/prompts` (campo `prompt_completo` com a alteração)
4. Ativar: `POST /api/serena/prompts/{id}/ativar`
5. Cache 5min — em até 5min todos os turnos novos usam a versão nova
6. Esperar 24-48h, abrir aba "Visão Geral" → comparar métricas com a versão anterior
7. Se piorou: ativar a versão anterior

## Dados sensíveis (LGPD)

- Conversations e contacts contêm dados pessoais (telefone, nome, email)
- Endpoint `/api/contacts/mark-inactive` exige `x-admin-secret` (cron)
- ADR pendente: política de retenção de conversas (ver decisões pendentes no README do test system)

## Decisões pendentes (Madonna go-live)

Bloqueiam decisões finais de política da Serena — ver `README.md` seção 6 decisões.
