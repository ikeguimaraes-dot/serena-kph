# Madonna Cucina — catálogo público para revisão

Fonte capturada em 17/09/2026. **253 itens, 35 categorias com itens, 223 opções e 253 IDs únicos.** A integridade e a origem estão `FONTE_VERIFICADA`. A revisão comercial humana permanece `PENDENTE`; esses estados são independentes. Este pacote não alterou banco, prompts, reservas ou mensagens.

## Fonte oficial e cadeia de evidência

O botão de cardápio de uma comunicação transacional da própria Tagme para Madonna Cucina forneceu o endereço público, sem adivinhar o identificador:

- Página pública: <https://livemenu.app/menu/691377229337bdf1ad07625f>
- Resposta pública do catálogo: <https://customers.tagme.com.br/dine-in/menu/691377229337bdf1ad07625f/Dine-in?ignoreDisabled=1>
- Página, scripts referenciados e resposta do catálogo retornaram HTTP 200, sem autenticação, cookies ou sessão de cliente.
- O JavaScript público chama esse caminho com `Dine-in`. O componente de preço usa `formatFromCents`, cuja implementação divide por 100. A moeda das três raízes é `R$`.

`raw_catalogo.json` contém os **bytes originais** da resposta, uma lista JSON. `captura_catalogo.json` registra URL, horário UTC, status, tamanho e SHA-256. `evidencia_origem_e_unidade.json` preserva trechos mínimos dos scripts, URLs e hashes. Não foram incluídos conteúdo de e-mail, dados pessoais de destinatários, identificadores privados de mensagens, links da fila de espera, cookies ou segredos presentes em configurações de terceiros.

## Conteúdo e leitura dos preços

| Medida | Quantidade |
| --- | ---: |
| Raízes: Menu Principal, Bar, Adega | 3 |
| Categorias com itens | 35 |
| Itens distintos por ID | 253 |
| Itens com preço direto | 88 |
| Vinhos sem preço direto, com uma opção | 165 |
| Opções preservadas | 223 |
| Filhos `sons` e `subitems` | 0 |
| Descrições em português ausentes | 169 |

Nos 58 itens que possuem preço direto e opção, ambos os valores coincidem. Cada item com opções tem exatamente uma opção, todas com `disabled: false`. Nenhuma promoção está ativa. A ausência de `disabled` no produto não foi transformada em uma declaração de disponibilidade de estoque.

Os CSVs usam UTF-8 com BOM, separador `;` e preço em reais com vírgula decimal. Nomes e descrições em português, inclusive quebras de linha, são preservados. `source_id` e `json_pointer` permitem voltar ao item original. Preço bruto em centavos e seu ponteiro são mantidos em colunas separadas. O rótulo de vinho vem de `wineVolume.name.pt`/`value`, sem inferir garrafa ou taça pelo valor.

## Exceções que não podem ser corrigidas por inferência

1. **Tenuta Delle Terre Nere Etna Rosato**, ID `69de933358b41df72973d2dc`: a única opção tem preço bruto `0`. Ponteiro `/2/menus/2/menuItems/5/options/0/price`. Preservar o zero na evidência e bloquear a oferta comercial desse item até existir valor confirmado. Não converter em gratuito, preço sob consulta, média ou valor de outro vinho.
2. **Carne Cruda**, ID `691390ff308a9fdefff0cf3e`: preço bruto `10808`, equivalente exato a **R$ 108,08**. Ponteiro `/0/menus/0/menuItems/1/price`. Há sinalização para confirmar se os centavos são intencionais; nenhum arredondamento foi aplicado.
3. **12 pares de nomes repetidos**, total de 24 linhas: ocorrem em categorias/volumes distintos, como Vallontano Brut, Prosecco Cabert Extra Dry DOC e vinhos em taça. Não deduplicar pelo nome; a chave deve conter restaurante, provedor e ID da fonte.
4. **169 descrições em português ausentes**: permaneceram vazias. Nenhuma descrição foi produzida a partir de vinhos semelhantes, notícias ou documentos antigos.

## Artefatos

- `madonna_253_revisao.csv`: todos os itens, valores, origem do preço, sinalizações e campos de revisão.
- `madonna_223_opcoes_revisao.csv`: opções, IDs, rótulos, preço, promoção, estado e ponteiro.
- `manifesto.json`: contagens, sinalizações, hashes e distinção entre fonte verificada e revisão humana.
- `verificacao.json`: reconciliação independente dos CSVs com os ponteiros e hashes do JSON.
- `gerar_revisao.py`: gerador local sem rede nem banco; recusa sobrescrever revisões existentes.

Reprodução em diretório novo:

```bash
python3 docs/sprint1/catalogos/madonna/gerar_revisao.py --output /tmp/madonna-revisao-nova
```

## Regras para uma importação posterior

Usar chave idempotente `(restaurant_id, source_provider, source_id)`, conservar IDs e relação das opções e registrar URL/data/hash do lote. Importar com `restaurant_id=madonna_cucina` explícito, nunca pelo nome da categoria. Atualizar apenas campos controlados pela fonte, preservando anotações humanas. Remoção de uma captura não deve apagar histórico automaticamente. O importador deve reconhecer preço zero, preço ausente, promoções e variantes antes de disponibilizar ofertas. Esta extração não implementa nem executa importação.

## Fontes históricas encontradas

A busca escopada no Drive localizou `Menu_MDNA_Revisado.docx`, `FRENTE_MENU_MADONNA.pdf`, `VERSO_MENU_MADONNA.pdf` e `madonna_menu_soft.pdf`, com modificações em março de 2026. O DOCX revisado foi lido: contém pratos e descrições, **sem preços**, e diverge do catálogo atual. Serviu como evidência histórica de existência do menu; não substitui a captura pública de setembro. Os documentos privados não foram copiados para o repositório.
