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
    """Monta link do widget de reservas da Serena com query params pré-preenchidos."""
    import os as _os
    painel = _os.environ.get("PAINEL_URL", "https://madonna-painel.vercel.app").rstrip("/")
    rid = _os.environ.get("RESTAURANT_ID", "madonna_cucina")
    base = f"{painel}/widget/reserva"
    params = [f"rid={rid}"]
    target = _resolve_date(data) if data else None
    if target:
        params.append(f"data={target.isoformat()}")
    t = _normalize_time(horario)
    if t:
        params.append(f"hora={t}")
    if pessoas:
        try:
            params.append(f"pessoas={int(pessoas)}")
        except Exception:
            pass
    return f"{base}?{'&'.join(params)}"


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

    cliente_email = email
    if not cliente_email:
        try:
            contact = await db.get_contact(user_phone)
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

    # Envia email de confirmação assincronamente se houver email cadastrado
    if cliente_email:
        try:
            import email_gateway
            import asyncio

            restaurant_nome = "Madonna Cucina"
            try:
                restaurant = await db.get_restaurant(restaurant_id)
                if restaurant and restaurant.get("nome"):
                    restaurant_nome = restaurant.get("nome")
            except Exception:
                pass

            subject = f"Confirmação de Reserva · {restaurant_nome}"
            html_content = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, Segoe UI, sans-serif; background-color: #1A1A1A; color: #F5F0E8; margin: 0; padding: 40px 20px; }}
    .card {{ max-width: 500px; margin: 0 auto; background: #242424; border: 1px solid #383838; border-radius: 12px; padding: 32px; box-shadow: 0 12px 32px rgba(0,0,0,0.5); }}
    .brand {{ color: #C4622D; font-size: 20px; font-weight: 700; text-align: center; margin-bottom: 24px; letter-spacing: -0.5px; }}
    .divider {{ border-top: 1px solid #383838; margin: 24px 0; }}
    .details {{ background: #2C2C2C; border: 1px solid #383838; border-radius: 8px; padding: 20px; margin: 20px 0; }}
    .code {{ font-size: 28px; font-weight: 800; color: #C4622D; margin: 8px 0; letter-spacing: 1px; }}
    .label {{ font-size: 11px; color: #8A8278; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 2px; }}
    .value {{ font-size: 15px; font-weight: 600; color: #F5F0E8; margin-bottom: 12px; }}
    .value:last-child {{ margin-bottom: 0; }}
    .footer {{ font-size: 12px; color: #8A8278; text-align: center; line-height: 1.5; margin-top: 24px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="brand">{restaurant_nome}</div>
    <h2 style="font-size: 22px; font-weight: 700; margin: 0 0 8px; color: #F5F0E8;">Sua mesa está confirmada.</h2>
    <p style="font-size: 14px; color: #8A8278; margin: 0 0 24px; line-height: 1.5;">Olá, {nome}. Confirmamos a reserva solicitada em nosso canal digital. Os detalhes de sua reserva estão abaixo:</p>
    
    <div class="details">
      <div class="label">Código da Reserva</div>
      <div class="code">{rid_short}</div>
      <div class="divider" style="margin: 16px 0;"></div>
      <div class="label">Data</div>
      <div class="value">{data_br}</div>
      <div class="label">Horário</div>
      <div class="value">{hora_fmt}</div>
      <div class="label">Pessoas</div>
      <div class="value">{pessoas} pax</div>
    </div>
    
    <p style="font-size: 13px; color: #8A8278; line-height: 1.6; margin: 24px 0 0;">Se precisar cancelar ou consultar sua reserva, utilize o código acima através do nosso WhatsApp oficial ou fale diretamente com a nossa equipe.</p>
    <div class="divider"></div>
    <div class="footer">
      <strong>{restaurant_nome}</strong><br>
      Hospitalidade premium · Processo e consistência
    </div>
  </div>
</body>
</html>"""
            
            asyncio.create_task(asyncio.to_thread(email_gateway.send_email, cliente_email, subject, html_content))
        except Exception as email_err:
            print(f"[TOOL fazer_reserva] Falha ao disparar email de confirmação: {email_err!r}")

    return (
        f"✅ Reserva confirmada!\n"
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
