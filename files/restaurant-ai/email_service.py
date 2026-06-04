"""
email_service.py — Emails transacionais via Resend SDK.

Tokens HOS:
  Carvão  #1A1A1A  — background
  Creme   #F5F0E8  — texto principal
  Brasa   #C4622D  — accent / botões
"""

import os
import logging

logger = logging.getLogger(__name__)

try:
    import resend as _resend
except ImportError:
    _resend = None  # type: ignore

FROM_EMAIL: str = os.environ.get("EMAIL_FROM", "Serena <noreply@mdna.com.br>")
# Em dev, quando o domínio ainda não propagou, redireciona para este endereço.
TEST_EMAIL: str | None = os.environ.get("RESEND_TEST_EMAIL")


def _api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "")


def _effective_to(email: str) -> str:
    """Retorna RESEND_TEST_EMAIL se definido (dev); caso contrário o email real."""
    return TEST_EMAIL if TEST_EMAIL else email


def _base_html(title: str, body_html: str) -> str:
    """Template base com visual Madonna Cucina — paleta HOS."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: #111111;
      font-family: system-ui, Arial, Helvetica, sans-serif;
      color: #F5F0E8;
      -webkit-text-size-adjust: 100%;
    }}
    .wrapper {{
      max-width: 600px;
      margin: 0 auto;
      background-color: #1A1A1A;
    }}
    .header {{
      background-color: #1A1A1A;
      padding: 36px 32px 24px;
      border-bottom: 2px solid #C4622D;
      text-align: center;
    }}
    .logo {{
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #F5F0E8;
    }}
    .logo span {{
      color: #C4622D;
    }}
    .tagline {{
      font-size: 12px;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: #9A9186;
      margin-top: 6px;
    }}
    .content {{
      padding: 32px 32px 24px;
    }}
    .content h1 {{
      font-size: 22px;
      font-weight: 600;
      color: #F5F0E8;
      margin-bottom: 16px;
    }}
    .content p {{
      font-size: 15px;
      line-height: 1.7;
      color: #D6D0C8;
      margin-bottom: 12px;
    }}
    .detail-box {{
      background-color: #242424;
      border-left: 3px solid #C4622D;
      border-radius: 4px;
      padding: 20px 24px;
      margin: 20px 0;
    }}
    .detail-box table {{
      width: 100%;
      border-collapse: collapse;
    }}
    .detail-box td {{
      padding: 6px 0;
      font-size: 14px;
      color: #D6D0C8;
      vertical-align: top;
    }}
    .detail-box td.label {{
      color: #9A9186;
      width: 140px;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .detail-box td.value {{
      color: #F5F0E8;
      font-weight: 500;
    }}
    .btn {{
      display: inline-block;
      background-color: #C4622D;
      color: #F5F0E8 !important;
      text-decoration: none;
      font-size: 14px;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      padding: 14px 28px;
      border-radius: 3px;
      margin: 16px 0;
    }}
    .footer {{
      padding: 20px 32px 28px;
      border-top: 1px solid #2E2E2E;
      text-align: center;
    }}
    .footer p {{
      font-size: 12px;
      color: #5A5550;
      line-height: 1.6;
    }}
    .divider {{
      height: 1px;
      background-color: #2E2E2E;
      margin: 20px 0;
    }}
    @media (max-width: 600px) {{
      .content {{ padding: 24px 20px 20px; }}
      .detail-box {{ padding: 16px 18px; }}
      .detail-box td.label {{ width: 110px; }}
      .header {{ padding: 28px 20px 20px; }}
      .footer {{ padding: 16px 20px 24px; }}
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <div class="logo">Madonna <span>Cucina</span></div>
      <div class="tagline">Cucina italiana · São Paulo</div>
    </div>
    <div class="content">
      {body_html}
    </div>
    <div class="footer">
      <p>Madonna Cucina · Rua da Consolação, 1234 — São Paulo, SP<br>
      Este é um email automático. Para falar conosco, responda via WhatsApp.</p>
    </div>
  </div>
</body>
</html>"""


def _send_email(to: str, subject: str, html: str) -> bool:
    """Envia email via Resend SDK. Retorna True se enviado com sucesso."""
    api_key = _api_key()
    if not api_key:
        logger.warning("[email_service] RESEND_API_KEY ausente — email não enviado")
        return False
    if _resend is None:
        logger.error("[email_service] pacote 'resend' não instalado — `pip install resend`")
        return False
    try:
        _resend.api_key = api_key
        _resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        logger.info(f"[email_service] email enviado → {to!r} | {subject!r}")
        return True
    except Exception as exc:
        logger.error(f"[email_service] falha ao enviar para {to!r}: {exc!r}")
        return False


# ── Helpers de formatação ─────────────────────────────────────

def _fmt_data(val) -> str:
    if not val:
        return "—"
    s = str(val)
    # yyyy-mm-dd → dd/mm/yyyy
    if len(s) == 10 and s[4] == "-":
        y, m, d = s.split("-")
        return f"{d}/{m}/{y}"
    return s


def _fmt_hora(val) -> str:
    if not val:
        return "—"
    # HH:MM:SS → HH:MM
    s = str(val)
    return s[:5] if len(s) >= 5 else s


def _fmt_valor(val) -> str:
    if val is None:
        return "—"
    try:
        return f"R$ {float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(val)


# ════════════════════════════════════════════════════════════════
# Emails transacionais
# ════════════════════════════════════════════════════════════════

async def send_confirmacao_reserva(reserva: dict) -> bool:
    """Envia email de confirmação quando uma reserva é confirmada.

    Args:
        reserva: dict com campos da tabela reservas
                 (cliente_email, cliente_nome, data, hora_inicio,
                  posicoes, tipo_evento, observacoes)
    """
    email = reserva.get("cliente_email") or ""
    if not email.strip():
        logger.debug("[email_service] send_confirmacao_reserva: cliente_email vazio, pulando")
        return False

    nome = (reserva.get("cliente_nome") or "").split()[0] or "cliente"
    data_fmt = _fmt_data(reserva.get("data"))
    hora_fmt = _fmt_hora(reserva.get("hora_inicio"))
    posicoes = reserva.get("posicoes") or "—"
    tipo = reserva.get("tipo_evento") or "Reserva"
    obs = reserva.get("observacoes") or ""

    obs_row = f"""
      <tr>
        <td class="label">Observações</td>
        <td class="value">{obs}</td>
      </tr>""" if obs else ""

    body_html = f"""
      <h1>Reserva confirmada!</h1>
      <p>Olá, {nome}! Sua reserva na <strong>Madonna Cucina</strong> está confirmada.
      Estamos ansiosos para recebê-lo(a).</p>

      <div class="detail-box">
        <table>
          <tr>
            <td class="label">Evento</td>
            <td class="value">{tipo}</td>
          </tr>
          <tr>
            <td class="label">Data</td>
            <td class="value">{data_fmt}</td>
          </tr>
          <tr>
            <td class="label">Horário</td>
            <td class="value">{hora_fmt}</td>
          </tr>
          <tr>
            <td class="label">Pessoas</td>
            <td class="value">{posicoes}</td>
          </tr>{obs_row}
        </table>
      </div>

      <p>Caso precise cancelar ou alterar sua reserva, entre em contato conosco
      com pelo menos 24 horas de antecedência pelo WhatsApp.</p>

      <p>Nos vemos em breve!</p>
    """

    html = _base_html("Reserva Confirmada — Madonna Cucina", body_html)
    to = _effective_to(email)
    return _send_email(to, f"Sua reserva está confirmada — {data_fmt}", html)


async def send_proposta_enviada(os_data: dict) -> bool:
    """Envia email com detalhes da proposta quando status da OS vira 'proposta_enviada'.

    Args:
        os_data: dict com campos da tabela ordens_servico
                 (cliente_email, cliente_nome, data, hora_inicio,
                  tipo_evento, pessoas, valor_total, valor_entrada,
                  stripe_payment_link ou link similar)
    """
    email = os_data.get("cliente_email") or ""
    if not email.strip():
        logger.debug("[email_service] send_proposta_enviada: cliente_email vazio, pulando")
        return False

    nome = (os_data.get("cliente_nome") or "").split()[0] or "cliente"
    data_fmt = _fmt_data(os_data.get("data"))
    hora_fmt = _fmt_hora(os_data.get("hora_inicio"))
    tipo = os_data.get("tipo_evento") or "Evento"
    pessoas = os_data.get("pessoas") or "—"
    valor_total = _fmt_valor(os_data.get("valor_total"))
    valor_entrada = _fmt_valor(os_data.get("valor_entrada"))
    link_pgto = os_data.get("stripe_payment_link") or os_data.get("payment_link") or ""

    btn_html = ""
    if link_pgto:
        btn_html = f"""
      <p style="margin-top: 20px;">Para confirmar seu evento, realize o pagamento da entrada:</p>
      <a href="{link_pgto}" class="btn">Pagar entrada agora</a>
        """

    body_html = f"""
      <h1>Sua proposta chegou!</h1>
      <p>Olá, {nome}! Preparamos uma proposta especial para o seu evento na
      <strong>Madonna Cucina</strong>. Confira os detalhes abaixo.</p>

      <div class="detail-box">
        <table>
          <tr>
            <td class="label">Evento</td>
            <td class="value">{tipo}</td>
          </tr>
          <tr>
            <td class="label">Data</td>
            <td class="value">{data_fmt}</td>
          </tr>
          <tr>
            <td class="label">Horário</td>
            <td class="value">{hora_fmt}</td>
          </tr>
          <tr>
            <td class="label">Pessoas</td>
            <td class="value">{pessoas}</td>
          </tr>
          <tr>
            <td class="label">Valor total</td>
            <td class="value">{valor_total}</td>
          </tr>
          <tr>
            <td class="label">Entrada</td>
            <td class="value">{valor_entrada}</td>
          </tr>
        </table>
      </div>

      {btn_html}

      <div class="divider"></div>
      <p style="font-size: 13px; color: #9A9186;">
        Dúvidas? Fale com nossa equipe pelo WhatsApp — respondemos em até 2 horas.
      </p>
    """

    html = _base_html("Proposta de Evento — Madonna Cucina", body_html)
    to = _effective_to(email)
    return _send_email(to, f"Sua proposta para {tipo} em {data_fmt} — Madonna Cucina", html)


async def send_comprovante_pagamento(os_data: dict, valor_pago: float) -> bool:
    """Envia comprovante de pagamento após confirmação do Stripe webhook.

    Args:
        os_data: dict com campos da tabela ordens_servico
        valor_pago: float com o valor efetivamente pago (em BRL)
    """
    email = os_data.get("cliente_email") or ""
    if not email.strip():
        logger.debug("[email_service] send_comprovante_pagamento: cliente_email vazio, pulando")
        return False

    nome = (os_data.get("cliente_nome") or "").split()[0] or "cliente"
    data_fmt = _fmt_data(os_data.get("data"))
    hora_fmt = _fmt_hora(os_data.get("hora_inicio"))
    tipo = os_data.get("tipo_evento") or "Evento"
    pessoas = os_data.get("pessoas") or "—"
    valor_pago_fmt = _fmt_valor(valor_pago)
    valor_total = _fmt_valor(os_data.get("valor_total"))
    payment_intent = os_data.get("stripe_payment_intent_id") or "—"

    body_html = f"""
      <h1>Pagamento confirmado!</h1>
      <p>Olá, {nome}! Recebemos seu pagamento e seu evento está reservado.
      Guarde este comprovante para seus registros.</p>

      <div class="detail-box">
        <table>
          <tr>
            <td class="label">Evento</td>
            <td class="value">{tipo}</td>
          </tr>
          <tr>
            <td class="label">Data</td>
            <td class="value">{data_fmt}</td>
          </tr>
          <tr>
            <td class="label">Horário</td>
            <td class="value">{hora_fmt}</td>
          </tr>
          <tr>
            <td class="label">Pessoas</td>
            <td class="value">{pessoas}</td>
          </tr>
          <tr>
            <td class="label">Valor pago</td>
            <td class="value" style="color: #C4622D;">{valor_pago_fmt}</td>
          </tr>
          <tr>
            <td class="label">Valor total</td>
            <td class="value">{valor_total}</td>
          </tr>
          <tr>
            <td class="label">Referência</td>
            <td class="value" style="font-size: 12px; word-break: break-all;">{payment_intent}</td>
          </tr>
        </table>
      </div>

      <p>Nossa equipe entrará em contato para alinhar os detalhes finais do seu evento.
      Estamos animados para tornar essa ocasião inesquecível!</p>

      <div class="divider"></div>
      <p style="font-size: 13px; color: #9A9186;">
        Restam dúvidas? Fale com nossa equipe pelo WhatsApp.
      </p>
    """

    html = _base_html("Comprovante de Pagamento — Madonna Cucina", body_html)
    to = _effective_to(email)
    return _send_email(to, f"Comprovante de pagamento — {tipo} em {data_fmt}", html)
