"""Módulo: schema das tools e dispatcher."""

from datetime import datetime
import tools as tool_fns
import tagme_handlers
import database as db


TOOLS = [
    {"name":"consultar_reserva","description":"Consulta reserva existente pelo nome do titular ou telefone no sistema Tagme. Use quando o cliente perguntar sobre reserva já feita.",
     "input_schema":{"type":"object","properties":{
         "nome":{"type":"string","description":"Nome do titular da reserva"},
         "data":{"type":"string","description":"Data da reserva (DD/MM/AAAA)"},
         "telefone":{"type":"string","description":"Telefone do cliente (opcional)"},
     },"required":["nome"]}},
    {"name":"cancelar_reserva","description":"Cancela reserva existente no Tagme. Use apenas quando o cliente confirmar explicitamente que quer cancelar.",
     "input_schema":{"type":"object","properties":{
         "reserva_id":{"type":"string","description":"ID da reserva a cancelar"},
         "nome":{"type":"string","description":"Nome do titular da reserva"},
         "motivo":{"type":"string","description":"Motivo do cancelamento (opcional)"},
     },"required":["nome"]}},
    {"name":"transferir_para_humano","description":"Transfere para atendente. Use quando cliente pedir, reclamação grave, ou situação que você não resolve.",
     "input_schema":{"type":"object","properties":{"motivo":{"type":"string"}},"required":["motivo"]}},
    {"name":"update_contact","description":(
        "Salva silenciosamente dados do cliente no CRM quando surgirem naturalmente na conversa — "
        "nome, ocasião (aniversário, corporativo, romântico, confraternização, amigos, familiar), "
        "restrição alimentar (vegetariano, vegano, sem glúten, sem lactose, alergia a X, halal, kosher), "
        "email, data de nascimento, canal de entrada (Instagram, Google, indicação), ou notas relevantes. "
        "NUNCA peça esses dados como formulário. Só chame quando o cliente mencionar de forma espontânea. "
        "Passe só os campos novos — campos omitidos não apagam o existente. Listas são mescladas, não substituídas. "
        "Não confirme pro cliente que salvou."
     ),
     "input_schema":{"type":"object","properties":{
        "nome":{"type":"string"}, "sobrenome":{"type":"string"},
        "email":{"type":"string"},
        "data_nascimento":{"type":"string","description":"ISO YYYY-MM-DD"},
        "ocasiao":{"type":"array","items":{"type":"string"}},
        "restricoes_alimentares":{"type":"array","items":{"type":"string"}},
        "canal_entrada":{"type":"string"},
        "tags":{"type":"array","items":{"type":"string"}},
        "notas":{"type":"string"}
     },"required":[]}},
    {"name":"lookup_menu","description":(
        "Busca pratos ou categorias no cardápio quando o cliente perguntar sobre comida, "
        "bebida, opções vegetarianas, sem glúten, ou preço de item específico."
     ),
     "input_schema":{"type":"object","properties":{
        "termo":{"type":"string","description":"Nome do prato, categoria ou restrição alimentar"}
     },"required":["termo"]}},
    {"name":"check_business_hours","description":(
        "Verifica se o restaurante está aberto em uma data específica, considerando datas especiais."
     ),
     "input_schema":{"type":"object","properties":{
        "data":{"type":"string","description":"Data no formato YYYY-MM-DD ou descrição como 'hoje', 'amanhã'"}
     },"required":["data"]}},
    {"name":"get_reservation_link","description":(
        "Gera link do Tagme pré-preenchido com data, horário e número de pessoas."
     ),
     "input_schema":{"type":"object","properties":{
        "pessoas":{"type":"integer","description":"Número de pessoas"},
        "data":{"type":"string","description":"Data desejada (YYYY-MM-DD ou texto)"},
        "horario":{"type":"string","description":"Horário desejado (ex: '20:00', '21h30')"}
     },"required":[]}},
    {"name":"lookup_contact_history","description":(
        "Consulta histórico de visitas, reservas anteriores e preferências do cliente atual."
     ),
     "input_schema":{"type":"object","properties":{},"required":[]}},
    {"name":"verificar_disponibilidade","description":(
        "Verifica horários disponíveis na agenda do restaurante para uma data e número de pessoas. "
        "Use SEMPRE antes de fazer_reserva. Retorna os turnos com vagas e seus IDs."
     ),
     "input_schema":{"type":"object","properties":{
        "data":{"type":"string","description":"Data desejada (YYYY-MM-DD, 'amanhã', 'sexta', etc.)"},
        "pessoas":{"type":"integer","description":"Número de pessoas"}
     },"required":["data","pessoas"]}},
    {"name":"fazer_reserva","description":(
        "Cria uma reserva na agenda própria. "
        "Só chame após verificar_disponibilidade E confirmar data, horário e nome com o cliente."
     ),
     "input_schema":{"type":"object","properties":{
        "nome":{"type":"string","description":"Nome completo do titular"},
        "data":{"type":"string","description":"Data da reserva (YYYY-MM-DD)"},
        "turno_id":{"type":"string","description":"UUID do turno retornado por verificar_disponibilidade"},
        "hora_inicio":{"type":"string","description":"Horário do turno (HH:MM)"},
        "pessoas":{"type":"integer","description":"Número de pessoas"},
        "observacoes":{"type":"string","description":"Pedidos especiais (opcional)"},
        "email":{"type":"string","description":"Email do cliente (opcional)"}
     },"required":["nome","data","turno_id","hora_inicio","pessoas"]}},
    {"name":"gerar_proposta","description":(
        "Gera e envia proposta comercial para eventos especiais, "
        "jantares corporativos ou celebrações com 4+ pessoas. "
        "Use quando lead for quente e pedir detalhes de evento. "
        "Cria OS automaticamente e move lead para etapa 'proposta' no CRM."
     ),
     "input_schema":{"type":"object","properties":{
        "nome":{"type":"string"},
        "tipo_evento":{"type":"string","description":"Ex: jantar corporativo, aniversário, confraternização"},
        "pessoas":{"type":"integer"},
        "data":{"type":"string","description":"Data do evento (YYYY-MM-DD ou texto)"},
        "ocasiao":{"type":"string","description":"Ocasião especial (opcional)"},
        "valor_por_pessoa":{"type":"number","description":"Valor por pessoa em R$ (default 300)"},
        "observacoes":{"type":"string"}
     },"required":["nome","tipo_evento","pessoas"]}},
]


async def execute_tool(name: str, inputs: dict, user_phone: str, rid: str) -> str:
    """Dispatcher de tools — mapeia nome → função. Captura exceções graciosamente."""
    try:
        if name == "consultar_reserva":
            phone = inputs.get("telefone") or user_phone
            reservas = await db.get_reservas_por_phone(rid, phone)
            if not reservas:
                return "Nenhuma reserva encontrada para este contato na agenda."
            lines = []
            for r in reservas:
                lines.append(f"Reserva {r['id']}: {r['data']} às {r['hora_inicio']} — {r['posicoes']} pessoa(s) — status: {r['status']}")
            return "\n".join(lines)

        if name == "cancelar_reserva":
            reserva_id = inputs.get("reserva_id")
            if not reserva_id:
                return "Por favor, informe o código da reserva para cancelar."
            success = await db.cancelar_reserva(reserva_id, rid)
            if success:
                return f"Reserva *{reserva_id[:8].upper()}* cancelada com sucesso ✅."
            return "Não encontrei essa reserva ou ela já foi cancelada."

        if name == "transferir_para_humano":
            return await tool_fns.transferir_para_humano(inputs["motivo"])

        if name == "update_contact":
            return await tool_fns.update_contact(
                user_phone=user_phone,
                nome=inputs.get("nome"),
                sobrenome=inputs.get("sobrenome"),
                email=inputs.get("email"),
                data_nascimento=inputs.get("data_nascimento"),
                ocasiao=inputs.get("ocasiao"),
                restricoes_alimentares=inputs.get("restricoes_alimentares"),
                canal_entrada=inputs.get("canal_entrada"),
                tags=inputs.get("tags"),
                notas=inputs.get("notas"),
            )

        if name == "lookup_menu":
            return await tool_fns.lookup_menu(rid, inputs.get("termo", ""))

        if name == "check_business_hours":
            return await tool_fns.check_business_hours(rid, inputs.get("data", ""))

        if name == "get_reservation_link":
            return tool_fns.get_reservation_link(
                pessoas=inputs.get("pessoas"),
                data=inputs.get("data"),
                horario=inputs.get("horario"),
            )

        if name == "lookup_contact_history":
            return await tool_fns.lookup_contact_history(user_phone, rid)

        if name == "verificar_disponibilidade":
            return await tool_fns.verificar_disponibilidade(
                rid,
                inputs.get("data", ""),
                int(inputs.get("pessoas", 2)),
            )

        if name == "fazer_reserva":
            return await tool_fns.fazer_reserva(
                restaurant_id=rid,
                user_phone=user_phone,
                nome=inputs["nome"],
                data=inputs["data"],
                turno_id=inputs["turno_id"],
                hora_inicio=inputs["hora_inicio"],
                pessoas=int(inputs["pessoas"]),
                observacoes=inputs.get("observacoes"),
                email=inputs.get("email"),
            )

        if name == "gerar_proposta":
            return await tool_fns.gerar_proposta(
                restaurant_id=rid,
                user_phone=user_phone,
                nome=inputs["nome"],
                tipo_evento=inputs["tipo_evento"],
                pessoas=int(inputs["pessoas"]),
                data=inputs.get("data"),
                ocasiao=inputs.get("ocasiao"),
                valor_por_pessoa=float(inputs.get("valor_por_pessoa", 300.0)),
                observacoes=inputs.get("observacoes"),
            )

        return f"Tool desconhecida: {name}"
    except Exception as e:
        return f"Erro: {e}"
