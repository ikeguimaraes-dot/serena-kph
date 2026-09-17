# Catálogos consultáveis — execução autorizada em 17/09/2026

A nova instrução de Ike foi executar o planejamento integralmente preservando o que funciona.
Esta entrega implementa publicação rastreável dos dados encontrados nas fontes oficiais.
**Fonte verificada não equivale a conferência humana:** os CSVs anteriores continuam PENDENTE.

| Casa | Fonte atual | Itens preparados | Tratamento |
|---|---|---:|---|
| Meet | Tagme público, consulta atual | 276 | 5 itens com variantes têm preço-base nulo e preços identificados por variante |
| Madonna | Tagme público, URL localizada em comunicação oficial | 253 | Vinho com preço zero fica sob consulta; Carne Cruda preserva R$ 108,08 |
| Frêneze | Shopfood público | 210 | 89 variantes identificadas; Experiência mantém R$ 349 pelo conjunto e componentes sem cobrança separada |

O arquivo anterior do Meet tinha 277 produtos. O ID `67254f95eae94ac3624cf5c2`
(Catena Zapata Angelica Zapata Cabernet Franc Alta) não está na consulta atual.
Os demais 276 mantêm nome, descrição, preço e opções. Nenhum produto existente no banco
é removido por essa ausência: o importador não executa DELETE.

## Compatibilidade e proteção

- Quatro colunas opcionais e um índice por unidade/fonte/ID. Itens manuais continuam no contrato anterior.
- Catálogo publicado não comprova estoque: a ferramenta informa essa distinção.
- Variantes, adicionais, opções desativadas e origem do preço são preservados.
- Preço desconhecido ou zero na fonte não vira oferta gratuita.
- Importação em transação, quantidade anterior explícita, validação da unidade e prova por SELECT.
- Reimportação idêntica não altera dados; alteração manual existente bloqueia sobrescrita.
- O endpoint de teste do agente bloqueia ferramentas que escrevem no banco ou enviam propostas.

## Verificação realizada

- 40 testes offline de catálogo, modo de teste e handoff aprovados.
- Dump real restaurado em PostgreSQL 17 local isolado: 64 tabelas, 988 registros e 4 prompts
  idênticos ao snapshot por contagem/hash.
- Migração e importação dos 739 itens testadas nessa cópia, incluindo reimportação,
  proteção de edição manual, separação por unidade e rollback integral ao final.
- Fontes brutas e comprovação das unidades monetárias estão nos pacotes em `docs/sprint1/catalogos`.

## Publicação e reversão

1. Aplicar a migração aditiva; publicar e verificar o leitor compatível.
2. Importar cada bundle com contagem anterior explícita e conferir dados no banco.
3. Somente então ativar versões de prompt que consultam `lookup_menu` e reconhecem imagens.
4. Em caso de falha, reativar a versão anterior do prompt e reverter o deploy. Não apagar
   registros nem restaurar o banco inteiro sobre conversas novas.

Os hashes dos bundles e as provas de publicação devem acompanhar o relatório de execução.
