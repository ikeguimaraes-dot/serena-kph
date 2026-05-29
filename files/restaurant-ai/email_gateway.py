"""
Email gateway — Resend HTTP API gated por env var.

Sem RESEND_API_KEY: vira no-op + log (modo dev, mesma pattern do Twilio
em notifications.py). Com a env: 1 chamada HTTP simples.

Setup quando quiser ativar:
  1. https://resend.com → Sign up (free 100 emails/dia)
  2. API Keys → Create
  3. Railway env: RESEND_API_KEY=re_...
  4. (opcional) RESEND_FROM="Serena <noreply@seu-dominio.com>" — exige domínio verificado.
     Se não setar, usa o fallback de onboarding da Resend (bom pra dev/teste).
  5. WEEKLY_REPORT_EMAIL=destinatario@... — quem recebe os relatórios semanais.
"""

import os
import httpx


_RESEND_URL = "https://api.resend.com/emails"
_DEFAULT_FROM = "Serena <onboarding@resend.dev>"


def send_email(to: str, subject: str, html: str) -> bool:
    """Envia email via Resend. Retorna True se sucesso, False caso contrário (incluindo no-op).

    No-op silencioso quando RESEND_API_KEY não está setada — mesmo padrão do
    notifications.py. Loga pra audit em ambos os caminhos.
    """
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        print(f"[EMAIL noop] to={to} subject={subject!r}")
        return False

    sender = os.environ.get("RESEND_FROM", _DEFAULT_FROM)
    payload = {"from": sender, "to": [to], "subject": subject, "html": html}

    try:
        with httpx.Client(timeout=10.0) as cli:
            r = cli.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
        print(f"[EMAIL sent] to={to} subject={subject!r}")
        return True
    except Exception as e:
        # Não derruba o cron por falha de email — só loga.
        print(f"[EMAIL error] to={to} subject={subject!r} err={e!r}")
        return False


async def send_reservation_confirmation(
    to: str,
    nome: str,
    data: str,
    hora: str,
    pessoas: int,
    codigo: str,
    restaurante: str = "Madonna Cucina",
) -> bool:
    """Envia e-mail de confirmação de reserva. Async via asyncio.to_thread."""
    import asyncio

    subject = f"Reserva confirmada — {restaurante}"
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#f5f0e8; margin:0; padding:32px 16px; }}
  .card {{ max-width:520px; margin:0 auto; background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,.08); }}
  .header {{ background:#1a1208; padding:28px 32px; text-align:center; }}
  .header h1 {{ color:#d4a574; font-size:22px; margin:0; letter-spacing:1px; font-weight:700; }}
  .header p {{ color:#a08060; font-size:13px; margin:6px 0 0; }}
  .body {{ padding:32px; }}
  .code-box {{ background:#faf7f2; border:2px solid #d4a574; border-radius:12px; padding:20px; text-align:center; margin:24px 0; }}
  .code-label {{ font-size:11px; color:#888; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:8px; }}
  .code {{ font-size:32px; font-weight:800; color:#1a1208; letter-spacing:4px; font-family:monospace; }}
  .details {{ border-top:1px solid #f0ebe3; padding-top:20px; margin-top:8px; }}
  .row {{ display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #f5f0e8; font-size:14px; }}
  .row .label {{ color:#888; }}
  .row .value {{ color:#1a1208; font-weight:600; }}
  .footer {{ background:#faf7f2; padding:20px 32px; text-align:center; border-top:1px solid #f0ebe3; }}
  .footer p {{ font-size:12px; color:#999; margin:4px 0; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <h1>{restaurante}</h1>
    <p>Confirmação de Reserva</p>
  </div>
  <div class="body">
    <p style="font-size:15px;color:#333;margin:0 0 4px">Olá, <strong>{nome}</strong>!</p>
    <p style="font-size:14px;color:#666;margin:0 0 20px">Sua reserva foi confirmada com sucesso.</p>
    <div class="code-box">
      <div class="code-label">Código da Reserva</div>
      <div class="code">{codigo}</div>
    </div>
    <div class="details">
      <div class="row"><span class="label">Data</span><span class="value">{data}</span></div>
      <div class="row"><span class="label">Horário</span><span class="value">{hora}</span></div>
      <div class="row"><span class="label">Pessoas</span><span class="value">{pessoas}</span></div>
      <div class="row" style="border:none"><span class="label">Restaurante</span><span class="value">{restaurante}</span></div>
    </div>
  </div>
  <div class="footer">
    <p>Guarde seu código para consultar ou cancelar a reserva.</p>
    <p>Dúvidas? Responda esta mensagem ou entre em contato via WhatsApp.</p>
  </div>
</div>
</body>
</html>"""

    return await asyncio.to_thread(send_email, to, subject, html)
