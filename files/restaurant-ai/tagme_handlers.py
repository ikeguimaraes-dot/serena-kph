from datetime import datetime, date
from typing import Optional
import httpx
from tagme_client import TagmeClient, map_status, format_datetime_br, format_reservation, build_widget_url


async def handle_consultar_reserva(phone: str, filter_date=None) -> str:
    async with TagmeClient() as tagme:
        reservations = await tagme.get_reservations_by_phone(phone)
    if not reservations:
        return "Não encontrei nenhuma reserva vinculada ao seu número.\n\nSe precisar fazer uma reserva, é só me dizer a data, horário e número de pessoas!"
    if filter_date:
        def _match_date(r):
            try:
                # reservationDay: "2026-04-23" ou "23/04/2026"
                raw = r.get("reservationDay", "")
                try:
                    d = datetime.strptime(raw, "%Y-%m-%d").date()
                except ValueError:
                    d = datetime.strptime(raw, "%d/%m/%Y").date()
                return d == filter_date
            except Exception:
                return False
        reservations = [r for r in reservations if _match_date(r)]
    active = [r for r in reservations if map_status(r.get("status", "")) not in ("cancelada", "no_show")]
    if not active:
        periodo = "hoje" if filter_date == date.today() else "neste período"
        return f"Não encontrei reservas ativas {periodo} para o seu número.\n\nQuer fazer uma nova reserva? Me diga a data, horário e quantas pessoas!"
    linhas = ["Encontrei as seguintes reservas para você:\n"]
    for r in active:
        dt_display = format_datetime_br(r.get("reservationDay", "")) or r.get("reservationTime", "—")
        pessoas = r.get("partySize", "—")
        status = map_status(r.get("status", ""))
        linha = f"📅 *{dt_display}*\n👥 {pessoas} pessoas | Status: {status}"
        obs = r.get("note") or ""
        if obs:
            linha += f"\n📝 {obs}"
        linhas.append(linha)
    linhas.append("\nPrecisa cancelar ou alterar? É só me avisar!")
    return "\n\n".join(linhas)


async def handle_fazer_reserva(phone, name=None, date_str=None, time_str=None, party_size=None, observation=None) -> str:
    faltando = []
    if not date_str: faltando.append("data")
    if not time_str: faltando.append("horário")
    if not party_size: faltando.append("número de pessoas")
    if faltando:
        return f"Para fazer sua reserva, preciso saber: {' e '.join(faltando)}. Pode me dizer?"
    link = build_widget_url(date=date_str, time=time_str, party_size=party_size, name=name, phone=phone, observation=observation)
    obs_txt = f"\n📝 Obs: _{observation}_" if observation else ""
    return (
        f"Preparei os dados da sua reserva:\n\n"
        f"📅 {date_str} às {time_str}\n"
        f"👥 {party_size} pessoas{obs_txt}\n\n"
        f"Confirme pelo link:\n🔗 {link}"
    )


async def handle_cancelar_reserva(phone: str, reservation_id: Optional[str] = None) -> str:
    async with TagmeClient() as tagme:
        if not reservation_id:
            all_res = await tagme.get_reservations_by_phone(phone)
            active = [r for r in all_res if map_status(r.get("status", "")) not in ("cancelada", "no_show")]
            if not active:
                return "Não encontrei reservas ativas para cancelar no seu número."
            if len(active) == 1:
                r = active[0]
                dt_display = format_datetime_br(r.get("reservationDay", "")) or "—"
                pessoas = r.get("partySize", "—")
                rid = r.get("_id")
                if not rid:
                    return "Não consegui identificar o ID da reserva. Entre em contato com o restaurante."
                try:
                    sucesso = await tagme.cancel_reservation(rid)
                except httpx.TimeoutException:
                    return "Não foi possível cancelar sua reserva no momento — o sistema de reservas está demorando para responder. Tente novamente em instantes ou chame nossa equipe."
                if sucesso:
                    return f"Reserva de *{dt_display}* para {pessoas} pessoas cancelada. ✅\n\nSe quiser fazer uma nova reserva, é só me avisar!"
                return "Tive um problema ao cancelar. Por favor, entre em contato com o restaurante."
            # Mais de uma reserva ativa
            linhas = ["Encontrei mais de uma reserva ativa. Qual você quer cancelar?\n"]
            for i, r in enumerate(active, 1):
                dt_display = format_datetime_br(r.get("reservationDay", "")) or "—"
                pessoas = r.get("partySize", "—")
                linhas.append(f"{i}. {dt_display} — {pessoas} pessoas")
            linhas.append("\nResponda com o número da reserva que deseja cancelar.")
            return "\n".join(linhas)
        # reservation_id fornecido diretamente
        try:
            sucesso = await tagme.cancel_reservation(reservation_id)
        except httpx.TimeoutException:
            return "Não foi possível cancelar sua reserva no momento — o sistema de reservas está demorando para responder. Tente novamente em instantes ou chame nossa equipe."
        return "Reserva cancelada com sucesso! ✅" if sucesso else "Não consegui cancelar. Entre em contato com o restaurante."
