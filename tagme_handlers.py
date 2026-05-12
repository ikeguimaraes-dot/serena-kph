"""
tagme_handlers.py
Handlers de intenção do agente Serena para integração com Tagme.

Cada handler recebe o contexto da conversa e retorna a resposta
em texto para ser enviada ao cliente via WhatsApp.

Intenções cobertas:
  - consultar_reserva  : "tenho reserva hoje?", "minha reserva"
  - fazer_reserva      : "quero reservar", "quero uma mesa"
  - cancelar_reserva   : "quero cancelar", "cancela minha reserva"
"""

from datetime import datetime, date
from typing import Optional
from tagme_client import TagmeClient, map_status, format_datetime_br, build_widget_url


# ─── Handler: Consultar reserva ───────────────────────────────────────────────

async def handle_consultar_reserva(
    phone: str,
    filter_date: Optional[date] = None,
) -> str:
    """
    Busca reservas do cliente na Tagme e retorna mensagem formatada.

    Args:
        phone: número do cliente (qualquer formato)
        filter_date: se informado, filtra só reservas desta data
    """
    async with TagmeClient() as tagme:
        reservations = await tagme.get_reservations_by_phone(phone)

    if not reservations:
        return (
            "Não encontrei nenhuma reserva vinculada ao seu número. 🙁\n\n"
            "Se precisar fazer uma reserva, é só me dizer a data, horário e "
            "número de pessoas!"
        )

    # Filtrar por data se solicitado
    if filter_date:
        def _is_today(r):
            try:
                dt_str = r.get("dateTime") or r.get("date") or ""
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                return dt.date() == filter_date
            except Exception:
                return False
        reservations = [r for r in reservations if _is_today(r)]

    # Filtra só reservas ativas (não canceladas)
    active = [
        r for r in reservations
        if map_status(r.get("status", "")) not in ("cancelada", "no_show")
    ]

    if not active:
        periodo = "hoje" if filter_date == date.today() else "neste período"
        return (
            f"Não encontrei reservas ativas {periodo} para o seu número.\n\n"
            "Quer fazer uma nova reserva? Me diga a data, horário e quantas pessoas! 😊"
        )

    # Monta resposta com todas as reservas ativas
    linhas = ["Encontrei as seguintes reservas para você:\n"]
    for r in active:
        dt_raw = r.get("dateTime") or r.get("date", "")
        hora_raw = r.get("time") or ""
        dt_display = format_datetime_br(dt_raw) if dt_raw else hora_raw
        pessoas = r.get("partySize") or r.get("party_size") or "—"
        status = map_status(r.get("status", ""))
        salao = r.get("section") or r.get("area") or ""
        obs = r.get("observation") or r.get("notes") or ""

        linha = f"📅 *{dt_display}*\n👥 {pessoas} pessoas | Status: {status}"
        if salao:
            linha += f" | {salao}"
        if obs:
            linha += f"\n📝 {obs}"
        linhas.append(linha)

    linhas.append(
        "\nPrecisa cancelar ou alterar? É só me avisar! 😊"
    )

    return "\n\n".join(linhas)


# ─── Handler: Fazer reserva (Caminho A — via widget) ─────────────────────────

async def handle_fazer_reserva(
    phone: str,
    name: Optional[str] = None,
    date_str: Optional[str] = None,
    time_str: Optional[str] = None,
    party_size: Optional[int] = None,
    observation: Optional[str] = None,
) -> str:
    """
    Gera link para o widget Tagme com dados pré-preenchidos.
    A criação da reserva em si acontece no widget (Tagme cuida da disponibilidade).

    Args:
        phone: número do cliente
        name: nome do cliente (se já coletado)
        date_str: data desejada (formato que o widget aceita)
        time_str: horário desejado
        party_size: número de pessoas
        observation: observações especiais (aniversário, etc.)
    """
    # Verifica quais dados ainda faltam
    faltando = []
    if not date_str:   faltando.append("data")
    if not time_str:   faltando.append("horário")
    if not party_size: faltando.append("número de pessoas")

    # Se faltar dados essenciais, perguntar antes de gerar o link
    if faltando:
        faltando_str = " e ".join(faltando)
        return f"Para fazer sua reserva, preciso saber: {faltando_str}. Pode me dizer? 😊"

    # Gera o link com dados pré-preenchidos
    link = build_widget_url(
        date=date_str,
        time=time_str,
        party_size=party_size,
        name=name,
        phone=phone,
        observation=observation,
    )

    # Monta mensagem com resumo + link
    obs_txt = f"\n📝 Obs: _{observation}_" if observation else ""
    return (
        f"Ótimo! Preparei sua reserva com os seguintes dados:\n\n"
        f"📅 {date_str} às {time_str}\n"
        f"👥 {party_size} pessoas{obs_txt}\n\n"
        f"Clique no link abaixo para confirmar — leva menos de 1 minuto:\n"
        f"🔗 {link}\n\n"
        f"Qualquer dúvida, estou aqui! 😊"
    )


# ─── Handler: Cancelar reserva ───────────────────────────────────────────────

async def handle_cancelar_reserva(
    phone: str,
    reservation_id: Optional[str] = None,
) -> str:
    """
    Cancela uma reserva diretamente no Tagme.
    Se o cliente tiver mais de uma reserva ativa, pergunta qual cancelar.

    Args:
        phone: número do cliente
        reservation_id: ID da reserva (se já identificado na conversa)
    """
    async with TagmeClient() as tagme:

        # Busca reservas ativas do cliente
        if not reservation_id:
            all_res = await tagme.get_reservations_by_phone(phone)
            active = [
                r for r in all_res
                if map_status(r.get("status", "")) not in ("cancelada", "no_show")
            ]

            if not active:
                return (
                    "Não encontrei reservas ativas para cancelar no seu número. 🙁\n"
                    "Se precisar de ajuda, é só me chamar!"
                )

            # Se tiver só uma, confirma antes de cancelar
            if len(active) == 1:
                r = active[0]
                dt_raw = r.get("dateTime") or r.get("date", "")
                dt_display = format_datetime_br(dt_raw) if dt_raw else "—"
                pessoas = r.get("partySize") or r.get("party_size") or "—"
                reservation_id = r.get("id") or r.get("reservationId")

                # Cancela direto
                sucesso = await tagme.cancel_reservation(reservation_id)

                if sucesso:
                    return (
                        f"Prontinho! Sua reserva de *{dt_display}* para "
                        f"{pessoas} pessoas foi cancelada com sucesso. ✅\n\n"
                        "Se quiser fazer uma nova reserva, é só me avisar! 😊"
                    )
                else:
                    return (
                        "Tive um problema ao tentar cancelar sua reserva. 😕\n"
                        "Por favor, entre em contato diretamente com o restaurante."
                    )

            # Se tiver mais de uma, lista e pergunta qual
            linhas = ["Encontrei mais de uma reserva ativa. Qual você quer cancelar?\n"]
            for i, r in enumerate(active, 1):
                dt_raw = r.get("dateTime") or r.get("date", "")
                dt_display = format_datetime_br(dt_raw) if dt_raw else "—"
                pessoas = r.get("partySize") or r.get("party_size") or "—"
                linhas.append(f"{i}. {dt_display} — {pessoas} pessoas")
            linhas.append("\nResponda com o número da reserva que deseja cancelar.")
            return "\n".join(linhas)

        # Se já tem o ID, cancela direto
        sucesso = await tagme.cancel_reservation(reservation_id)
        if sucesso:
            return (
                "Reserva cancelada com sucesso! ✅\n\n"
                "Se precisar de mais alguma coisa, estou por aqui! 😊"
            )
        return (
            "Não consegui cancelar a reserva. 😕\n"
            "Por favor, entre em contato diretamente com o restaurante."
        )
