# Serena OS — execução integral do plano

Referência: Book Mestre v1.1. Autorização de 17/09/2026: executar todo o planejamento
preservando o que funciona. Checkouts originais preservados; trabalho em branches
isoladas e releases pequenos. Este documento distingue implantação de código de
resultados que dependem de operação, clientes e tempo de medição.

## Release 1 — catálogo, acesso e recuperação

- Painel publicado: commit `061001f`, Vercel `dpl_EWt5jneXQkyEAYvQzEaGtqyv2Yeu`,
  domínio `https://madonna-painel.vercel.app`. Login HTTP 200; APIs privadas anônimas
  HTTP 401; disponibilidade pública HTTP 200. Build e seis testes de proxy passaram.
- Backend preparado: catálogo com preço/opções de origem, teste de agente sem escrita,
  autenticação administrativa e CRM por unidade. 56 testes backend passaram, além
  de contrato CRM transacional com dois tenants e rollback.
- Migração aditiva `catalog_provenance_variants` aplicada; colunas verificadas,
  catálogo ainda vazio antes da carga. Sem mudança de policy ou exclusão de itens.
- 739 itens extraídos de fontes públicas oficiais: Meet 276, Madonna 253, Frêneze 210.
  Importação/reimportação e preservação de edições manuais passaram no banco restaurado.
  Status `SOURCE_VERIFIED`; revisão humana item a item continua `PENDING`.
- Backup real de 64 tabelas/988 registros/4 prompts restaurado com hashes e contagens
  idênticos. Job local diário ativado às 03:15; depende do Mac ligado/conectado.

## Frentes em execução

1. Publicar backend, carregar catálogo com SELECT de prova e versionar prompts.
2. Captura CTWA, custo com cache, desfecho e relatório por unidade.
3. Reserva pública na mesma agenda, validação e capacidade atômica.
4. Exportação legada restrita às unidades autorizadas; sem contornar autenticação.
5. Completar régua/consentimento, onboarding, documentação de acesso e material comercial.

## Limites de conclusão

- Capacidade, preços comerciais, destinatários e turnos não serão estimados.
- Dados de origem não equivalem a confirmação de estoque.
- Recebimento humano de handoff exige prova; aceite da API não comprova entrega.
- Histórico protegido do incumbente depende de exportação autenticada por unidade.
- Cliente externo real, faturamento observado e retenção exigem operação real;
  não serão preenchidos com registros sintéticos nem projeções.
- Pagamento/caução, fila conversacional, app e integração PDV continuam fora dos
  90 dias, conforme seção 3.4 do plano.
