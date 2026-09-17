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
    restaurant_id: str,
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
    current = await db.get_contact(user_phone, restaurant_id=restaurant_id) or {}

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

    await db.upsert_contact(payload, restaurant_id=restaurant_id)
    return "Contato atualizado."


# ════════════════════════════════════════════════════════════════
# HOTFIX 3 — Tools funcionais
# ════════════════════════════════════════════════════════════════

async def lookup_menu(restaurant_id: str, termo: str) -> str:
    """Busca até 5 itens; distingue catálogo ausente, busca sem resultado e erro."""
    orientacao_sem_dados = (
        "Não invente itens ou preços nem conclua que o item não existe, está esgotado "
        "ou que a casa está lotada. Explique que não consegue confirmar essa informação "
        "e ofereça atendimento humano para verificar."
    )
    try:
        items = await db.search_menu_items(restaurant_id, termo, limit=5)
        if not items:
            # Categorias vazias não provam catálogo vazio: podem existir itens
            # sem categoria ou indisponíveis. Consulte a existência no mesmo tenant.
            if not await db.has_menu_items(restaurant_id):
                return (
                    "CATALOGO_INDISPONIVEL: A base de catálogo desta unidade está vazia; "
                    "não há dados para confirmar itens, disponibilidade ou preços. "
                    + orientacao_sem_dados
                )
            cats = await db.get_menu_categories(restaurant_id)
            categorias = f" Categorias cadastradas: {', '.join(cats)}." if cats else ""
            return (
                f"SEM_CORRESPONDENCIA: Há catálogo cadastrado, mas a busca por '{termo}' "
                "não encontrou registros correspondentes na base consultada."
                + categorias + " " + orientacao_sem_dados
            )
    except Exception as e:
        print(f"[TOOL lookup_menu] erro: {type(e).__name__}")
        return (
            "ERRO_CONSULTA_CATALOGO: Não foi possível consultar o catálogo agora. "
            "A falha não informa se há catálogo cadastrado. " + orientacao_sem_dados
        )

    linhas = []
    for it in items:
        from catalog import imported_item_text
        imported = imported_item_text(it)
        if imported is not None:
            linhas.append(imported)
            continue
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

    if info.get("aberto") is None:
        return f"HORARIO_NAO_CONFIRMADO: {data_br} ({dia_sem}). Consulte a equipe; ausência de cadastro não significa casa fechada."
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


def get_reservation_link(restaurant_id: str, pessoas=None, data: str | None = None, horario: str | None = None) -> str:
    """Página de reserva da unidade da conversa, sem fallback para tenant global."""
    import os as _os
    from urllib.parse import urlencode, quote
    from reservation_service import valid_tenant
    rid = valid_tenant(restaurant_id)
    painel = _os.environ.get("PAINEL_URL", "https://madonna-painel.vercel.app").rstrip("/")
    params = {}
    target = _resolve_date(data) if data else None
    if target:
        params["data"] = target.isoformat()
    normalized = _normalize_time(horario)
    if normalized:
        params["hora"] = normalized
    if pessoas:
        try:
            params["pessoas"] = int(pessoas)
        except (TypeError, ValueError):
            pass
    suffix = "?" + urlencode(params) if params else ""
    return f"{painel}/reservar/{quote(rid, safe='')}{suffix}"


async def lookup_contact_history(user_phone: str, restaurant_id: str) -> str:
    """Resumo do CRM + últimas 5 reservas (qualquer status)."""
    try:
        contact = await db.get_contact(user_phone, restaurant_id=restaurant_id)
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

    from reservation_service import availability, BookingError
    try:
        async with db.pool().acquire() as c:
            result = await availability(c, restaurant_id, target, pessoas)
    except BookingError as exc:
        return exc.message
    except Exception:
        return "Não consegui consultar a agenda agora. Confirme com a equipe; não conclua que está lotado."
    if result["state"] != "available":
        return result.get("message", "Confirme a disponibilidade com a equipe.")
    lines = [f"Horários disponíveis para {pessoas} pessoa(s) em {target.strftime('%d/%m/%Y')}:"]
    for slot in result["slots"]:
        if slot["available"]:
            lines.append(f"• {slot['start']} | id:{slot['id']}")
    return "\n".join(lines)


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
        return (disp or {}).get("motivo", "Confirme a disponibilidade com a equipe.")

    cliente_email = email
    if not cliente_email:
        try:
            contact = await db.get_contact(user_phone, restaurant_id=restaurant_id)
            if contact and contact.get("email"):
                cliente_email = contact.get("email")
        except Exception as e:
            print(f"[TOOL fazer_reserva] Falha ao recuperar email do CRM: {e!r}")

    hora_fmt = _normalize_time(hora_inicio) or hora_inicio

    payload = {
        "restaurant_id": restaurant_id,
        "turno_id": turno_id,
        "cliente_phone": user_phone,
        "cliente_nome": nome,
        "cliente_email": cliente_email,
        "data": target.isoformat(),
        "hora_inicio": hora_fmt,
        "posicoes": pessoas,
        "canal": "whatsapp",
        "observacoes": observacoes,
        "pagamento_status": "nao_requerido",
        "status": "pendente",
    }

    # Idempotência — evita reserva duplicada para mesma data/turno
    try:
        existentes = await db.get_reservas_por_phone(restaurant_id, user_phone)
        for r in existentes:
            if str(r['data']) == target.isoformat() and str(r['turno_id']) == turno_id:
                rid_short = str(r['id'])[:8].upper()
                return f"Você já tem uma reserva registrada para esta data (status: {r['status']}). Código: *{rid_short}*"
    except Exception as e:
        print(f"[TOOL fazer_reserva] checar_duplicata erro: {e!r}")

    try:
        reserva = await db.criar_reserva(payload)
    except Exception as e:
        from reservation_service import BookingError
        if isinstance(e, BookingError):
            return e.message
        return "Erro ao registrar a reserva. Tente novamente em instantes."

    rid_short = str(reserva["id"])[:8].upper()
    data_br = target.strftime("%d/%m/%Y")

    # Pending bookings await the existing staff confirmation flow. Do not send
    # a confirmation email before that state transition has actually occurred.
    return (
        f"Reserva registrada; aguardando confirmação da equipe.\n"
        f"• Código: *{rid_short}*\n"
        f"• Nome: {nome}\n"
        f"• Data: {data_br} às {hora_fmt}\n"
        f"• Pessoas: {pessoas}\n"
        f"Guarde o código para consultar ou cancelar."
    )


# ── gerar_proposta (Sprint 3) ─────────────────────────────────

async def gerar_proposta(
    restaurant_id: str,
    user_phone: str,
    nome: str,
    tipo_evento: str,
    pessoas: int,
    data: str | None = None,
    ocasiao: str | None = None,
    valor_por_pessoa: float = 300.0,
    observacoes: str | None = None,
) -> str:
    """Gera proposta comercial, cria OS e retorna texto para WhatsApp."""
    from datetime import date as _date

    data_br = ""
    data_iso = None
    if data:
        target = _resolve_date(data)
        if target:
            data_br = target.strftime("%d/%m/%Y")
            data_iso = target.isoformat()

    valor_total = valor_por_pessoa * pessoas
    valor_entrada = valor_total * 0.5

    # Cria OS no banco
    try:
        os_data = {
            "restaurant_id": restaurant_id,
            "cliente_phone": user_phone,
            "cliente_nome": nome,
            "tipo_evento": tipo_evento,
            "data": data_iso or _date.today().isoformat(),
            "hora_inicio": "19:00",
            "pessoas": pessoas,
            "valor_total": valor_total,
            "valor_entrada": valor_entrada,
            "status": "proposta_enviada",
            "observacoes": observacoes,
        }
        await db.criar_os(os_data)
    except Exception as e:
        print(f"[TOOL gerar_proposta] erro ao criar OS: {e!r}")

    # Salva no CRM
    try:
        await db.upsert_contact({
            "restaurant_id": restaurant_id,
            "celular": user_phone,
            "notas": f"Proposta enviada: {tipo_evento}, {pessoas} pax, {data_br}, R${valor_total:.0f}",
            "estagio_kanban": "proposta",
        })
    except Exception as e:
        print(f"[TOOL gerar_proposta] erro ao atualizar CRM: {e!r}")

    ocasiao_linha = f"🎉 Ocasião: {ocasiao}\n" if ocasiao else ""
    data_linha = f"📅 Data: {data_br}\n" if data_br else ""

    proposta = (
        f"🍽️ *Proposta Madonna Cucina*\n\n"
        f"Olá, {nome}! Com base no que conversamos:\n\n"
        f"{data_linha}"
        f"👥 Pessoas: {pessoas}\n"
        f"{ocasiao_linha}\n"
        f"*O que incluímos:*\n"
        f"• Menu degustação exclusivo\n"
        f"• Mise en place especial\n"
        f"• Atendimento dedicado\n"
        f"• Harmonização disponível (opcional)\n\n"
        f"💰 *Investimento:* R$ {valor_por_pessoa:.0f}/pessoa\n"
        f"💳 *Total:* R$ {valor_total:.0f}\n"
        f"📋 *Condições:* 50% entrada (R$ {valor_entrada:.0f}) + 50% no dia\n\n"
        f"Proposta válida por 48h. Posso garantir sua data agora?"
    )
    return proposta


# ── Sprint 3 — Tool determinístico de proposta ───────────────────────────────

async def calcular_proposta(
    restaurant_id: str,
    user_phone: str,
    nome: str,
    tipo: str,
    plano,
    n_pessoas: int,
    ambiente: str,
    data: str | None = None,
    addons: list | None = None,
    observacoes: str | None = None,
) -> str:
    """
    Lê preços de proposta_pricing, calcula via proposta_calc (determinístico),
    grava em ordens_servico e retorna texto formatado para WhatsApp.
    O gerar_proposta antigo permanece intacto — este tool nasce ao lado.
    """
    import proposta_calc
    from decimal import Decimal
    from datetime import date as _date

    addons_req = addons or []

    # ── 1. Lookup de preços no banco ────────────────────────────────────────
    valor_plano_db = None
    if plano:
        valor_plano_db = await db.get_proposta_plano(restaurant_id, tipo, plano)
        if valor_plano_db is None:
            return (
                f"⚠️ Plano '{plano}' ({tipo}) não encontrado na tabela de preços. "
                f"Verifique com a Vic ou cadastre o plano em proposta_pricing."
            )

    valor_plano = Decimal(str(valor_plano_db)) if valor_plano_db is not None else Decimal("0")

    precos_addons_db = await db.get_proposta_addons(
        restaurant_id, tipo, plano or "", addons_req
    )
    precos_addons = {
        k: {"valor": Decimal(str(v["valor"])), "sob_consulta": v["sob_consulta"]}
        for k, v in precos_addons_db.items()
    }

    valor_locacao_db = await db.get_proposta_ambiente(restaurant_id, ambiente)
    if valor_locacao_db is None:
        return (
            f"⚠️ Ambiente '{ambiente}' não encontrado na tabela de preços. "
            f"Verifique com a Vic ou cadastre o ambiente em proposta_pricing."
        )
    valor_locacao = Decimal(str(valor_locacao_db))

    # ── 2. Cálculo determinístico (função pura) ─────────────────────────────
    resultado = proposta_calc.calcular(
        tipo=tipo,
        plano=plano,
        n_pessoas=n_pessoas,
        valor_plano=valor_plano,
        valor_locacao=valor_locacao,
        addons_solicitados=addons_req,
        precos_addons=precos_addons,
    )

    if not resultado["ok"]:
        return f"⚠️ {resultado['erro']}"

    # ── 3. Persistência ─────────────────────────────────────────────────────
    data_br = ""
    data_iso = None
    if data:
        target = _resolve_date(data)
        if target:
            data_br = target.strftime("%d/%m/%Y")
            data_iso = target.isoformat()

    addons_json = [
        {"nome": a["nome"], "valor_pessoa": float(a["valor_pessoa"])}
        for a in resultado["addons_aplicados"]
    ]

    try:
        await db.criar_os_proposta({
            "restaurant_id":  restaurant_id,
            "cliente_phone":  user_phone,
            "cliente_nome":   nome,
            "tipo_evento":    tipo,
            "data":           data_iso or _date.today().isoformat(),
            "pessoas":        n_pessoas,
            "valor_total":    float(resultado["total_base"]),
            "valor_entrada":  float(resultado["sinal"]),
            "status":         "proposta_enviada",
            "plano":          plano,
            "ambiente":       ambiente,
            "addons":         addons_json,
            "observacoes":    observacoes,
        })
        await db.upsert_contact({
            "restaurant_id": restaurant_id,
            "celular":        user_phone,
            "estagio_kanban": "proposta",
            "notas": (
                f"Proposta: {tipo} {plano}, {n_pessoas}px, "
                f"{ambiente}, R${float(resultado['total_base']):.0f}"
            ),
        })
    except Exception as e:
        print(f"[TOOL calcular_proposta] erro ao gravar OS: {e!r}")

    # ── 4. Texto WhatsApp ───────────────────────────────────────────────────
    r = resultado

    def _fmt(slug: str) -> str:
        return (slug or "").replace("_", " ").title()

    addons_linhas = "".join(
        f"\n• {_fmt(a['nome'])}: R$ {float(a['valor_pessoa']):.0f}/pessoa"
        for a in r["addons_aplicados"]
    )
    sc_items = r.get("addons_sob_consulta", [])
    wagyu_linha = (
        "\n\n🥩 *" + ", ".join(_fmt(a["nome"]) for a in sc_items) + ":* valor sob consulta — a Vic confirma"
        if sc_items else ""
    )
    data_linha = f"📅 Data: {data_br}\n" if data_br else ""

    return (
        f"🍷 *Proposta Meet & Eat — {_fmt(tipo)}*\n\n"
        f"{data_linha}"
        f"👥 Pessoas: {n_pessoas}\n"
        f"🏛️ Ambiente: {_fmt(ambiente)}\n"
        f"📋 Plano: {_fmt(plano)}\n\n"
        f"*Composição:*\n"
        f"• Plano {_fmt(plano)}: R$ {float(r['valor_plano_pessoa']):.0f}/pessoa"
        f"{addons_linhas}\n"
        f"• Subtotal pessoas: R$ {float(r['subtotal_pessoas']):,.0f}\n"
        f"• Locação {_fmt(ambiente)}: R$ {float(r['valor_locacao']):,.0f}\n"
        f"━━━━━━━━━━━\n"
        f"💰 *Total: R$ {float(r['total_base']):,.0f}*\n\n"
        f"💳 *Pagamento:*\n"
        f"  Sinal (reserva): R$ {float(r['sinal']):,.0f}\n"
        f"  Saldo (até 1 sem. antes): R$ {float(r['saldo']):,.0f}\n\n"
        f"ℹ️ Taxas adicionais: rolha R$ 150 | valet R$ 40/carro\n"
        f"⏰ Proposta válida por 48h — posso garantir sua data agora?"
        f"{wagyu_linha}"
    )


async def enviar_midia(restaurant_id: str, user_phone: str, chave: str) -> str:
    """Busca URL de mídia cadastrada pela chave e envia via Twilio (efeito colateral).
    Retorna confirmação curta para o agente compor a resposta.
    Best-effort: falha nunca quebra o fluxo.
    """
    import httpx
    import notifications as notif

    item = await db.get_midia_disponivel(restaurant_id, chave)
    if not item:
        return (
            f"Não tenho '{chave}' disponível no momento. "
            f"Vou confirmar com a equipe e te envio em seguida."
        )

    restaurant_phone = await db.get_restaurant_whatsapp(restaurant_id)
    if not restaurant_phone:
        return "Não consegui identificar o número do restaurante. Vou confirmar com a equipe."

    url = item["url"]

    # Validação de tamanho — best-effort, nunca bloqueia o envio
    try:
        async with httpx.AsyncClient() as c:
            head = await c.head(url, timeout=5, follow_redirects=True)
            size = int(head.headers.get("content-length", 0))
            if size > 5 * 1024 * 1024:
                print(f"[MIDIA] aviso: {chave!r} tem {size / 1024 / 1024:.1f}MB — recomendado <5MB")
    except Exception as e:
        print(f"[MIDIA] verificação de tamanho falhou (best-effort): {e!r}")

    try:
        notif.send_to_customer(restaurant_phone, user_phone, "", media_url=url)
        print(f"[MIDIA] enviado chave={chave!r} url={url!r} para {user_phone!r}")
        return f"✅ {item['descricao']} enviado!"
    except Exception as e:
        print(f"[MIDIA] falha ao enviar: {e!r}")
        return "Não consegui enviar o arquivo agora. Vou confirmar com a equipe."
