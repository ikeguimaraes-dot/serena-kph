# Claude Code — Serena Backend + Painel

Instruções pro Claude Code operar neste repositório.

---

## Arquitetura

| Camada | Stack | Deploy |
|--------|-------|--------|
| Backend API | FastAPI + asyncpg + Supabase/PostgreSQL | Railway (`restaurant-ai`) |
| Painel | Next.js 16 (App Router, React 19) | Vercel (`madonna-cucina-painel.vercel.app`) |
| Agente WhatsApp | Claude Sonnet 4.6 com tool use loop | Integrado ao backend |
| Reservas | Tagme API (`api.tagme.com.br/v1/partners`) | Via `tagme_client.py` |

**Repos git:**
- `files/restaurant-ai/` — backend (sem remote; deploy via `railway up`)
- `files/restaurant-ai/painel/` — painel (Vercel-linked; deploy via `npx vercel --prod --yes`)

---

## Comandos de deploy

```bash
# Backend — Railway
railway up --service restaurant-ai --detach

# Painel — Vercel (rodar de dentro de /painel/)
cd files/restaurant-ai/painel
npx vercel --prod --yes
```

**Railway CLI:** o `railway login` exige browser interativo. Se a sessão expirar, o usuário deve rodar `! railway login` no terminal. O `railway up --detach` (upload) ainda funciona sem login completo.

---

## Variáveis de ambiente

### Backend (Railway)
| Var | Descrição |
|-----|-----------|
| `ADMIN_SECRET` | Secret do header `x-admin-secret` para endpoints protegidos |
| `DATABASE_URL` | Supabase PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | API da Claude |
| `TAGME_API_KEY` | Chave Tagme |
| `TAGME_PARTNER_APP_ID` | ID do parceiro Tagme |
| `CORS_ORIGINS` | Se setada, sobrescreve o default do código — incluir `https://madonna-cucina-painel.vercel.app` |

### Painel (Vercel)
| Var | Onde fica | Descrição |
|-----|-----------|-----------|
| `NEXT_PUBLIC_API_URL` | Dashboard Vercel | URL do Railway |
| `NEXT_PUBLIC_ADMIN_SECRET` | `.env.production` (no repo) | Secret do painel |
| `PANEL_AUTH_USER` / `PANEL_AUTH_PASS` | Dashboard Vercel | Basic Auth do `middleware.js` |

> **Atenção:** variáveis `NEXT_PUBLIC_*` são baked no bundle em build time. Vars do dashboard Vercel têm precedência sobre `.env.production`. Se uma var do dashboard estiver vazia (`""`), o bundle recebe string vazia — não usa o fallback do código. Quando em dúvida, remover a var do dashboard e colocar em `.env.production`.

---

## Auth no backend

```python
def require_admin(x_admin_secret: Optional[str] = Header(None)):
    secret = os.environ.get("ADMIN_SECRET")
    if not secret:      raise HTTPException(503)   # Railway mal configurado
    if x_admin_secret != secret: raise HTTPException(403)
```

Endpoints **sem** `require_admin` (públicos):
- `GET /api/restaurants`, `GET /api/restaurants/{rid}` e subrotas
- `GET /api/contacts/{celular}` e subrotas de leitura individual
- `POST /api/contacts`, `GET /api/contacts`, `PATCH /api/contacts/{celular}` e subrotas
- `POST /api/contacts/mark-inactive`, `POST /api/contacts/{phone}/retag`
- `POST /api/handoff/assumir`
- `GET /api/serena/*` (métricas, weekly-report, prompts)
- `POST /api/serena/weekly-report` (geração — sem auth)
- Webhooks WhatsApp

Endpoints **com** `require_admin`:
- `POST /api/serena/prompts` e `/ativar` e `/seed-v1`
- `POST /api/serena/test-message`

### POST /api/handoff/assumir — comportamento
Cria handoff manualmente a partir do painel (sem solicitação do cliente).
```python
# Body esperado
{ "user_phone": str, "restaurant_id": str, "atendente_nome": str (opcional) }
# Fluxo: create_handoff() → update_handoff_status("em_atendimento") → {"id": hid, "status": "em_atendimento"}
```
Após retorno com `id`, o painel recarrega handoffs + conversas e o `useEffect` de re-sync atualiza `selected.handoff_id` automaticamente, habilitando o textarea de resposta.

---

## CORS

```python
_default_origins = "https://madonna-painel.vercel.app,https://madonna-cucina-painel.vercel.app,http://localhost:3000"
```

Se Railway tiver `CORS_ORIGINS` setada como env var, ela **sobrescreve** esse default. Verificar se inclui `madonna-cucina-painel.vercel.app`.

---

## Padrões de código

### Python (backend)
- `(r.get("campo") or "").strip()` — nunca `.get("campo", "").strip()` (não trata `None`)
- `asyncpg` + `async with pool().acquire() as c:`
- Logs com `print()` simples
- Python 3.10+, `pathlib.Path`

### JavaScript (painel)
- `"use client"` em todos os componentes com estado/hooks
- Dados dinâmicos de tempo (`new Date()`, `Date.now()`) somente após mount:
  ```js
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  // render: {mounted ? valor_dinamico : null}  ← null, nunca ""
  ```
- `""` (string vazia) em JSX causa React hydration error #418 — usar `null`
- `x-admin-secret` injetado globalmente em `src/lib/api.js` via `request()`

---

## Estrutura de arquivos chave

```
files/restaurant-ai/
├── main.py               # FastAPI app, todos os endpoints; /health aceita GET e HEAD
├── agent_prompt.py       # Montagem do system prompt da Serena
├── agent_context.py      # Contexto CRM do contato atual
├── tagme_client.py       # Cliente Tagme (reservas)
├── tagme_handlers.py     # Handlers de tool use (consultar/cancelar reserva)
├── database.py           # Todas as queries asyncpg
├── serena_weekly.py      # Geração do relatório semanal via Claude
└── painel/
    ├── src/lib/api.js    # Camada de fetch — cache 14s + x-admin-secret
    ├── src/components/Shell.jsx          # Layout global + nav
    ├── src/components/views/ConversasView.jsx  # botão ⚡ Assumir conversa → POST /api/handoff/assumir
    ├── src/components/views/SerenaAdminView.jsx
    └── middleware.js     # Basic Auth Vercel Edge
```

---

## agent_prompt.py — estrutura do prompt

O prompt final = `_dynamic_header(r, contact_block)` + `"\n"` + body (DB ou `_FALLBACK_BODY`).

### Blocos do `_FALLBACK_BODY` (em ordem)
1. IDENTIDADE — voz, arquétipo, VOZ (regras invioláveis), COMPORTAMENTO, FRASES PROIBIDAS, ABERTURAS, CONFIRMAÇÕES, DISPONIBILIDADE NEGATIVA, ENCERRAMENTOS, REGRA DE OURO
2. RESERVAS — canal oficial Tagme (link widget); tools `consultar_reserva` e `cancelar_reserva`
3. ESCALAÇÃO PARA HUMANO — critérios obrigatórios
4. CADÊNCIA — pós-23h, delays
5. CRM — coleta invisível via tool `update_contact`; NOME DO CLIENTE
6. FILOSOFIA
7. VARIAÇÕES COMUNS DE LINGUAGEM — aliases de intent (reserva, consulta, cardápio, urgência)
8. RESERVAS PARA 2 PESSOAS — widget exige mín. 3; nunca enviar link; sempre handoff cat. "reserva"
9. RESERVAS EXISTENTES — sem acesso ao sistema; sempre handoff com motivo claro
10. EVENTOS E DATAS COMEMORATIVAS — handoff cat. "cardápio"; datas: Namorados, Mães, Páscoa, Natal, Réveillon

### Padrões de código — agent_prompt.py
- `(r.get("campo") or "").strip()` — nunca `.get("campo", "").strip()` (não trata `None`)
- `d.get("nome") or "Data especial"` — guard em loops de datas especiais
- Blocos de texto do prompt em ASCII puro (sem acentos) — evita encoding issues

### tagme_handlers.py
- `import httpx` no topo
- Toda chamada a `cancel_reservation` envolve `try/except httpx.TimeoutException`
- Mensagem de timeout: "Não foi possível cancelar sua reserva no momento — o sistema de reservas está demorando para responder. Tente novamente em instantes ou chame nossa equipe."

---

## Serena — sistema de testes (v6)

Arquitetura: corpus JSON → runner → judge → aggregator.

### Regras do corpus
- NUNCA editar `corpus/mdna_v6.json` diretamente — sempre via `build_corpus.py`
- IDs imutáveis (MDNA-001 a MDNA-228) — não renumerar
- Ao adicionar casos, atualizar `assert len(CASES) == N`

### Rodar testes
```bash
python smoke_test.py                          # 5 casos canônicos (~$0.05, 10s)
python run.py --severity critical             # 53 casos críticos (~$1.50, ~5 min)
python run.py --block situacoes_eticas        # 10 casos éticos (revisão humana obrigatória)
python run.py --baseline results/judged_*.json # comparar com baseline
python build_corpus.py                        # regenerar corpus após edição
```

### Sensibilidade máxima
Casos MDNA-211/212/213 (crise emocional, violência doméstica, ideação suicida):
- Nunca otimizar sem consulta profissional
- Sempre incluir CVV 188, 180, SAMU 192, 190 no topo das respostas
- Resposta padrão: (a) números, (b) pergunta de segurança, (c) porta aberta neutra

---

## Decisões pendentes (bloqueiam go-live)

Não improvisar sem input do Ike:
1. Política de áudio
2. Identificação de IA
3. DPO do grupo KPH
4. Confirmação de números de emergência
5. Protocolo de escalação sensível
6. Retenção de conversas

---

## Contexto do grupo KPH

- **Madonna (MDNA)**: marca piloto, voz sofisticada/autoral
- **Meet & Eat**: informal, energética
- **Pipokaê**: aeroportos, bilíngue, funcional
- **Klauss**: hedonista, noturno, masculino
- **The Forge**: elevado, técnico, gastronomia fogo

---

## Workflow preferencial

- Planejar e revisar no Claude.ai
- Executar no Claude Code
- Trazer outputs/erros de volta pro Claude.ai para diagnóstico
