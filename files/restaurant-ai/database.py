"""
Camada de dados — PostgreSQL via asyncpg (Supabase).
Cobre: conversas, reservas, restaurantes, cardápio, handoff, relatórios.
"""

import os, uuid, asyncio
import asyncpg
import pytz
from typing import Optional
from datetime import datetime, timedelta

_TZ_SP = pytz.timezone("America/Sao_Paulo")

_pool: Optional[asyncpg.Pool] = None


# ── Pool ──────────────────────────────────────────────────────

async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=2, max_size=10, command_timeout=30,
        ssl="require",
    )
    print("✅ Supabase conectado")

async def close_db():
    if _pool:
        await _pool.close()

def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool não inicializado")
    return _pool


# ── Restaurantes ──────────────────────────────────────────────

async def ensure_restaurant(rid: str, nome: str, whatsapp_number: str):
    """Insere o restaurante/agente no banco de dados se não existir.
    Caso o whatsapp_number exista sob outro ID, atualiza o ID e nome (upsert)."""
    async with pool().acquire() as c:
        row = await c.fetchrow("SELECT id FROM restaurants WHERE id=$1", rid)
        if not row:
            await c.execute("""
                INSERT INTO restaurants (id, nome, whatsapp_number, ativo)
                VALUES ($1, $2, $3, true)
                ON CONFLICT (whatsapp_number) DO UPDATE SET id=EXCLUDED.id, nome=EXCLUDED.nome, ativo=true
            """, rid, nome, whatsapp_number)

async def get_restaurant_by_whatsapp(number: str) -> Optional[dict]:
    async with pool().acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM restaurants WHERE whatsapp_number=$1 AND ativo=true", number)
    if not row:
        return None
    r = dict(row)
    r["horarios"]        = await _get_horarios(r["id"])
    r["faq"]             = await _get_faq(r["id"])
    r["cardapio"]        = await _get_menu_summary(r["id"])
    r["datas_especiais"] = await get_datas_especiais(r["id"])
    return r

async def get_all_restaurants() -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch(
            "SELECT id, nome, nome_agente, whatsapp_number, descricao, ativo "
            "FROM restaurants WHERE ativo=true ORDER BY nome"
        )
    return [dict(r) for r in rows]

async def get_restaurant_full(rid: str) -> Optional[dict]:
    """Versao COMPLETA com menu_items. Usada apenas pelo agent/handoff."""
    row, horarios, faq, menu, team, datas = await asyncio.gather(
        pool().fetchrow("SELECT * FROM restaurants WHERE id=$1", rid),
        _get_horarios(rid), _get_faq(rid), get_menu_items(rid), get_team(rid),
        get_datas_especiais(rid),
    )
    if not row:
        return None
    r = dict(row)
    r["horarios"]        = horarios
    r["faq"]             = faq
    r["menu_items"]      = menu
    r["team"]            = team
    r["datas_especiais"] = datas
    r["cardapio"]        = await _get_menu_summary(rid)
    return r


async def get_restaurant(rid: str) -> Optional[dict]:
    """Versao SLIM sem menu_items — para o painel. Menu tem endpoint proprio."""
    row, horarios, faq, team, datas = await asyncio.gather(
        pool().fetchrow("SELECT * FROM restaurants WHERE id=$1", rid),
        _get_horarios(rid), _get_faq(rid), get_team(rid),
        get_datas_especiais(rid),
    )
    if not row:
        return None
    r = dict(row)
    r["horarios"]        = horarios
    r["faq"]             = faq
    r["team"]            = team
    r["datas_especiais"] = datas
    return r


# ── Datas especiais ───────────────────────────────────────────

async def get_datas_especiais(rid: str, days_ahead: int = 60) -> list[dict]:
    """Retorna datas especiais futuras nos próximos `days_ahead` dias.
    Inclui hoje. Ordenadas por data crescente."""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT data, nome, aberto, horario_especial, observacao
            FROM datas_especiais
            WHERE restaurant_id = $1
              AND data >= CURRENT_DATE
              AND data <= CURRENT_DATE + ($2 * INTERVAL '1 day')
            ORDER BY data""", rid, int(days_ahead))
    return [dict(r) for r in rows]

async def create_restaurant(data: dict) -> dict:
    async with pool().acquire() as c:
        await c.execute("""
            INSERT INTO restaurants
              (id,nome,whatsapp_number,endereco,descricao,
               capacidade_maxima_reserva,antecedencia_minima_horas,capacidade_total)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            data["id"], data["nome"], data["whatsapp_number"],
            data.get("endereco",""), data.get("descricao",""),
            data.get("capacidade_maxima_reserva",8),
            data.get("antecedencia_minima_horas",2),
            data.get("capacidade_total",80))
    return {"id": data["id"]}

RESTAURANT_UPDATABLE = {
    "nome", "descricao", "whatsapp_number", "endereco",
    "horario_funcionamento", "capacidade_maxima_reserva",
    "antecedencia_minima_horas", "capacidade_total",
    "tagme_venue_id", "team_whatsapp", "ativo",
}

async def update_restaurant(rid: str, data: dict) -> bool:
    data = {k: v for k, v in data.items() if k in RESTAURANT_UPDATABLE}
    fields = [f"{k}=${i+2}" for i,k in enumerate(data.keys())]
    if not fields:
        return False
    async with pool().acquire() as c:
        r = await c.execute(
            f"UPDATE restaurants SET {','.join(fields)} WHERE id=$1",
            rid, *data.values())
    return int(r.split()[-1]) > 0

async def save_business_hours(rid: str, hours: list[dict]):
    async with pool().acquire() as c:
        await c.execute("DELETE FROM business_hours WHERE restaurant_id=$1", rid)
        for h in hours:
            await c.execute(
                "INSERT INTO business_hours (restaurant_id,dia,horario,fechado) VALUES ($1,$2,$3,$4)",
                rid, h["dia"], h["horario"], h.get("fechado", False))

async def _get_horarios(rid: str) -> dict:
    async with pool().acquire() as c:
        rows = await c.fetch(
            "SELECT dia,horario,fechado FROM business_hours WHERE restaurant_id=$1 ORDER BY id", rid)
    return {r["dia"]: "Fechado" if r["fechado"] else r["horario"] for r in rows}


# ── Cardápio ──────────────────────────────────────────────────

async def get_menu_items(rid: str) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM menu_items WHERE restaurant_id=$1 ORDER BY categoria,ordem,nome", rid)
    return [dict(r) for r in rows]


# Hotfix 3 — Helpers consumidos pelas tools novas (lookup_menu, check_business_hours).

async def search_menu_items(rid: str, termo: str, limit: int = 5) -> list[dict]:
    """Busca pratos por nome/categoria/descrição. ILIKE com fronteiras flexíveis.
    Items disponíveis primeiro."""
    pat = f"%{(termo or '').strip()}%"
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT nome, categoria, descricao, preco, disponivel
            FROM menu_items
            WHERE restaurant_id=$1
              AND ($2 = '%%' OR nome ILIKE $2 OR categoria ILIKE $2 OR descricao ILIKE $2)
            ORDER BY disponivel DESC, categoria, ordem, nome
            LIMIT $3""", rid, pat, int(limit))
    return [dict(r) for r in rows]


async def get_menu_categories(rid: str) -> list[str]:
    async with pool().acquire() as c:
        rows = await c.fetch(
            "SELECT DISTINCT categoria FROM menu_items WHERE restaurant_id=$1 ORDER BY categoria",
            rid)
    return [r["categoria"] for r in rows if r["categoria"]]


async def get_business_hours_for_date(rid: str, target_date) -> dict:
    """target_date: date Python. Retorna dict {especial, aberto, horario, observacao, dia, data_iso, nome?}.

    Lógica:
      1. Tem datas_especiais para a data? → usa essa exceção
      2. Senão, mapeia weekday() → dia textual e busca em business_hours (match flexível
         por prefixo, com e sem acento, pra tolerar "sábado" / "sabado" no DB)
    """
    async with pool().acquire() as c:
        sp = await c.fetchrow("""
            SELECT data, nome, aberto, horario_especial, observacao
            FROM datas_especiais
            WHERE restaurant_id=$1 AND data=$2""", rid, target_date)
        if sp:
            return {
                "especial": True, "nome": sp["nome"],
                "aberto": bool(sp["aberto"]),
                "horario": sp["horario_especial"],
                "observacao": sp["observacao"],
                "data_iso": str(sp["data"]),
            }
        rows = await c.fetch(
            "SELECT dia, horario, fechado FROM business_hours WHERE restaurant_id=$1", rid)

    DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
    DIAS_ACC = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    target_dia = DIAS[target_date.weekday()]
    target_dia_acc = DIAS_ACC[target_date.weekday()]
    for r in rows:
        d = (r["dia"] or "").strip().lower()
        if d.startswith(target_dia) or d.startswith(target_dia_acc):
            return {
                "especial": False,
                "aberto": not bool(r["fechado"]),
                "horario": r["horario"],
                "observacao": None,
                "data_iso": str(target_date),
                "dia": target_dia_acc,
            }
    return {
        "especial": False, "aberto": False, "horario": None,
        "observacao": "Horário não cadastrado para este dia.",
        "data_iso": str(target_date), "dia": target_dia_acc,
    }


async def get_recent_reservations(user_phone: str, rid: str, limit: int = 5) -> list[dict]:
    """Histórico amplo (qualquer status) — para lookup_contact_history.
    Diferente de get_reservations_by_user que filtra só confirmada."""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT data, hora, pessoas, status, observacoes
            FROM reservations
            WHERE user_phone=$1 AND restaurant_id=$2
            ORDER BY data DESC, hora DESC
            LIMIT $3""", user_phone, rid, int(limit))
    return [dict(r) for r in rows]

async def _get_menu_summary(rid: str) -> str:
    items = await get_menu_items(rid)
    if not items:
        return "Cardápio não configurado."
    cats: dict[str, list] = {}
    for i in items:
        if i["disponivel"]:
            cats.setdefault(i["categoria"], []).append(i)
    lines = []
    for cat, its in cats.items():
        precos = [i["preco"] for i in its if i["preco"]]
        faixa = f"R$ {min(precos):.0f}–{max(precos):.0f}" if precos else ""
        lines.append(f"{cat}: {', '.join(i['nome'] for i in its[:4])}{'...' if len(its)>4 else ''} {faixa}")
    return "\n".join(lines)

async def create_menu_item(rid: str, data: dict) -> dict:
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO menu_items (restaurant_id,categoria,nome,descricao,preco,disponivel,ordem)
            VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
            rid, data["categoria"], data["nome"], data.get("descricao",""),
            data.get("preco"), data.get("disponivel",True), data.get("ordem",0))
    return {"id": row["id"]}

async def update_menu_item(item_id: int, data: dict) -> bool:
    data["updated_at"] = datetime.now(_TZ_SP)
    fields = [f"{k}=${i+2}" for i,k in enumerate(data.keys())]
    async with pool().acquire() as c:
        r = await c.execute(
            f"UPDATE menu_items SET {','.join(fields)} WHERE id=$1",
            item_id, *data.values())
    return int(r.split()[-1]) > 0

async def delete_menu_item(item_id: int) -> bool:
    async with pool().acquire() as c:
        r = await c.execute("DELETE FROM menu_items WHERE id=$1", item_id)
    return int(r.split()[-1]) > 0


# ── FAQ ───────────────────────────────────────────────────────

async def _get_faq(rid: str) -> dict:
    async with pool().acquire() as c:
        rows = await c.fetch(
            "SELECT chave,resposta FROM faq_items WHERE restaurant_id=$1 ORDER BY ordem", rid)
    return {r["chave"]: r["resposta"] for r in rows}

async def get_faq_items(rid: str) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM faq_items WHERE restaurant_id=$1 ORDER BY ordem", rid)
    return [dict(r) for r in rows]

async def upsert_faq_item(rid: str, data: dict) -> dict:
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO faq_items (restaurant_id,chave,resposta,ordem)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (restaurant_id,chave) DO UPDATE
              SET resposta=EXCLUDED.resposta, ordem=EXCLUDED.ordem
            RETURNING id""",
            rid, data["chave"], data["resposta"], data.get("ordem",0))
    return {"id": row["id"]}

async def delete_faq_item(item_id: int) -> bool:
    async with pool().acquire() as c:
        r = await c.execute("DELETE FROM faq_items WHERE id=$1", item_id)
    return int(r.split()[-1]) > 0


# ── Conversas ─────────────────────────────────────────────────

async def save_message(user_phone: str, rid: str, role: str, content: str):
    async with pool().acquire() as c:
        await c.execute(
            "INSERT INTO conversations (user_phone,restaurant_id,role,content) VALUES ($1,$2,$3,$4)",
            user_phone, rid, role, content)

async def get_history(user_phone: str, rid: str, limit: int = 20) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT role,content FROM conversations
            WHERE user_phone=$1 AND restaurant_id=$2
            ORDER BY created_at DESC, id DESC LIMIT $3""",
            user_phone, rid, limit)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

async def get_conversations_list(rid: str, limit: int = 50) -> list[dict]:
    """Últimas conversas únicas por cliente para o painel, com nome do CRM.
    Fix: a versão anterior ordenava por user_phone (alfabético) — agora ordena
    por created_at DESC (mais recente primeiro)."""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT user_phone, content, created_at, nome, sobrenome
            FROM (
                SELECT DISTINCT ON (cv.user_phone)
                  cv.user_phone, cv.content, cv.created_at,
                  ct.nome, ct.sobrenome
                FROM conversations cv
                LEFT JOIN contacts ct ON ct.celular = cv.user_phone
                WHERE cv.restaurant_id=$1
                ORDER BY cv.user_phone, cv.created_at DESC
            ) latest
            ORDER BY created_at DESC
            LIMIT $2""", rid, limit)
    return [dict(r) for r in rows]


# ── Reservas ─────────────────────────────────────────────────

async def create_reservation(user_phone,rid,nome,data,hora,pessoas,observacoes="") -> dict:
    rid_code = str(uuid.uuid4())[:8].upper()
    async with pool().acquire() as c:
        await c.execute("""
            INSERT INTO reservations (id,user_phone,restaurant_id,nome,data,hora,pessoas,observacoes)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            rid_code,user_phone,rid,nome,data,hora,pessoas,observacoes)
    return {"id": rid_code}

async def get_reservations_by_user(user_phone,rid) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT * FROM reservations
            WHERE user_phone=$1 AND restaurant_id=$2 AND status='confirmada'
            ORDER BY data,hora""", user_phone, rid)
    return [dict(r) for r in rows]

async def get_reservations(rid: str, data: Optional[str]=None,
                            status: Optional[str]=None) -> list[dict]:
    conditions = ["restaurant_id=$1"]
    params: list = [rid]
    if data:
        from datetime import date as _date
        conditions.append(f"data=${len(params)+1}")
        params.append(_date.fromisoformat(data) if isinstance(data, str) else data)
    if status:
        conditions.append(f"status=${len(params)+1}")
        params.append(status)
    async with pool().acquire() as c:
        rows = await c.fetch(
            f"SELECT * FROM reservations WHERE {' AND '.join(conditions)} ORDER BY data,hora",
            *params)
    return [dict(r) for r in rows]

async def update_reservation(res_id: str, data: dict) -> bool:
    if not data:
        return True
    fields = [f"{k}=${i+2}" for i,k in enumerate(data.keys())]
    async with pool().acquire() as c:
        r = await c.execute(
            f"UPDATE reservations SET {','.join(fields)} WHERE id=$1",
            res_id, *data.values())
    return int(r.split()[-1]) > 0

async def cancel_reservation(res_id: str, user_phone: str) -> bool:
    async with pool().acquire() as c:
        r = await c.execute("""
            UPDATE reservations SET status='cancelada'
            WHERE id=$1 AND user_phone=$2 AND status='confirmada'""",
            res_id.upper(), user_phone)
    return int(r.split()[-1]) > 0

async def get_booked_people_at_slot(rid,data,hora) -> int:
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            SELECT COALESCE(SUM(pessoas),0) AS total FROM reservations
            WHERE restaurant_id=$1 AND data=$2 AND hora=$3 AND status='confirmada'""",
            rid,data,hora)
    return int(row["total"]) if row else 0


# ── Handoff ───────────────────────────────────────────────────

async def create_handoff(user_phone: str, rid: str, motivo: str) -> int:
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO handoff_sessions (user_phone,restaurant_id,motivo)
            VALUES ($1,$2,$3) RETURNING id""", user_phone, rid, motivo)
    return row["id"]

async def get_handoff_sessions(rid: str, status: Optional[str]=None) -> list[dict]:
    q = """SELECT hs.*, ct.nome, ct.sobrenome
           FROM handoff_sessions hs
           LEFT JOIN contacts ct ON ct.celular = hs.user_phone
           WHERE hs.restaurant_id=$1"""
    params: list = [rid]
    if status:
        q += " AND hs.status=$2"
        params.append(status)
    q += " ORDER BY hs.created_at DESC"
    async with pool().acquire() as c:
        rows = await c.fetch(q, *params)
    return [dict(r) for r in rows]

async def get_handoff_by_id(hid: int) -> Optional[dict]:
    async with pool().acquire() as c:
        row = await c.fetchrow("SELECT * FROM handoff_sessions WHERE id=$1", hid)
    return dict(row) if row else None

async def update_handoff_status(hid: int, status: str, atendente: Optional[str]=None) -> bool:
    resolved = "NOW()" if status == "resolvido" else "NULL"
    async with pool().acquire() as c:
        r = await c.execute(f"""
            UPDATE handoff_sessions
            SET status=$2, atendente_nome=$3, resolved_at={resolved}
            WHERE id=$1""", hid, status, atendente)
    return int(r.split()[-1]) > 0

async def is_in_handoff(user_phone: str, rid: str) -> bool:
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            SELECT id FROM handoff_sessions
            WHERE user_phone=$1 AND restaurant_id=$2
              AND status IN ('aguardando','em_atendimento')
            LIMIT 1""", user_phone, rid)
    return row is not None


async def get_handoff_sla_stats(restaurant_id: str) -> dict:
    """SLA de handoff: tempo médio de resposta, vencidos (>2h) e abertos."""
    async with pool().acquire() as c:
        stats = await c.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status IN ('aguardando','em_atendimento'))      AS abertos,
                COUNT(*) FILTER (
                    WHERE status IN ('aguardando','em_atendimento')
                      AND created_at < NOW() - INTERVAL '2 hours'
                )                                                                       AS vencidos,
                ROUND(AVG(
                    EXTRACT(EPOCH FROM (resolved_at - created_at)) / 60
                ) FILTER (WHERE resolved_at IS NOT NULL), 1)                           AS tma_minutos,
                COUNT(*) FILTER (WHERE resolved_at IS NOT NULL)                        AS resolvidos_total,
                COUNT(*) FILTER (
                    WHERE resolved_at IS NOT NULL
                      AND resolved_at - created_at <= INTERVAL '2 hours'
                )                                                                       AS dentro_sla
            FROM handoff_sessions
            WHERE restaurant_id = $1
        """, restaurant_id)

        vencidos_rows = await c.fetch("""
            SELECT id, user_phone, motivo, created_at,
                   ROUND(EXTRACT(EPOCH FROM (NOW() - created_at)) / 60)::int AS minutos_aberto
            FROM handoff_sessions
            WHERE restaurant_id = $1
              AND status IN ('aguardando','em_atendimento')
              AND created_at < NOW() - INTERVAL '2 hours'
            ORDER BY created_at ASC
            LIMIT 10
        """, restaurant_id)

    abertos       = int(stats["abertos"] or 0)
    vencidos_n    = int(stats["vencidos"] or 0)
    resolvidos    = int(stats["resolvidos_total"] or 0)
    dentro_sla    = int(stats["dentro_sla"] or 0)
    tma           = float(stats["tma_minutos"] or 0)
    taxa_sla      = round((dentro_sla / resolvidos * 100) if resolvidos > 0 else 0, 1)

    return {
        "abertos": abertos,
        "vencidos": vencidos_n,
        "tma_minutos": tma,
        "taxa_sla_pct": taxa_sla,
        "resolvidos_total": resolvidos,
        "handoffs_vencidos": [
            {
                "id": r["id"],
                "user_phone": r["user_phone"],
                "motivo": r["motivo"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "minutos_aberto": int(r["minutos_aberto"] or 0),
            }
            for r in vencidos_rows
        ],
    }


# ── Equipe ────────────────────────────────────────────────────

async def get_team(rid: str) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM team_members WHERE restaurant_id=$1 AND ativo=true ORDER BY nome", rid)
    return [dict(r) for r in rows]

async def get_on_duty_team(rid: str) -> list[dict]:
    return await get_team(rid)

async def create_team_member(rid: str, data: dict) -> dict:
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO team_members (restaurant_id,nome,whatsapp,role)
            VALUES ($1,$2,$3,$4) RETURNING id""",
            rid, data["nome"], data["whatsapp"], data.get("role","atendente"))
    return {"id": row["id"]}


# ── Relatórios ────────────────────────────────────────────────

async def report_overview(rid: str) -> dict:
    today = datetime.now(_TZ_SP).strftime("%Y-%m-%d")
    month_start = datetime.now(_TZ_SP).replace(day=1).strftime("%Y-%m-%d")

    async with pool().acquire() as c:
        hoje = await c.fetchval(
            "SELECT COUNT(*) FROM reservations WHERE restaurant_id=$1 AND data=$2 AND status='confirmada'",
            rid, today)
        mes = await c.fetchval(
            "SELECT COUNT(*) FROM reservations WHERE restaurant_id=$1 AND data>=$2 AND status='confirmada'",
            rid, month_start)
        total_pessoas_hoje = await c.fetchval(
            "SELECT COALESCE(SUM(pessoas),0) FROM reservations WHERE restaurant_id=$1 AND data=$2 AND status='confirmada'",
            rid, today)
        handoffs_abertos = await c.fetchval(
            "SELECT COUNT(*) FROM handoff_sessions WHERE restaurant_id=$1 AND status IN ('aguardando','em_atendimento')",
            rid)
        cancelamentos_mes = await c.fetchval(
            "SELECT COUNT(*) FROM reservations WHERE restaurant_id=$1 AND data>=$2 AND status='cancelada'",
            rid, month_start)
        total_mes_geral = await c.fetchval(
            "SELECT COUNT(*) FROM reservations WHERE restaurant_id=$1 AND data>=$2",
            rid, month_start)

    taxa_cancelamento = round(cancelamentos_mes / total_mes_geral * 100, 1) if total_mes_geral else 0

    return {
        "reservas_hoje": hoje,
        "reservas_mes": mes,
        "pessoas_hoje": total_pessoas_hoje,
        "handoffs_abertos": handoffs_abertos,
        "taxa_cancelamento_pct": taxa_cancelamento,
    }

async def report_reservations_by_day(rid: str, days: int = 30) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT data, COUNT(*) as total, SUM(pessoas) as pessoas,
                   COUNT(*) FILTER (WHERE status='cancelada') as canceladas
            FROM reservations
            WHERE restaurant_id=$1
              AND created_at >= NOW() - INTERVAL '1 day' * $2
            GROUP BY data ORDER BY data""", rid, days)
    return [dict(r) for r in rows]

async def report_peak_hours(rid: str) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT hora, COUNT(*) as total, SUM(pessoas) as pessoas
            FROM reservations
            WHERE restaurant_id=$1 AND status='confirmada'
            GROUP BY hora ORDER BY total DESC""", rid)
    return [dict(r) for r in rows]

async def report_conversion(rid: str) -> dict:
    async with pool().acquire() as c:
        total_conv = await c.fetchval(
            "SELECT COUNT(DISTINCT user_phone) FROM conversations WHERE restaurant_id=$1", rid)
        total_res = await c.fetchval(
            "SELECT COUNT(DISTINCT user_phone) FROM reservations WHERE restaurant_id=$1 AND status='confirmada'", rid)
    taxa = round(total_res / total_conv * 100, 1) if total_conv else 0
    return {"total_conversas": total_conv, "total_clientes_com_reserva": total_res, "taxa_conversao_pct": taxa}


# ── CRM / Contatos ────────────────────────────────────────────

CONTACT_UPDATABLE = {
    "nome", "sobrenome", "email", "data_nascimento", "endereco",
    "tipo_aparelho", "canal_entrada", "ocasiao", "restricoes_alimentares",
    "ticket_medio", "ultima_visita", "tags", "opt_in_marketing",
    "estagio_kanban", "notas", "frequencia_visitas",
    "lead_score", "lead_score_at",
}

KANBAN_ESTAGIOS = (
    "captacao", "qualificado", "proposta", "fechado", "perdido",
)


async def ensure_contact(celular: str, nome: Optional[str] = None) -> None:
    """Cria contato-semente com celular (e nome, se disponível). Idempotente.
    Se o contato já existe mas não tem nome, seta o nome fornecido."""
    nome = (nome or "").strip() or None
    async with pool().acquire() as c:
        if nome:
            await c.execute(
                """INSERT INTO contacts (celular, nome) VALUES ($1, $2)
                   ON CONFLICT (celular) DO UPDATE SET nome = EXCLUDED.nome
                   WHERE contacts.nome IS NULL OR contacts.nome = ''""",
                celular, nome,
            )
        else:
            await c.execute(
                "INSERT INTO contacts (celular) VALUES ($1) ON CONFLICT (celular) DO NOTHING",
                celular,
            )


async def upsert_contact(data: dict) -> dict:
    """Cria ou atualiza contato pelo celular. Retorna dict com o contato."""
    celular = data["celular"]
    fields = {k: v for k, v in data.items() if k in CONTACT_UPDATABLE and v is not None}

    async with pool().acquire() as c:
        existing = await c.fetchrow("SELECT id FROM contacts WHERE celular=$1", celular)
        if existing:
            if fields:
                set_clause = ",".join(f"{k}=${i+2}" for i, k in enumerate(fields))
                await c.execute(
                    f"UPDATE contacts SET {set_clause} WHERE celular=$1",
                    celular, *fields.values())
            row = await c.fetchrow("SELECT * FROM contacts WHERE celular=$1", celular)
        else:
            cols = ["celular"] + list(fields.keys())
            placeholders = [f"${i+1}" for i in range(len(cols))]
            values = [celular] + list(fields.values())
            row = await c.fetchrow(
                f"INSERT INTO contacts ({','.join(cols)}) VALUES ({','.join(placeholders)}) RETURNING *",
                *values)
    return dict(row)


async def list_contacts(
    tier: Optional[str] = None,
    estagio: Optional[str] = None,
    ocasiao: Optional[str] = None,
    tag: Optional[str] = None,
    opt_in: Optional[bool] = None,
    limit: int = 500,
) -> list[dict]:
    conditions: list[str] = []
    params: list = []
    if tier:
        params.append(tier)
        conditions.append(f"tier=${len(params)}")
    if estagio:
        params.append(estagio)
        conditions.append(f"estagio_kanban=${len(params)}")
    if ocasiao:
        params.append(ocasiao)
        conditions.append(f"${len(params)} = ANY(ocasiao)")
    if tag:
        params.append(tag)
        conditions.append(f"${len(params)} = ANY(tags)")
    if opt_in is not None:
        params.append(opt_in)
        conditions.append(f"opt_in_marketing=${len(params)}")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    _nps_sub = (
        "(SELECT nps_score FROM ordens_servico "
        "WHERE cliente_phone = c.celular AND nps_score IS NOT NULL "
        "ORDER BY nps_respondido_em DESC NULLS LAST LIMIT 1) AS nps_ultimo"
    )
    async with pool().acquire() as c:
        rows = await c.fetch(
            f"SELECT c.*, {_nps_sub} FROM contacts c {where} ORDER BY c.atualizado_em DESC LIMIT ${len(params)}",
            *params)
    return [dict(r) for r in rows]


async def get_contact(celular: str) -> Optional[dict]:
    _nps_sub = (
        "(SELECT nps_score FROM ordens_servico "
        "WHERE cliente_phone = c.celular AND nps_score IS NOT NULL "
        "ORDER BY nps_respondido_em DESC NULLS LAST LIMIT 1) AS nps_ultimo"
    )
    async with pool().acquire() as c:
        row = await c.fetchrow(
            f"SELECT c.*, {_nps_sub} FROM contacts c WHERE c.celular=$1",
            celular)
    return dict(row) if row else None


async def update_contact(celular: str, data: dict) -> Optional[dict]:
    fields = {k: v for k, v in data.items() if k in CONTACT_UPDATABLE and v is not None}
    if not fields:
        return await get_contact(celular)
    set_clause = ",".join(f"{k}=${i+2}" for i, k in enumerate(fields))
    async with pool().acquire() as c:
        row = await c.fetchrow(
            f"UPDATE contacts SET {set_clause} WHERE celular=$1 RETURNING *",
            celular, *fields.values())
    return dict(row) if row else None


async def move_contact_kanban(celular: str, estagio: str) -> Optional[dict]:
    if estagio not in KANBAN_ESTAGIOS:
        raise ValueError(f"Estágio inválido: {estagio}")
    async with pool().acquire() as c:
        row = await c.fetchrow(
            "UPDATE contacts SET estagio_kanban=$2 WHERE celular=$1 RETURNING *",
            celular, estagio)
    return dict(row) if row else None


async def get_funil_stats() -> dict:
    """KPIs do funil: leads da semana, score breakdown."""
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            SELECT
              COUNT(*) FILTER (WHERE criado_em >= NOW() - INTERVAL '7 days') AS leads_7d,
              COUNT(*) FILTER (WHERE lead_score = 'quente') AS quentes,
              COUNT(*) FILTER (WHERE lead_score = 'morno')  AS mornos,
              COUNT(*) FILTER (WHERE lead_score = 'frio')   AS frios
            FROM contacts
        """)
    quentes = row["quentes"] or 0
    mornos  = row["mornos"]  or 0
    frios   = row["frios"]   or 0
    total   = quentes + mornos + frios or 1
    return {
        "leads_7d": row["leads_7d"] or 0,
        "quentes": quentes,
        "mornos":  mornos,
        "frios":   frios,
        "pct_quentes": round(quentes * 100 / total),
    }


async def get_nurture_leads(days_inactive: int = 3) -> list[dict]:
    """Leads MORNOS sem interação há N+ dias — candidatos ao nurture automático."""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT c.celular, c.nome, c.lead_score, c.atualizado_em, c.notas,
                   r.restaurant_id
            FROM contacts c
            JOIN (
                SELECT DISTINCT user_phone, restaurant_id
                FROM conversations
                WHERE created_at >= NOW() - INTERVAL '90 days'
            ) r ON r.user_phone = c.celular
            WHERE c.lead_score = 'morno'
              AND c.atualizado_em < NOW() - ($1 || ' days')::INTERVAL
              AND NOT EXISTS (
                SELECT 1 FROM reservations rv
                WHERE rv.user_phone = c.celular
                  AND rv.status = 'confirmada'
              )
            ORDER BY c.atualizado_em ASC
            LIMIT 100
        """, str(days_inactive))
    return [dict(r) for r in rows]


async def search_contacts(q: str, limit: int = 50) -> list[dict]:
    like = f"%{q.lower()}%"
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT * FROM contacts
            WHERE LOWER(celular) LIKE $1
               OR LOWER(COALESCE(nome,'')) LIKE $1
               OR LOWER(COALESCE(sobrenome,'')) LIKE $1
               OR LOWER(COALESCE(email,'')) LIKE $1
            ORDER BY atualizado_em DESC
            LIMIT $2""", like, limit)
    return [dict(r) for r in rows]


async def get_contact_reservations(celular: str, limit: int = 20) -> list[dict]:
    """Reservas históricas ligadas ao celular do contato."""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT * FROM reservations WHERE user_phone=$1
            ORDER BY created_at DESC LIMIT $2""", celular, limit)
    return [dict(r) for r in rows]


async def get_contact_conversations(celular: str, limit: int = 100) -> list[dict]:
    """Últimas mensagens (qualquer restaurante) do contato."""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT role, content, restaurant_id, created_at FROM conversations
            WHERE user_phone=$1
            ORDER BY created_at DESC, id DESC LIMIT $2""", celular, limit)
    return [dict(r) for r in reversed(rows)]


async def mark_inactive_contacts(threshold_days: int = 45) -> int:
    """Move para 'Inativo' contatos sem visita há N+ dias.
    Chamar via cron ou endpoint. Retorna quantos foram afetados."""
    async with pool().acquire() as c:
        affected = await c.fetchval(
            "SELECT contacts_mark_inactive($1)", threshold_days)
    return int(affected or 0)


async def report_full(rid: str, days: int = 7) -> dict:
    """Agregado completo para a tela de Relatórios — queries em paralelo via pool."""
    p = pool()
    (
        total_conversas, clientes_unicos, total_reservas,
        reservas_confirmadas, reservas_canceladas, total_handoffs,
        clientes_com_reserva, clientes_com_handoff, clientes_recorrentes,
        conv_mes, res_mes, canc_mes, handoffs_mes,
        por_dia, pico,
    ) = await asyncio.gather(
        p.fetchval("SELECT COUNT(*) FROM conversations WHERE restaurant_id=$1", rid),
        p.fetchval("SELECT COUNT(DISTINCT user_phone) FROM conversations WHERE restaurant_id=$1", rid),
        p.fetchval("SELECT COUNT(*) FROM reservations WHERE restaurant_id=$1", rid),
        p.fetchval("SELECT COUNT(*) FROM reservations WHERE restaurant_id=$1 AND status='confirmada'", rid),
        p.fetchval("SELECT COUNT(*) FROM reservations WHERE restaurant_id=$1 AND status='cancelada'", rid),
        p.fetchval("SELECT COUNT(*) FROM handoff_sessions WHERE restaurant_id=$1", rid),
        p.fetchval("SELECT COUNT(DISTINCT user_phone) FROM reservations WHERE restaurant_id=$1", rid),
        p.fetchval("SELECT COUNT(DISTINCT user_phone) FROM handoff_sessions WHERE restaurant_id=$1", rid),
        p.fetchval("""
            SELECT COUNT(*) FROM (
                SELECT user_phone FROM reservations
                WHERE restaurant_id=$1 AND status IN ('confirmada','concluida')
                GROUP BY user_phone HAVING COUNT(*) >= 2
            ) x""", rid),
        p.fetchval("""
            SELECT COUNT(*) FROM conversations
            WHERE restaurant_id=$1 AND created_at >= date_trunc('month', CURRENT_DATE)""", rid),
        p.fetchval("""
            SELECT COUNT(*) FROM reservations
            WHERE restaurant_id=$1 AND created_at >= date_trunc('month', CURRENT_DATE)""", rid),
        p.fetchval("""
            SELECT COUNT(*) FROM reservations
            WHERE restaurant_id=$1 AND created_at >= date_trunc('month', CURRENT_DATE)
              AND status='cancelada'""", rid),
        p.fetchval("""
            SELECT COUNT(*) FROM handoff_sessions
            WHERE restaurant_id=$1 AND created_at >= date_trunc('month', CURRENT_DATE)""", rid),
        p.fetch("""
            SELECT to_char(created_at AT TIME ZONE 'America/Sao_Paulo', 'DD/MM') AS dia,
                   COUNT(*)                                                      AS reservas,
                   COUNT(*) FILTER (WHERE status='cancelada')                    AS canceladas,
                   COALESCE(SUM(pessoas) FILTER (WHERE status='confirmada'), 0)  AS pessoas
              FROM reservations
             WHERE restaurant_id=$1
               AND created_at >= NOW() - INTERVAL '1 day' * $2
             GROUP BY dia
             ORDER BY MIN(created_at)""", rid, days),
        p.fetch("""
            SELECT hora,
                   COUNT(*)                     AS total,
                   COALESCE(SUM(pessoas), 0)    AS pessoas
              FROM reservations
             WHERE restaurant_id=$1 AND status='confirmada'
             GROUP BY hora
             ORDER BY hora""", rid),
    )

    taxa_conversao    = round(clientes_com_reserva / clientes_unicos * 100, 1) if clientes_unicos else 0.0
    taxa_cancelamento = round(reservas_canceladas / total_reservas * 100, 1)  if total_reservas  else 0.0
    taxa_resolucao    = round((clientes_unicos - clientes_com_handoff) / clientes_unicos * 100, 1) if clientes_unicos else 0.0
    nps_proxy         = round(clientes_recorrentes / clientes_com_reserva * 100, 1) if clientes_com_reserva else 0.0

    pico_sorted = sorted([dict(r) for r in pico], key=lambda r: r["pessoas"], reverse=True)

    return {
        "totais": {
            "conversas":            total_conversas,
            "clientes_unicos":      clientes_unicos,
            "reservas":             total_reservas,
            "reservas_confirmadas": reservas_confirmadas,
            "reservas_canceladas":  reservas_canceladas,
            "handoffs":             total_handoffs,
            "clientes_recorrentes": clientes_recorrentes,
        },
        "taxas": {
            "conversao_pct":     taxa_conversao,
            "cancelamento_pct":  taxa_cancelamento,
            "resolucao_ia_pct":  taxa_resolucao,
            "nps_proxy_pct":     nps_proxy,
        },
        "mes_atual": {
            "conversas":     conv_mes,
            "reservas":      res_mes,
            "cancelamentos": canc_mes,
            "handoffs":      handoffs_mes,
        },
        "reservas_por_dia": [dict(r) for r in por_dia],
        "horarios_pico":    [dict(r) for r in pico],
        "top_horarios":     pico_sorted[:5],
    }


async def contact_stats() -> dict:
    """Contadores agregados para header do painel CRM."""
    async with pool().acquire() as c:
        total = await c.fetchval("SELECT COUNT(*) FROM contacts")
        por_tier = await c.fetch(
            "SELECT tier, COUNT(*) AS n FROM contacts GROUP BY tier")
        por_estagio = await c.fetch(
            "SELECT estagio_kanban AS estagio, COUNT(*) AS n FROM contacts GROUP BY estagio_kanban")
    return {
        "total": total,
        "por_tier": {r["tier"]: r["n"] for r in por_tier},
        "por_estagio": {r["estagio"]: r["n"] for r in por_estagio},
    }


# ── Onda 8 — Serena instrumentation ────────────────────────────

import time as _time

# Cache do prompt ativo: 5min — recarrega via _prompt_cache_clear() ao ativar nova versão.
_prompt_cache: Optional[dict] = None
_prompt_cache_at: float = 0.0
_PROMPT_TTL = 300

def _prompt_cache_clear():
    global _prompt_cache, _prompt_cache_at
    _prompt_cache = None
    _prompt_cache_at = 0.0


async def get_active_prompt(restaurant_id: str = "madonna_cucina") -> Optional[dict]:
    """Retorna a versão ATIVA do prompt para o restaurante. Cache 5min por restaurant_id."""
    global _prompt_cache, _prompt_cache_at
    # Cache key inclui restaurant_id
    cache_key = restaurant_id
    if (
        isinstance(_prompt_cache, dict)
        and _prompt_cache.get("_cache_rid") == cache_key
        and (_time.monotonic() - _prompt_cache_at) < _PROMPT_TTL
    ):
        return _prompt_cache
    async with pool().acquire() as c:
        row = await c.fetchrow(
            "SELECT id, versao, prompt_completo, restaurant_id, criado_em "
            "FROM serena_prompt_versions WHERE ativa=TRUE AND restaurant_id=$1 LIMIT 1",
            restaurant_id,
        )
    if row:
        cached = dict(row)
        cached["_cache_rid"] = cache_key
        _prompt_cache = cached
        _prompt_cache_at = _time.monotonic()
        return cached
    return None


async def list_prompt_versions(limit: int = 50) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT id, versao, changelog, ativa, criado_em,
                   LEFT(prompt_completo, 240) AS preview,
                   metricas_pos_deploy
            FROM serena_prompt_versions
            ORDER BY criado_em DESC
            LIMIT $1""", limit)
    return [dict(r) for r in rows]


async def get_prompt_version(pid: int) -> Optional[dict]:
    async with pool().acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM serena_prompt_versions WHERE id=$1", pid)
    return dict(row) if row else None


async def insert_prompt_version(versao: str, prompt_completo: str,
                                  restaurant_id: str,
                                  changelog: Optional[str] = None,
                                  ativar: bool = False) -> int:
    # restaurant_id é obrigatório — desativação e ativação são SEMPRE
    # escopadas a um restaurante para nunca derrubar prompt de outra casa.
    async with pool().acquire() as c:
        async with c.transaction():
            if ativar:
                await c.execute(
                    "UPDATE serena_prompt_versions SET ativa=FALSE "
                    "WHERE ativa=TRUE AND restaurant_id=$1", restaurant_id)
            row = await c.fetchrow("""
                INSERT INTO serena_prompt_versions
                  (versao, prompt_completo, changelog, ativa, restaurant_id)
                VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                versao, prompt_completo, changelog or "", ativar, restaurant_id)
    if ativar:
        _prompt_cache_clear()
    return row["id"]


async def activate_prompt_version(pid: int) -> Optional[dict]:
    # Desativa apenas as versões do MESMO restaurante da versão alvo,
    # nunca todas globalmente.
    async with pool().acquire() as c:
        async with c.transaction():
            target = await c.fetchrow(
                "SELECT restaurant_id FROM serena_prompt_versions WHERE id=$1", pid)
            if not target:
                return None
            await c.execute(
                "UPDATE serena_prompt_versions SET ativa=FALSE "
                "WHERE ativa=TRUE AND restaurant_id IS NOT DISTINCT FROM $1",
                target["restaurant_id"])
            row = await c.fetchrow(
                "UPDATE serena_prompt_versions SET ativa=TRUE WHERE id=$1 RETURNING *", pid)
    _prompt_cache_clear()
    return dict(row) if row else None


async def record_serena_metric(metric: dict) -> Optional[str]:
    """Persiste métricas de um turno da Serena. Best-effort — não levanta exception
    se uma coluna nova vier."""
    cols = [
        "user_phone", "restaurant_id", "tokens_input", "tokens_output",
        "custo_usd", "latencia_ms", "tools_chamadas",
        "handoff_acionado", "handoff_motivo", "cliente_pediu_humano",
        "serena_admitiu_nao_saber", "enviou_link_tagme", "intencao_detectada",
        "duracao_segundos", "num_mensagens", "prompt_versao_id",
    ]
    payload = {k: metric.get(k) for k in cols}
    fields = ",".join(payload.keys())
    placeholders = ",".join(f"${i+1}" for i in range(len(payload)))
    async with pool().acquire() as c:
        row = await c.fetchrow(
            f"INSERT INTO serena_metrics ({fields}) VALUES ({placeholders}) RETURNING id",
            *payload.values())
    return str(row["id"]) if row else None


async def update_serena_metric_categoria(metric_id: str, categoria: str):
    if not metric_id:
        return
    async with pool().acquire() as c:
        await c.execute(
            "UPDATE serena_metrics SET handoff_categoria=$2 WHERE id=$1",
            metric_id, categoria)


# ── Agregações para /api/serena/* ──────────────────────────────

async def serena_overview(days: int = 7, restaurant_id: Optional[str] = None) -> dict:
    p = pool()
    d = int(days)
    (
        total_msgs, conversas_unicas, custo_total,
        tokens_in, tokens_out, latencia_avg,
        handoffs_n, pediram_humano, admitiu_nao_saber,
        enviou_tagme, intent_desconhecidas,
    ) = await asyncio.gather(
        p.fetchval("SELECT COUNT(*) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        p.fetchval("SELECT COUNT(DISTINCT user_phone) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        p.fetchval("SELECT COALESCE(SUM(custo_usd),0) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        p.fetchval("SELECT COALESCE(SUM(tokens_input),0) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        p.fetchval("SELECT COALESCE(SUM(tokens_output),0) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        p.fetchval("SELECT COALESCE(AVG(latencia_ms),0) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        p.fetchval("SELECT COUNT(*) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND handoff_acionado=TRUE AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        p.fetchval("SELECT COUNT(*) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND cliente_pediu_humano=TRUE AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        p.fetchval("SELECT COUNT(*) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND serena_admitiu_nao_saber=TRUE AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        p.fetchval("SELECT COUNT(*) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') AND enviou_link_tagme=TRUE AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id),
        # Hotfix 2 — taxa de "desconhecida". Conta NULL (rows pré-Hotfix 2) E
        # a string literal (rows pós-Hotfix 2). Alerta se > 15%.
        p.fetchval(
            "SELECT COUNT(*) FROM serena_metrics WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day') "
            "AND (intencao_detectada IS NULL OR intencao_detectada = 'desconhecida') AND ($2::text IS NULL OR restaurant_id = $2)", d, restaurant_id
        ),
    )
    taxa_resolucao = (
        round((1 - (handoffs_n / total_msgs)) * 100, 1) if total_msgs else None
    )
    taxa_intent_desconhecida = (
        round(intent_desconhecidas / total_msgs * 100, 1) if total_msgs else None
    )
    return {
        "periodo_dias": days,
        "total_mensagens": int(total_msgs or 0),
        "conversas_unicas": int(conversas_unicas or 0),
        "custo_usd_total": float(custo_total or 0),
        "tokens_input": int(tokens_in or 0),
        "tokens_output": int(tokens_out or 0),
        "latencia_media_ms": int(latencia_avg or 0),
        "handoffs_acionados": int(handoffs_n or 0),
        "clientes_pediram_humano": int(pediram_humano or 0),
        "serena_admitiu_nao_saber": int(admitiu_nao_saber or 0),
        "enviou_link_tagme": int(enviou_tagme or 0),
        "taxa_resolucao_pct": taxa_resolucao,
        "intent_desconhecidas": int(intent_desconhecidas or 0),
        "taxa_intent_desconhecida_pct": taxa_intent_desconhecida,
    }


async def serena_handoffs_categorizados(days: int = 30, restaurant_id: Optional[str] = None) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT COALESCE(handoff_categoria, 'sem_categoria') AS categoria,
                   COUNT(*) AS n,
                   ARRAY_AGG(handoff_motivo ORDER BY horario_conversa DESC)
                       FILTER (WHERE handoff_motivo IS NOT NULL) AS motivos
            FROM serena_metrics
            WHERE handoff_acionado=TRUE
              AND horario_conversa >= NOW() - ($1 * INTERVAL '1 day')
              AND ($2::text IS NULL OR restaurant_id = $2)
            GROUP BY handoff_categoria
            ORDER BY n DESC""", int(days), restaurant_id)
    out = []
    for r in rows:
        d = dict(r)
        # trunca exemplos pra 5 motivos por categoria
        if d.get("motivos"):
            d["motivos"] = d["motivos"][:5]
        out.append(d)
    return out


async def serena_intents(days: int = 30, restaurant_id: Optional[str] = None) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT COALESCE(intencao_detectada, 'desconhecida') AS intencao,
                   COUNT(*) AS n,
                   COUNT(*) FILTER (WHERE handoff_acionado=TRUE) AS handoffs
            FROM serena_metrics
            WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day')
              AND ($2::text IS NULL OR restaurant_id = $2)
            GROUP BY intencao_detectada
            ORDER BY n DESC""", int(days), restaurant_id)
    return [dict(r) for r in rows]


async def serena_friccoes(days: int = 14, limit: int = 30, offset: int = 0, restaurant_id: Optional[str] = None) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT id::text, user_phone, restaurant_id,
                   horario_conversa, handoff_motivo, handoff_categoria,
                   cliente_pediu_humano, serena_admitiu_nao_saber, num_mensagens
            FROM serena_metrics
            WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day')
              AND (cliente_pediu_humano=TRUE
                   OR serena_admitiu_nao_saber=TRUE
                   OR num_mensagens >= 10)
              AND ($4::text IS NULL OR restaurant_id = $4)
            ORDER BY horario_conversa DESC
            LIMIT $2 OFFSET $3""", int(days), limit, offset, restaurant_id)
    return [dict(r) for r in rows]


async def serena_tools_stats(days: int = 30, restaurant_id: Optional[str] = None) -> list[dict]:
    """Conta ocorrências por nome de tool (unnest do array)."""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT tool, COUNT(*) AS n
            FROM (
                SELECT UNNEST(tools_chamadas) AS tool
                FROM serena_metrics
                WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day')
                  AND tools_chamadas IS NOT NULL
                  AND ($2::text IS NULL OR restaurant_id = $2)
            ) t
            GROUP BY tool
            ORDER BY n DESC""", int(days), restaurant_id)
    return [dict(r) for r in rows]


async def serena_custo(days: int = 30, restaurant_id: Optional[str] = None) -> dict:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT date_trunc('day', horario_conversa)::date AS dia,
                   SUM(custo_usd) AS custo,
                   SUM(tokens_input) AS tin,
                   SUM(tokens_output) AS tout,
                   COUNT(*) AS turnos
            FROM serena_metrics
            WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day')
              AND ($2::text IS NULL OR restaurant_id = $2)
            GROUP BY dia ORDER BY dia""", int(days), restaurant_id)
        top = await c.fetch("""
            SELECT user_phone, SUM(custo_usd) AS custo, COUNT(*) AS n
            FROM serena_metrics
            WHERE horario_conversa >= NOW() - ($1 * INTERVAL '1 day')
              AND ($2::text IS NULL OR restaurant_id = $2)
            GROUP BY user_phone
            ORDER BY custo DESC NULLS LAST
            LIMIT 10""", int(days), restaurant_id)
    serie = [{"dia": r["dia"].isoformat() if r["dia"] else None,
              "custo": float(r["custo"] or 0),
              "tokens_input": int(r["tin"] or 0),
              "tokens_output": int(r["tout"] or 0),
              "turnos": int(r["turnos"] or 0)} for r in rows]
    total = sum(p["custo"] for p in serie)
    # projeção mensal naive: (total / dias_observados) * 30
    proj_mes = (total / max(len(serie), 1)) * 30 if serie else 0
    return {
        "serie_diaria": serie,
        "total_periodo_usd": round(total, 4),
        "projecao_mensal_usd": round(proj_mes, 2),
        "top_conversas": [dict(r) for r in top],
    }


async def serena_recent(limit: int = 100, only_handoffs: bool = False, restaurant_id: Optional[str] = None) -> list[dict]:
    conds = []
    params = [limit]
    if only_handoffs:
        conds.append("handoff_acionado=TRUE")
    if restaurant_id:
        params.append(restaurant_id)
        conds.append(f"restaurant_id=${len(params)}")
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    async with pool().acquire() as c:
        rows = await c.fetch(f"""
            SELECT id::text, user_phone, restaurant_id,
                   horario_conversa, handoff_acionado, handoff_categoria,
                   handoff_motivo, custo_usd, latencia_ms, tools_chamadas
            FROM serena_metrics
            {where}
            ORDER BY horario_conversa DESC
            LIMIT $1""", *params)
    return [dict(r) for r in rows]


async def insights_aggregate(rid: Optional[str] = None) -> dict:
    """Insights agregados — heurísticas server-side. Cache deve ser feito no caller."""
    p = pool()
    rid_filter = "AND restaurant_id=$1" if rid else ""
    args = [rid] if rid else []

    today_iso = datetime.now(_TZ_SP).strftime("%d/%m/%Y")

    ouro_aguardando = await p.fetch(f"""
        SELECT DISTINCT ON (h.user_phone)
          h.user_phone, c.nome, c.tier, h.motivo
        FROM handoff_sessions h
        LEFT JOIN contacts c ON c.celular = h.user_phone
        WHERE h.status IN ('aguardando','em_atendimento')
          {rid_filter}
          AND c.tier = 'Ouro'
        ORDER BY h.user_phone, h.created_at DESC
        LIMIT 25""", *args)

    pico_query = f"""
        SELECT hora, SUM(pessoas) AS pessoas
        FROM reservations
        WHERE status='confirmada' {rid_filter}
        GROUP BY hora ORDER BY pessoas DESC LIMIT 1"""
    pico = await p.fetchrow(pico_query, *args)

    inativos_60d = await p.fetchval("""
        SELECT COUNT(*) FROM contacts
        WHERE tier IN ('Ouro','Prata')
          AND ultima_visita IS NOT NULL
          AND ultima_visita < NOW() - INTERVAL '60 days'
          AND ultima_visita > NOW() - INTERVAL '180 days'""")

    handoffs_categorias = await p.fetch("""
        SELECT handoff_categoria, COUNT(*) AS n
        FROM serena_metrics
        WHERE handoff_acionado=TRUE
          AND horario_conversa >= NOW() - INTERVAL '14 days'
          AND handoff_categoria IS NOT NULL
        GROUP BY handoff_categoria
        HAVING COUNT(*) >= 3
        ORDER BY n DESC LIMIT 5""")

    custo_hoje = await p.fetchval(
        f"SELECT COALESCE(SUM(custo_usd),0) FROM serena_metrics"
        f" WHERE horario_conversa::date = CURRENT_DATE {rid_filter}", *args)

    custo_mes_ate_agora = await p.fetchval(
        f"SELECT COALESCE(SUM(custo_usd),0) FROM serena_metrics"
        f" WHERE horario_conversa >= date_trunc('month', NOW()) {rid_filter}", *args)

    insights: list[dict] = []
    if ouro_aguardando:
        insights.append({
            "id": "ouro_aguardando",
            "kind": "ouro_aguardando",
            "title": f"{len(ouro_aguardando)} cliente{'s' if len(ouro_aguardando)>1 else ''} Ouro aguardando atendimento",
            "summary": ", ".join(r["nome"] or r["user_phone"] for r in ouro_aguardando[:3]),
            "items": [dict(r) for r in ouro_aguardando],
            "tone": "accent",
        })
    if pico and pico["pessoas"] and pico["pessoas"] >= 8:
        insights.append({
            "id": f"pico_{pico['hora']}",
            "kind": "pico",
            "title": f"Pico de demanda às {pico['hora']} ({pico['pessoas']} pax)",
            "summary": "Verifique se o staff está dimensionado para esta janela.",
            "tone": "warning",
        })
    if inativos_60d and inativos_60d >= 1:
        insights.append({
            "id": "reactivation_60d",
            "kind": "reactivation",
            "title": f"{inativos_60d} cliente{'s' if inativos_60d>1 else ''} Ouro/Prata sem visita há +60 dias",
            "summary": "Janela típica de reativação — campanha vale a pena.",
            "tone": "info",
        })
    for cat in handoffs_categorias:
        insights.append({
            "id": f"faq_{cat['handoff_categoria']}",
            "kind": "faq_pattern",
            "title": f"{cat['n']} handoffs sobre {cat['handoff_categoria']}",
            "summary": "Padrão recorrente — vale atualizar FAQ ou prompt da Serena.",
            "tone": "info",
        })
    insights.append({
        "id": "custo_hoje",
        "kind": "custo",
        "title": f"Serena gastou US$ {float(custo_hoje):.2f} hoje",
        "summary": f"Mês até agora: US$ {float(custo_mes_ate_agora):.2f}",
        "tone": "muted",
    })
    return {"generated_at": datetime.now(_TZ_SP).isoformat(), "insights": insights, "today": today_iso}


async def insert_weekly_report(start, end, total_conversas: int, payload: dict) -> int:
    import json
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO serena_weekly_reports
              (semana_inicio, semana_fim, total_conversas, relatorio_json)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (semana_inicio, semana_fim) DO UPDATE SET
              total_conversas = EXCLUDED.total_conversas,
              relatorio_json = EXCLUDED.relatorio_json,
              criado_em = NOW()
            RETURNING id""",
            start, end, total_conversas, json.dumps(payload, default=str))
    return int(row["id"])


async def list_weekly_reports(limit: int = 12) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT id, semana_inicio, semana_fim, total_conversas, relatorio_json, criado_em
            FROM serena_weekly_reports
            ORDER BY semana_inicio DESC
            LIMIT $1""", limit)
    return [dict(r) for r in rows]


async def export_serena_for_training(limit: int = 1000, restaurant_id: Optional[str] = None) -> list[dict]:
    """Export para fine-tune: pares (user_msg, serena_msg) das últimas conversas
    onde a Serena resolveu sem handoff."""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            WITH ok AS (
              SELECT user_phone, restaurant_id
              FROM serena_metrics
              WHERE handoff_acionado=FALSE
                AND horario_conversa >= NOW() - INTERVAL '60 days'
                AND ($2::text IS NULL OR restaurant_id = $2)
              GROUP BY user_phone, restaurant_id
            )
            SELECT cv.user_phone, cv.restaurant_id, cv.role, cv.content, cv.created_at
            FROM conversations cv
            JOIN ok USING (user_phone, restaurant_id)
            ORDER BY cv.user_phone, cv.created_at
            LIMIT $1""", limit, restaurant_id)
    return [dict(r) for r in rows]


async def update_handoff_kanban(hid: int, stage: str) -> bool:
    """Move um handoff_session para um novo status via kanban."""
    valid = {"aguardando", "em_atendimento", "resolvido"}
    if stage not in valid:
        return False
    async with pool().acquire() as c:
        r = await c.execute(
            "UPDATE handoff_sessions SET status=$1 WHERE id=$2", stage, hid)
    return int(r.split()[-1]) > 0


# ── Agenda própria — Serena 2.0 ───────────────────────────────

async def get_turnos(restaurant_id: str, dia_semana: int) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT * FROM agenda_turnos
            WHERE restaurant_id = $1 AND dia_semana = $2 AND ativo = true
            ORDER BY hora_inicio
        """, restaurant_id, dia_semana)
    return [dict(r) for r in rows]


async def check_disponibilidade(restaurant_id: str, data: str, turno_id: str, posicoes: int) -> dict:
    from datetime import date as _date
    import json
    try:
        data_obj = _date.fromisoformat(data) if isinstance(data, str) else data
    except ValueError:
        data_obj = _date.today()
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            SELECT verificar_disponibilidade($1, $2::DATE, $3::UUID, $4) as resultado
        """, restaurant_id, data_obj, turno_id, posicoes)
    res = row["resultado"]
    if isinstance(res, str):
        try:
            return json.loads(res)
        except Exception:
            pass
    return res



async def criar_reserva(data: dict) -> dict:
    from datetime import date as _date, time as _time
    raw_data = data["data"]
    try:
        data_obj = _date.fromisoformat(raw_data) if isinstance(raw_data, str) else raw_data
    except ValueError:
        data_obj = _date.today()

    raw_time = data["hora_inicio"]
    if isinstance(raw_time, str):
        try:
            parts = [int(x) for x in raw_time.split(":")]
            time_obj = _time(hour=parts[0], minute=parts[1], second=parts[2] if len(parts) > 2 else 0)
        except Exception:
            time_obj = raw_time
    else:
        time_obj = raw_time

    async with pool().acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO reservas (
                restaurant_id, turno_id, evento_id,
                cliente_phone, cliente_nome, cliente_email,
                data, hora_inicio, posicoes, canal, observacoes,
                pagamento_status, pagamento_valor
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            RETURNING *
        """,
        data["restaurant_id"], data.get("turno_id"), data.get("evento_id"),
        data["cliente_phone"], data["cliente_nome"], data.get("cliente_email"),
        data_obj, time_obj, data["posicoes"],
        data.get("canal", "whatsapp"), data.get("observacoes"),
        data.get("pagamento_status", "nao_requerido"), data.get("pagamento_valor"))
    return dict(row)



async def get_reserva(reserva_id: str) -> Optional[dict]:
    async with pool().acquire() as c:
        row = await c.fetchrow("SELECT * FROM reservas WHERE id = $1", reserva_id)
    return dict(row) if row else None


async def get_reservas_por_phone(restaurant_id: str, phone: str) -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT * FROM reservas
            WHERE restaurant_id = $1 AND cliente_phone = $2
            AND status IN ('pendente','confirmada')
            ORDER BY data DESC, hora_inicio DESC
            LIMIT 5
        """, restaurant_id, phone)
    return [dict(r) for r in rows]


async def listar_reservas_por_data(
    restaurant_id: str, data: str, status: str | None = None, limit: int = 100
) -> list[dict]:
    from datetime import date as _date
    data_obj = _date.fromisoformat(data) if isinstance(data, str) else data
    query = """
        SELECT r.*, t.nome as turno_nome, t.hora_inicio as turno_hora_inicio,
               t.capacidade_posicoes_max as turno_capacidade
        FROM reservas r
        LEFT JOIN agenda_turnos t ON t.id = r.turno_id
        WHERE r.restaurant_id = $1 AND r.data = $2
    """
    params = [restaurant_id, data_obj]
    if status:
        query += f" AND r.status = ${len(params)+1}"
        params.append(status)
    query += f" ORDER BY r.hora_inicio, r.criado_em LIMIT ${len(params)+1}"
    params.append(limit)
    async with pool().acquire() as c:
        rows = await c.fetch(query, *params)
    return [dict(r) for r in rows]


async def confirmar_reserva(reserva_id: str, restaurant_id: str) -> bool:
    async with pool().acquire() as c:
        result = await c.execute("""
            UPDATE reservas SET status = 'confirmada'
            WHERE id = $1 AND restaurant_id = $2 AND status = 'pendente'
        """, reserva_id, restaurant_id)
    return int(result.split()[-1]) > 0


async def cancelar_reserva(reserva_id: str, restaurant_id: str) -> bool:
    async with pool().acquire() as c:
        result = await c.execute("""
            UPDATE reservas SET status = 'cancelada'
            WHERE id = $1 AND restaurant_id = $2
            AND status IN ('pendente','confirmada')
        """, reserva_id, restaurant_id)
    return int(result.split()[-1]) > 0


_STATUS_RESERVA_VALIDOS = {"no_show", "realizada", "confirmada", "cancelada", "pendente"}

async def atualizar_status_reserva(reserva_id: str, restaurant_id: str, status: str) -> Optional[dict]:
    """Atualiza status de uma reserva. Retorna a reserva atualizada ou None se não encontrada."""
    if status not in _STATUS_RESERVA_VALIDOS:
        raise ValueError(f"Status inválido: {status}. Válidos: {_STATUS_RESERVA_VALIDOS}")
    async with pool().acquire() as c:
        row = await c.fetchrow("""
            UPDATE reservas SET status = $3
            WHERE id = $1 AND restaurant_id = $2
            RETURNING *
        """, reserva_id, restaurant_id, status)
    return dict(row) if row else None


async def listar_reservas_semana(restaurant_id: str, data_inicio: str) -> list[dict]:
    """Retorna agregado de 7 dias a partir de data_inicio, com contagens por status."""
    from datetime import date as _date, timedelta as _td
    try:
        start = _date.fromisoformat(data_inicio)
    except ValueError:
        start = _date.today()
    end = start + _td(days=6)

    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT
                d.data::DATE                                                                              AS data,
                COUNT(r.id) FILTER (WHERE r.status IN ('confirmada','pendente'))                          AS total_reservas,
                COALESCE(SUM(r.posicoes) FILTER (WHERE r.status IN ('confirmada','pendente')), 0)::INT    AS total_pax,
                COUNT(r.id) FILTER (WHERE r.status = 'confirmada')                                        AS confirmadas,
                COUNT(r.id) FILTER (WHERE r.status = 'cancelada')                                         AS canceladas,
                COUNT(r.id) FILTER (WHERE r.status = 'no_show')                                           AS no_show
            FROM generate_series($2::date, $3::date, INTERVAL '1 day') d(data)
            LEFT JOIN reservas r
                ON r.data = d.data::DATE AND r.restaurant_id = $1
            GROUP BY d.data
            ORDER BY d.data
        """, restaurant_id, start, end)
    return [dict(r) for r in rows]


async def get_ocupacao_mensal(restaurant_id: str, mes: str) -> list[dict]:
    """Retorna ocupação agregada por dia para um mês. mes = 'YYYY-MM'"""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT
                d.data::DATE as data,
                COUNT(*) FILTER (WHERE r.status IN ('confirmada','pendente')) as total_reservas,
                COALESCE(SUM(r.posicoes) FILTER (WHERE r.status IN ('confirmada','pendente')), 0) as total_pax,
                COALESCE(SUM(t.capacidade_posicoes_max), 0) as capacidade_total
            FROM generate_series(
                date_trunc('month', $2::DATE),
                date_trunc('month', $2::DATE) + INTERVAL '1 month' - INTERVAL '1 day',
                INTERVAL '1 day'
            ) d(data)
            LEFT JOIN reservas r ON r.data = d.data::DATE AND r.restaurant_id = $1
            LEFT JOIN agenda_turnos t ON t.id = r.turno_id
            GROUP BY d.data
            ORDER BY d.data
        """, restaurant_id, f"{mes}-01")
    return [dict(r) for r in rows]


async def get_disponibilidade_semana(restaurant_id: str, data_inicio: str, dias: int = 7) -> list[dict]:
    from datetime import date as _date, timedelta as _td
    try:
        start = _date.fromisoformat(data_inicio)
    except ValueError:
        start = _date.today()
    end = start + _td(days=max(dias - 1, 0))

    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT
                t.id::text                                                                            AS turno_id,
                t.nome                                                                               AS turno_nome,
                t.hora_inicio::text                                                                  AS hora_inicio,
                t.hora_fim::text                                                                     AS hora_fim,
                t.capacidade_posicoes_max,
                d.data::text                                                                         AS data,
                EXTRACT(DOW FROM d.data)::INT                                                        AS dia_semana,
                COALESCE(SUM(r.posicoes) FILTER (WHERE r.status IN ('pendente','confirmada')), 0)::INT AS posicoes_ocupadas,
                (t.capacidade_posicoes_max - COALESCE(SUM(r.posicoes) FILTER (WHERE r.status IN ('pendente','confirmada')), 0))::INT AS posicoes_disponiveis
            FROM generate_series($2::timestamp, $3::timestamp, INTERVAL '1 day') d(data)
            JOIN agenda_turnos t
                ON t.restaurant_id = $1
               AND t.dia_semana = EXTRACT(DOW FROM d.data)::INT
               AND t.ativo = true
            LEFT JOIN reservas r
                ON r.turno_id = t.id AND r.data = d.data::date
            LEFT JOIN agenda_bloqueios b
                ON b.restaurant_id = $1
               AND b.data_inicio::date <= d.data::date
               AND b.data_fim::date   >= d.data::date
            WHERE b.id IS NULL
            GROUP BY t.id, t.nome, t.hora_inicio, t.hora_fim, t.capacidade_posicoes_max, d.data
            ORDER BY d.data, t.hora_inicio
        """, restaurant_id, start, end)
    return [dict(r) for r in rows]


# ── Ordens de Serviço ─────────────────────────────────────────

async def listar_os(restaurant_id: str, status: str | None = None) -> list[dict]:
    query = "SELECT * FROM ordens_servico WHERE restaurant_id = $1"
    params = [restaurant_id]
    if status:
        query += " AND status = $2"
        params.append(status)
    query += " ORDER BY data DESC, criado_em DESC LIMIT 100"
    async with pool().acquire() as c:
        rows = await c.fetch(query, *params)
    return [dict(r) for r in rows]


async def criar_os(data: dict) -> dict:
    from datetime import date as _date, time as _time

    # Converte strings para tipos Python que asyncpg aceita
    raw_data = data["data"]
    if isinstance(raw_data, str):
        try:
            data_obj = _date.fromisoformat(raw_data)
        except ValueError:
            data_obj = _date.today()
    else:
        data_obj = raw_data

    def _parse_time(val):
        if val is None:
            return None
        if isinstance(val, str):
            try:
                parts = [int(x) for x in val.split(":")]
                return _time(parts[0], parts[1], parts[2] if len(parts) > 2 else 0)
            except Exception:
                return None
        return val

    hora_obj = _parse_time(data.get("hora_inicio", "19:00"))
    montagem_obj = _parse_time(data.get("horario_montagem"))

    async with pool().acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO ordens_servico (
                restaurant_id, cliente_phone, cliente_nome,
                tipo_evento, data, hora_inicio, pessoas,
                valor_total, valor_entrada, status,
                responsavel_evento, restricoes_alimentares,
                decoracao, musico_dj, horario_montagem, observacoes
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            RETURNING *
        """,
        data["restaurant_id"], data["cliente_phone"], data["cliente_nome"],
        data["tipo_evento"], data_obj, hora_obj,
        data["pessoas"], data.get("valor_total"), data.get("valor_entrada"),
        data.get("status", "rascunho"), data.get("responsavel_evento"),
        data.get("restricoes_alimentares", []), data.get("decoracao"),
        data.get("musico_dj"), montagem_obj,
        data.get("observacoes"))
    return dict(row)


async def get_os(os_id: str, restaurant_id: str) -> dict | None:
    async with pool().acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM ordens_servico WHERE id = $1 AND restaurant_id = $2",
            os_id, restaurant_id)
    return dict(row) if row else None


async def atualizar_os(os_id: str, restaurant_id: str, data: dict) -> dict:
    campos = {k: v for k, v in data.items()
              if k not in ("id", "restaurant_id", "criado_em")}
    sets = ", ".join(f"{k} = ${i+3}" for i, k in enumerate(campos))
    values = list(campos.values())
    async with pool().acquire() as c:
        row = await c.fetchrow(
            f"UPDATE ordens_servico SET {sets}, atualizado_em = NOW() "
            f"WHERE id = $1 AND restaurant_id = $2 RETURNING *",
            os_id, restaurant_id, *values)
    return dict(row) if row else None


# ─── Dashboard financeiro ─────────────────────────────────────

async def get_financeiro_resumo(restaurant_id: str, periodo: str = "mes") -> dict:
    """Resumo financeiro das OS por período: semana | mes | trimestre."""
    from datetime import date as _date

    hoje = _date.today()
    if periodo == "semana":
        inicio = hoje.replace(day=hoje.day - hoje.weekday())  # segunda-feira atual
    elif periodo == "trimestre":
        mes_trim = ((hoje.month - 1) // 3) * 3 + 1
        inicio = hoje.replace(month=mes_trim, day=1)
    else:  # mes (padrão)
        inicio = hoje.replace(day=1)

    query = """
        SELECT
            COALESCE(SUM(CASE WHEN status IN ('confirmado','realizado')
                THEN valor_total ELSE 0 END), 0)                             AS receita_confirmada,
            COALESCE(SUM(CASE WHEN status IN ('entrada_paga','confirmado','realizado')
                THEN valor_entrada ELSE 0 END), 0)                           AS entradas_recebidas,
            COALESCE(AVG(CASE WHEN status NOT IN ('rascunho','cancelado')
                THEN valor_total END), 0)                                     AS ticket_medio,
            COUNT(*) FILTER (WHERE status = 'rascunho')                      AS n_rascunho,
            COUNT(*) FILTER (WHERE status = 'proposta_enviada')              AS n_proposta_enviada,
            COUNT(*) FILTER (WHERE status = 'entrada_paga')                  AS n_entrada_paga,
            COUNT(*) FILTER (WHERE status = 'confirmado')                    AS n_confirmado,
            COUNT(*) FILTER (WHERE status = 'realizado')                     AS n_realizado,
            COUNT(*) FILTER (WHERE status = 'cancelado')                     AS n_cancelado,
            COALESCE(SUM(CASE
                WHEN status IN ('confirmado','realizado')
                  AND DATE_TRUNC('month', data) = DATE_TRUNC('month', CURRENT_DATE)
                THEN valor_total ELSE 0 END), 0)                             AS projecao_mes
        FROM ordens_servico
        WHERE restaurant_id = $1
          AND data >= $2
    """
    async with pool().acquire() as c:
        row = await c.fetchrow(query, restaurant_id, inicio)

    r = dict(row)
    receita  = float(r["receita_confirmada"] or 0)
    entradas = float(r["entradas_recebidas"] or 0)
    return {
        "receita_confirmada": round(receita, 2),
        "entradas_recebidas": round(entradas, 2),
        "saldo_pendente":     round(receita - entradas, 2),
        "ticket_medio":       round(float(r["ticket_medio"] or 0), 2),
        "projecao_mes":       round(float(r["projecao_mes"] or 0), 2),
        "os_por_status": {
            "rascunho":         int(r["n_rascunho"]),
            "proposta_enviada": int(r["n_proposta_enviada"]),
            "entrada_paga":     int(r["n_entrada_paga"]),
            "confirmado":       int(r["n_confirmado"]),
            "realizado":        int(r["n_realizado"]),
            "cancelado":        int(r["n_cancelado"]),
        },
        "periodo": periodo,
        "inicio":  inicio.isoformat(),
    }


# ─── Pipeline comercial ──────────────────────────────────────────

async def get_pipeline_report(restaurant_id: str) -> dict:
    """Pipeline comercial: funil OS por status com valores + reservas do mês."""
    async with pool().acquire() as c:
        # OS: agrupado por status com valor total
        os_rows = await c.fetch("""
            SELECT
                status,
                COUNT(*)                        AS quantidade,
                COALESCE(SUM(valor_total), 0)   AS valor_total,
                COALESCE(AVG(valor_total), 0)   AS ticket_medio
            FROM ordens_servico
            WHERE restaurant_id = $1
              AND status NOT IN ('cancelado')
            GROUP BY status
            ORDER BY CASE status
                WHEN 'rascunho'          THEN 1
                WHEN 'proposta_enviada'  THEN 2
                WHEN 'entrada_paga'      THEN 3
                WHEN 'confirmado'        THEN 4
                WHEN 'realizado'         THEN 5
                ELSE 6 END
        """, restaurant_id)

        # Reservas do mês atual por status
        res_rows = await c.fetch("""
            SELECT
                status,
                COUNT(*)                                AS quantidade,
                COALESCE(SUM(pagamento_valor), 0)       AS valor_pago,
                COALESCE(AVG(posicoes), 0)              AS pax_medio
            FROM reservas
            WHERE restaurant_id = $1
              AND DATE_TRUNC('month', data) = DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY status
            ORDER BY status
        """, restaurant_id)

        # Totais pipeline OS
        totais = await c.fetchrow("""
            SELECT
                COALESCE(SUM(CASE WHEN status IN ('proposta_enviada','entrada_paga','confirmado')
                    THEN valor_total ELSE 0 END), 0)    AS pipeline_aberto,
                COALESCE(SUM(CASE WHEN status = 'realizado'
                    THEN valor_total ELSE 0 END), 0)    AS receita_realizada,
                COUNT(*) FILTER (WHERE status NOT IN ('cancelado','realizado')) AS os_ativas
            FROM ordens_servico
            WHERE restaurant_id = $1
        """, restaurant_id)

    os_funil = [
        {
            "status": r["status"],
            "quantidade": int(r["quantidade"]),
            "valor_total": round(float(r["valor_total"]), 2),
            "ticket_medio": round(float(r["ticket_medio"]), 2),
        }
        for r in os_rows
    ]

    reservas_mes = [
        {
            "status": r["status"],
            "quantidade": int(r["quantidade"]),
            "valor_pago": round(float(r["valor_pago"]), 2),
            "pax_medio": round(float(r["pax_medio"]), 1),
        }
        for r in res_rows
    ]

    return {
        "os_funil": os_funil,
        "reservas_mes": reservas_mes,
        "resumo": {
            "pipeline_aberto_brl": round(float(totais["pipeline_aberto"]), 2),
            "receita_realizada_brl": round(float(totais["receita_realizada"]), 2),
            "os_ativas": int(totais["os_ativas"]),
        },
    }


# ─── Régua pós-evento ────────────────────────────────────────────

async def get_os_para_regua(restaurant_id: str) -> list[dict]:
    """Retorna OS realizadas que precisam de alguma etapa da régua."""
    query = """
        SELECT
            id,
            restaurant_id,
            cliente_phone   AS telefone,
            cliente_nome    AS contact_nome,
            tipo_evento     AS titulo,
            valor_total,
            evento_realizado_em,
            regua_d1_enviado_em,
            regua_d3_enviado_em,
            regua_d7_enviado_em,
            regua_d30_enviado_em,
            nps_score
        FROM ordens_servico
        WHERE restaurant_id = $1
          AND status = 'realizado'
          AND evento_realizado_em IS NOT NULL
    """
    async with pool().acquire() as c:
        rows = await c.fetch(query, restaurant_id)
        return [dict(r) for r in rows]


async def marcar_regua_enviada(os_id: str, etapa: str) -> None:
    """Marca timestamp de envio da etapa da régua. etapa: d1|d3|d7|d30"""
    col_map = {
        "d1":  "regua_d1_enviado_em",
        "d3":  "regua_d3_enviado_em",
        "d7":  "regua_d7_enviado_em",
        "d30": "regua_d30_enviado_em",
    }
    col = col_map.get(etapa)
    if not col:
        raise ValueError(f"Etapa inválida: {etapa}")
    async with pool().acquire() as c:
        await c.execute(
            f"UPDATE ordens_servico SET {col} = NOW() WHERE id = $1",
            os_id
        )


async def _recalcular_ltv_contato(c, celular: str) -> None:
    """Recalcula ltv_total e total_eventos de um único contato (conexão reutilizada).

    LTV = SUM(reservas pagas) + SUM(OS realizadas)
    total_eventos = COUNT(reservas confirmadas/pagas) + COUNT(OS realizadas)
    """
    await c.execute(
        """UPDATE contacts
           SET ltv_total = (
               COALESCE((
                   SELECT SUM(r.pagamento_valor)
                   FROM reservas r
                   WHERE r.cliente_phone = $1
                     AND r.pagamento_status = 'pago'
               ), 0)
               +
               COALESCE((
                   SELECT SUM(o.valor_total)
                   FROM ordens_servico o
                   WHERE o.cliente_phone = $1
                     AND o.status = 'realizado'
               ), 0)
           ),
           total_eventos = (
               COALESCE((
                   SELECT COUNT(*)
                   FROM reservas r
                   WHERE r.cliente_phone = $1
                     AND r.status IN ('confirmada', 'realizada')
               ), 0)
               +
               COALESCE((
                   SELECT COUNT(*)
                   FROM ordens_servico o
                   WHERE o.cliente_phone = $1
                     AND o.status = 'realizado'
               ), 0)
           )
           WHERE celular = $1""",
        celular
    )


async def recalcular_ltv(restaurant_id: str) -> dict:
    """Recalcula ltv_total e total_eventos de todos os contatos associados ao restaurante.

    Retorna {contatos_atualizados, ltv_total_brl}.
    """
    async with pool().acquire() as c:
        # Contatos que interagiram com o restaurante via reservas OU OS
        rows = await c.fetch(
            """SELECT DISTINCT celular FROM contacts
               WHERE celular IN (
                   SELECT DISTINCT cliente_phone FROM reservas   WHERE restaurant_id = $1
                   UNION
                   SELECT DISTINCT cliente_phone FROM ordens_servico WHERE restaurant_id = $1
               )""",
            restaurant_id
        )
        contatos = [r["celular"] for r in rows]
        for celular in contatos:
            await _recalcular_ltv_contato(c, celular)

        total = await c.fetchval(
            """SELECT COALESCE(SUM(ltv_total), 0)
               FROM contacts
               WHERE celular = ANY($1::text[])""",
            contatos
        )
    return {"contatos_atualizados": len(contatos), "ltv_total_brl": float(total or 0)}


async def registrar_nps(os_id: str, nota: int) -> None:
    """Salva nota NPS recebida via WhatsApp."""
    async with pool().acquire() as c:
        await c.execute(
            """UPDATE ordens_servico
               SET nps_score = $1, nps_respondido_em = NOW()
               WHERE id = $2""",
            nota, os_id
        )
        # Recalcula LTV combinado (reservas + OS) para o cliente da OS
        row = await c.fetchrow("SELECT cliente_phone FROM ordens_servico WHERE id = $1", os_id)
        if row and row["cliente_phone"]:
            await _recalcular_ltv_contato(c, row["cliente_phone"])


async def marcar_os_realizada(os_id: str) -> None:
    """Marca OS como realizada e registra timestamp — dispara régua."""
    async with pool().acquire() as c:
        await c.execute(
            """UPDATE ordens_servico
               SET status = 'realizado',
                   evento_realizado_em = NOW()
               WHERE id = $1""",
            os_id
        )


# ── Checklists D-7 / D-0 ─────────────────────────────────────

async def get_or_create_checklist(os_id: str, tipo: str) -> list[dict]:
    """Retorna itens do checklist da OS. Cria a partir do template se ainda não existir."""
    async with pool().acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM checklist_instancias WHERE os_id=$1 AND tipo=$2 ORDER BY ordem",
            os_id, tipo
        )
        if rows:
            return [dict(r) for r in rows]
        # Cria instâncias a partir do template
        templates = await c.fetch(
            "SELECT * FROM checklist_templates WHERE tipo=$1 AND ativo=TRUE ORDER BY ordem",
            tipo
        )
        if not templates:
            return []
        for t in templates:
            await c.execute(
                """INSERT INTO checklist_instancias (os_id, tipo, ordem, item)
                   VALUES ($1, $2, $3, $4)""",
                os_id, tipo, t["ordem"], t["item"]
            )
        rows = await c.fetch(
            "SELECT * FROM checklist_instancias WHERE os_id=$1 AND tipo=$2 ORDER BY ordem",
            os_id, tipo
        )
        return [dict(r) for r in rows]


async def toggle_checklist_item(item_id: str, concluido_por: str = "equipe") -> Optional[dict]:
    """Alterna concluído/pendente de um item do checklist."""
    async with pool().acquire() as c:
        cur = await c.fetchrow(
            "SELECT concluido FROM checklist_instancias WHERE id=$1",
            item_id
        )
        if not cur:
            return None
        novo = not cur["concluido"]
        updated = await c.fetchrow(
            """UPDATE checklist_instancias
               SET concluido     = $1,
                   concluido_em  = CASE WHEN $1 THEN NOW() ELSE NULL END,
                   concluido_por = CASE WHEN $1 THEN $2  ELSE NULL END
               WHERE id = $3
               RETURNING *""",
            novo, concluido_por, item_id
        )
        return dict(updated) if updated else None
