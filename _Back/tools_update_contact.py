# ─── tools.py — adicionar à lista TOOLS existente ────────────────────────────

UPDATE_CONTACT_TOOL = {
    "name": "update_contact",
    "description": (
        "Atualiza informações de um contato existente no CRM. "
        "Use para registrar preferências, restrições alimentares, notas, "
        "mudar tier ou mover no kanban. Sempre confirme o contact_id antes de chamar."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "contact_id": {
                "type": "integer",
                "description": "ID numérico do contato a ser atualizado"
            },
            "updates": {
                "type": "object",
                "description": "Campos a atualizar (apenas os que mudaram)",
                "properties": {
                    "nome":                  {"type": "string"},
                    "telefone":              {"type": "string"},
                    "email":                 {"type": "string"},
                    "preferencias":          {"type": "string", "description": "Preferências gastronômicas"},
                    "restricoes_alimentares":{"type": "string"},
                    "notas_internas":        {"type": "string"},
                    "tier": {
                        "type": "string",
                        "enum": ["vip", "regular", "new", "inactive"]
                    },
                    "estagio_kanban": {
                        "type": "string",
                        "enum": ["lead", "primeiro_contato", "ativo", "fidelizado", "inativo"]
                    }
                }
            }
        },
        "required": ["contact_id", "updates"]
    }
}

# Adicione UPDATE_CONTACT_TOOL à lista TOOLS:
# TOOLS = [...tools_existentes..., UPDATE_CONTACT_TOOL]


# ─── agent.py — adicionar no handle_tool_call / process_tool_use ──────────────
# Dentro do bloco if/elif que processa tool calls:

"""
elif tool_name == "update_contact":
    contact_id = tool_input.get("contact_id")
    updates    = tool_input.get("updates", {})

    if not contact_id:
        result = {"error": "contact_id é obrigatório"}
    elif not updates:
        result = {"error": "Nenhum campo para atualizar"}
    else:
        updated = await db.update_contact(contact_id, updates)
        if updated:
            result = {
                "success": True,
                "contact": updated,
                "message": f"Contato #{contact_id} atualizado com sucesso"
            }
        else:
            result = {"error": f"Contato #{contact_id} não encontrado"}
"""

# ── Exemplo de uso pelo agente ─────────────────────────────────────────────────
# Usuário: "O João tem intolerância a lactose, anota aí"
# Agente chama:
# {
#   "name": "update_contact",
#   "input": {
#     "contact_id": 42,
#     "updates": { "restricoes_alimentares": "Intolerância a lactose" }
#   }
# }
