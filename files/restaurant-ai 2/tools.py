"""
Tools executadas pelo agente Claude — todas assíncronas (asyncpg).
"""

from datetime import datetime, timedelta
import database as db
from restaurants import get_restaurant_by_id


async def verificar_disponibilidade(
    restaurant_id: str, data: str, hora: str, pessoas: int
) -> str:
    restaurant = get_restaurant_by_id(restaurant_id)
    if not restaurant:
        return "Restaurante não encontrado."

    try:
        data_obj = datetime.strptime(data, "%d/%m/%Y")
    except ValueError:
        return "Formato de data inválido. Use DD/MM/YYYY."

    try:
        hora_obj = datetime.strptime(hora, "%H:%M")
    except ValueError:
        return "Formato de hora inválido. Use HH:MM (ex: 20:00)."

    reservation_dt = datetime.combine(data_obj.date(), hora_obj.time())
    min_hours = restaurant.get("antecedencia_minima_horas", 2)

    if reservation_dt < datetime.now() + timedelta(hours=min_hours):
        proxima = (datetime.now() + timedelta(hours=min_hours)).strftime("%H:%M")
        return (
            f"Reservas devem ser feitas com pelo menos {min_hours}h de antecedência. "
            f"Para hoje, o horário mais próximo seria {proxima}."
        )

    max_size = restaurant.get("capacidade_maxima_reserva_whatsapp", 8)
    if pessoas > max_size:
        return (
            f"Reservas via WhatsApp são para grupos de até {max_size} pessoas. "
            f"Para grupos maiores, entre em contato diretamente com o restaurante."
        )

    if pessoas < 1:
        return "Número de pessoas inválido."

    CAPACIDADE_POR_SLOT = 40
    ocupado = await db.get_booked_people_at_slot(restaurant_id, data, hora)
    disponivel = CAPACIDADE_POR_SLOT - ocupado

    if disponivel >= pessoas:
        return f"Disponível ✅ — {data} às {hora} para {pessoas} pessoa(s)."

    sugestoes = []
    for delta in [-60, -30, 30, 60]:
        alt = (hora_obj + timedelta(minutes=delta)).strftime("%H:%M")
        alt_ocupado = await db.get_booked_people_at_slot(restaurant_id, data, alt)
        if CAPACIDADE_POR_SLOT - alt_ocupado >= pessoas:
            sugestoes.append(alt)
        if len(sugestoes) == 2:
            break

    msg = f"Horário {hora} do dia {data} não tem disponibilidade para {pessoas} pessoa(s)."
    if sugestoes:
        msg += f" Horários disponíveis próximos: {' ou '.join(sugestoes)}."
    return msg


async def fazer_reserva(
    user_phone: str,
    restaurant_id: str,
    nome: str,
    data: str,
    hora: str,
    pessoas: int,
    observacoes: str = "",
) -> str:
    check = await verificar_disponibilidade(restaurant_id, data, hora, pessoas)
    if "✅" not in check:
        return check

    result = await db.create_reservation(
        user_phone=user_phone,
        restaurant_id=restaurant_id,
        nome=nome,
        data=data,
        hora=hora,
        pessoas=pessoas,
        observacoes=observacoes,
    )

    obs_txt = f"\nObservações: {observacoes}" if observacoes else ""
    return (
        f"Reserva confirmada ✅\n"
        f"Código: *{result['id']}*\n"
        f"Nome: {nome}\n"
        f"Data: {data} às {hora}\n"
        f"Pessoas: {pessoas}{obs_txt}\n\n"
        f"Guarde o código para consultas ou cancelamentos."
    )


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
