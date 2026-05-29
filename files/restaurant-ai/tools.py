"""
Tools executadas pelo agente Claude — todas assíncronas (asyncpg).
"""

from datetime import timedelta, date
import database as db


# ── Hotfix 3 — helpers compartilhados ────────────────────────────

_DIA_TO_WEEKDAY = {
    "segunda": 0, "segundafeira": 0,
    "terca": 1, "terça": 1, "tercafeira": 1, "terçafeira": 1,
    "quarta": 2, "quartafeira": 2,
    "quinta": 3, "quintafeira": 3,
    "sexta": 4, "sextafeira": 4,
    "sabado": 5, "sábado": 5,
    "domingo": 6,
}

def _resolve_date(text: str | None) -> date | None:
    """'2026-05-10', 'hoje', 'amanha', 'amanhã', 'sábado', 'sexta' → date.
    Retorna None se não conseguir parsear (tools tratam o None com fallback)."""
    if not text:
        return None
    s = text.strip().lower()
    # ISO
    try:
        return date.fromisoformat(s)
    except Exception:
        pass
    today = date.today()
    if s in ("hoje", "today"):
        return today
    if s in ("amanha", "amanhã", "tomorrow"):
        return today + timedelta(days=1)
    if s in ("depois de amanha", "depois de amanhã"):
        return today + timedelta(days=2)
    # tenta achar dia da semana mencionado em qualquer lugar do texto
    for token in s.replace("-", "").split():
        wd = _DIA_TO_WEEKDAY.get(token)
        if wd is not None:
            delta = (wd - today.weekday()) % 7
            if delta == 0:
                delta = 7  # próxima ocorrência, não hoje
            return today + timedelta(days=delta)
    return None


def _normalize_time(t: str | None) -> str | None:
    """'21h30' / '21:30' / '21h' / '21' → 'HH:MM' (24h). None se inválido."""
    if not t:
        return None
    s = t.strip().lower().replace("h", ":")
    if s.endswith(":"):
        s = s[:-1]
    try:
        if ":" in s:
            hh, mm = s.split(":", 1)
            normalized = f"{int(hh):02d}:{int(mm or '0'):02d}"
        else:
            normalized = f"{int(s):02d}:00"
        h, m = map(int, normalized.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return normalized
    except Exception:
        return None


async def consultar_reservas(user_phone: str, restaurant_id: str) -> str:
    reservas = await db.get_reservations_by_user(user_phone, restaurant_id)

    if not reservas:
        return "Nenhuma reserva ativa encontrada para este número."

    linhas = ["Suas reservas ativas:"]
    for r in reservas:
        obs = f" | {r['observacoes']}" if r.get("observacoes") else ""
        linhas.append(
            f"• *{r['id']}* — {r['data']} às {r['hora']} — "
            f"{r['pessoas']} pessoa(s) — {r['nome']}{obs}"
        )
    return "\n".join(linhas)


async def cancelar_reserva(user_phone: str, reservation_id: str) -> str:
    success = await db.cancel_reservation(reservation_id, user_phone)
    if success:
        return f"Reserva *{reservation_id.upper()}* cancelada com sucesso ✅."
    return (
        f"Não encontrei a reserva *{reservation_id.upper()}* associada a este número, "
        f"ou ela já foi cancelada. Verifique o código e tente novamente."
    )


async def transferir_para_humano(motivo: str) -> str:
    return f"__HANDOFF__:{motivo}"


async def update_contact(
    user_phone: str,
    nome: str | None = None,
    sobrenome: str | None = None,
    email: str | None = None,
    data_nascimento: str | None = None,
    ocasiao: list[str] | None = None,
    restricoes_alimentares: list[str] | None = None,
    canal_entrada: str | None = None,
    tags: list[str] | None = None,
    notas: str | None = None,
) -> str:
    """Enriquece o contato CRM com dados extraídos da conversa.
    Merge não-destrutivo: listas são unidas com as existentes, strings só sobrescrevem se vieram não-vazias."""
    current = await db.get_contact(user_phone) or {}

    def _merge_list(new, old):
        if not new:
            return None
        existing = old or []
        merged = list(existing)
        for item in new:
            if item and item not in merged:
                merged.append(item)
        return merged if merged != existing else None

    payload: dict = {"celular": user_phone}
    for k, v in [
        ("nome", nome), ("sobrenome", sobrenome), ("email", email),
        ("data_nascimento", data_nascimento), ("canal_entrada", canal_entrada),
        ("notas", notas),
    ]:
        if v:
            payload[k] = v

    merged_oc = _merge_list(ocasiao, current.get("ocasiao"))
    if merged_oc is not None:
        payload["ocasiao"] = merged_oc
    merged_rest = _merge_list(restricoes_alimentares, current.get("restricoes_alimentares"))
    if merged_rest is not None:
        payload["restricoes_alimentares"] = merged_rest
    merged_tags = _merge_list(tags, current.get("tags"))
    if merged_tags is not None:
        payload["tags"] = merged_tags

    if len(payload) == 1:
        return "Nada para atualizar."

    await db.upsert_contact(payload)
    return "Contato atualizado."


# ════════════════════════════════════════════════════════════════
# HOTFIX 3 — Tools funcionais
# ════════════════════════════════════════════════════════════════

async def lookup_menu(restaurant_id: str, termo: str) -> str:
    """Busca pratos no cardápio. Máx 5 itens. Indisponíveis aparecem por último."""
    try:
        items = await db.search_menu_items(restaurant_id, termo, limit=5)
    except Exception as e:
        print(f"[TOOL lookup_menu] erro: {e!r}")
        return "Não consegui consultar o cardápio agora."

    if not items:
        try:
            cats = await db.get_menu_categories(restaurant_id)
        except Exception:
            cats = []
        if cats:
            return f"Não encontrei '{termo}' no cardápio. Temos: {', '.join(cats)}."
        return f"Não encontrei '{termo}' no cardápio."

    linhas = []
    for it in items:
        preco = it.get("preco")
        if preco is not None:
            preco_txt = f"R$ {float(preco):.2f}".replace(".", ",")
        else:
            preco_txt = "preço sob consulta"
        disp = "disponível" if it.get("disponivel") else "indisponível"
        nome = it.get("nome") or "(sem nome)"
        desc = (it.get("descricao") or "").strip()
        if desc:
            linhas.append(f"{nome} — {preco_txt} ({disp}): {desc}")
        else:
            linhas.append(f"{nome} — {preco_txt} ({disp})")
    return "\n".join(linhas)


async def check_business_hours(restaurant_id: str, data: str) -> str:
    """Verifica funcionamento numa data específica (considerando datas_especiais)."""
    target = _resolve_date(data)
    if target is None:
        return f"Não entendi a data '{data}'. Use formato YYYY-MM-DD ou expressões como 'amanhã', 'domingo'."
    try:
        info = await db.get_business_hours_for_date(restaurant_id, target)
    except Exception as e:
        print(f"[TOOL check_business_hours] erro: {e!r}")
        return "Não consegui consultar o horário agora."

    data_br = target.strftime("%d/%m/%Y")
    DIA_BR = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    dia_sem = DIA_BR[target.weekday()]

    if info.get("especial"):
        nome = info.get("nome") or "Data especial"
        if info.get("aberto"):
            h = info.get("horario") or "horário padrão da casa"
            obs = (info.get("observacao") or "").strip()
            tail = f" — {obs}" if obs else ""
            return f"{data_br} ({dia_sem}, {nome}): aberto excepcionalmente, {h}{tail}."
        return f"{data_br} ({dia_sem}, {nome}): fechado nesse dia."
    if info.get("aberto"):
        return f"{data_br} ({dia_sem}): aberto, {info.get('horario')}."
    obs = info.get("observacao")
    return f"{data_br} ({dia_sem}): fechado." + (f" {obs}" if obs else "")


def get_reservation_link(pessoas=None, data: str | None = None, horario: str | None = None) -> str:
    """Monta link Tagme com query params pré-preenchidos. Sem params, retorna o link base."""
    base = "https://reservation-widget.tagme.com.br/reservation/schedule/691377229337bdf1ad07625f/reservationWidget"
    params = []
    target = _resolve_date(data) if data else None
    if target:
        params.append(f"date={target.isoformat()}")
    t = _normalize_time(horario)
    if t:
        params.append(f"time={t}")
    if pessoas:
        try:
            params.append(f"guests={int(pessoas)}")
        except Exception:
            pass
    return f"{base}?{'&'.join(params)}" if params else base


async def lookup_contact_history(user_phone: str, restaurant_id: str) -> str:
    """Resumo do CRM + últimas 5 reservas (qualquer status)."""
    try:
        contact = await db.get_contact(user_phone)
        reservas = await db.get_recent_reservations(user_phone, restaurant_id, limit=5)
    except Exception as e:
        print(f"[TOOL lookup_contact_history] erro: {e!r}")
        return "Não consegui consultar o histórico agora."

    if not contact and not reservas:
        return "Nenhum histórico encontrado para este número."

    parts = []
    if contact:
        nome = (contact.get("nome") or "").strip()
        sobrenome = (contact.get("sobrenome") or "").strip()
        nome_completo = f"{nome} {sobrenome}".strip()
        if nome_completo:
            parts.append(f"Cliente: {nome_completo}")
        criado = contact.get("criado_em")
        if criado:
            parts.append(f"cadastrado em {str(criado)[:10]}")
        oc = contact.get("ocasiao") or []
        if oc:
            parts.append(f"ocasiões: {', '.join(oc)}")
        rest = contact.get("restricoes_alimentares") or []
        if rest:
            parts.append(f"restrições: {', '.join(rest)}")
        notas = (contact.get("notas") or "").strip()
        if notas:
            parts.append(f"notas: {notas}")
    if reservas:
        ult = reservas[0]  # ordenado DESC, primeira = mais recente
        parts.append(
            f"{len(reservas)} reserva(s); última {ult['data']} às {ult['hora']} "
            f"para {ult['pessoas']} pessoa(s) [{ult.get('status') or 'confirmada'}]"
        )
    return " | ".join(parts) if parts else "Histórico vazio."


# ════════════════════════════════════════════════════════════════
# SERENA 2.0 — Agenda própria
# ════════════════════════════════════════════════════════════════

async def verificar_disponibilidade(restaurant_id: str, data: str, pessoas: int) -> str:
    """Retorna turnos com vagas para uma data e número de pessoas."""
    target = _resolve_date(data)
    if target is None:
        return f"Não entendi a data '{data}'. Use YYYY-MM-DD ou 'amanhã', 'sexta'."

    try:
        slots = await db.get_disponibilidade_semana(restaurant_id, target.isoformat(), dias=1)
    except Exception as e:
        print(f"[TOOL verificar_disponibilidade] erro: {e!r}")
        return "Não consegui consultar a disponibilidade agora."

    data_br = target.strftime("%d/%m/%Y")
    DIA_BR = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    dia_sem = DIA_BR[target.weekday()]

    if not slots:
        return f"Não há turnos configurados para {data_br} ({dia_sem})."

    disponiveis = [s for s in slots if int(s.get("posicoes_disponiveis") or 0) >= pessoas]

    if not disponiveis:
        return (
            f"Sem vagas para {pessoas} pessoa(s) em {data_br} ({dia_sem}). "
            f"Gostaria de verificar outra data?"
        )

    linhas = [f"Horários disponíveis para {pessoas} pessoa(s) em {data_br} ({dia_sem}):"]
    for s in disponiveis:
        hora = str(s["hora_inicio"])[:5]
        nome_turno = s.get("turno_nome") or hora
        vagas = int(s.get("posicoes_disponiveis") or 0)
        linhas.append(f"• *{nome_turno}* às {hora} — {vagas} vaga(s) | id:{s['turno_id']}")
    return "\n".join(linhas)


async def fazer_reserva(
    restaurant_id: str,
    user_phone: str,
    nome: str,
    data: str,
    turno_id: str,
    hora_inicio: str,
    pessoas: int,
    observacoes: str | None = None,
    email: str | None = None,
) -> str:
    """Cria reserva na agenda própria após confirmar disponibilidade."""
    target = _resolve_date(data)
    if target is None:
        return f"Não entendi a data '{data}'."

    try:
        disp = await db.check_disponibilidade(
            restaurant_id, target.isoformat(), turno_id, pessoas
        )
    except Exception as e:
        print(f"[TOOL fazer_reserva] check_disponibilidade erro: {e!r}")
        return "Não consegui verificar a disponibilidade antes de confirmar. Tente novamente."

    if not disp or not disp.get("disponivel"):
        vagas = disp.get("posicoes_livres", 0) if disp else 0
        return f"Sem vagas suficientes neste horário ({vagas} vaga(s) restante(s)). Escolha outro turno."

    hora_fmt = _normalize_time(hora_inicio) or hora_inicio

    payload = {
        "restaurant_id": restaurant_id,
        "turno_id": turno_id,
        "cliente_phone": user_phone,
        "cliente_nome": nome,
        "cliente_email": email,
        "data": target.isoformat(),
        "hora_inicio": hora_fmt,
        "posicoes": pessoas,
        "canal": "whatsapp",
        "observacoes": observacoes,
        "pagamento_status": "nao_requerido",
        "status": "confirmada",
    }

    # Idempotência — evita reserva duplicada para mesma data/turno
    try:
        existentes = await db.get_reservas_por_phone(restaurant_id, user_phone)
        for r in existentes:
            if str(r['data']) == target.isoformat() and str(r['turno_id']) == turno_id:
                rid_short = str(r['id'])[:8].upper()
                return f"Você já tem reserva confirmada para esta data. Código: *{rid_short}*"
    except Exception as e:
        print(f"[TOOL fazer_reserva] checar_duplicata erro: {e!r}")

    try:
        reserva = await db.criar_reserva(payload)
    except Exception as e:
        print(f"[TOOL fazer_reserva] criar_reserva erro: {e!r}")
        return "Erro ao registrar a reserva. Tente novamente em instantes."

    rid_short = str(reserva["id"])[:8].upper()
    data_br = target.strftime("%d/%m/%Y")

    return (
        f"✅ Reserva confirmada!\n"
        f"• Código: *{rid_short}*\n"
        f"• Nome: {nome}\n"
        f"• Data: {data_br} às {hora_fmt}\n"
        f"• Pessoas: {pessoas}\n"
        f"Guarde o código para consultar ou cancelar."
    )
