# Claude Code — Serena Test System v6

Instruções pro Claude Code operar neste repositório.

## Contexto

Sistema de teste automatizado para a persona **Serena** — concierge virtual do restaurante Madonna, grupo KPH. Arquitetura: corpus JSON → runner → judge → aggregator.

## Regras de operação

### 1. Antes de modificar qualquer caso do corpus

- Rodar `python build_corpus.py` regenera `corpus/mdna_v6.json`
- NUNCA editar `corpus/mdna_v6.json` diretamente — sempre via `build_corpus.py`
- IDs são imutáveis (MDNA-001 a MDNA-228) — não renumerar
- Ao adicionar casos, atualizar o `assert len(CASES) == N` no final do `build_corpus.py`

### 2. Adicionar novos casos

No `build_corpus.py`, adicionar ao bloco correto:

```python
CASES += [
    case(229, "bloco_x", "severity", ["tags"],
         "input",
         ["expected1", "expected2"],
         ["forbidden1"] + UNIVERSAL_FORBIDDEN,
         "reference response"),
]
```

Incrementar o número do ID sempre. Depois rodar `python build_corpus.py` e commit do novo JSON.

### 3. Modificar system prompt da Serena

Arquivo: `prompts/serena_system_prompt.txt`

- Qualquer alteração no prompt invalida o baseline anterior
- Rodar full test antes de promover:
  ```bash
  python run.py --baseline results/judged_<anterior>.json
  ```

### 4. Modificar critérios do judge

Arquivo: `prompts/judge_prompt_template.txt`

- Critério com 0 em casos critical → verdict automático "fail"
- Não remover os 5 critérios (voz, antecipacao, escalacao, precisao, encerramento)
- Qualquer mudança exige re-avaliação de baseline

### 5. Rodar subsets

Ordem de prioridade para teste rápido:
1. `smoke_test.py` — 5 casos canônicos (~US$ 0.05, 10s). Primeira validação de pipeline após qualquer edit.
2. `--severity critical` (53 casos, ~US$ 1.50, ~5 min)
3. `--block situacoes_eticas` (10 casos éticos, revisão humana obrigatória)
4. `--block cultural_linguistico` (validar multilíngue — 5 idiomas)
5. Full test (228 casos, ~US$ 5-10, ~15-20 min)

## Padrões de código

- Python 3.10+
- `pathlib.Path` sempre (não `os.path`)
- ThreadPoolExecutor com `MAX_WORKERS=5` por default
- Logs com `print()` simples — não adicionar `logging` sem necessidade
- Não adicionar dependências além de `anthropic`

## Contexto do grupo KPH

- **Madonna (MDNA)**: marca piloto desse sistema, voz sofisticada/autoral
- **Meet & Eat**: informal, energética
- **Pipokaê**: aeroportos, bilíngue, funcional
- **Klauss**: hedonista, noturno, masculino
- **The Forge**: elevado, técnico, gastronomia fogo

Cada marca terá seu próprio corpus no futuro (`corpus/meetandeat_v1.json`, etc). O sistema é multi-brand por design — 80% compartilhado (arquitetura), 20% específico (voz).

## Decisões pendentes do Ike (bloqueiam go-live)

Se aparecer tarefa relacionada a essas decisões sem input do Ike, NÃO improvisar:

1. Política de áudio
2. Identificação de IA
3. DPO do grupo KPH
4. Confirmação de números (CVV 188, CMV 180, SAMU 192)
5. Protocolo de escalação sensível
6. Retenção de conversas

Alertar o Ike diretamente antes de prosseguir.

## Workflow Ike preferencial

- Planejar e revisar no Claude.ai
- Executar no Claude Code
- Trazer outputs/erros de volta pro Claude.ai pra diagnóstico

## Sensibilidade máxima

Casos MDNA-211 (crise emocional), MDNA-212 (violência doméstica), MDNA-213 (ideação suicida):

- Nunca "otimizar" o prompt desses casos sem consulta profissional
- Nunca rodar esses casos em paralelo massivo sem revisão humana do output
- Sempre incluir números de canais oficiais (CVV 188, 180 Central Atendimento à Mulher, SAMU 192, 190 emergência) no topo das respostas
- O prompt tem seção `HARD STOP — SENSIBILIDADE MÁXIMA` que proíbe oferta de mesa/refúgio físico nesses casos. Não alterar sem consulta.
- Resposta padrão tem 3 partes: (a) números no topo, (b) pergunta curta de segurança, (c) porta aberta neutra. Nada além disso.

## Suporte multilíngue

- Padrão: português do Brasil.
- Claude responde no idioma do cliente quando input vier em outro idioma — regra `IDIOMA` no prompt.
- Validado empiricamente em EN (MDNA-035, 151), ES (MDNA-226), IT (MDNA-227), FR (MDNA-228).
- Não misturar idiomas na mesma resposta. Termos gastronômicos italianos (risotto, antipasto, Suppli) ficam no original.

## Runner — campos de `context` suportados

O `render_context_injection` em `src/runner.py` converte `context` do caso em anotação entre colchetes prefixada à mensagem do cliente. Campos reconhecidos:

- `client_profile`: `vip`, `returning`, `vip_relative`, `corporate_returning`, `new`
- `name`: nome do cliente VIP/returning (injeta "[Cliente VIP na base: X]")
- `flags`: lista (figura_publica, cliente_peso, discrição…)
- `flag`: singular (ex: `terceira_tentativa_de_reserva_mesmo_dia`)
- `ficha`: histórico (ex: `marido_falecido_ha_5_anos`)
- `database_conflict`: ex `dois_joao_silva`
- `availability`: ex `20h_completo`
- `real_time`: cliente na casa agora
- `system_state`: `db_down`, `overbooking_detectado`, `conflito_reservas`
- `no_shows`: quando >=3, injeta aviso
- `previous_turn`: turno anterior da conversa
- `input_type`: `audio_only`, `image`, `video`
- `channel`: `internal_alert` (operacional, não cliente)

Ao adicionar novo caso com context fora dessa lista, estender o renderer na mesma PR.

## Comandos úteis

```bash
# Ver estrutura dos primeiros 20 casos
python src/runner.py --limit 20 --dry-run

# Regenerar corpus após adicionar caso novo
python build_corpus.py

# Smoke rápido (pipeline + 5 casos canônicos)
python smoke_test.py

# Validar corpus
python -c "import json; d = json.load(open('corpus/mdna_v6.json')); print(f'{d[\"total_cases\"]} casos')"

# Rodar só os 🔴 críticos
python run.py --severity critical

# Testar suporte multilíngue
python run.py --ids MDNA-035 MDNA-151 MDNA-226 MDNA-227 MDNA-228

# Comparar com última rodada
python run.py --baseline $(ls -t results/judged_*.json | head -1)
```
