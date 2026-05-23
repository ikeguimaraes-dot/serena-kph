"""Testa 3 cenários da Serena sem tocar no DB (tools stubadas)."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

import database as db
from agent import RestaurantAgent, _build_prompt

SCENARIOS = [
    ("CENARIO 1 — Reserva nova (deve mandar link Tagme)",
     "Quero fazer uma reserva",
     "sem tool call, resposta deve conter o link do widget Tagme"),
    ("CENARIO 2 — Consulta de reserva (deve escalar)",
     "Qual minha reserva pro sábado?",
     "deve chamar transferir_para_humano"),
    ("CENARIO 3 — Cancelamento (deve escalar)",
     "Quero cancelar minha reserva",
     "deve chamar transferir_para_humano"),
]

WIDGET_URL = "reservation-widget.tagme.com.br/reservation/schedule/691377229337bdf1ad07625f"

calls_made: list[tuple[str, dict]] = []


async def spy_tool(self, name, inputs, user_phone, rid):
    """Stub que registra chamadas e devolve respostas canned."""
    calls_made.append((name, dict(inputs)))
    if name == "verificar_disponibilidade":
        return f"Disponivel ✅ — {inputs.get('data')} as {inputs.get('hora')} para {inputs.get('pessoas')} pessoa(s). (STUB)"
    if name == "fazer_reserva":
        return f"Reserva confirmada ✅\nCodigo: *TESTE123*\nNome: {inputs.get('nome')}\nData: {inputs.get('data')} as {inputs.get('hora')}\nPessoas: {inputs.get('pessoas')}. (STUB)"
    if name == "consultar_reservas":
        return "Nenhuma reserva ativa encontrada. (STUB)"
    if name == "cancelar_reserva":
        return "Reserva cancelada. (STUB)"
    if name == "transferir_para_humano":
        return f"__HANDOFF__:{inputs.get('motivo','sem motivo')}"
    if name == "update_contact":
        return "Contato atualizado. (STUB)"
    return f"tool desconhecida: {name}"


RestaurantAgent._tool = spy_tool


async def run_scenario(label: str, message: str, expectativa: str, restaurant: dict):
    global calls_made
    calls_made = []
    print("\n" + "=" * 74)
    print(label)
    print(f"Expectativa: {expectativa}")
    print("=" * 74)
    print(f"Cliente: {message}")

    agent = RestaurantAgent()
    response = await agent._run(
        system=_build_prompt(restaurant),
        messages=[{"role": "user", "content": message}],
        user_phone="+5500000000001",
        rid=restaurant["id"],
    )

    print(f"\nSerena: {response}")
    if calls_made:
        print(f"\nTools chamadas:")
        for name, inp in calls_made:
            print(f"  🔧 {name}({inp})")
    else:
        print("\nTools chamadas: NENHUMA")

    # veredito automatico. transferir_para_humano é interceptado em _run() e
    # retorna "__HANDOFF__:motivo" antes de chegar no _tool() — por isso
    # conferimos tanto calls_made quanto a string do response.
    names = [n for n, _ in calls_made]
    escalou = (response or "").startswith("__HANDOFF__")
    print("\nVeredito:")
    if "CENARIO 1" in label:
        has_link = WIDGET_URL in (response or "")
        called_reserva_tool = any(n in ("fazer_reserva","verificar_disponibilidade") for n in names)
        if has_link and not escalou and not called_reserva_tool:
            print("  ✅ PASS — link Tagme enviado, sem tool de reserva")
        elif called_reserva_tool:
            print(f"  ❌ FAIL — chamou tool desligada: {names}")
        elif escalou:
            print("  ❌ FAIL — escalou em vez de mandar link")
        elif not has_link:
            print(f"  ❌ FAIL — resposta NAO contém URL do widget Tagme. response: {(response or '')[:200]}")
    elif "CENARIO 2" in label:
        if escalou:
            print("  ✅ PASS — escalou consulta de reserva pra humano")
        elif "consultar_reservas" in names:
            print(f"  ❌ FAIL — usou tool local consultar_reservas em vez de escalar: {names}")
        else:
            print(f"  ⚠ INDEFINIDO — response: {(response or '')[:200]}")
    elif "CENARIO 3" in label:
        if escalou:
            print("  ✅ PASS — escalou cancelamento pra humano")
        elif "cancelar_reserva" in names:
            print(f"  ❌ FAIL — usou tool local cancelar_reserva em vez de escalar: {names}")
        else:
            print(f"  ⚠ INDEFINIDO — response: {(response or '')[:200]}")


async def main():
    await db.init_db()
    try:
        restaurant = await db.get_restaurant_by_whatsapp("+5511988302367")
        if not restaurant:
            raise RuntimeError("Restaurante madonna_cucina nao encontrado")
        print(f"Restaurante carregado: {restaurant['nome']} ({restaurant['id']})")

        for label, msg, exp in SCENARIOS:
            await run_scenario(label, msg, exp, restaurant)

    finally:
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
