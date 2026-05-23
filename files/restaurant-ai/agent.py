"""Agente Claude — carrega config do Supabase, totalmente async.

Onda 8: instrumentação completa.
- Captura tokens/custo/latência por turno e persiste em serena_metrics
- Categoriza motivo do handoff via Claude (fire-and-forget)
- System prompt versionado (lido da DB, fallback hardcoded)
- Detecta fricções: cliente pediu humano, Serena admitiu não saber

Sprint C2: agent.py refatorado em 4 módulos:
  agent_prompt.py  — construção do system prompt
  agent_context.py — contexto CRM do contato
  agent_tools.py   — TOOLS schema + dispatcher execute_tool()
  agent.py         — classe RestaurantAgent + detectores + métricas
"""

import os, re, asyncio, time, anthropic
from datetime import datetime
import database as db
from agent_prompt import build_prompt, _FALLBACK_BODY
from agent_context import build_contact_context
from agent_tools import TOOLS, execute_tool

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 20
MAX_ITERATIONS = 6

# Preço Sonnet 4.6 (USD por milhão de tokens) — atualizar quando trocar de modelo.
PRICE_INPUT_USD_PER_MTOK = 3.0
PRICE_OUTPUT_USD_PER_MTOK = 15.0


# ── Detectores de fricção ──────────────────────────────────────

_RE_PEDIU_HUMANO = re.compile(
    r"\b(falar com (?:um |uma |o |a )?(?:humano|atendente|gerente|pessoa|alguem|alguém)|"
    r"quero falar com|me transfere|me passa|chama (?:um |uma )?(?:humano|atendente|gerente)|"
    r"sai do automatico|sair do automatico|sair do bot|nao quero (?:bot|robo|robô))",
    re.IGNORECASE,
)

_RE_NAO_SEI = re.compile(
    r"\b(nao sei|não sei|nao consigo|não consigo|nao tenho como|não tenho como|"
    r"nao posso ajudar|não posso ajudar|nao vou conseguir|não vou conseguir|"
    r"nao tenho essa informacao|não tenho essa informação|fora do meu alcance)",
    re.IGNORECASE,
)

# Taxonomia de intenções — mais específico primeiro.
_RE_INTENCAO = [
    ("reserva_existente", re.compile(r"\b(cancel|alterar reserva|mudar reserva|confirmar reserva|minha reserva|já reservei|já tenho reserva)", re.I)),
    ("reserva_nova",      re.compile(r"\b(reserv|mesa|lugar|assento|disponib|horario|horário|tagme|agendar|marcar mesa|quero jantar|quero almoç)", re.I)),
    ("reclamacao",        re.compile(r"\b(reclam|insatisf|nojent|estragad|horrivel|horrível|pessim|péssim|decepcion|problema|demor|frio|gelado|mal atendid)", re.I)),
    ("cardapio",          re.compile(r"\b(cardapio|cardápio|prato|menu|comida|opcao|opção|tem.*pra comer|o que vocês servem|vegeta|vegan|sem gluten|sem lactose|alergi)", re.I)),
    ("horario",           re.compile(r"\b(horario|horário|abre|fecha|funcionamento|expediente|que horas|aberto|fechado|domingo|segunda|sabado|sábado)", re.I)),
    ("estacionamento",    re.compile(r"\b(estacionament|valet|carro|garagem|vaga|parking|moto)", re.I)),
    ("localizacao",       re.compile(r"\b(endereço|endereco|onde fica|como chegar|localiz|bairro|rua|maps|google|uber|taxi|estacion)", re.I)),
    ("evento",            re.compile(r"\b(evento|aniversari|confraterniza|corporativ|grupo|festa|celebr|formatura|bodas|noivado|15 anos)", re.I)),
    ("dress_code",        re.compile(r"\b(dress|traje|roupa|terno|smoking|social|formal|posso ir de|precisa de)", re.I)),
    ("agradecimento",     re.compile(r"\b(obrigad|obrigada|valeu|muito bom|excelente|adorei|amei|perfeito|ótimo|otimo|parabens|parabéns|foi incrível)", re.I)),
    ("preco",             re.compile(r"\b(preço|preco|valor|caro|barato|custa|quanto custa|ticket|meio de pagamento|aceita|cartao|cartão|pix|dinheiro)", re.I)),
    ("info_geral",        re.compile(r"\b(oi|olá|ola|bom dia|boa tarde|boa noite|tudo bem|informaç|informac|queria saber|pode me dizer|me fala sobre)", re.I)),
]

def _detect_intent(message: str) -> str:
    for intent, rx in _RE_INTENCAO:
        if rx.search(message or ""):
            return intent
    print(f"[INTENT] desconhecida — msg={(message or '')[:80]!r}")
    return "desconhecida"


def _detect_pediu_humano(history: list[dict]) -> bool:
    for m in history[-3:]:
        if m.get("role") == "user" and _RE_PEDIU_HUMANO.search(m.get("content", "") or ""):
            return True
    return False


def _detect_admitiu_nao_saber(text: str | None) -> bool:
    if not text:
        return False
    return bool(_RE_NAO_SEI.search(text))


def _detect_link_tagme(text: str | None) -> bool:
    if not text:
        return False
    return "reservation-widget.tagme.com.br" in text or "tagme.com.br" in text


def _calc_cost_usd(tin: int, tout: int) -> float:
    return round(
        (tin / 1_000_000) * PRICE_INPUT_USD_PER_MTOK
        + (tout / 1_000_000) * PRICE_OUTPUT_USD_PER_MTOK,
        6,
    )


# ── Categorização de handoff (background, fire-and-forget) ─────

CATEGORIAS = (
    "reserva", "evento", "reclamacao", "fora_escopo",
    "vip", "dress_code", "estacionamento", "cardapio", "outros",
)

async def _categorize_handoff(metric_id: str, motivo: str):
    """Chama Claude Haiku rápido para classificar — best effort."""
    if not motivo or not metric_id:
        return
    try:
        resp = await asyncio.to_thread(
            client.messages.create,
            model="claude-haiku-4-5",
            max_tokens=20,
            messages=[{
                "role": "user",
                "content": (
                    f"Classifique este motivo de handoff em UMA categoria entre: "
                    f"{', '.join(CATEGORIAS)}. Responda só com a palavra da categoria.\n\n"
                    f"Motivo: {motivo}"
                ),
            }],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip().lower()
        cat = text.split()[0] if text else "outros"
        cat = cat if cat in CATEGORIAS else "outros"
        await db.update_serena_metric_categoria(metric_id, cat)
    except Exception as e:
        print(f"[CATEGORIZE] falhou metric={metric_id}: {e!r}")


# ── Agent ──────────────────────────────────────────────────────

class RestaurantAgent:
    async def test_turn(self, message: str, restaurant: dict,
                         prompt_body_override: str | None = None,
                         user_phone: str | None = None) -> dict:
        """Roda 1 turno SEM persistir nada — para testes em /api/serena/test-message."""
        if prompt_body_override is not None:
            from agent_prompt import _dynamic_header
            contact_block = await build_contact_context(user_phone)
            system = _dynamic_header(restaurant, contact_block) + "\n" + prompt_body_override
            pid = "OVERRIDE"
        else:
            system, pid = await build_prompt(restaurant, user_phone=user_phone)
        messages = [{"role": "user", "content": message}]
        t0 = time.monotonic()
        result = await self._run(system=system, messages=messages,
                                  user_phone=user_phone or "+test", rid=restaurant["id"])
        latencia_ms = int((time.monotonic() - t0) * 1000)
        text = result["text"]
        if text and text.startswith("__HANDOFF__:"):
            text = f"[HANDOFF] {text.replace('__HANDOFF__:', '').strip()}"
        return {
            "text": text,
            "tokens_input": result["tokens_input"],
            "tokens_output": result["tokens_output"],
            "tools_called": result["tools_called"],
            "latencia_ms": latencia_ms,
            "prompt_versao_id": pid,
            "system_chars": len(system),
            "intencao_detectada": _detect_intent(message),
        }

    async def process(self, user_phone: str, restaurant_phone: str, message: str, profile_name: str = "") -> str:
        print(f"[AGENT] process user={user_phone!r} restaurant_phone={restaurant_phone!r} profile_name={profile_name!r}")
        restaurant = await db.get_restaurant_by_whatsapp(restaurant_phone)
        if not restaurant:
            print(f"[AGENT] Restaurante NÃO encontrado para whatsapp_number={restaurant_phone!r}")
            return "Desculpe, não consegui identificar o restaurante. Tente novamente."

        rid = restaurant["id"]
        print(f"[AGENT] Restaurante={rid} ({restaurant['nome']})")

        try:
            await db.ensure_contact(user_phone, nome=profile_name)
        except Exception as e:
            print(f"[AGENT] ensure_contact falhou user={user_phone!r}: {e!r}")

        if await db.is_in_handoff(user_phone, rid):
            await db.save_message(user_phone, rid, "user", message)
            return None

        history = await db.get_history(user_phone, rid, MAX_HISTORY)
        history.append({"role":"user","content":message})

        system, prompt_versao_id = await build_prompt(restaurant, user_phone=user_phone)

        t0 = time.monotonic()
        result = await self._run(system=system, messages=history, user_phone=user_phone, rid=rid)
        latencia_ms = int((time.monotonic() - t0) * 1000)

        response_text = result["text"]
        handoff_triggered = response_text and response_text.startswith("__HANDOFF__:")
        handoff_motivo = None

        if handoff_triggered:
            handoff_motivo = response_text.replace("__HANDOFF__:", "").strip()
            hid = await db.create_handoff(user_phone, rid, handoff_motivo)
            print(f"[AGENT] Handoff criado id={hid} user={user_phone} motivo={handoff_motivo!r}")
            team = await db.get_on_duty_team(rid)
            if team:
                import notifications as notif
                for m in team[:2]:
                    notif.notify_handoff(
                        m["whatsapp"], restaurant["nome"],
                        user_phone, handoff_motivo,
                        "\n".join(f"{x['role']}: {x['content']}" for x in history[-4:])
                    )
            response_text = (
                "Vou te conectar com um de nossos atendentes agora. 🙏\n"
                "Um momento, por favor."
            )

        await db.save_message(user_phone, rid, "user", message)
        await db.save_message(user_phone, rid, "assistant", response_text)

        # ── Métricas (best-effort, não bloqueia resposta) ────
        try:
            metric = {
                "user_phone": user_phone,
                "restaurant_id": rid,
                "tokens_input": result["tokens_input"],
                "tokens_output": result["tokens_output"],
                "custo_usd": _calc_cost_usd(result["tokens_input"], result["tokens_output"]),
                "latencia_ms": latencia_ms,
                "tools_chamadas": result["tools_called"] or None,
                "handoff_acionado": bool(handoff_triggered),
                "handoff_motivo": handoff_motivo,
                "cliente_pediu_humano": _detect_pediu_humano(history),
                "serena_admitiu_nao_saber": _detect_admitiu_nao_saber(result["text"]),
                "enviou_link_tagme": _detect_link_tagme(response_text),
                "intencao_detectada": _detect_intent(message),
                "num_mensagens": len(history),
                "prompt_versao_id": prompt_versao_id,
            }
            metric_id = await db.record_serena_metric(metric)
            if handoff_triggered and metric_id and handoff_motivo:
                asyncio.create_task(_categorize_handoff(metric_id, handoff_motivo))
        except Exception as e:
            print(f"[AGENT] record_serena_metric falhou: {e!r}")

        return response_text

    async def _run(self, system, messages, user_phone, rid) -> dict:
        msgs = list(messages)
        tokens_input = 0
        tokens_output = 0
        tools_called: list[str] = []

        for _ in range(MAX_ITERATIONS):
            response = await asyncio.to_thread(
                client.messages.create,
                model=MODEL, max_tokens=1024,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=msgs, tools=TOOLS,
            )
            usage = getattr(response, "usage", None)
            if usage:
                tokens_input  += getattr(usage, "input_tokens",  0) or 0
                tokens_output += getattr(usage, "output_tokens", 0) or 0

            if response.stop_reason == "tool_use":
                # Intercepta handoff antes de devolver ao Claude.
                for b in response.content:
                    if b.type == "tool_use" and b.name == "transferir_para_humano":
                        motivo = b.input.get("motivo", "sem motivo informado")
                        print(f"[AGENT] Tool transferir_para_humano → motivo={motivo!r}")
                        tools_called.append("transferir_para_humano")
                        return {
                            "text": f"__HANDOFF__:{motivo}",
                            "tokens_input": tokens_input,
                            "tokens_output": tokens_output,
                            "tools_called": tools_called,
                        }
                ac = [{"type":"text","text":b.text} if b.type=="text"
                      else {"type":"tool_use","id":b.id,"name":b.name,"input":b.input}
                      for b in response.content]
                msgs.append({"role":"assistant","content":ac})
                results = []
                for b in response.content:
                    if b.type == "tool_use":
                        tools_called.append(b.name)
                        res = await execute_tool(b.name, b.input, user_phone, rid)
                        results.append({"type":"tool_result","tool_use_id":b.id,"content":res})
                msgs.append({"role":"user","content":results})
                continue

            if response.stop_reason == "end_turn":
                text = ""
                for b in response.content:
                    if hasattr(b,"text"):
                        text = b.text
                        break
                return {
                    "text": text or "Desculpe, tente novamente.",
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "tools_called": tools_called,
                }

        return {
            "text": "Estou com dificuldades técnicas. Tente novamente.",
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tools_called": tools_called,
        }
