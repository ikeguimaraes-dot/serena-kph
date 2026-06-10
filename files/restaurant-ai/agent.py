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

# ── Interceptor hardcoded: Dia dos Namorados 12/06 ─────────────
#
# REGRA: qualquer menção a 12/06 ou "namorados" — em QUALQUER
# mensagem ou no histórico recente — NUNCA chega à LLM nem às tools
# de reserva/proposta. Resposta única: captura de lead para concierge.
#
_DIA_NAMORADOS_PATTERNS = [
    r"12[\/\-\.]?06",      # 12/06, 12-06, 12.06, 1206
    r"dia dos namorados",
    r"\bnamorados?\b",     # "namorado", "namorados"
    r"12 de junho",
    r"junho.{0,5}12",      # "junho dia 12", "junho, 12"
    r"menu.{0,20}junho",   # "menu de junho", "menu especial de junho"
    r"junho.{0,20}menu",   # "junho tem menu especial?"
]

_MSG_NAMORADOS_CONCIERGE = (
    "O Dia dos Namorados é uma das nossas noites mais especiais do ano. "
    "Para garantir que tudo fique perfeito, nossa concierge entrará em "
    "contato com você pessoalmente com todas as informações e disponibilidade. "
    "Posso registrar seu nome para a lista?"
)
_MSG_NAMORADOS_CONFIRMACAO = (
    "Perfeito, {nome}. Nossa concierge entrará em contato em breve."
)

# Ferramenta bloqueadas para 12/06 — mesmo se a LLM tentar chamá-las
_TOOLS_BLOQUEADAS_NAMORADOS = {"fazer_reserva", "gerar_proposta", "verificar_disponibilidade"}

# Data hard-block (YYYY-MM-DD) — bloqueia na camada de tools
_DATA_NAMORADOS = "2026-06-12"


def _mensagem_e_namorados(texto: str) -> bool:
    t = texto.lower()
    return any(re.search(p, t) for p in _DIA_NAMORADOS_PATTERNS)


def _historico_tem_namorados(history: list) -> bool:
    """Retorna True se qualquer mensagem recente do histórico menciona namorados.
    Verifica as últimas 6 mensagens para detectar contexto ativo.
    """
    for msg in history[-6:]:
        content = msg.get("content", "")
        if isinstance(content, str) and _mensagem_e_namorados(content):
            return True
    return False


def _em_captura_nome_namorados(history: list) -> bool:
    """Retorna True se a última mensagem do assistente foi a pergunta de captura de nome."""
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            return _MSG_NAMORADOS_CONCIERGE in msg.get("content", "")
        if msg.get("role") == "user":
            break
    return False


def _tool_e_bloqueada_namorados(name: str, inputs: dict) -> bool:
    """Retorna True se a tool deve ser bloqueada por ser sobre 12/06."""
    if name not in _TOOLS_BLOQUEADAS_NAMORADOS:
        return False
    data_arg = inputs.get("data", "") or ""
    # Bloqueia se data é 12/06 OU se qualquer input menciona namorados
    if _DATA_NAMORADOS in str(data_arg):
        return True
    return any(_mensagem_e_namorados(str(v)) for v in inputs.values())

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
    ("reserva_existente", re.compile(r"\b(cancel|alterar reserva|mudar reserva|minha reserva|já reservei|já tenho reserva|tenho reserva)", re.I)),
    ("reserva_nova",      re.compile(r"\b(reserv|mesa|lugar|assento|disponib|horario|horário|agendar|marcar mesa|quero jantar|quero almoç)", re.I)),
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
        
        agent_name_env = os.environ.get("AGENT_NAME")
        restaurant = None
        
        if agent_name_env:
            rid = agent_name_env.lower().strip()
            print(f"[AGENT] Usando AGENT_NAME={agent_name_env!r} (rid={rid!r}) para segregação.")
            restaurant = await db.get_restaurant(rid)
            
            if not restaurant:
                # Tenta buscar pelo número de WhatsApp
                restaurant = await db.get_restaurant_by_whatsapp(restaurant_phone)
                
                # Se ainda não encontrado, cria/garante a existência do restaurante/agente de forma autocurativa
                if not restaurant:
                    business_context = os.environ.get("BUSINESS_CONTEXT") or f"{agent_name_env} Core"
                    print(f"[AGENT] Restaurante/Agente {rid!r} não encontrado no banco. Criando de forma autocurativa...")
                    await db.ensure_restaurant(rid, business_context, restaurant_phone)
                    restaurant = await db.get_restaurant_by_whatsapp(restaurant_phone)
                    if not restaurant:
                        # Fallback em memória se por algum motivo a DB falhar temporariamente
                        restaurant = {
                            "id": rid,
                            "nome": business_context,
                            "whatsapp_number": restaurant_phone,
                            "endereco": "",
                            "descricao": business_context,
                            "capacidade_maxima_reserva": 8,
                            "antecedencia_minima_horas": 2,
                            "capacidade_total": 80,
                            "ativo": True,
                            "horarios": {},
                            "faq": {},
                            "cardapio": business_context,
                            "datas_especiais": []
                        }
        else:
            restaurant = await db.get_restaurant_by_whatsapp(restaurant_phone)
            
        if not restaurant:
            print(f"[AGENT] Restaurante/Agente NÃO encontrado para whatsapp_number={restaurant_phone!r}")
            return "Desculpe, não consegui identificar o agente ou restaurante. Tente novamente."

        rid = restaurant["id"]
        print(f"[AGENT] Restaurante/Agente={rid} ({restaurant['nome']})")


        try:
            await db.ensure_contact(user_phone, nome=profile_name)
        except Exception as e:
            print(f"[AGENT] ensure_contact falhou user={user_phone!r}: {e!r}")

        if await db.is_in_handoff(user_phone, rid):
            await db.save_message(user_phone, rid, "user", message)
            return None

        # ── Interceptor 12/06 — NUNCA chega à LLM nem às tools ──────
        # Carrega histórico ANTES do interceptor para detectar contexto.
        history_pre = await db.get_history(user_phone, rid, MAX_HISTORY)

        _trigger_namorados = (
            _mensagem_e_namorados(message)
            or _historico_tem_namorados(history_pre)
        )

        if _trigger_namorados:
            # Estado 2: assistente já perguntou o nome → captura e cria handoff
            if _em_captura_nome_namorados(history_pre):
                nome = message.strip().split()[0].capitalize() if message.strip() else "você"
                confirmacao = _MSG_NAMORADOS_CONFIRMACAO.format(nome=nome)
                motivo = f"Lead Dia dos Namorados (12/06) — nome: {nome}"
                hid = await db.create_handoff(user_phone, rid, motivo)
                print(f"[AGENT] Interceptor 12/06 Estado-2 nome={nome!r} hid={hid} user={user_phone!r}")
                team = await db.get_on_duty_team(rid)
                if team:
                    import notifications as notif_handoff
                    for m in team[:2]:
                        notif_handoff.notify_handoff(
                            m["whatsapp"], restaurant["nome"],
                            user_phone, motivo,
                            "\n".join(
                                f"{x['role']}: {x['content']}"
                                for x in history_pre[-4:]
                                if isinstance(x.get("content"), str)
                            )
                        )
                await db.save_message(user_phone, rid, "user", message)
                await db.save_message(user_phone, rid, "assistant", confirmacao)
                return confirmacao

            # Estado 1: primeira menção — pergunta o nome (sem handoff ainda)
            print(f"[AGENT] Interceptor 12/06 Estado-1 user={user_phone!r}")
            await db.save_message(user_phone, rid, "user", message)
            await db.save_message(user_phone, rid, "assistant", _MSG_NAMORADOS_CONCIERGE)
            return _MSG_NAMORADOS_CONCIERGE

        history = history_pre
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
                        # Segunda linha de defesa: bloqueia tools de reserva/proposta
                        # se a LLM tentar usar 12/06 apesar do interceptor.
                        if _tool_e_bloqueada_namorados(b.name, b.input):
                            print(f"[AGENT] BLOQUEADO tool={b.name!r} inputs={b.input!r} — dia dos namorados")
                            res = (
                                "Esta data não está disponível para reservas online. "
                                "Nossa concierge entrará em contato pessoalmente."
                            )
                        else:
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
