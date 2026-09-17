# Frêneze — catálogo público extraído em 17/09/2026

**Extração concluída: 210 produtos únicos e 146 variantes/componentes preservados.** Todos permanecem `PENDENTE` de revisão por Ike. Nenhuma escrita no banco, prompt ou catálogo original foi realizada.

Este pacote atualiza o diagnóstico inicial, no qual os arquivos antigos de Frêneze estavam vazios. O pacote do Meet e os arquivos antigos foram preservados.

## O que foi obtido

| Medida | Resultado |
|---|---:|
| Produtos únicos | 210 |
| Seções principais | 5 |
| Categorias com produtos | 17 |
| Produtos simples | 120 |
| Produtos compostos | 90 |
| Etapas dos compostos | 97 |
| Variantes/componentes | 146 |
| Variantes cobradas | 89 |
| Componentes sem cobrança separada | 57 |
| Produtos sem descrição | 92 |
| Duplicatas por ID | 0 |

Os 210 produtos retornados pela API estão ativos e visíveis na fonte. Isso não comprova estoque ou disponibilidade comercial no momento do atendimento. Produtos ocultos ou fora da resposta pública não foram procurados.

## Arquivos de revisão

- `freneze_210_revisao.csv`: produtos, categorias, descrição original, valor de referência, origem exata do preço, sinalizações e campos de aprovação.
- `freneze_146_componentes_revisao.csv`: variantes, volumes e componentes, com regras da etapa, preços, IDs de origem e aprovação independente.
- `raw_catalogo.json`: corpo original da resposta pública de catálogo, sem alteração.
- `raw_detalhes.json`: as 90 respostas públicas de detalhes, com URL, momento de captura, status e corpo JSON preservado. `response_original_sha256` registra o hash da resposta HTTP original antes da serialização no envelope; o manifesto verifica o arquivo consolidado.
- `captura_catalogo.json`: metadados e hash do corpo original do catálogo.
- `evidencia_origem_e_unidade.json`: trechos do JavaScript público que comprovam as rotas, o tipo do catálogo e a formatação monetária.
- `manifesto.json`: contagens e hashes de fontes/artefatos.
- `gerar_revisao.py`: gerador offline; não acessa rede ou banco e recusa sobrescrever as planilhas já criadas.

CSV em UTF-8 com BOM, separador `;`, vírgula decimal. Nenhum valor de referência equivale a aprovação para publicação.

## Proveniência e acesso

Página pública confirmada no extrator original:

`https://freneze.tagme.menu/menu/freneze`

O GET da página retornou HTTP 403 com o shell HTML da aplicação. O shell referenciava `/static/js/main.41e76d6a.js`, que respondeu HTTP 200. O JavaScript público referenciava a API **Shopfood**, diferente do host usado na extração do Meet. Isso explica uma limitação do extrator anterior, que filtrava hosts `tagme` e `livemenu`: a resposta principal deste catálogo vem de outro host. Não foi provado que essa seja a única causa da extração vazia anterior.

As chamadas públicas foram reconstruídas exclusivamente a partir do código servido pela página e da identidade pública da loja:

1. `GET https://api.shopfood.io/v2/stores/freneze/info` retornou `id=2195`, `name=Frêneze`, `slug=freneze`.
2. O código mapeia o tipo `menu` para `order_type=5` e usa o parâmetro `catalog_type=menu`.
3. `GET https://api.shopfood.io/v2/stores/products?store_id=2195&order_type=5&catalog_type=menu` retornou as cinco seções e os 210 produtos.
4. Para cada um dos 90 produtos de tipo composto, foi usada a mesma chamada GET do modal público: `products/composite/steps?store_id=2195&product_id=<ID observado>&order_type=5`. Todas responderam HTTP 200.

Foram enviados somente cabeçalhos comuns de leitura pública (`Origin`, `Referer`, `Accept`, `Accept-Language`). Não foram usados autorização, cookies, tokens, sessão de cliente, carrinho, login ou painel administrativo. JavaScript foi lido como texto, nunca executado. Não foi instalado navegador ou dependência. O navegador CUA estava indisponível.

O horário exato em UTC e a URL de cada resposta estão nos arquivos de captura. A tentativa inicial HTTP 403 está em `tentativa_http.json`; ela não representa o resultado final da extração.

## Preços e unidades: diferenças em relação ao Meet

**Shopfood entrega valores em reais diretamente. Não dividir por 100.** Essa unidade foi confirmada pelo componente público: ele passa os campos diretamente para `Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL", ...})`, sem conversão de centavos. Os trechos estão no arquivo de evidência.

- Nos 120 produtos simples, a referência é o campo `price`.
- Em 89 compostos, existe exatamente uma variante cobrada e ativa. A referência vem do `price` dessa variante; em todos os 89 casos coincide com o preço do resumo. Os rótulos de volume foram preservados, não deduzidos do nome do vinho.
- **Experiência Frêneze** é o único caso com `price=0` no resumo. O componente público usa `default_price=349` para esse produto composto. Portanto, R$ 349,00 foi registrado como referência dessa origem, sujeito à aprovação. O indicador `display_default_price=false` controla o rótulo “a partir de”, não suprime o valor no componente examinado.
- A Experiência possui oito etapas e 57 componentes com `price=0` e `chargeable=false`: são componentes sem cobrança separada na fonte, **não 57 produtos gratuitos**.
- Todos os 210 produtos têm referência positiva com origem identificada. A menor é R$ 9,00 e a maior R$ 7.145,00; nenhum valor foi “corrigido” por parecer alto.

## O que Ike precisa conferir

1. Os 210 produtos, incluindo valores, disponibilidade, descrições e eventual diferença entre catálogo público e operação atual.
2. Os 89 rótulos de variante (como 300 ml e 750 ml), preservados no CSV de componentes. Não publicar um preço sem a identificação da variante correspondente.
3. A Experiência Frêneze: valor de referência R$ 349,00, oito etapas, conteúdo e regra de cobrança. A descrição original é “consulte o Garçon.”; não foi substituída por promessa comercial.
4. **“Ostra Fresca - und” aparece duas vezes**, com IDs diferentes, nas categorias Entradas e Balcão do Mar. Ambos valem R$ 18,00 e têm descrições semelhantes. Confirmar se são duas apresentações legítimas ou duplicação de cadastro; nada foi eliminado automaticamente.
5. As 92 descrições ausentes permanecem vazias.

Preencher `status_revisao` como `APROVADO`, `CORRIGIR` ou `NAO_IMPORTAR` e registrar observações. Não alterar silenciosamente os campos extraídos. Nova versão deve registrar as correções aprovadas e o hash do pacote final.

**Ainda não está pronto para carga:** faltam a aprovação item a item e uma importação que represente variantes/etapas sem reduzir tudo a um preço mínimo. A retirada de modo seguro continua dependendo de carga comprovada por SELECT e testes do agente.

## Validação

O gerador confronta o hash da captura, exige resposta 200 e identidade consistente em cada detalhe, conserva IDs de origem e registra caminhos JSON exatos para cada produto, preço e componente. Também verifica divergências entre resumo e variante e recusa sobrescrever revisões existentes. O verificador executado após a geração conferiu os 210 preços contra suas respectivas origens e os 146 componentes contra seus IDs no bruto, além de hashes, estados de revisão e preservação do pacote Meet.
