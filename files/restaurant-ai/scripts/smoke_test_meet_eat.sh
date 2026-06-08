#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# 9.5 — Smoke test Meet & Eat
# Valida que todos os pré-requisitos estão OK antes do go-live com a Meta/Twilio.
#
# Uso:
#   bash scripts/smoke_test_meet_eat.sh
#
# Variáveis de ambiente (opcionais — usa defaults de produção se não setadas):
#   BACKEND_URL     URL do Railway
#   ADMIN_SECRET    segredo de admin
#   DB_URL          connection string Supabase
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

BACKEND="${BACKEND_URL:-https://restaurant-ai-production-bb5d.up.railway.app}"
SECRET="${ADMIN_SECRET:-kph@serena2026}"
DB_URL="${DB_URL:-postgresql://postgres.fgntcrxuhfwcauvahaiz:123%40Ike456%23@aws-1-sa-east-1.pooler.supabase.com:5432/postgres}"
RID="meet_and_eat"

PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET}  $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}✗${RESET}  $1"; FAIL=$((FAIL+1)); }
info() { echo -e "  ${YELLOW}→${RESET}  $1"; }

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Smoke Test — Meet & Eat (${RID})"
echo "  Backend: ${BACKEND}"
echo "════════════════════════════════════════════════════════"
echo ""

# ── 1. Health check ─────────────────────────────────────────────────────────
echo "1. Health check"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND}/health")
if [ "$STATUS" = "200" ]; then
  ok "GET /health → 200"
else
  fail "GET /health → ${STATUS} (esperado 200)"
fi

# ── 2. Registro no banco ─────────────────────────────────────────────────────
echo ""
echo "2. Registro do restaurante no banco"
ROW=$(python3 -c "
import asyncio, asyncpg, sys

async def main():
    conn = await asyncpg.connect('${DB_URL}')
    row = await conn.fetchrow(\"SELECT id, nome, nome_agente, whatsapp_number FROM restaurants WHERE id='${RID}' AND ativo=true\")
    await conn.close()
    if row:
        print(f'{row[\"id\"]}|{row[\"nome\"]}|{row[\"nome_agente\"]}|{row[\"whatsapp_number\"]}')
    else:
        print('NOT_FOUND')

asyncio.run(main())
" 2>/dev/null || echo "DB_ERROR")

RID_PLACEHOLDER='NOT_FOUND'

if [[ "$ROW" == "NOT_FOUND" || "$ROW" == "DB_ERROR" ]]; then
  fail "Restaurante '${RID}' não encontrado ou ativo=false no banco"
else
  IFS='|' read -r rid nome agente phone <<< "$ROW"
  ok "Restaurante: ${nome} (id=${rid})"
  if [ "$agente" != "" ]; then
    ok "nome_agente: ${agente}"
  else
    fail "nome_agente está vazio"
  fi
  if [[ "$phone" == "+55"* && ${#phone} -ge 13 ]]; then
    ok "whatsapp_number: ${phone}"
    if [[ "$phone" == "+5511000000000" ]]; then
      fail "whatsapp_number ainda é o placeholder +5511000000000 — atualizar antes do go-live"
    fi
  else
    fail "whatsapp_number inválido ou placeholder: ${phone}"
  fi
fi

# ── 3. Prompt ativo em serena_prompt_versions ─────────────────────────────────
echo ""
echo "3. Prompt ativo da Camila"
PROMPT_ROW=$(python3 -c "
import asyncio, asyncpg

async def main():
    conn = await asyncpg.connect('${DB_URL}')
    row = await conn.fetchrow(\"SELECT versao, ativa, LENGTH(prompt_completo) as tam FROM serena_prompt_versions WHERE restaurant_id='${RID}' AND ativa=true\")
    await conn.close()
    if row:
        print(f'{row[\"versao\"]}|{row[\"tam\"]}')
    else:
        print('NOT_FOUND')

asyncio.run(main())
" 2>/dev/null || echo "DB_ERROR")

if [[ "$PROMPT_ROW" == "NOT_FOUND" || "$PROMPT_ROW" == "DB_ERROR" ]]; then
  fail "Nenhum prompt ativo para restaurant_id='${RID}' em serena_prompt_versions"
else
  IFS='|' read -r versao tam <<< "$PROMPT_ROW"
  ok "Prompt versão ${versao} ativo (${tam} chars)"
  if [ "$tam" -lt 200 ]; then
    fail "Prompt parece muito curto (${tam} chars) — verificar conteúdo"
  fi
fi

# ── 4. Turnos cadastrados ────────────────────────────────────────────────────
echo ""
echo "4. Turnos (agenda_turnos)"
TURNOS=$(python3 -c "
import asyncio, asyncpg

async def main():
    conn = await asyncpg.connect('${DB_URL}')
    rows = await conn.fetch(\"SELECT COUNT(*) AS n, STRING_AGG(DISTINCT nome, ', ') AS nomes FROM agenda_turnos WHERE restaurant_id='${RID}'\")
    await conn.close()
    r = rows[0]
    print(f'{r[\"n\"]}|{r[\"nomes\"]}')

asyncio.run(main())
" 2>/dev/null || echo "DB_ERROR")

if [[ "$TURNOS" == "DB_ERROR" ]]; then
  fail "Erro ao consultar agenda_turnos"
else
  IFS='|' read -r n_turnos nomes_turnos <<< "$TURNOS"
  if [ "$n_turnos" -ge 1 ]; then
    ok "${n_turnos} turno(s): ${nomes_turnos}"
  else
    fail "Nenhum turno cadastrado em agenda_turnos para '${RID}'"
  fi
fi

# ── 5. Disponibilidade via API ────────────────────────────────────────────────
echo ""
echo "5. API de disponibilidade"
DATA_TEST=$(python3 -c "from datetime import date, timedelta; print((date.today() + timedelta(days=7)).isoformat())")
DISP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "${BACKEND}/api/agenda/${RID}/disponibilidade?data=${DATA_TEST}&dias=1" \
  -H "x-admin-secret: ${SECRET}")
if [ "$DISP_STATUS" = "200" ]; then
  ok "GET /api/agenda/${RID}/disponibilidade → 200"
else
  fail "GET /api/agenda/${RID}/disponibilidade → ${DISP_STATUS}"
fi

# ── 6. Restaurante aparece no GET /api/restaurants ────────────────────────────
echo ""
echo "6. GET /api/restaurants lista o restaurante"
LISTED=$(curl -s "${BACKEND}/api/restaurants" -H "x-admin-secret: ${SECRET}" \
  | python3 -c "import json,sys; rs=json.load(sys.stdin); ids=[r['id'] for r in rs]; print('yes' if '${RID}' in ids else f'no — ids: {ids}')" 2>/dev/null || echo "ERROR")
if [ "$LISTED" = "yes" ]; then
  ok "${RID} aparece em GET /api/restaurants"
else
  fail "GET /api/restaurants não contém '${RID}' (${LISTED})"
fi

# ── Resultado final ──────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
TOTAL=$((PASS+FAIL))
echo -e "  Resultado: ${GREEN}${PASS}/${TOTAL}${RESET} checks passando"
if [ $FAIL -gt 0 ]; then
  echo -e "  ${RED}${FAIL} check(s) falhando — corrigir antes do go-live${RESET}"
  echo "════════════════════════════════════════════════════════"
  echo ""
  exit 1
else
  echo -e "  ${GREEN}✓ APROVADO — Meet & Eat pronto para go-live${RESET}"
  echo "════════════════════════════════════════════════════════"
  echo ""
  exit 0
fi
