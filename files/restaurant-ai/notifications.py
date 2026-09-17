"""
Notificações para a equipe.
- Discord webhook (primário): sem restrição de janela de 24h. Requer DISCORD_HANDOFF_WEBHOOK_URL.
- Twilio WhatsApp (secundário): só funciona dentro de janela de 24h ativa. Requer TWILIO_*.
Ambos best-effort: falha não quebra o handoff.
"""

import os
import json
import re
import urllib.request
from dataclasses import dataclass

_twilio_client = None


@dataclass
class NotificationResult:
    state: str
    provider_message_sid: str | None = None
    provider_status: str | None = None
    reason: str | None = None

    def __bool__(self):
        return self.state == "accepted"


def whatsapp_address(number: str) -> str:
    value = re.sub(r"[\s()\-]", "", (number or "").removeprefix("whatsapp:"))
    if not re.fullmatch(r"\+?[1-9][0-9]{7,14}", value):
        raise ValueError("Número WhatsApp ausente ou inválido")
    return "whatsapp:+" + value.lstrip("+")


def accepted_message(message):
    sid = getattr(message, "sid", None)
    status = getattr(message, "status", None)
    if not isinstance(sid, str) or not re.fullmatch(r"SM[0-9a-fA-F]{32}", sid):
        raise RuntimeError("Twilio não retornou SID válido; aceitação incerta")
    if status in ("failed", "undelivered", "canceled"):
        raise RuntimeError("Twilio rejeitou a mensagem")
    return {"provider_message_sid": sid, "provider_status": status}

def _client():
    global _twilio_client
    if _twilio_client is not None:
        return _twilio_client
    try:
        from twilio.rest import Client
        sid = os.environ.get("TWILIO_ACCOUNT_SID")
        token = os.environ.get("TWILIO_AUTH_TOKEN")
        if not sid or not token:
            return None
        _twilio_client = Client(sid, token)
        return _twilio_client
    except Exception:
        return None

def notify_handoff_discord(
    restaurant_nome: str,
    customer_phone: str,
    motivo: str,
    resumo: str = "",
) -> bool:
    """Retorna se o Discord aceitou o alerta; não confirma leitura pela equipe."""
    discord_url = os.environ.get("DISCORD_HANDOFF_WEBHOOK_URL")
    if not discord_url:
        print(f"[HANDOFF] Discord não configurado — {restaurant_nome} | {customer_phone}")
        return False
    try:
        partes = [
            "🚨 **Atendimento humano solicitado**",
            f"**Restaurante:** {restaurant_nome}",
            f"**Cliente:** {customer_phone}",
            f"**Motivo:** {motivo}",
        ]
        if resumo:
            partes.append(f"**Contexto:** {resumo[:300]}")
        partes.append("<https://madonna-painel.vercel.app>")
        payload = json.dumps({"content": "\n".join(partes)}).encode()
        req = urllib.request.Request(
            discord_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Serena/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
        print(f"[HANDOFF] Discord aceitou alerta — {restaurant_nome} | {customer_phone}")
        return True
    except Exception as e:
        print(f"[HANDOFF] Discord falhou (best-effort): {e!r}")
        return False

def notify_handoff(
    team_whatsapp: str,
    restaurant_nome: str,
    customer_phone: str,
    motivo: str,
    resumo: str,
):
    """Twilio WhatsApp — reservado para quando houver template Meta aprovado.
    Fora da janela de 24h retorna error 63016 (undelivered). Não usar para notificações
    de equipe enquanto não houver content_sid aprovado.
    """
    # This legacy helper has no tenant sender or approved template contract.
    # It has no production callers; refuse rather than route via a global sender.
    return NotificationResult("skipped", reason="approved_tenant_template_not_configured")


def notify_escalacao_gerente(
    from_number: str,
    gerente_whatsapp: str,
    customer_phone: str,
    motivo: str,
) -> NotificationResult:
    """Rota clínica: solicita envio ao gerente da unidade, sem prometer entrega.

    Texto livre exige janela de 24h aberta pelo gerente com o número da clínica.
    Ainda falta um template Utility aprovado para alertar fora dessa janela.
    True significa apenas aceitação pela API Twilio; entrega exige status posterior.
    O handoff permanece no painel e o Discord é tentado independentemente.
    """
    client = _client()
    if not client:
        print("[ESCALACAO] Twilio não configurado; envio não solicitado")
        return NotificationResult("skipped", reason="provider_unavailable")

    try:
        sender = whatsapp_address(from_number)
        recipient = whatsapp_address(gerente_whatsapp)
        if sender == recipient:
            return NotificationResult("skipped", reason="sender_equals_recipient")
        clean_motivo = motivo.replace("[LARA]:", "").replace("[LARA]", "").strip()
        msg = client.messages.create(
            from_=sender,
            to=recipient,
            body=(
                "🔴 Atenção — ação necessária\n\n"
                f"Paciente: {customer_phone}\n"
                f"Motivo: {clean_motivo}"
            ),
        )
        observed = accepted_message(msg)
        print(f"[ESCALACAO] Twilio aceitou solicitação sid={msg.sid} status={msg.status}; entrega não confirmada")
        return NotificationResult("accepted", **observed)
    except Exception as e:
        print(f"[ESCALACAO] Envio não solicitado ou rejeitado (best-effort): {e!r}")
        return NotificationResult("unconfirmed", reason=type(e).__name__)


def send_to_customer(
    restaurant_number: str,
    customer_phone: str,
    message: str,
    media_url: str | None = None,
):
    """Envia mensagem (e opcionalmente mídia) para o cliente via Twilio.

    Usa restaurant_number como remetente (número que recebeu a mensagem do cliente).
    Exige o remetente da unidade; não há fallback global.
    media_url: URL pública de arquivo (PDF, imagem) — entregue como anexo WhatsApp.

    Lança exceção em caso de falha — callers decidem como tratar:
      - _process_and_reply (background): captura e loga
      - handoff_reply (painel): captura e retorna HTTP 502
    """
    client = _client()
    if not client:
        raise RuntimeError("Twilio não configurado; envio não solicitado")
    sender = whatsapp_address(restaurant_number)
    to_number = whatsapp_address(customer_phone)
    if sender == to_number:
        raise ValueError("Remetente e destinatário não podem ser o mesmo número")
    kwargs: dict = {
        "from_": sender,
        "to": to_number,
        "body": message,
    }
    if media_url:
        kwargs["media_url"] = [media_url]
    msg = client.messages.create(**kwargs)
    observed = accepted_message(msg)
    print(f"[MSG] Twilio aceitou sid={msg.sid}; entrega não confirmada")
    return observed
