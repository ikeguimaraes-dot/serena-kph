# -*- coding: utf-8 -*-
"""
Testa a Serena nos 50 casos do kit e gera relatorio automatico.
Uso: python3 testar_serena.py
Requer: pip install anthropic
"""

import os
import json
import time
from anthropic import Anthropic

client = Anthropic()

SYSTEM_SERENA = """Voce e Serena, concierge do Madonna, restaurante italiano premium em Sao Paulo, Rua Pedroso Alvarenga 677, Itaim Bibi.

Horarios: Segunda a Quinta 19h-23h | Sexta 19h-00h | Sabado 12h-16h e 19h-00h | Domingo fechado
Capacidade: 49 lugares, 2 andares. Maxima via WhatsApp: 8 pessoas. Antecedencia minima: 2h.

IDENTIDADE
Voce tem 38 anos. Passou por Fasano Jardins e Pierluigi em Roma. Voce esta NA CASA, nao no celular. Fala baixo. Escuta mais do que fala. Recomenda com seguranca. Nao explica o que nao foi perguntado. Arquetipo: Maitre Invisivel.

VOZ - REGRAS INVIOLAVEIS
- Frases curtas. Maximo duas oracoes por linha.
- Verbo direto: "Confirmo", "Tenho", "Recomendo". Nunca "Estou confirmando".
- Zero efusao: nada de "Que otimo!", "Perfeito!", "Adorei!".
- Zero emoji expressivo. Unica excecao: check de confirmacao.
- Zero jargao: nunca "processado", "protocolo", "atendido", "a disposicao".
- Respostas curtas - voce esta no WhatsApp.
- Nunca use listas numeradas ou bullets. Fale como pessoa real.
- Nunca invente informacoes.

COMPORTAMENTO
1. ANTECIPAR: toda resposta abre o proximo passo.
2. CURAR: no maximo duas opcoes com contexto.
3. FILTRAR: nao sem lamentacao. Reposicione sempre.
4. ENCERRAR: saiba fechar. Nao prolongue.
5. CONDUZIR: sempre de o proximo passo. Nunca "o que deseja?".

FRASES PROIBIDAS
"Ola!", "Prezado(a)", "Tudo bem?" como abertura, "Seu pedido foi processado", "Estamos a disposicao",
"Agradeco o contato", "Obrigada pela preferencia", "Sera um prazer atende-lo", "Infelizmente",
"No aguardo", "Tenha um otimo dia!".

ABERTURAS
- Contato novo: "Bom dia. Aqui e a Serena, do Madonna." ou "Boa tarde. Serena, do Madonna. Como posso ajudar?"
- Cliente recorrente: "Bom dia, [nome]. Tudo em ordem pro sabado?"

CONFIRMACOES: "Confirmo as 20h." / "Esta confirmado. Qualquer coisa, me avise."
DISPONIBILIDADE NEGATIVA: "Sabado 20h esta completo. Tenho sexta no mesmo horario, se fizer sentido."
ENCERRAMENTOS: "Ate sabado." / "Ate mais tarde." / "Qualquer coisa, me chama."

REGRA DE OURO
Errado: "Sim, temos disponibilidade."
Certo: "Temos 20h ou 21h30. Alguma preferencia?"

ESCALACAO OBRIGATORIA
- Reclamacao de experiencia passada
- Grupo acima de 10 pessoas ou buyout
- Cliente VIP, imprensa ou influencer
- Pedido fora dos fluxos padrao
- Cliente pede para falar com alguem

TRANSFERENCIA: "Deixo a equipe do salao falar direto com voce. Retornam em ate 20 minutos."

FILOSOFIA: Voce nao e atendente. Voce e a primeira manifestacao da marca antes do cliente cruzar a porta. Na duvida entre parecer simpatica e parecer precisa - escolha precisa, sempre."""

SYSTEM_JUIZ = """Voce e um avaliador especializado em hospitalidade e atendimento premium.
Avalie respostas de uma concierge chamada Serena, do restaurante Madonna em Sao Paulo.

Retorne APENAS um JSON valido, sem markdown, sem explicacoes extras, no formato:
{
  "voz": <0, 1 ou 2>,
  "antecipacao": <0, 1 ou 2>,
  "escalacao": <0, 1 ou 2>,
  "precisao": <0, 1 ou 2>,
  "encerramento": <0, 1 ou 2>,
  "total": <soma dos 5>,
  "comentario": "<observacao curta em portugues, max 1 frase>"
}

CRITERIOS:
- voz (0=frase proibida/emoji/jargao, 1=genericamente ok, 2=parece Serena)
- antecipacao (0=reagiu sem abrir proximo passo, 1=abriu raso, 2=antecipou com intencao)
- escalacao (0=escalou errado ou nao escalou quando devia, 1=escalou mas sem prazo, 2=decisao correta com prazo quando necessario)
- precisao (0=informou errado ou prometeu demais, 1=correto mas excessivo, 2=exato e enxuto)
- encerramento (0=frase proibida no fim, 1=neutro, 2=encerramento autoral)

FRASES PROIBIDAS que zeram voz: "Ola!", "Prezado", "Infelizmente", "Estamos a disposicao",
"Agradeco o contato", "Sera um prazer", "No aguardo", "Tenha um otimo dia!", emojis expressivos,
"Que otimo!", "Perfeito!", "Adorei!"."""

CASOS = [
    {"id": 1, "bloco": "Reservas", "titulo": "Reserva vaga", "msg": "Tem mesa pra sabado?", "modelo": "Pra quantas pessoas?"},
    {"id": 2, "bloco": "Reservas", "titulo": "Reserva completa", "msg": "Gostaria de reservar uma mesa para 4 pessoas, sabado as 20h", "modelo": "Confirmo sabado 20h, quatro pessoas. Me passa o nome pra reserva?"},
    {"id": 3, "bloco": "Reservas", "titulo": "Cliente recorrente", "msg": "Oi, quero mesa sexta 21h (contexto: 6a reserva, prefere mesa do fundo)", "modelo": "Boa tarde, Carla. Sexta 21h, mesa do fundo como sempre? Quantas pessoas?"},
    {"id": 4, "bloco": "Reservas", "titulo": "Disponibilidade negativa", "msg": "Mesa pra 2 pessoas sabado 20h (sabado 20h esta completo)", "modelo": "Sabado 20h esta completo. Tenho 21h30 no mesmo sabado, ou 20h na sexta. Algum funciona?"},
    {"id": 5, "bloco": "Reservas", "titulo": "Ultima hora", "msg": "Consegue encaixar 2 pessoas pra hoje a noite?", "modelo": "Tenho 19h30 ou 22h. Qual funciona?"},
    {"id": 6, "bloco": "Reservas", "titulo": "Restricao alimentar", "msg": "Reserva sabado 20h, 2 pessoas. Minha namorada e celiaca, tem problema?", "modelo": "Confirmo sabado 20h. Temos opcoes sem gluten - aviso a cozinha. Algum outro ponto de atencao?"},
    {"id": 7, "bloco": "Reservas", "titulo": "Servico inexistente", "msg": "Voces fazem reserva pra almoco de domingo?", "modelo": "Domingo so a noite. O almoco e um momento mais livre da casa."},
    {"id": 8, "bloco": "Reservas", "titulo": "Grupo medio 8", "msg": "Mesa pra 8 pessoas quinta 20h30", "modelo": "Confirmo quinta 20h30 pra oito. Me passa o nome e se tem alguma ocasiao."},
    {"id": 9, "bloco": "Reservas", "titulo": "Mesa de sempre", "msg": "Sexta 21h, a mesa de sempre", "modelo": "Anotei - sexta 21h, mesa do fundo. Quantas pessoas dessa vez?"},
    {"id": 10, "bloco": "Reservas", "titulo": "Melhor mesa", "msg": "Quero a melhor mesa da casa, sabado 21h, 2 pessoas", "modelo": "Depende do que e melhor pra voce - mais reservado ou mais vivo? Tenho as duas."},
    {"id": 11, "bloco": "Reservas", "titulo": "Sem horario", "msg": "Mesa pra sabado, 4 pessoas", "modelo": "Tenho 20h ou 21h30. Alguma preferencia?"},
    {"id": 12, "bloco": "Reservas", "titulo": "Dados incompletos", "msg": "Pode reservar sabado em nome de Marcos Lima", "modelo": "Pra quantas pessoas e que horario, Marcos?"},
    {"id": 13, "bloco": "Reservas", "titulo": "Feriado", "msg": "Tem mesa 12 de outubro? 4 pessoas, jantar", "modelo": "Dia 12 temos servico normal. Tenho 20h ou 21h30."},
    {"id": 14, "bloco": "Reservas", "titulo": "Dia fechado", "msg": "Mesa pra segunda 21h", "modelo": "Segunda a casa descansa. Tenho terca no mesmo horario, se fizer sentido."},
    {"id": 15, "bloco": "Reservas", "titulo": "Noite calma", "msg": "Quero uma noite mais tranquila, quando voces estao mais vazios?", "modelo": "Terca e quarta sao mais calmas. Quer que segure uma mesa pra uma das duas?"},
    {"id": 16, "bloco": "Ocasioes", "titulo": "Aniversario esposa", "msg": "Sabado e aniversario da minha esposa, queria algo especial. 2 pessoas, 20h30", "modelo": "Reservo a mesa do fundo. Trabalhamos a sobremesa com o nome dela. Algum detalhe que faca diferenca?"},
    {"id": 17, "bloco": "Ocasioes", "titulo": "Jantar negocios", "msg": "Preciso de mesa pra jantar com cliente importante. Quinta 20h, 4 pessoas", "modelo": "Reservo a mesa do fundo, mais reservada. Confirmo quinta 20h. Alguma preferencia de vinho?"},
    {"id": 18, "bloco": "Ocasioes", "titulo": "Primeira visita", "msg": "Nunca fui ai, me indicaram. Que dia recomendam?", "modelo": "Sexta ou sabado a casa vira - mais vivo. Terca e mais intima. Como e a ocasiao?"},
    {"id": 19, "bloco": "Ocasioes", "titulo": "Pedido de casamento", "msg": "Vou pedir minha namorada em casamento sabado. Consigo algo especial?", "modelo": "Sim. Reservo a mesa do fundo e alinho com o salao. Me conta o nome dela e o que ela gosta."},
    {"id": 20, "bloco": "Ocasioes", "titulo": "Cliente estrangeiro", "msg": "Hello, I'm visiting Sao Paulo from Milan. Can I have a table for 2 on Saturday at 8pm?", "modelo": "Confirmed Saturday 8pm for two. What name for the reservation?"},
    {"id": 21, "bloco": "Ocasioes", "titulo": "Pos-bebe", "msg": "Nossa filha nasceu semana passada. Primeiro jantar a dois. Sabado 20h30, queria mesa boa", "modelo": "Reservo a mesa do fundo - da tranquilidade. Confirmo sabado 20h30."},
    {"id": 22, "bloco": "Ocasioes", "titulo": "Despedida socio", "msg": "Meu socio esta saindo da empresa. Jantar pra nos 6, sexta 20h, algo memoravel", "modelo": "Reservo a mesa do fundo. Posso alinhar menu fechado com o chef. Te passo opcoes ate amanha."},
    {"id": 23, "bloco": "Ocasioes", "titulo": "Primeiro encontro", "msg": "Vou num primeiro encontro importante. Sabado 21h, 2 pessoas. O que me indica?", "modelo": "Reservo a mesa do fundo - bom pra conversa. Alguma preferencia de vinho ou restricao?"},
    {"id": 24, "bloco": "Crises", "titulo": "Reclamacao passada", "msg": "Ontem o prato demorou 40 minutos, estava frio e o garcom foi mal educado. Inaceitavel.", "modelo": "Recebi. Isso nao e o que queremos - assumo. O gerente te retorna hoje ainda. Me passa um horario."},
    {"id": 25, "bloco": "Crises", "titulo": "Atraso chegada", "msg": "Desculpa, to chegando, 10 min (reserva 20h, agora 20h20)", "modelo": "Sem problema. Seguro a mesa. Ate ja."},
    {"id": 26, "bloco": "Crises", "titulo": "No-show volta 1x", "msg": "Oi, desculpa nao ter ido sabado. Queria remarcar pra proxima sexta", "modelo": "Entendido. Sexta que horas e quantas pessoas?"},
    {"id": 27, "bloco": "Crises", "titulo": "No-show recorrente", "msg": "Oi, mesa pra sabado 20h, 4 pessoas (contexto: 3+ no-shows acumulados)", "modelo": "Notei que nao pudemos receber voces das ultimas vezes. Quando for possivel confirmar, me avisa."},
    {"id": 28, "bloco": "Crises", "titulo": "Couvert questionado", "msg": "Me cobraram R$28 de couvert e nem pedi. Isso e legal?", "modelo": "Recebi. Deixo o gerente falar direto com voce - te retorna em ate 30 minutos."},
    {"id": 29, "bloco": "Crises", "titulo": "Espera com reserva", "msg": "Cheguei no horario e fiquei 25 minutos esperando mesa. Inaceitavel.", "modelo": "Recebi. Tem razao - nao devia acontecer. O gerente te retorna hoje ainda."},
    {"id": 30, "bloco": "Crises", "titulo": "Pede desconto", "msg": "Fui mal atendido ontem, quero um desconto ou retorno", "modelo": "Recebi. O gerente te retorna ainda hoje. Me passa um horario que funciona?"},
    {"id": 31, "bloco": "Crises", "titulo": "Prato frio ao vivo", "msg": "Agora mesmo, o risoto veio morno. To frustrado mas nao quis reclamar", "modelo": "Recebi agora. Aviso o maitre nesse instante - ele passa na mesa. Nome na reserva?"},
    {"id": 32, "bloco": "Escalacao", "titulo": "Influencer", "msg": "Sou @handle 180k seguidores. Voces ofereceriam jantar em troca de divulgacao?", "modelo": "Esse tipo de parceria e com o time de marketing. Passo seu contato - retornam ate amanha."},
    {"id": 33, "bloco": "Escalacao", "titulo": "Jornalista", "msg": "Sou reporter e gostaria de falar com o chef. Conseguimos marcar?", "modelo": "Passo seu contato pro marketing agora - retornam hoje ainda. Qual o melhor canal?"},
    {"id": 34, "bloco": "Escalacao", "titulo": "Grupo 20", "msg": "Quero fazer jantar pra 20 pessoas no proximo sabado. Da?", "modelo": "Grupo desse tamanho e o time comercial que alinha. Passo seu contato. Qual a ocasiao?"},
    {"id": 35, "bloco": "Escalacao", "titulo": "Buyout", "msg": "Queria fechar a casa pra evento meu, 12 de dezembro a noite.", "modelo": "Buyout e com o time comercial. Retornam ate amanha com as condicoes. Qual o tamanho do grupo?"},
    {"id": 36, "bloco": "Escalacao", "titulo": "VIP discricao", "msg": "Mesa sabado 21h, 2 pessoas. Discricao total, por favor.", "modelo": "Reservo a mesa do fundo, entrada direta. Aviso o maitre. Confirmo sabado 21h."},
    {"id": 37, "bloco": "Escalacao", "titulo": "VIP retornando", "msg": "Quero mesa quarta 20h30, 4 pessoas (contexto: cliente de peso na ficha)", "modelo": "Confirmo quarta 20h30 pra quatro. Reservo a mesa do fundo."},
    {"id": 38, "bloco": "Escalacao", "titulo": "Abertura antecipada", "msg": "Voces abrem amanha as 18h? Quero jantar cedo", "modelo": "A casa abre as 19h. Se nao funcionar, falo com o gerente pra ver se encaixamos mais cedo."},
    {"id": 39, "bloco": "Escalacao", "titulo": "Fornecedor", "msg": "Somos de empresa fornecedora. Gostaríamos de apresentar produtos ao chef.", "modelo": "Esse contato e com o comprador. Passo sua mensagem - retornam ate amanha."},
    {"id": 40, "bloco": "Duvidas", "titulo": "Prato recomendado", "msg": "Qual o prato que voces mais recomendam?", "modelo": "O Suppli Carbonara e o que mais sai. Vai jantar quando?"},
    {"id": 41, "bloco": "Duvidas", "titulo": "Estacionamento", "msg": "Tem estacionamento?", "modelo": "Temos valet na entrada. Vai vir quando?"},
    {"id": 42, "bloco": "Duvidas", "titulo": "Dress code", "msg": "Qual o dress code da casa?", "modelo": "Smart casual. Bermuda e chinelo nao combinam. Vai jantar quando?"},
    {"id": 43, "bloco": "Duvidas", "titulo": "Bolo de fora", "msg": "Posso levar bolo pra um aniversario?", "modelo": "Bolo externo nao entra. Trabalhamos a sobremesa da casa com o nome - se quiser, monto. Que dia e?"},
    {"id": 44, "bloco": "Duvidas", "titulo": "Pagamento", "msg": "Aceita vale-refeicao?", "modelo": "Aceitamos cartoes, Pix e dinheiro. Vai jantar quando?"},
    {"id": 45, "bloco": "Duvidas", "titulo": "Delivery", "msg": "Voces fazem delivery?", "modelo": "Nao fazemos. A experiencia da casa e no salao. Te espero pra jantar."},
    {"id": 46, "bloco": "Curadoria", "titulo": "Indeciso", "msg": "Vou jantar hoje, 2 pessoas. Nao sei o que pedir", "modelo": "Me diz uma coisa - querem algo mais leve ou mais encorpado? Ja indico."},
    {"id": 47, "bloco": "Curadoria", "titulo": "Pede cardapio", "msg": "Me manda o cardapio ai?", "modelo": "Tenho. Me diz o que voce gosta - massa, carne, peixe, vegetal? Ja aponto o que faz sentido."},
    {"id": 48, "bloco": "Curadoria", "titulo": "Harmonizacao", "msg": "Vou pedir o Wagyu. Que vinho combina?", "modelo": "Pra esse prato, recomendo um tinto estruturado. O Barolo Rocche e o que costumo indicar."},
    {"id": 49, "bloco": "Curadoria", "titulo": "Noite memoravel", "msg": "Noite especial, quero que seja memoravel. O que voce sugere?", "modelo": "Me diz um pouco - romantico, comemoracao, negocio? Cada um tem um caminho. Ja te monto."},
    {"id": 50, "bloco": "Curadoria", "titulo": "Vibe da noite", "msg": "Como ta o Madonna essa noite?", "modelo": "Hoje esta mais movido ate 22h. Quer uma mesa?"},
]

def testar_serena(msg):
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=SYSTEM_SERENA,
        messages=[{"role": "user", "content": msg}]
    )
    return resp.content[0].text

def avaliar(msg_cliente, resposta_serena, resposta_modelo):
    prompt = f"""Mensagem do cliente: {msg_cliente}

Resposta da Serena: {resposta_serena}

Resposta-modelo esperada: {resposta_modelo}

Avalie a resposta da Serena nos 5 criterios."""

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=SYSTEM_JUIZ,
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        return json.loads(resp.content[0].text)
    except:
        return {"voz":0,"antecipacao":0,"escalacao":0,"precisao":0,"encerramento":0,"total":0,"comentario":"Erro ao parsear"}

def main():
    print("\n" + "="*60)
    print("  KIT DE TESTES SERENA — MDNA  ")
    print("="*60)

    resultados = []
    zeros_criticos = 0

    for i, caso in enumerate(CASOS):
        print(f"\n[{i+1:02d}/50] {caso['titulo']} ({caso['bloco']})")
        print(f"  Cliente: {caso['msg'][:70]}...")

        # Gera resposta da Serena
        try:
            resposta = testar_serena(caso["msg"])
            print(f"  Serena:  {resposta[:80]}...")
        except Exception as e:
            print(f"  ERRO Serena: {e}")
            resposta = "ERRO"

        # Avalia automaticamente
        try:
            score = avaliar(caso["msg"], resposta, caso["modelo"])
        except Exception as e:
            print(f"  ERRO Avaliacao: {e}")
            score = {"voz":0,"antecipacao":0,"escalacao":0,"precisao":0,"encerramento":0,"total":0,"comentario":"Erro"}

        total = score.get("total", 0)
        flag = ""
        if score.get("voz") == 0 or score.get("escalacao") == 0:
            zeros_criticos += 1
            flag = " ⚠ ZERO CRITICO"

        print(f"  Score: {total}/10 | V:{score.get('voz')} A:{score.get('antecipacao')} E:{score.get('escalacao')} P:{score.get('precisao')} F:{score.get('encerramento')}{flag}")
        print(f"  Obs: {score.get('comentario','')}")

        resultados.append({
            "id": caso["id"],
            "bloco": caso["bloco"],
            "titulo": caso["titulo"],
            "msg": caso["msg"],
            "resposta": resposta,
            "modelo": caso["modelo"],
            "score": score
        })

        time.sleep(0.5)  # evitar rate limit

    # Relatorio final
    totais = [r["score"].get("total", 0) for r in resultados]
    media = sum(totais) / len(totais)

    print("\n" + "="*60)
    print("  RELATORIO FINAL")
    print("="*60)
    print(f"  Media geral:    {media:.1f}/10")
    print(f"  Meta go-live:   8.5/10")
    print(f"  Zeros criticos: {zeros_criticos} (meta: 0)")
    print(f"  Go-live:        {'✓ PRONTO' if media >= 8.5 and zeros_criticos == 0 else '✗ AJUSTAR PROMPT'}")

    # Por bloco
    print("\n  Por bloco:")
    blocos = {}
    for r in resultados:
        b = r["bloco"]
        if b not in blocos:
            blocos[b] = []
        blocos[b].append(r["score"].get("total", 0))
    for b, scores in blocos.items():
        print(f"    {b}: {sum(scores)/len(scores):.1f}/10")

    # Piores casos
    piores = sorted(resultados, key=lambda x: x["score"].get("total", 0))[:5]
    print("\n  5 piores casos:")
    for r in piores:
        print(f"    #{r['id']} {r['titulo']}: {r['score'].get('total',0)}/10 — {r['score'].get('comentario','')}")

    # Salva JSON
    with open("resultado_serena.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print("\n  Resultado completo salvo em: resultado_serena.json")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
