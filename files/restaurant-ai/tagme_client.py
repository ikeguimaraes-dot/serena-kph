"""
tagme_client.py
Cliente assíncrono para a ReservationPartnersAPI da Tagme.

Endpoints cobertos:
  GET  /reservations/by-phone/{phone}  -> consultar reservas
  DELETE /reservations/{id}            -> cancelar reserva
  PUT  /reservations/{id}/confirm      -> confirmar reserva

Pendência futura (Caminho B):
  - POST /reservations                 -> criar reserva (solicitar acesso à Tagme)
  - GET  /availability                 -> checar disponibilidade (solicitar acesso)
"""

import httpx
import re
from datetime import datetime
from enum import Enum
from typing import Optional
import os


# ─── Configuração ───────────────────────────────────────────────────────────

TAGME_BASE_URL = os.getenv("TAGME_BASE_URL", "https://api.tagme.com.br/v1/partners")
TAGME_WIDGET_URL = os.getenv("TAGME_WIDGET_URL", "https://usetag.me/madonnacucina")


def _build_headers() -> dict:
    """Lê env vars em runtime — garante que TAGME_API_KEY e TAGME_PARTNER_APP_ID
    estejam presentes mesmo que o módulo seja importado antes das envs serem setadas."""
    return {
        "Authorization": f"Bearer {os.environ.get('TAGME_API_KEY', '')}",
        "Content-Type": "application/json",
        "X-Partner-App-Id": os.environ.get("TAGME_PARTNER_APP_ID", ""),
    }


# ─── Mapeamento de status ────────────────────────────────────────────────────

class StatusTagme(str, Enum):
    NEW = "New"
    CONFIRMED = "Confirmed"
    CANCELLED = "Cancelled"
    SEATED = "Seated"
    NO_SHOW = "NoShow"
    WAITING = "Waiting"


STATUS_MAP: dict[str, str] = {
    StatusTagme.NEW:       "pendente",
    StatusTagme.CONFIRMED: "confirmada",
    StatusTagme.CANCELLED: "cancelada",
    StatusTagme.SEATED:    "sentada",
    StatusTagme.NO_SHOW:   "no_show",
    StatusTagme.WAITING:   "lista_espera",
}


def map_status(tagme_status: str) -> str:
    """Converte status Tagme → status interno do DB. Case-insensitive."""
    # API real devolve lowercase ("confirmed"), enum usa Title ("Confirmed")
    normalised = tagme_status.strip().lower().capitalize()
    return STATUS_MAP.get(tagme_status, STATUS_MAP.get(normalised, "desconhecido"))


# ─── Normalização de telefone ────────────────────────────────────────────────

def normalize_phone(raw: str) -> str:
    """
    Normaliza telefone para o formato que a Tagme aceita.
    Remove DDI 55 se presente e mantém apenas dígitos.
    Exemplos:
      '+5511999998888' -> '11999998888'
      '5511999998888'  -> '11999998888'
      '11 99999-8888'  -> '11999998888'
    """
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("55") and len(digits) >= 12:
        digits = digits[2:]
    return digits


def phone_to_tagme(raw: str) -> str:
    """
    Formata o número para o padrão que a API da Tagme usa.
    Ajustar aqui se a Tagme precisar do DDI ou outro formato.
    """
    return normalize_phone(raw)


# ─── Formatação de data para resposta ao cliente ─────────────────────────────

def format_datetime_br(iso_datetime: str) -> str:
    """
    Converte datetime ISO (ex: '2026-04-23T19:30:00') para exibição em pt-BR.
    Retorna ex: 'quinta-feira, 23 de abril às 19h30'
    """
    try:
        dt = datetime.fromisoformat(iso_datetime.replace("Z", "+00:00"))
        dias_semana = ["segunda-feira", "terça-feira", "quarta-feira",
                       "quinta-feira", "sexta-feira", "sábado", "domingo"]
        meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                 "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
        dia_semana = dias_semana[dt.weekday()]
        mes = meses[dt.month - 1]
        return f"{dia_semana}, {dt.day} de {mes} às {dt.hour:02d}h{dt.minute:02d}"
    except Exception:
        return iso_datetime


# ─── Geração do link para o widget Tagme ─────────────────────────────────────

def build_widget_url(
    date: Optional[str] = None,
    time: Optional[str] = None,
    party_size: Optional[int] = None,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    observation: Optional[str] = None,
) -> str:
    """
    Monta link do widget Tagme com parâmetros pré-preenchidos.
    A Tagme aceita query params para pré-preencher o formulário.
    Ajustar os nomes dos params conforme documentação do widget.
    """
    params = {}
    if date:        params["date"] = date          # formato esperado pelo widget
    if time:        params["time"] = time
    if party_size:  params["partySize"] = party_size
    if name:        params["name"] = name
    if phone:       params["phone"] = normalize_phone(phone)
    if observation: params["observation"] = observation

    if not params:
        return TAGME_WIDGET_URL

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{TAGME_WIDGET_URL}?{query}"


# ─── Cliente Tagme ────────────────────────────────────────────────────────────

class TagmeClient:
    """Cliente assíncrono para a ReservationPartnersAPI da Tagme."""

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=TAGME_BASE_URL,
            headers=_build_headers(),
            timeout=10.0,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def get_reservations_by_phone(self, phone: str) -> list[dict]:
        """
        Busca todas as reservas vinculadas a um número de telefone.
        Retorna lista vazia se não encontrar.
        """
        normalized = phone_to_tagme(phone)
        resp = await self._client.get(f"/reservations/by-phone/{normalized}")

        if resp.status_code == 404:
            return []
        resp.raise_for_status()

        payload = resp.json()
        # Formato real da API: {"ok": true, "data": [...]}
        if isinstance(payload, dict):
            reservations = payload.get("data", payload.get("reservations", []))
        elif isinstance(payload, list):
            reservations = payload
        else:
            reservations = []

        return reservations

    async def cancel_reservation(self, reservation_id: str) -> bool:
        """
        Cancela uma reserva diretamente no Tagme.
        Retorna True se bem-sucedido.
        """
        resp = await self._client.delete(f"/reservations/{reservation_id}")
        return resp.status_code in (200, 204)

    async def confirm_reservation(self, reservation_id: str) -> bool:
        """
        Confirma uma reserva (PUT confirm).
        Retorna True se bem-sucedido.
        """
        resp = await self._client.put(f"/reservations/{reservation_id}/confirm")
        return resp.status_code in (200, 204)


# ─── Formatação de reserva para resposta da Serena ───────────────────────────

def format_reservation(r: dict) -> str:
    """Converte objeto de reserva da API Tagme em texto legível para a Serena."""
    customer = r.get("customer") or {}
    nome = f"{customer.get('name', '')} {customer.get('lastName', '')}".strip() or "—"
    return (
        f"Reserva encontrada:\n"
        f"• Nome: {nome}\n"
        f"• Data: {r.get('reservationDay', '—')}\n"
        f"• Horário: {r.get('reservationTime', '—')}\n"
        f"• Pessoas: {r.get('partySize', '—')}\n"
        f"• Status: {map_status(r.get('status', ''))}\n"
        f"• Obs: {r.get('note', '—')}"
    )


# ─── Instância global (opcional, para uso no agent) ──────────────────────────

tagme = TagmeClient()
