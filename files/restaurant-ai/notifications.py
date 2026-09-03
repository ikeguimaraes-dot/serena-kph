"""
Notificações para a equipe.
- Discord webhook (primário): sem restrição de janela de 24h. Requer DISCORD_HANDOFF_WEBHOOK_URL.
- Twilio WhatsApp (secundário): só funciona dentro de janela de 24h ativa. Requer TWILIO_*.
Ambos best-effort: falha não quebra o handoff.
"""

import os
import json
import urllib.request

_twilio_client = None

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
) -> None:
    """Envia alerta de handoff para o canal Discord. Nunca lança exceção."""
    discord_url = os.environ.get("DISCORD_HANDOFF_WEBHOOK_URL")
    if not discord_url:
        print(f"[HANDOFF] Discord não configurado — {restaurant_nome} | {customer_phone}")
        return
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
        urllib.request.urlopen(req, timeout=5)
        print(f"[HANDOFF] Discord OK — {restaurant_nome} | {customer_phone}")
    except Exception as e:
        print(f"[HANDOFF] Discord falhou (best-effort): {e!r}")

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
    client = _client()
    if not client:
        return
    body = (
        f"🚨 *Atendimento humano solicitado*\n\n"
        f"Restaurante: {restaurant_nome}\n"
        f"Cliente: {customer_phone}\n"
        f"Motivo: {motivo}\n\n"
        f"Contexto:\n{resumo}\n\n"
        f"Acesse o painel ou contate o cliente diretamente."
    )
    raw_from = os.environ.get("TWILIO_FROM_NUMBER", "")
    from_number = raw_from.replace("whatsapp:", "").strip()
    try:
        client.messages.create(
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{team_whatsapp}",
            body=body,
        )
    except Exception as e:
        print(f"[HANDOFF] Twilio falhou: {e!r}")

def send_to_customer(
    restaurant_number: str,
    customer_phone: str,
    message: str,
    media_url: str | None = None,
):
    """Envia mensagem (e opcionalmente mídia) para o cliente via Twilio.

    Usa restaurant_number como remetente (número que recebeu a mensagem do cliente).
    Fallback para TWILIO_FROM_NUMBER apenas quando restaurant_number estiver vazio.
    media_url: URL pública de arquivo (PDF, imagem) — entregue como anexo WhatsApp.

    Lança exceção em caso de falha — callers decidem como tratar:
      - _process_and_reply (background): captura e loga
      - handoff_reply (painel): captura e retorna HTTP 502
    """
    client = _client()
    if not client:
        print(f"[MSG → {customer_phone}] (Twilio não configurado): {message[:80]}")
        return
    raw_sender = restaurant_number or os.environ.get("TWILIO_FROM_NUMBER", "")
    # Normaliza: remove "whatsapp:" prefix se já estiver no env var
    sender = raw_sender.replace("whatsapp:", "").strip()
    # Normaliza: garante formato E.164 no destinatário
    to_number = customer_phone if customer_phone.startswith("+") else f"+{customer_phone}"
    kwargs: dict = {
        "from_": f"whatsapp:{sender}",
        "to": f"whatsapp:{to_number}",
        "body": message,
    }
    if media_url:
        kwargs["media_url"] = [media_url]
    msg = client.messages.create(**kwargs)
    print(f"[MSG → {to_number}] Twilio OK sid={msg.sid}")
