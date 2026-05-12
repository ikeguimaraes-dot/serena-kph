"""
agent_tagme_integration.py
Exemplo de como integrar os handlers Tagme no agent principal da Serena.

Este arquivo NÃO substitui o agent atual — mostra o padrão de
detecção de intenção e chamada dos handlers. Adaptar conforme
a estrutura do agent existente.

Intenções detectadas:
  - CONSULTAR_RESERVA
  - FAZER_RESERVA
  - CANCELAR_RESERVA
"""

import re
from datetime import date
from typing import Optional

from tagme_handlers import (
    handle_consultar_reserva,
    handle_fazer_reserva,
    handle_cancelar_reserva,
)


# ─── Detecção de intenção (regex simples — adaptar ao LLM do agent) ──────────

INTENT_CONSULTAR = re.compile(
    r"(minha reserva|tenho reserva|verificar reserva|checar reserva"
    r"|tem reserva|ver minha reserva|confirmar reserva|reserva hoje"
    r"|reserva amanhã|minhas reservas)",
    re.IGNORECASE,
)

INTENT_FAZER = re.compile(
    r"(quero reservar|fazer uma reserva|quero uma mesa|reservar mesa"
    r"|fazer reserva|nova reserva|agendar|marcar mesa|reservar)",
    re.IGNORECASE,
)

INTENT_CANCELAR = re.compile(
    r"(cancelar reserva|quero cancelar|cancela minha|desmarcar"
    r"|cancela a reserva|não vou mais|desistir da reserva)",
    re.IGNORECASE,
)


def detect_intent(message: str) -> Optional[str]:
    """Detecta intenção da mensagem. Retorna None se não reconhecer."""
    if INTENT_CANCELAR.search(message):  # cancelar antes de fazer (evitar falso positivo)
        return "CANCELAR_RESERVA"
    if INTENT_FAZER.search(message):
        return "FAZER_RESERVA"
    if INTENT_CONSULTAR.search(message):
        return "CONSULTAR_RESERVA"
    return None


# ─── Roteador de intenções ────────────────────────────────────────────────────

async def route_tagme_intent(
    message: str,
    phone: str,
    session: dict,  # dict de contexto da conversa (nome, dados coletados, etc.)
) -> Optional[str]:
    """
    Tenta resolver a mensagem como intenção de reserva Tagme.
    Retorna a resposta em texto, ou None se não for intenção de reserva.

    Args:
        message: texto recebido do cliente
        phone: número do WhatsApp do cliente
        session: contexto da sessão (dados já coletados na conversa)
    """
    intent = detect_intent(message)

    if intent is None:
        return None  # não é intenção de reserva — continua no fluxo normal

    if intent == "CONSULTAR_RESERVA":
        # Detecta se é "hoje" ou "amanhã"
        filter_date = None
        if "hoje" in message.lower():
            filter_date = date.today()
        return await handle_consultar_reserva(phone, filter_date=filter_date)

    if intent == "FAZER_RESERVA":
        return await handle_fazer_reserva(
            phone=phone,
            name=session.get("name"),
            date_str=session.get("reservation_date"),
            time_str=session.get("reservation_time"),
            party_size=session.get("party_size"),
            observation=session.get("observation"),
        )

    if intent == "CANCELAR_RESERVA":
        return await handle_cancelar_reserva(
            phone=phone,
            reservation_id=session.get("reservation_id"),
        )

    return None


# ─── Exemplo de uso no loop do agent ─────────────────────────────────────────

"""
# No agent principal (pseudocódigo):

async def process_message(message: str, phone: str, session: dict):
    # 1. Tenta intenção Tagme primeiro
    response = await route_tagme_intent(message, phone, session)
    if response:
        return response

    # 2. Segue para o fluxo normal do agent (LLM, FAQ, etc.)
    return await llm_response(message, session)
"""


# ─── Variáveis de ambiente necessárias (.env) ─────────────────────────────────

"""
Adicionar ao .env do projeto:

TAGME_BASE_URL=https://api.tagme.com.br           # confirmar com Tagme
TAGME_API_KEY=sua_api_key_aqui
TAGME_PARTNER_APP_ID=seu_partner_app_id            # confirmar: d37 ou d38
TAGME_WIDGET_URL=https://widget.tagme.com.br/...   # URL do widget Madonna Cucina
"""
