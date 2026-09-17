# Serena OS — execução do Sprint 1

Início: 17/09/2026. Referência: [Book mestre v1.1](BOOK_MESTRE_v1.1_2026-09-17.md).

## Escopo e decisões

Iniciada a onda de estabilização. Este arquivo registra evidência de execução;
o book original está preservado integralmente como documento recebido.
O Sprint 2 só começa após o encerramento e o OK explícito do Ike, conforme seção 3.3.
Não houve carga de catálogo, alteração de preços ou remoção de modo seguro sem revisão.
Os checkouts originais têm trabalho local em andamento e foram preservados.

## Baseline conferido diretamente

| Tema | Evidência em 17/09 | Consequência |
|---|---|---|
| Produção | Railway deployment `d51e706b-0f05-40de-8d16-6b3ef4e9238f`, upload do commit de recuperação `a063cf6` | Incorporar recuperação na `main` |
| Git | `origin/main=ae2d3f4`; PRs #38 recuperação e #36 rota clínica abertos | A rota clínica ainda não está na main, diferente do anexo |
| Banco | Pooler IPv4 `aws-0-sa-east-1.pooler.supabase.com:5432` | O anexo cita porta 6543, mas o serviço usa 5432; manter a configuração funcional |
| Catálogos | `menu_items` tem zero registros | Nenhuma negativa comercial pode ser inferida dessa ausência |
| Meet | 277 registros extraídos em CSV/JSON | Revisar variantes, adicionais e disponibilidade antes de importar |
| Frêneze | CSV apenas com cabeçalho e JSON vazio | Extração pendente; arquivo existente não significa extração concluída |
| Madonna | URL do catálogo ainda não localizada | Solicitar link oficial ao Ike |
| Agenda | Madonna: 1 configuração, 17 turnos; demais sem turnos | Não inventar disponibilidade nem capacidade |
| Equipe | Frêneze: 1 atendente; Levvai: 1 gerente + 1 atendente ativos com telefone; Meet/Madonna: zero | Faltam destinatários autorizados de duas unidades |
| Discord | `DISCORD_HANDOFF_WEBHOOK_URL` presente, mesmo nome usado pelo código | Nome da variável confirmado; não equivale a teste de entrega atual |
| WhatsApp de equipe | Nenhuma variável de template de handoff; 10 conteúdos listados, nenhum específico para handoff | Rota clínica de texto livre depende de janela de atendimento ativa |
| Personas | Stella, Eva, Serena, Camila preenchidas corretamente | Preservar o trabalho de conteúdo já realizado |
| Prompts | Meet `v13-safemode`, Madonna `v12-safemode`; Levvai contém `[LARA]` | Manter proteção até catálogo revisado; ligar rota clínica existente |
| Visão | Código recebe imagens; prompts de 3 restaurantes não mencionam imagem, Levvai menciona | Preparação de conteúdo ainda necessária; ausência de palavra não é prova de incapacidade |
| Dados operacionais | Telefone público/site nulos nas quatro unidades; limite por reserva 8 | Aguardar dados confirmados; WhatsApp técnico não substitui telefone público automaticamente |
| CRM/funil | Código e tabelas `contacts`, métricas e endpoints já existem parcialmente | Auditar cobertura antes de criar estruturas duplicadas nos próximos sprints |

## Backlog executável

| ID | Entrega | Critério de conclusão | Estado |
|---|---|---|---|
| S1-01 | Consulta de catálogo segura | Distinguir base vazia, busca sem resultado e erro; testes e deploy | Publicada e verificada dentro do container nas quatro unidades |
| S1-02 | Reconciliação de código | Recuperação + rota clínica integradas na main, deploy identificado e verificado | Main reconciliada e deploy SUCCESS; função clínica presente; entrega humana ainda pendente |
| S1-03 | Revisão do Meet | CSV completo, divergências marcadas, aprovação item a item do Ike | Pacote de 277 itens + 203 opções pronto; aprovação pendente |
| S1-04 | Extração Frêneze/Madonna | Fonte real, preços e opções preservados, revisão e prova | Frêneze: 210 produtos + 146 componentes extraídos e verificados, revisão pendente; Madonna sem URL |
| S1-05 | Carga de catálogo | Aprovação dos dados + importação transacional + SELECT de prova | Bloqueada por S1-03/04 |
| S1-06 | Handoff de quatro unidades | Destinatário por unidade, canal e recebimento comprovado | Meet/Madonna sem responsáveis; WhatsApp fora de janela depende de template |
| S1-07 | Dados das casas | Telefones/sites/limites/ambientes confirmados | Aguardando dados do Ike |
| S1-08 | Prompts completos e visão | Novas versões coerentes com fontes, testes e aprovação | Preparar após dados; modo seguro mantido |
| S1-09 | Erro de insights pós-recuperação | Endpoint sem 500 e sem cruzar nomes/tier entre unidades | Publicada; quatro endpoints retornaram HTTP 200; isolamento testado com rollback |
| S1-10 | Autorização e operações CRM | Operações mutáveis autenticadas e escopo por unidade, incluindo proxy do painel | P1 identificado; requer entrega própria antes de uso externo |

## Dados solicitados e revisão

Pergunta enviada ao Ike: URL oficial do cardápio Madonna e WhatsApps dos responsáveis
por Meet & Eat e Madonna, incluindo se são compartilhados.

Após localizar/importar fontes, ainda são necessários:

- Revisão dos 277 itens Meet, especialmente variantes de preço, adicionais e itens desativados.
- Revisão dos 210 produtos Frêneze e 146 variantes/componentes, incluindo a Experiência Frêneze.
- Limite de pessoas por reserva de cada unidade, coerente com os prompts.
- Nome comercial dos ambientes Meet e capacidades reais das demais unidades.
- Telefone público/site oficial por unidade.
- Conteúdo e aprovação do template de notificação de equipe, caso seja necessário WhatsApp fora da janela ativa.

Nenhum dado ausente será preenchido por estimativa. Pedido de número ao usuário não
equivale a comprovação de consentimento para campanhas; este sprint trata do atendimento.

## Próximos portões (planejados, ainda não iniciados)

1. **Sprint 2:** origem de anúncio, desfecho, backup externo com restauração testada e custos.
2. **Sprint 3:** completar CRM existente, consentimento e régua por evento.
3. **Sprint 4:** completar funil e medir conversão/receita atribuída.
4. **Sprint 5:** página pública de reservas e exportação do legado.
5. **Sprint 6:** onboarding repetível e cliente externo assistido.

Preços, volume de conversas, retorno financeiro e benchmark de mercado continuam
dependendo de medição/verificação própria. Este trabalho não valida as afirmações comerciais do book.

## Validação e release

Primeira entrega técnica:

- 9 testes offline da consulta de catálogo e 18 testes offline de handoff passaram.
- `test_recovery_contract.py` passou contra o banco atual, validando o contrato de recuperação.
- `test_sprint1_contract.py` passou contra o banco atual: SQL dos insights nas quatro unidades,
  nomes/tier do mesmo telefone, clientes inativos e categorias de handoff isolados por unidade.
- Ambos os testes transacionais desfizeram todos os registros sintéticos.
- Snapshot pontual de 8 tabelas operacionais/prompts preservado em arquivo privado fora do
  Supabase (`~/.local/share/serena-recovery/2026-09-17/sprint1-before-release.json`).
  Isso não constitui a rotina periódica com restauração testada prevista no Sprint 2.
- [Pacote de revisão do catálogo](../sprint1/catalogos/README.md): todos os itens permanecem PENDENTE.
- O remetente clínico vem da própria Levvai; falta de gerente/remetente/falha de canal
  mantém o atendimento no painel com alerta. Aceitação Twilio não é entrega confirmada.

- [PR #39](https://github.com/ikeguimaraes-dot/serena-kph/pull/39) integrado à `main`:
  merge `bab278b27045673552c605b2d0f5ad7547e035ed`.
- Railway deployment `3343c7ec-9543-4792-87ed-f87de45b4e2b`, SUCCESS, origem GitHub/main.
- CI pós-deploy `35180594088` concluído com sucesso.
- `/health` e `/api/insights?rid=...` nas quatro unidades retornaram HTTP 200.
- Verificação dentro do container: `lookup_menu` retornou `CATALOGO_INDISPONIVEL`
  nas quatro unidades; função clínica presente. SHA-256 dos quatro arquivos de código
  iguais aos do release local. Não houve envio de mensagem nessa verificação.

### Complemento de isolamento e catálogo

- Listagens de conversas e handoffs agora associam contatos por telefone **e unidade**.
  O teste transacional passou com o mesmo telefone, nomes diferentes em duas unidades
  e consultas com/sem filtro de status. Todos os registros sintéticos foram desfeitos.
- [Frêneze: pacote de revisão](../sprint1/catalogos/freneze/README.md) contém 210 produtos,
  146 componentes, fontes brutas, datas, caminhos dos preços no JSON e hashes.
  A API pública e os 90 detalhes retornaram HTTP 200, sem autenticação.
  Os arquivos vazios citados no baseline eram os antigos; esta extração os complementa.
- Os 210 preços e 146 componentes foram confrontados com a origem. Todos seguem
  PENDENTE. Valores e disponibilidade ainda precisam de confirmação operacional.

### Pendências adicionais encontradas no código

- Algumas rotas de escrita de handoff/CRM não têm a dependência `require_admin`;
  algumas atualizações de CRM usam somente telefone, apesar da chave ser composta.
  A correção exige revisar também a autorização do proxy Next.js e as permissões
  por unidade. Registrado como P1; este release não resolve esse conjunto nem certifica
  isolamento completo/autorização para clientes externos.

Testes de mensagens devem usar mocks ou chamadas comprovadamente somente de leitura.
O endpoint `/api/serena/test-message` pode executar ferramentas com efeitos colaterais;
não deve ser tratado como sandbox geral. Entrega real de handoff só será declarada
após evidência de recebimento.
