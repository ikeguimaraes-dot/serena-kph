"""
Camada de dados — PostgreSQL via asyncpg (Supabase).
Cobre: conversas, reservas, restaurantes, cardápio, handoff, relatórios.
"""

import os, uuid
import asyncpg
from typing import Optional
from datetime import datetime, timedelta

_pool: Optional[asyncpg.Pool] = None


# ── Pool ──────────────────────────────────────────────────────

async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=2, max_size=10, command_timeout=30,
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

async def get_restaurant_by_whatsapp(number: str) -> Optional[dict]:
    async with pool().acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM restaurants WHERE whatsapp_number=$1 AND ativo=true", number)
    if not row:
        return None
    r = dict(row)
    r["horarios"]  = await _get_horarios(r["id"])
    r["faq"]       = await _get_faq(r["id"])
    r["cardapio"]  = await _get_menu_summary(r["id"])
    return r

async def get_all_restaurants() -> list[dict]:
    async with pool().acquire() as c:
        rows = await c.fetch("SELECT * FROM restaurants ORDER BY nome")
    return [dict(r) for r in rows]

async def get_restaurant_full(rid: str) -> Optional[dict]:
    async with pool().acquire() as c:
        row = await c.fetchrow("SELECT * FROM restaurants WHERE id=$1", rid)
    if not row:
        return None
    r = dict(row)
    r["horarios"]    = await _get_horarios(rid)
    r["faq"]         = await _get_faq(rid)
    r["menu_items"]  = await get_menu_items(rid)
    r["team"]        = await get_team(rid)
    return r

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

async def update_restaurant(rid: str, data: dict) -> bool:
    fields = [f"{k}=${i+2}" for i,k in enumerate(data.keys())]
    if not fields:
        return False
    async with pool().acquire() as c:
        r = await c.execute(
            f"UPDATE restaurants SET {','.join(fields)} WHERE id=$1",
            rid, *data.values())
    return r.split()[-1] != "0"

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
    data["updated_at"] = datetime.now()
    fields = [f"{k}=${i+2}" for i,k in enumerate(data.keys())]
    async with pool().acquire() as c:
        r = await c.execute(
            f"UPDATE menu_items SET {','.join(fields)} WHERE id=$1",
            item_id, *data.values())
    return r.split()[-1] != "0"

async def delete_menu_item(item_id: int) -> bool:
    async with pool().acquire() as c:
        r = await c.execute("DELETE FROM menu_items WHERE id=$1", item_id)
    return r.split()[-1] != "0"


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
    return r.split()[-1] != "0"


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
    """Últimas conversas únicas por cliente para o painel."""
    async with pool().acquire() as c:
        rows = await c.fetch("""
            SELECT DISTINCT ON (user_phone)
              user_phone, content, created_at
            FROM conversations
            WHERE restaurant_id=$1
            ORDER BY user_phone, created_at DESC
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
        conditions.append(f"data=${len(params)+1}")
        params.append(data)
    if status:
        conditions.append(f"status=${len(params)+1}")
        params.append(status)
    async with pool().acquire() as c:
        rows = await c.fetch(
            f"SELECT * FROM reservations WHERE {' AND '.join(conditions)} ORDER BY data,hora",
            *params)
    return [dict(r) for r in rows]

async def update_reservation(res_id: str, data: dict) -> bool:
    fields = [f"{k}=${i+2}" for i,k in enumerate(data.keys())]
    async with pool().acquire() as c:
        r = await c.execute(
            f"UPDATE reservations SET {','.join(fields)} WHERE id=$1",
            res_id, *data.values())
    return r.split()[-1] != "0"

async def cancel_reservation(res_id: str, user_phone: str) -> bool:
    async with pool().acquire() as c:
        r = await c.execute("""
            UPDATE reservations SET status='cancelada'
            WHERE id=$1 AND user_phone=$2 AND status='confirmada'""",
            res_id.upper(), user_phone)
    return r.split()[-1] != "0"

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
    q = "SELECT * FROM handoff_sessions WHERE restaurant_id=$1"
    params: list = [rid]
    if status:
        q += f" AND status=$2"
        params.append(status)
    q += " ORDER BY created_at DESC"
    async with pool().acquire() as c:
        rows = await c.fetch(q, *params)
    return [dict(r) for r in rows]

async def update_handoff_status(hid: int, status: str, atendente: Optional[str]=None) -> bool:
    resolved = "NOW()" if status == "resolvido" else "NULL"
    async with pool().acquire() as c:
        r = await c.execute(f"""
            UPDATE handoff_sessions
            SET status=$2, atendente_nome=$3, resolved_at={resolved}
            WHERE id=$1""", hid, status, atendente)
    return r.split()[-1] != "0"

async def is_in_handoff(user_phone: str, rid: str) -> bool:
    async with pool().acquire() as c:
        row = await pool().acquire() if False else await c.fetchrow("""
            SELECT id FROM handoff_sessions
            WHERE user_phone=$1 AND restaurant_id=$2
              AND status IN ('aguardando','em_atendimento')
            LIMIT 1""", user_phone, rid)
    return row is not None


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
    today = datetime.now().strftime("%d/%m/%Y")
    month_start = datetime.now().replace(day=1).strftime("%d/%m/%Y")

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
