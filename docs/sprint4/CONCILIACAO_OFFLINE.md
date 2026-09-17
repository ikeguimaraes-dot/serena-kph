# Conciliação offline de recebimentos por unidade

## Entrega e limite

`files/restaurant-ai/reconcile_revenue_offline.py` calcula recebimentos reais conciliados a reservas/OS e uma atribuição **observacional** a conversas assistidas. Usa apenas a biblioteca padrão do Python, sem importar o aplicativo, abrir rede/banco, criar cobrança, enviar mensagens ou alterar produção.

Este cálculo não é fechamento financeiro, faturamento por competência, auditoria de documentos nem prova de receita incremental. `receita_incremental_brl` permanece `null`. O KR de duas casas com receita validada depende de exportações reais autorizadas, fonte financeira fechada e revisão dos comprovantes; os testes sintéticos não o cumprem.

## Dois arquivos de entrada

Armazene dados reais fora do repositório. Não inclua nomes, mensagens ou descrições de atendimento: o contrato precisa apenas das identidades e metadados abaixo. Referências de evidência devem localizar os comprovantes autorizados na origem; a ferramenta não baixa nem autentica esses documentos.

### 1. `operations.json`

Objeto com `schema_version: "serena-reconciliation-input-v1"`, `restaurant_id`, `sources`, `entities` e `interactions`. O arquivo deve conter uma única unidade, a mesma passada na linha de comando.

`sources` contém três objetos: `entities`, `interactions` e `receipts`.

| Campo da fonte | Contrato |
|---|---|
| `complete` | Boolean fornecido pelo responsável pela exportação. Ausente/false nunca significa conjunto fechado. |
| `source_ref` | Referência da extração/fonte e sua declaração de completude; não segredo ou token de acesso. O relatório inclui somente seu SHA-256. |
| `as_of` | Timestamp ISO-8601 com fuso, posterior ou igual ao fim do período. |
| `window_start`, `window_end` | Obrigatórios para receipts/interactions. Janela exportada, início inclusivo/fim exclusivo. |

A fonte de recebimentos deve cobrir o período inteiro. A fonte operacional deve conter todas as referências citadas nos recebimentos, inclusive reservas/OS criadas antes do período. A fonte de interações deve cobrir pelo menos o período e os sete dias anteriores à criação de cada reserva/OS referenciada. A completude é uma declaração verificável na fonte, não algo inferido pela ferramenta a partir do número de linhas.

Cada elemento de `entities`:

| Campo | Contrato |
|---|---|
| `kind` | `reservation` ou `order`. Não somar valores previstos da entidade. |
| `id`, `restaurant_id` | Identidade exata; IDs são únicos dentro de cada kind/unidade. |
| `customer_phone` | Telefone normalizado, formato `+` e 7–15 dígitos; correspondência exata, sem aproximação por nome. Ausente/inválido deixa atribuição desconhecida. |
| `created_at` | ISO-8601 com fuso; âncora da janela de atribuição. Ausente ou posterior ao recebimento impede atribuição. |
| `status` | Estado atual exportado; serve para diagnóstico, não para comprovar receita. |
| `evidence_ref` | Referência obrigatória ao registro operacional. |

Adaptação explícita das fontes existentes: `reservas.id/restaurant_id/cliente_phone/criado_em/status` e `ordens_servico.id/restaurant_id/cliente_phone/criado_em/status`. IDs devem ser exportados como strings. Não é necessário migrar tabelas nem alterar seus estados. O adaptador/exportador é responsabilidade de quem fornece os arquivos; não existe consulta automática a produção neste script.

Cada elemento de `interactions`:

| Campo | Contrato |
|---|---|
| `id`, `restaurant_id`, `customer_phone` | Identidade e telefone exatos na unidade. |
| `occurred_at` | Timestamp da conversa, com fuso, fundamentado na mensagem de origem. |
| `agent_assisted` | Boolean explícito: true apenas quando há evidência de assistência efetiva do agente nessa conversa. false para conversa sem tal assistência. Não inferir a partir de opt-in, estágio ou existência de reserva. |
| `intent` | Opcional; `reserva_nova`/`evento` são contados como intenção registrada. Ausente não é inventado. |
| `evidence_ref` | Referência obrigatória à conversa/mensagem e, quando aplicável, classificação de intenção. Sem texto de cliente no arquivo. |

Conversa e intenção devem ser relacionadas pelo identificador real da mensagem quando disponível. Uma classificação posterior sem vínculo verificável não pode ser usada para preencher assistência automaticamente. Exporte também conversas humanas relevantes: omiti-las invalida a regra de última conversa.

### 2. `receipts.csv`

Use [receipts_template.csv](receipts_template.csv). Cabeçalho exato, CSV separado por vírgula, UTF-8:

```csv
transaction_id,restaurant_id,reservation_id,order_id,amount_brl,occurred_at,evidence_ref
```

- `transaction_id` é único no arquivo inteiro, inclusive fora do período; duplicatas abortam a execução, em vez de serem somadas ou descartadas silenciosamente. Se a fonte reutiliza IDs entre adquirentes, o exportador deve fornecer uma identidade composta estável.
- Preencha **um** de `reservation_id` ou `order_id`. Ambos preenchidos ficam não conciliados por ambiguidade. Ambos vazios representam dinheiro documentado sem vínculo operacional; não há atribuição por aproximação.
- `amount_brl` usa ponto decimal e no máximo duas casas (`100.10`, `-10.05`). Não aceita float, vírgula decimal, expoente, NaN, arredondamento de frações de centavo ou valor estimado. Zero só é aceito se foi o valor explícito da linha documentada.
- `occurred_at` é a data/hora real do recebimento ou estorno, com fuso. A reserva não substitui a data do movimento financeiro.
- `evidence_ref` é obrigatório, inclusive para estornos. O valor deve vir de fonte de recebimento real; campos `pagamento_valor`, valor de OS, ticket médio e status pago no app não bastam sem essa fonte.
- Um estorno tem ID próprio e valor negativo. Não é criado automaticamente a partir de cancelamento e não precisa ter a venda original dentro do mesmo período. A referência de evidência deve permitir rastrear a devolução na origem.

## Regras de cálculo

1. O período é `[--start, --end)`, datas de São Paulo. Cada recebimento/estorno pertence ao período da sua própria `occurred_at`. Estorno após o fim não reescreve o relatório anterior; um período pode ter valor líquido negativo.
2. Unidade divergente em qualquer linha aborta toda a execução, mesmo que a linha esteja fora do período. IDs operacionais duplicados e interações duplicadas também abortam. JSON com chaves repetidas é rejeitado.
3. Identidade, valor, timestamp ou evidência faltantes deixam a linha inválida e impedem totais fechados. Referência operacional desconhecida/ambígua fica na soma observada `nao_conciliado`.
4. O vínculo financeiro aceita **qualquer estado atual** da reserva/OS. Um pagamento de reserva cancelada ou no-show continua existindo até que haja um estorno real. Esses estados ficam visíveis em diagnóstico agregado. Isso evita confundir caixa, comparecimento e receita contábil.
5. A atribuição usa a **última conversa observada** da mesma unidade/telefone no intervalo `[created_at - 7 dias, created_at)`. Ela recebe rótulo assistido somente se `agent_assisted=true`. Conversa humana posterior substitui a anterior do agente. Empate de horário com evidências divergentes fica desconhecido. Conversa igual/posterior à criação não atribui retroativamente.
6. Ausência de conversa só pode virar `conciliado_sem_interacao_elegivel` com fonte completa e janela coberta. Telefone desconhecido, exportação incompleta ou evidência inválida ficam como atribuição desconhecida. Mesmo quando há assistência observada em arquivo parcial, os totais fechados continuam nulos.
7. A mesma transação entra uma única vez. Múltiplos pagamentos/estornos da mesma entidade são somados com `Decimal`; nenhuma multiplicação por quantidade de conversas ou join de OS/reservas.

## Saída agregada

- `status`: `complete` somente quando todas as fontes fecham o recorte e não restam erros de identidade, vínculo ou atribuição. `complete` descreve o contrato dos arquivos, não uma auditoria financeira independente.
- `somas_observadas_brl`: valores documentados válidos nos arquivos, separados em assistidos, sem interação elegível, atribuição desconhecida, sem vínculo operacional e não conciliados. Conjunto parcial vazio é `null`; não se transforma ausência de dados em zero.
- `totais_fechados_brl`: as mesmas somas somente com conjunto fechado. Caso contrário, **todos** os valores ficam `null`.
- `diagnosticos`: códigos fixos e posição numérica da linha (dados CSV a partir de 1, sem contar o cabeçalho). Nunca contém telefone, nome, ID do pagamento ou texto da evidência.
- `input_sha256`: impressão dos dois arquivos lidos pelo CLI; permite identificar precisamente a versão reconciliada.
- Valores monetários são strings com duas casas, preservando precisão decimal. O relatório não inclui nomes, telefones, conteúdo de conversa ou referências financeiras individuais.

## Execução

```bash
python3 files/restaurant-ai/reconcile_revenue_offline.py \
  --operations /caminho/privado/operations.json \
  --receipts /caminho/privado/receipts.csv \
  --restaurant-id meet_and_eat \
  --start 2026-09-01 --end 2026-10-01 \
  --output /caminho/privado/reconciliation.json
```

O CLI não sobrescreve entradas nem relatório existente. Stdout contém somente status e contagem de diagnósticos. Códigos de saída: `0` conjunto fechado; `2` relatório parcial/incompleto salvo para revisão; `1` contrato rejeitado ou arquivo inválido. A ferramenta não imprime valores de entradas nem caminhos em falhas de leitura.

## Validação sintética

```bash
cd files/restaurant-ai
python3 -m unittest test_reconcile_revenue_offline -v
```

Somente dois arquivos de fixtures são versionados em `tests/fixtures/reconciliation_*.synthetic.*`. Os testes cobrem caixa por período, Decimal, estorno, duplicidade, identidade, unidade, referência desconhecida, atribuição anterior, empate, fonte incompleta, ausência de PII na saída, parser estrito e CLI. Nenhum comprovante ou cliente real foi usado, nenhum número de receita de unidade real foi publicado e nenhuma operação externa foi executada.
