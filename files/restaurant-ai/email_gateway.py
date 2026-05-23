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
