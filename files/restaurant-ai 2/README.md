# Restaurant AI — WhatsApp

Sistema de atendimento inteligente via WhatsApp para múltiplas unidades de restaurante.  
Powered by **Anthropic Claude** com tool use nativo.

---

## O que o sistema faz

- Faz, consulta e cancela **reservas** via conversa natural
- Verifica **disponibilidade** em tempo real
- Responde **dúvidas** (cardápio, horários, estacionamento, políticas)
- Mantém **histórico de conversa** por cliente por unidade
- Suporta **múltiplas unidades** — cada número WhatsApp = um restaurante
- **Transfere para humano** quando necessário

---

## Arquitetura

```
WhatsApp (cliente)
      ↓
   Twilio (canal oficial Meta)
      ↓
   FastAPI /webhook/whatsapp        ← main.py
      ↓
   RestaurantAgent                  ← agent.py
      ├── Histórico de conversa     ← database.py
      ├── System prompt por unidade ← restaurants.py
      └── Claude + Tool Use
             ├── verificar_disponibilidade
             ├── fazer_reserva
             ├── consultar_reservas
             ├── cancelar_reserva
             └── transferir_para_humano ← tools.py
```

---

## Setup em 5 passos

### 1. Clonar e instalar dependências

```bash
git clone <seu-repo>
cd restaurant-ai
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite .env e coloque sua ANTHROPIC_API_KEY
```

Obtenha sua chave em: https://console.anthropic.com

### 3. Configurar os restaurantes

Edite `restaurants.py` e preencha cada unidade com:
- Número WhatsApp Business (chave do dicionário)
- Nome, endereço, horários
- Cardápio resumido
- FAQ da unidade

### 4. Configurar o Twilio (WhatsApp)

1. Crie conta em https://twilio.com
2. Ative o **WhatsApp Business** (sandbox para testes, número real para produção)
3. Para cada unidade, aponte o webhook para:
   ```
   https://seu-dominio.com/webhook/whatsapp
   ```
4. Por que Twilio? É parceiro oficial Meta — sem risco de ban, suporte real, escalável.

### 5. Rodar

```bash
python main.py
```

Para expor localmente durante desenvolvimento:
```bash
# Instale o ngrok: https://ngrok.com
ngrok http 8000
# Use a URL gerada no webhook do Twilio
```

---

## Estrutura de arquivos

```
restaurant-ai/
├── main.py          # FastAPI + webhook Twilio
├── agent.py         # Agente Claude com tool use e memória
├── tools.py         # Lógica de negócio (reservas, cancelamentos)
├── database.py      # SQLite — histórico e reservas
├── restaurants.py   # Configuração multi-unidade
├── requirements.txt
└── .env.example
```

---

## Integrando com seu sistema de reservas atual

No `tools.py`, as funções `fazer_reserva`, `consultar_reservas` e `cancelar_reserva`  
hoje usam o banco SQLite interno. Para conectar ao seu sistema:

```python
# tools.py — exemplo de integração via API REST
import httpapi

def fazer_reserva(user_phone, restaurant_id, nome, data, hora, pessoas, observacoes=""):
    r = httpapi.post("https://seu-sistema.com/api/reservas", json={
        "restaurante": restaurant_id,
        "nome": nome,
        "data": data,
        "hora": hora,
        "pessoas": pessoas,
        "obs": observacoes,
    }, headers={"Authorization": f"Bearer {SEU_TOKEN}"})
    
    if r.status_code == 201:
        codigo = r.json()["codigo"]
        return f"Reserva confirmada ✅ Código: {codigo}"
    return "Não foi possível confirmar a reserva. Tente novamente."
```

---

## Escalando para produção

| Aspecto | Recomendação |
|---|---|
| Banco de dados | Migre SQLite → PostgreSQL (mudar `DB_PATH` + adapter) |
| Deploy | Railway, Render, ou VPS própria |
| Múltiplos workers | `uvicorn main:app --workers 4` |
| Monitoramento | Adicione logs estruturados (loguru) |
| Notificações de handoff | Slack / email no bloco `__HANDOFF__` em `main.py` |

---

## Adicionando uma nova unidade

1. Abra `restaurants.py`
2. Adicione uma nova entrada no dicionário `RESTAURANTS` com o número WhatsApp da unidade
3. Configure o webhook no Twilio para esse número
4. Pronto — zero código adicional

---

## Licença

MIT
