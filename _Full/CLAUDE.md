# Claude Code — Serena Test System v6

## Convenção de versionamento do prompt

**Três regras, sem exceção:**

1. **Arquivo imutável por versão:** ao finalizar um set coeso de edits, salvar como `prompts/serena_system_prompt_v<N>.txt`. O `serena_system_prompt.txt` (current) fica sempre igual ao último vN.

2. **Notificação obrigatória:** encerrar a mensagem com a linha literal:
   `📌 VERSION BUMP: serena_system_prompt_v<N>.txt — <diff summary 1 linha>`
   Isso permite buscar "VERSION BUMP" e rastrear toda a história sem ler a conversa.

3. **vN só sobe com justificativa real:** edit de prompt, mudança em HARD STOP, novos protocolos. Ajustes cosméticos ficam no mesmo vN.

**Utilitário:**
```bash
python src/version_prompt.py list              # lista versões salvas
python src/version_prompt.py diff v9 v10       # diff entre duas versões
python src/version_prompt.py save v10          # copia current → _v10.txt + atualiza VERSION
python src/version_prompt.py current           # mostra qual versão o current aponta
```

**Workflow de edição:**
```bash
# 1. Edita prompts/serena_system_prompt.txt
# 2. Salva a versão imutável
python src/version_prompt.py save v10
# 3. Valida
python smoke_test.py
python run.py --severity critical
# 4. Notifica com a linha de VERSION BUMP na mensagem
```

---

## ⚠️ LOCK v8 — LEIA ANTES DE EDITAR QUALQUER COISA

**v8 é o baseline congelado.** Qualquer edição no prompt, corpus ou infra é v9+.

Regras de lock:
1. Qualquer edit em `prompts/serena_system_prompt.txt` → rodar `python version_prompt.py -m "descrição"` ANTES
2. Qualquer edit no corpus → rodar `python build_corpus.py` e commitar o JSON gerado
3. Qualquer alteração que afete critérios do judge → invalidar `results/baseline_v8.json` e gerar novo baseline
4. `results/baseline_v8.json` é referência — não sobrescrever sem antes copiar como backup

Workflow obrigatório para v9+:
```
1. python smoke_test.py                          # confirma que baseline não quebrou
2. [faz a edição]
3. python version_prompt.py -m "o que mudou"    # registra no histórico
4. python run.py --severity critical             # valida
5. python run.py                                 # full run se critical limpo
6. cp results/judged_<novo>.json results/baseline_v8.json  # atualiza baseline
```


Instruções pro Claude Code operar neste repositório.

## Contexto

Sistema de teste automatizado para a persona **Serena** — concierge virtual do restaurante Madonna, grupo KPH. Arquitetura: corpus JSON → runner → judge → aggregator.

## Regras de operação

### 1. Antes de modificar qualquer caso do corpus

- Rodar `python build_corpus.py` regenera `corpus/mdna_v6.json`
- NUNCA editar `corpus/mdna_v6.json` diretamente — sempre via `build_corpus.py`
- IDs são imutáveis (MDNA-001 a MDNA-225) — não renumerar

### 2. Adicionar novos casos

No `build_corpus.py`, adicionar ao bloco correto:

```python
CASES += [
    case(226, "bloco_x", "severity", ["tags"],
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
1. `--severity critical` (53 casos, ~US$ 1.50, ~5 min)
2. `--block situacoes_eticas` (10 casos éticos, revisão humana obrigatória)
3. Full test (225 casos, ~US$ 5-10, ~15-20 min)

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
- Sempre incluir números de canais oficiais (CVV, CMV, SAMU) no topo das respostas

## Comandos úteis

```bash
# Ver estrutura dos primeiros 20 casos
python src/runner.py --limit 20 --dry-run

# Regenerar corpus após adicionar caso novo
python build_corpus.py

# Validar corpus
python -c "import json; d = json.load(open('corpus/mdna_v6.json')); print(f'{d[\"total_cases\"]} casos')"

# Rodar só os 🔴 críticos
python run.py --severity critical

# Comparar com última rodada
python run.py --baseline $(ls -t results/judged_*.json | head -1)
```