"""Agente Claude — carrega config do Supabase, totalmente async."""

import os, asyncio, anthropic
from datetime import datetime
import database as db
import tools as tool_fns

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 20
MAX_ITERATIONS = 6

TOOLS = [
    {"name":"verificar_disponibilidade","description":"Verifica disponibilidade para reserva. SEMPRE chame antes de fazer_reserva.",
     "input_schema":{"type":"object","properties":{"data":{"type":"string","description":"DD/MM/YYYY"},"hora":{"type":"string","description":"HH:MM"},"pessoas":{"type":"integer"}},"required":["data","hora","pessoas"]}},
    {"name":"fazer_reserva","description":"Cria reserva confirmada. Só use após verificar_disponibilidade ✅. Confirme dados com o cliente antes.",
     "input_schema":{"type":"object","properties":{"nome":{"type":"string"},"data":{"type":"string"},"hora":{"type":"string"},"pessoas":{"type":"integer"},"observacoes":{"type":"string"}},"required":["nome","data","hora","pessoas"]}},
    {"name":"consultar_reservas","description":"Lista reservas ativas do cliente.",
     "input_schema":{"type":"object","properties":{},"required":[]}},
    {"name":"cancelar_reserva","description":"Cancela reserva pelo código.",
     "input_schema":{"type":"object","properties":{"codigo_reserva":{"type":"string"}},"required":["codigo_reserva"]}},
    {"name":"transferir_para_humano","description":"Transfere para atendente. Use quando cliente pedir, reclamação grave, ou situação que você não resolve.",
     "input_schema":{"type":"object","properties":{"motivo":{"type":"string"}},"required":["motivo"]}},
]

def _build_prompt(r: dict) -> str:
    now = datetime.now()
    dias = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
    horarios = "\n".join(f"  {d}: {h}" for d,h in r.get("horarios",{}).items())
    faq = "\n".join(f"  {k}: {v}" for k,v in r.get("faq",{}).items())
    return f"""Você é o assistente do {r['nome']}, restaurante de alto padrão.

DATA E HORA: {now.strftime('%d/%m/%Y %H:%M')} ({dias[now.weekday()]})

RESTAURANTE
Nome: {r['nome']} | Endereço: {r['endereco']}
Horários:\n{horarios}

CARDÁPIO\n{r.get('cardapio','Consulte a equipe.')}

PERGUNTAS FREQUENTES\n{faq}

REGRAS
- Tom caloroso, sofisticado, direto — como maître experiente
- Nunca use listas numeradas ou bullets — fale como pessoa real
- Confirme dados antes de reservar
- Respostas curtas (WhatsApp)
- Nunca invente informações
- Máx. {r.get('capacidade_maxima_reserva',8)} pessoas via WhatsApp
- Antecedência mínima: {r.get('antecedencia_minima_horas',2)}h

CLASSIFICAÇÃO DE INTENÇÕES — CONTEXTOS ESPECIAIS
Além das categorias principais, identifique estes padrões:
- "Vocês aceitam/trabalham com X?" → informação geral (ex: eventos, grandes grupos, animais)
- "Queria saber se…", "Será que…" → identifique o objeto (cardápio, reserva, horário)
- Mensagens de confirmação ("Ok", "Entendi", "Valeu", "Obrigado") → agradecimento, responda brevemente
- Pedidos vagos de "informações" → pergunte especificamente o que desejam
- Propostas comerciais, parcerias, imprensa → informação geral + protocolo VIP (ver abaixo)
Se após 1 pergunta de clarificação ainda não identificar a intenção, responda com base na mais provável dado o histórico da conversa.

RESERVAS ACIMA DA CAPACIDADE ONLINE
Para grupos de {r.get('capacidade_maxima_reserva',8)+1} ou mais pessoas, OU reservas em datas especiais (feriados, Dia das Mães, Ano Novo, Réveillon):
1. Responda com entusiasmo: "Que ótimo! Para garantir a melhor experiência para grupos maiores, vou conectar você com nossa equipe de reservas."
2. Colete antes de transferir: nome completo, data e horário desejados, número exato de pessoas, ocasião especial se houver (aniversário, corporativo etc.), telefone de contato se ainda não tiver.
3. Chame transferir_para_humano com motivo estruturado: "Cliente [nome] solicita reserva para [N] pessoas em [data/hora]. Motivo: grupo grande / data especial. Tel: [telefone]."
Nunca tente usar verificar_disponibilidade ou fazer_reserva nessas situações.

PROTOCOLO VIP E PARCERIAS
Identifique e transfira imediatamente quando o cliente mencionar: influencer, criador de conteúdo, blog, canal, Instagram ou TikTok profissional, imprensa, matéria, reportagem, publicação, parceria, colaboração, divulgação, assessoria, evento corporativo, empresa ou team building.
Ao detectar:
1. Responda: "Que honra! Parcerias e colaborações especiais são tratadas diretamente pela nossa gestão. Vou conectar você agora mesmo."
2. Colete: nome e @ (Instagram/TikTok) ou veículo, tipo de proposta (conteúdo, evento, matéria), alcance/audiência se mencionarem, contato preferencial.
3. Chame transferir_para_humano com motivo: "VIP/Parceria — [nome/@] — [tipo de proposta] — alcance: [X] — contato: [telefone/email]."
Trate com prioridade e entusiasmo — essas oportunidades geram visibilidade para o restaurante."""

class RestaurantAgent:
    async def process(self, user_phone: str, restaurant_phone: str, message: str) -> str:
        restaurant = await db.get_restaurant_by_whatsapp(restaurant_phone)
        if not restaurant:
            return "Desculpe, não consegui identificar o restaurante. Tente novamente."

        rid = restaurant["id"]

        # Verifica se está em modo handoff
        if await db.is_in_handoff(user_phone, rid):
            await db.save_message(user_phone, rid, "user", message)
            return None  # main.py roteia para equipe

        history = await db.get_history(user_phone, rid, MAX_HISTORY)
        history.append({"role":"user","content":message})

        response_text = await self._run(
            system=_build_prompt(restaurant),
            messages=history,
            user_phone=user_phone,
            rid=rid,
        )

        if response_text and response_text.startswith("__HANDOFF__:"):
            motivo = response_text.replace("__HANDOFF__:","").strip()
            hid = await db.create_handoff(user_phone, rid, motivo)
            # notifica equipe (importado inline para evitar circular)
            team = await db.get_on_duty_team(rid)
            if team:
                import notifications as notif
                for m in team[:2]:  # notifica os 2 primeiros disponíveis
                    notif.notify_handoff(
                        m["whatsapp"], restaurant["nome"],
                        user_phone, motivo,
                        "\n".join(f"{x['role']}: {x['content']}" for x in history[-4:])
                    )
            response_text = (
                "Vou te conectar com um de nossos atendentes agora. 🙏\n"
                "Um momento, por favor."
            )

        await db.save_message(user_phone, rid, "user", message)
        await db.save_message(user_phone, rid, "assistant", response_text)
        return response_text

    async def _run(self, system, messages, user_phone, rid) -> str:
        msgs = list(messages)
        for _ in range(MAX_ITERATIONS):
            response = await asyncio.to_thread(
                client.messages.create,
                model=MODEL, max_tokens=1024,
                system=system, messages=msgs, tools=TOOLS,
            )
            if response.stop_reason == "end_turn":
                for b in response.content:
                    if hasattr(b,"text"):
                        return b.text
                return "Desculpe, tente novamente."
            if response.stop_reason == "tool_use":
                ac = [{"type":"text","text":b.text} if b.type=="text"
                      else {"type":"tool_use","id":b.id,"name":b.name,"input":b.input}
                      for b in response.content]
                msgs.append({"role":"assistant","content":ac})
                results = []
                for b in response.content:
                    if b.type == "tool_use":
                        res = await self._tool(b.name, b.input, user_phone, rid)
                        results.append({"type":"tool_result","tool_use_id":b.id,"content":res})
                msgs.append({"role":"user","content":results})
        return "Estou com dificuldades técnicas. Tente novamente."

    async def _tool(self, name, inputs, user_phone, rid) -> str:
        try:
            if name == "verificar_disponibilidade":
                return await tool_fns.verificar_disponibilidade(rid, inputs["data"], inputs["hora"], inputs["pessoas"])
            if name == "fazer_reserva":
                return await tool_fns.fazer_reserva(user_phone, rid, inputs["nome"], inputs["data"], inputs["hora"], inputs["pessoas"], inputs.get("observacoes",""))
            if name == "consultar_reservas":
                return await tool_fns.consultar_reservas(user_phone, rid)
            if name == "cancelar_reserva":
                return await tool_fns.cancelar_reserva(user_phone, inputs["codigo_reserva"])
            if name == "transferir_para_humano":
                return await tool_fns.transferir_para_humano(inputs["motivo"])
            return f"Tool desconhecida: {name}"
        except Exception as e:
            return f"Erro: {e}"
