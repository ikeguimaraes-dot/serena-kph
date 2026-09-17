# Sprint 1 — auditoria e revisão dos catálogos

Auditoria local de 17/09/2026. **Carga no banco bloqueada até aprovação explícita de Ike, item a item.** Nenhum preço, nome, descrição, prompt ou conteúdo do banco foi alterado. Os arquivos originais foram preservados e seus hashes estão em `manifesto.json`.

## Estado verificado

| Casa | Evidência local | Resultado |
|---|---|---|
| Meet & Eat | CSV, JSON normalizado e JSON bruto do Tagme | 277 itens, 46 categorias, 277 IDs de produto únicos |
| Frêneze | CSV de 63 bytes só com cabeçalho; JSON `[]` de 2 bytes; captura de tela | **Extração não concluída: 0 itens extraídos.** A captura mostra um cardápio renderizado; os arquivos vazios não significam ausência de produtos |
| Madonna | Extrator configurado com `https://livemenu.app/menu/COLE_O_ID_AQUI` | Sem catálogo ou URL válida nos arquivos examinados; pendente obter fonte oficial |

Escopo da busca de Madonna: `cardapios_extraidos`, extratores da raiz, `docs`, `files/restaurant-ai` e `restaurant-ai`, excluindo dependências. Foram encontradas referências históricas de testes e migrações de agenda; nenhuma era fonte de catálogo comercial. Não foi feita extração autenticada nem busca em arquivos pessoais fora desse escopo.

## Arquivos para revisar

- **`meet_277_revisao.csv`**: uma linha por item original, com preço preservado, categoria, descrição, opção/adicional, sinalizações, ID de origem e localização exata no JSON bruto.
- **`meet_opcoes_revisao.csv`**: 203 linhas de opções e filhos, com rótulos, preços brutos em centavos, preços convertidos, condição de desativação e origem. Permite conferir o que não cabia no CSV anterior.
- **`manifesto.json`**: contagens, hashes SHA-256 de fontes e artefatos, URL de origem e limitações. Não contém cópia do JSON bruto nem credenciais.

Os CSV usam UTF-8 com BOM, separador ponto e vírgula e vírgula decimal para facilitar a abertura no Excel. `preco_exportado_reais` é o valor do arquivo original, **não um preço comercial já aprovado**. `disponivel_no_csv_original=true` foi produzido pelo parser e não comprova estoque ou disponibilidade atual.

## Resultado da conferência mecânica do Meet

- CSV e JSON normalizado coincidem campo a campo nas 277 linhas.
- 0 preços ausentes, zerados ou negativos no catálogo normalizado; intervalo R$ 9,00 a R$ 15.590,00.
- 0 nomes vazios, 0 categorias vazias e 0 duplicatas de categoria + nome.
- 277 itens no bruto correspondem aos 277 exportados. Nenhuma seção ou item-base examinado está marcado como desativado.
- 63 itens não têm `price` direto: cada um possui exatamente uma opção ativa com preço positivo, que explica o preço exportado. Nenhuma divergência foi encontrada entre o valor bruto dividido por 100 e o valor exportado.
- 190 itens possuem opções; suas opções e filhos totalizam 203 registros.
- 5 itens têm variantes ativas com preços diferentes, omitidas no CSV original.
- 3 itens têm adicionais ou sabores; 1 deles possui todos os filhos da opção desativados.
- 2 itens têm uma opção adicional de preço zero e sem rótulo. Não interpretar essas opções como produtos gratuitos.
- 28 itens têm rótulo de opção/volume fora do CSV anterior.
- 99 itens não têm descrição na fonte exportada. Não completar por inferência.
- 6 linhas compartilham o nome com outra categoria: são 3 pares de vinho/taça. Não excluir como duplicatas.

## Pontos que exigem atenção na revisão

Valores abaixo são os encontrados na fonte, ainda sujeitos à confirmação de Ike.

| Item | O que precisa ser confirmado |
|---|---|
| Dry Martini | Bombay Sapphire R$ 48,00; Hendricks R$ 62,00. O CSV anterior conserva apenas R$ 48,00 |
| Fitzgerald | Bombay Sapphire R$ 58,00; Hendricks R$ 66,00 |
| Negroni | Bombay Sapphire R$ 58,00; Hendricks R$ 66,00 |
| Pencilin Dewar's | Dewar's 12 anos R$ 58,00; Dewar's 15 anos R$ 68,00 |
| Mark Twain | Dewar's 12 anos R$ 52,00; Dewar's 15 anos R$ 62,00 |
| Cheese Burger | Base R$ 82,00; grupo “Adicional”: Bacon R$ 8,00 e Salada R$ 6,00. Confirmar apresentação e regra de adicional |
| Sorvetes Tradicionais | Base R$ 18,00; Creme e Canela com incremento zero, ambos ativos |
| Sorvete Zero | Base R$ 18,00; Doce de leite e Pistache estão desativados. Isso não prova que o item-base está indisponível; confirmar com a operação |
| Caipirinha | Famigerada R$ 48,00 e outra opção ativa sem rótulo/preço zero |
| Eisenbahn American IPA | 355 ml R$ 25,00 e outra opção ativa sem rótulo/preço zero |
| Santa Magdalena Reserva Chardonnay | Vinho Branco R$ 210,00 / Vinho Taça R$ 49,00; manter distinção |
| Alamos Torrontés | Vinho Branco R$ 225,00 / Vinho Taça R$ 59,00; manter distinção |
| Kabbalah Merlot | Vinho Tinto R$ 210,00 / Vinho Taça R$ 48,00; manter distinção |

Preços altos também foram preservados, sem “correção” automática: Vega Sicília Único Reserva Especial R$ 15.590,00, Louis Roederer Cristal R$ 7.400,00 e Clase Azul Tequila R$ 5.000,00. O bruto comprova o valor extraído; não comprova que esses valores continuam vigentes na operação.

## Limitações do parser atual

Arquivo original: `parse_cardapio_tagme.py` na raiz de `_Serena`.

1. Linha 39 deduz a unidade monetária pelo tamanho do número (`> 100`). Um preço real de 100 centavos seria interpretado como R$ 100,00. Não afetou os preços-base auditados, mas precisa ser corrigido antes de novas cargas.
2. Linhas 56–78 retornam um único preço e podem escolher o menor entre opções. Isso perde a identidade de tamanho, volume ou variante.
3. Linha 71 procura `subitems`, mas os adicionais/sabores encontrados no bruto estão em `sons`.
4. Linhas 86–88 descartam colisões silenciosamente por categoria/nome; IDs estáveis da fonte não são preservados.
5. A disponibilidade vira `true` no CSV; seções-pai desativadas não são filtradas. Promoções e seus estados também não fazem parte da exportação atual. Não havia promoções ativas nos itens-base desta amostra.
6. Linhas 133–140 escolhem o maior arquivo bruto, não a fonte/versão explicitamente identificada.

O gerador de revisão incluído neste sprint lê uma fonte explícita, exige correspondência entre bruto/CSV/JSON, preserva os arquivos originais e sinaliza as opções. **Ele não substitui o parser nem implementa carga.**

## Aprovação humana

1. Ike confere as 277 linhas com o cardápio vigente e a operação, inclusive bebidas, rolhas, disponibilidade e descrições.
2. Preencher `status_revisao` com `APROVADO`, `CORRIGIR` ou `NAO_IMPORTAR`. Todos começam em `PENDENTE`; ausência de sinalização não significa aprovação.
3. Registrar em `observacoes_ike` a correção e a evidência, quando aplicável. Não alterar silenciosamente os campos de origem. Conferir também as opções na segunda planilha.
4. Preços alternativos/adicionais precisam de representação explícita antes de chegar ao agente. Um preço mínimo não pode parecer válido para todas as variantes.
5. Consolidar um novo pacote aprovado, com hash e registro de responsável/data. A aprovação é desta versão concreta; nova extração exige nova conferência das diferenças.
6. A retirada do modo seguro depende de carga comprovada por SELECT e teste de respostas, além da revisão; não é consequência automática de gerar estes arquivos.

## Desenho da importação futura

Não implementado ou executado nesta entrega.

- Validar primeiro o schema real. O schema local de referência só define `id` incremental e não contém chave única de origem para importação idempotente.
- Separar estágio de revisão da tabela publicada; cada linha precisa de `restaurant_id`, ID do produto na fonte, categoria/variante, hash do conteúdo, lote e aprovação.
- Usar identidade estável do produto e da variante, sempre junto do tenant. O mesmo arquivo importado duas vezes deve resultar em zero duplicações e zero alterações na segunda passagem.
- Preservar variantes e adicionais, nunca mesclá-los pelo nome ou escolher preço mínimo silenciosamente. Caso o modelo atual ainda não suporte uma linha, mantê-la fora da publicação até decisão explícita.
- Aplicar somente a versão aprovada em transação. Antes: snapshot e diff por tenant; depois: SELECT de contagem, preço, disponibilidade e comparativo com o manifesto. Falha em qualquer conferência causa rollback.
- Ausência na nova extração não autoriza apagar produto do catálogo. Remoções ou desativações precisam aparecer no diff e receber aprovação própria.
- Não misturar itens de outros tenants, não escrever em prompts e não alterar o modo seguro como efeito colateral da importação.

## Reproduzir a auditoria

Na raiz do worktree:

```bash
python3 scripts/catalog_review.py \
  --source /Users/henriqueguimaraes/Desktop/_HOS/_RUPTURA/_Serena/cardapios_extraidos \
  --output docs/sprint1/catalogos/nova_revisao
```

O script recusa sobrescrever artefatos existentes para preservar anotações de revisão humana. O campo `url` do bruto registra a origem da captura do Meet:

`https://customers.tagme.com.br/dine-in/menu/62ffd74ddaf31500126b3e29/Dine-in?ignoreDisabled=1`

A data de captura não existe no payload; o horário do arquivo local não foi tratado como confirmação da vigência do cardápio. Não foi feita nova consulta à API nesta auditoria.
