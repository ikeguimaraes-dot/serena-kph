"""Módulo: contexto CRM do contato atual — injetado no system prompt a cada turno."""

from datetime import datetime
import pytz
import database as db

_TZ_SP = pytz.timezone("America/Sao_Paulo")


def _format_contact_block(contact: dict | None, reservations: list) -> str:
    """Bloco CRM injetado no system prompt — Serena sabe quem está do outro lado."""
    if not contact:
        return "  Cliente novo — não há cadastro no CRM. Apresente-se naturalmente."

    nome = (contact.get("nome") or "").strip()
    sobrenome = (contact.get("sobrenome") or "").strip()
    nome_completo = " ".join(p for p in (nome, sobrenome) if p) or "(sem nome cadastrado)"

    lines = [f"  Nome: {nome_completo}"]
    if contact.get("tier"):
        lines.append(f"  Tier: {contact['tier']}")

    freq = contact.get("frequencia_visitas") or 0
    ultima = contact.get("ultima_visita")
    if ultima:
        try:
            dias = (datetime.now(_TZ_SP).date() - ultima).days
            quando = "hoje" if dias == 0 else f"há {dias} dia{'s' if dias != 1 else ''}"
            lines.append(f"  Última visita: {ultima.strftime('%d/%m/%Y')} ({quando}) · {freq} visita{'s' if freq != 1 else ''} no total")
        except Exception:
            lines.append(f"  Última visita: {ultima} · {freq} visitas no total")
    elif freq:
        lines.append(f"  Visitas registradas: {freq}")

    estagio = contact.get("estagio_kanban")
    if estagio:
        lines.append(f"  Estágio CRM: {estagio}")

    ocasiao = contact.get("ocasiao") or []
    if ocasiao:
        lines.append(f"  Ocasiões anteriores: {', '.join(ocasiao)}")

    restricoes = contact.get("restricoes_alimentares") or []
    if restricoes:
        lines.append(f"  Restrições alimentares: {', '.join(restricoes)}")

    tags = contact.get("tags") or []
    if tags:
        lines.append(f"  Tags: {', '.join(tags)}")

    notas = (contact.get("notas") or "").strip()
    if notas:
        lines.append(f"  Notas internas: {notas[:200]}")

    # Reserva pendente (futura, status confirmada)
    hoje = datetime.now(_TZ_SP).date()
    pendentes = []
    for rsv in reservations or []:
        if rsv.get("status") not in ("confirmada", "pendente"):
            continue
        try:
            rdate = datetime.strptime(rsv["data"], "%d/%m/%Y").date()
        except Exception:
            continue
        if rdate >= hoje:
            pendentes.append((rdate, rsv))
    if pendentes:
        pendentes.sort(key=lambda x: x[0])
        rdate, rsv = pendentes[0]
        hora = rsv.get("hora") or rsv.get("horario") or ""
        pessoas = rsv.get("pessoas", "?")
        lines.append(f"  Reserva pendente: {rdate.strftime('%d/%m/%Y')} {hora} · {pessoas} pessoa(s) · status {rsv.get('status')}")

    # Anti-fricção: quando o nome JÁ está no CRM, reforça pra Serena não perguntar de novo.
    if nome:
        lines.append(
            f"  IMPORTANTE: o nome do cliente JÁ é conhecido ({nome_completo}). "
            "NÃO pergunte \"com quem estou falando?\" nem peça o nome novamente."
        )

    return "\n".join(lines)


async def build_contact_context(user_phone: str | None) -> str:
    """Busca contato + reservas e devolve bloco formatado. Best-effort — nunca quebra."""
    if not user_phone:
        return _format_contact_block(None, [])
    try:
        contact = await db.get_contact(user_phone)
        reservations = await db.get_contact_reservations(user_phone, limit=10) if contact else []
        return _format_contact_block(contact, reservations)
    except Exception as e:
        print(f"[AGENT] build_contact_context falhou user={user_phone!r}: {e!r}")
        return "  (CRM indisponível neste turno)"
