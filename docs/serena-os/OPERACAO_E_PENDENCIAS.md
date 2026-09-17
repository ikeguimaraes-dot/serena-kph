# Serena OS — operação, evidências e pendências dos Sprints 1–6

**Corte de evidência: 17/09/2026.** Mapa dos 30 itens do
[Book Mestre v1.1](BOOK_MESTRE_v1.1_2026-09-17.md), seção 3.3. Código backend
inspecionado até `9792d26`; frontend em validação no release 2. Este documento
complementa o [registro de execução e deploys](EXECUCAO_COMPLETA.md).

O plano tem entregas técnicas prontas, dados já carregados e resultados que ainda
dependem da operação. **Não está comprovada a conclusão integral dos seis sprints.**
Autorização para executar o plano não substitui conferência humana de catálogo,
recebimento por uma pessoa, aprovação de template, faturamento conciliado ou um
cliente externo real.

## 1. Como ler os estados

- **Entregue:** o critério indicado tem evidência verificável; os limites continuam
  registrados. Não significa que todo o sprint está concluído.
- **Em validação:** implementação/artefato preparado, mas falta publicação,
  comprovação na versão publicada ou validação do uso real.
- **Depende de operação:** falta dado, decisão ou execução por responsável externo
  à implementação. Pode haver código pronto apoiando o item.

Nas matrizes, “preparado” significa código/documento presente no checkout
integrado e testado conforme a evidência citada. **Não significa deploy concluído.**
Testes sintéticos usam banco local descartável; nunca comprovam atividade de
clientes reais. As contagens de testes dos pacotes se sobrepõem e não devem ser
somadas como testes distintos de uma única execução.

## 2. Produção confirmada e próximo release

| Camada | Evidência disponível neste corte | Estado e próximo aceite |
| --- | --- | --- |
| Painel do release 1 | Registro `061001f`, Vercel `dpl_EWt5jneXQkyEAYvQzEaGtqyv2Yeu`; login 200, APIs privadas anônimas 401 e disponibilidade pública 200 no [registro de execução](EXECUCAO_COMPLETA.md) | Publicação anterior registrada. Não usar essa prova para certificar telas novas do release 2. |
| Catálogos em produção | [Prova de carga por SELECT](catalog-release-20260917/production-proof.json): Meet 276, Madonna 253, Frêneze 210; hashes dos três bundles | **739 itens carregados.** `SOURCE_VERIFIED` / fonte verificada; aprovação humana item a item continua pendente. |
| Prompts finais das três casas | [Versões e hashes](catalog-release-20260917/prompt-final-drafts.json): Frêneze v4, Madonna v14, Meet v15, todos com `ativa=false` no artefato | Rascunhos persistidos e versionados. Saída do modo seguro, visão e uso dos links próprios não são certificados por um rascunho inativo. Registrar a ativação e os testes posteriores. |
| Backend do release 2 | Pacotes de agenda, CTWA/custo, CRM, régua e handoff integrados; último código inspecionado `9792d26`; [PR #42](https://github.com/ikeguimaraes-dot/serena-kph/pull/42) aberto no corte | **Publicação ainda pendente de prova.** Registrar merge/main, commit efetivamente implantado, resultado Railway e checks de leitura. Migração aplicada isoladamente não comprova comportamento do deploy. |
| Frontend do release 2 | Commit informado `154a540`, com ajuste de concorrência da reserva em andamento; contratos em [E06](#e06--reserva-pública) | **Publicação ainda pendente de prova.** Registrar commit final, deploy Vercel e verificação das telas/rotas nas quatro unidades. |
| Templates de reserva | Confirmação e lembrete criados/submetidos; status observado `received`, zero mensagens enviadas, no artefato preparado `reservation-template-proof-20260917.json` | Submissão **não é aprovação**. Aguardar status `approved`, configuração por unidade e demais portas da régua. Scheduler/etapas de reserva ainda em implementação no corte; não declarar disparo automático ativo. |
| Backup privado | Primeiro snapshot de 64 tabelas, 988 linhas e 4 prompts restaurado; job local diário às **03:15** ativado [E02](#e02--backup-e-restauração) | Entregue com dependência do Mac/sessão/rede. Os números são do snapshot de teste, não a contagem atual após novas migrações. Não há cópia em GitHub ou artifact público. |

O mantenedor do release deve atualizar esta seção com as provas finais antes de
trocar “preparado” por “publicado”. Não criar reservas, leads ou mensagens
sintéticas em produção apenas para produzir uma prova de sucesso.

## 3. Sprint 1 — fechar o incidente

| ID / item do plano | Estado | Entrega e evidência | Critério ainda aberto |
| --- | --- | --- | --- |
| **S1.1 — Carga do catálogo Meet** | Depende de operação | 276 itens atuais carregados, prova por SELECT; importação/reimportação e preservação de edição manual testadas [E01](#e01--catálogos-e-prompts). A fonte antiga tinha 277; a ausência de um produto foi documentada, sem exclusão automática. | **Ike conferir e aprovar item a item**, registrando diferenças e a versão revisada. Carga e fonte verificada não substituem esse aceite. |
| **S1.2 — Extrair Frêneze e Madonna** | Entregue | CSVs revisáveis, fontes brutas e hashes: Frêneze 210 itens e Madonna 253. Preços ausentes/zerados, variantes e componentes têm tratamento explícito [E01](#e01--catálogos-e-prompts). | Revisão operacional integra o aceite do catálogo; extração não comprova estoque. Valor anômalo permanece fiel à fonte até correção confirmada. |
| **S1.3 — Sair do modo seguro nas duas casas** | Em validação | Rascunhos de prompt de Meet/Madonna preparados com consulta ao catálogo, sem preços fabricados [E01](#e01--catálogos-e-prompts). | Publicar dependências, ativar a versão correta e comprovar conversa da unidade, cardápio consultável e fallback. Os rascunhos finais estão inativos na prova disponível. |
| **S1.4 — `lookup_menu` com base vazia** | Em validação | Resposta explícita de base indisponível, distinguindo catálogo vazio de item não encontrado; testes de segurança do menu e modo de teste sem escrita [E01](#e01--catálogos-e-prompts). | Anexar commit/deploy que contém a correção e resultado do contrato na versão publicada. Não converter indisponibilidade em “não temos”. |
| **S1.5 — Equipe e handoff Madonna/Meet** | Depende de operação | Estado persistido, resposta humana com SID observado, isolamento da unidade e bloqueio de autoenvio testados [E05](#e05--handoff). Fonte de contato Meet localizada; contato de gerente Madonna identificado, responsabilidade pendente. | Confirmar titular/suplente e cobertura, cadastrar destino humano seguro e comprovar recebimento/assunção/resposta. Telefone cadastrado ou SID não comprova entrega a uma pessoa. |
| **S1.6 — Produção reconciliada com main e rota clínica** | Em validação | Código integrado, regressões de roteamento/handoff e proteção da rota clínica [E03](#e03--acesso-e-isolamento) / [E05](#e05--handoff). PR #42 preparado para release 2. | Registrar main e commit real de produção; conferir rota clínica na publicação e validação operacional autorizada. Não certificar entrega clínica a partir de mock. |
| **S1.7 — `restaurants` com dados reais nas quatro unidades** | Depende de operação | Fontes oficiais de catálogo/links e dados públicos localizados; cabeçalho dinâmico evita preencher dado ausente com defaults [E01](#e01--catálogos-e-prompts) / [E08](#e08--onboarding-acessos-e-comercial). | Conferir campos de cada unidade, fontes, horários, capacidade e contatos; remover placeholders apenas com dado confirmado. Não há prova de cadastro completo nas quatro. |
| **S1.8 — Bloco de visão nas três casas** | Em validação | Regra de imagem preparada nas versões de prompt das três casas [E01](#e01--catálogos-e-prompts). | Ativar versões e testar reconhecimento de imagem na unidade correta, sem assumir conteúdo de imagem não interpretada. Preparação do prompt não prova reconhecimento em operação. |

## 4. Sprint 2 — instrumentar

| ID / item do plano | Estado | Entrega e evidência | Critério ainda aberto |
| --- | --- | --- | --- |
| **S2.1 — CTWA em conversas/reservas** | Em validação | Captura real de `ReferralCtwaClid`/`MessageSid`; persistência idempotente por unidade/SID; reserva recebe último referral elegível da mesma unidade/telefone em sete dias [E04](#e04--instrumentação-e-relatório). | Publicar e observar novos eventos reais elegíveis. Sem backfill: ausência de CTWA antigo não comprova origem orgânica. Persistência idempotente não promete processamento externo exatamente uma vez. |
| **S2.2 — Desfecho de reserva** | Em validação | Reuso de status existentes; constraint aceita `realizada` e preserva `concluida`; histórico prospectivo de transições com operador/fonte [E04](#e04--instrumentação-e-relatório) / [E07](#e07--crm-e-histórico). | Publicar API/UI; definir operador e momento para registrar realização, cancelamento ou no-show. Não completar desfecho por tempo decorrido. |
| **S2.3 — Backup periódico externo e restore** | Entregue | Dump privado fora do Supabase/Git, restauração comparada por tabelas/contagens/hashes; job Mac 03:15 ativado [E02](#e02--backup-e-restauração). | Monitorar frescor/restore e providenciar segundo destino privado/execução independente do Mac. Binários de Storage e configurações externas não estão cobertos pelo dump. |
| **S2.4 — Titularidade dos acessos** | Depende de operação | Inventário de recursos, campos de dono/suplente/cofre/recuperação e checklist preparados [E08](#e08--onboarding-acessos-e-comercial). | Preencher inventário privado nominal e testar recuperação com segundo responsável. Sessão autenticada não comprova titularidade nem recuperação. |
| **S2.5 — Custo por conversa no WBR** | Em validação | Uso/modelo observados; componentes de cache e tarifa versionada; relatório por unidade e coleta semanal corrigida [E04](#e04--instrumentação-e-relatório). | Publicar, medir período com volume real e publicar WBR com denominador explícito. Conciliar Twilio/fatura, custos fora do agente principal e câmbio; legado sem cache não será recalculado como custo completo. |
| **S2.6 — Horários e agenda Meet/Frêneze** | Depende de operação | Auditoria pública de disponibilidade e regras observadas, sem transformar mesas disponíveis em capacidade fixa [E09](#e09--agenda-e-legado-tagme). | **1 de 3 agendas próprias configurada; faltam Meet e Frêneze.** Confirmar turnos, ambientes, capacidade compartilhada, duração, antecedência e bloqueios; validar também a agenda existente da Madonna. |

## 5. Sprint 3 — CRM mínimo

| ID / item do plano | Estado | Entrega e evidência | Critério ainda aberto |
| --- | --- | --- | --- |
| **S3.1 — Cliente por telefone e unidade** | Em validação | Cadastro existente reaproveitado; leitura/escrita por tenant, histórico de reserva, preferências e consentimento com evidência/revogação [E03](#e03--acesso-e-isolamento) / [E07](#e07--crm-e-histórico) / [E10](#e10--régua-e-consentimento). | Validar dados e fluxos nas unidades publicadas. Histórico de visita depende de desfecho real; cadastro de consentimento não certifica toda a governança de dados. |
| **S3.2 — Agente consulta ficha antes de responder** | Em validação | Contexto e ferramentas propagam a unidade; testes impedem usar ficha de outra casa com o mesmo telefone [E03](#e03--acesso-e-isolamento). | Comprovar reconhecimento por nome e última visita existentes em cenário autorizado. Sem visita registrada, não inventar recorrência. |
| **S3.3 — Ficha no painel sem SQL** | Em validação | CRM isolado e permissões operacionais; painel com consentimento/histórico preparado para release 2 [E03](#e03--acesso-e-isolamento) / [E07](#e07--crm-e-histórico). | Publicar frontend final e validar leitura/edição com perfil de atendimento e unidade selecionada. Conta criada não comprova uso do fluxo. |
| **S3.4 — Régua por evento com templates aprovados** | Em validação | Retorno/nurture com outbox por evento/unidade, consentimento auditável, aprovação consultada e uma tentativa; dry-run padrão [E10](#e10--régua-e-consentimento). Confirmação/lembrete submetidos; scheduler/etapas ainda em implementação no corte. | Concluir integração e prova, obter `approved`, configurar regras e validar consentimento/evento antes de habilitar. Todos os envios permanecem desligados por padrão; nenhum disparo real foi certificado. |

## 6. Sprint 4 — funil

| ID / item do plano | Estado | Entrega e evidência | Critério ainda aberto |
| --- | --- | --- | --- |
| **S4.1 — Estágio e motivo de perda** | Em validação | Estágios do CRM existentes, lista fechada de perda e histórico prospectivo; perda sem motivo recusada; inatividade não vira perda automática [E07](#e07--crm-e-histórico). | Publicar UI/API e assegurar rotina de classificação pelo operador. Ter campos/validação não prova que todas as conversas foram classificadas; não inventar motivo histórico. |
| **S4.2 — Dashboard de funil** | Em validação | Relatório determinístico inclui conversa → intenção → proposta registrada → reserva → realização/no-show; unidade/período explícitos, frontend em integração [E04](#e04--instrumentação-e-relatório). | Publicar tela e validar denominadores/lacunas com operação. Proposta registrada não prova envio; reserva de mesa pode não passar por proposta. |
| **S4.3 — Conversão por casa/persona no WBR** | Em validação | Taxas por unidade e nome atual do agente no relatório; períodos e versão do relatório definidos [E04](#e04--instrumentação-e-relatório). | Publicar semanas comparáveis de dados reais. Nome atual da persona não reconstrói versões antigas; falta série longitudinal para comparação por versão/persona sem viés. |
| **S4.4 — Receita atribuída em duas casas** | Depende de operação | Receita realizada, custo Twilio e ROI ficam nulos enquanto faltam fontes; pagamentos registrados são agregado identificado, não faturamento conciliado [E04](#e04--instrumentação-e-relatório). | Conciliar documentos financeiros, reservas/OS, estornos, datas e regra de atribuição em **duas casas**. A análise offline em preparação não fecha receita sem documentos reais. |

## 7. Sprint 5 — reserva própria

| ID / item do plano | Estado | Entrega e evidência | Critério ainda aberto |
| --- | --- | --- | --- |
| **S5.1 — Página pública na mesma agenda** | Em validação | Página/API próprias; serviço compartilhado com reserva do agente/painel; lock de capacidade e idempotência; corrida pela última vaga e duplo clique testados [E06](#e06--reserva-pública). | Publicar frontend/backend coordenados e validar configuração real. Sem agenda, mostrar indisponibilidade de configuração. A garantia cobre escritores desta aplicação, não inventário Tagme ou SQL externo. |
| **S5.2 — Link próprio nos prompts** | Em validação | Links por unidade no código e rascunhos finais; fontes oficiais preservadas para continuidade [E01](#e01--catálogos-e-prompts) / [E06](#e06--reserva-pública). | Primeiro comprovar página publicada; depois ativar prompt e verificar link da unidade. Não retirar continuidade externa de uma agenda própria ainda não configurada. |
| **S5.3 — Exportar/importar histórico e fila** | Depende de operação | Auditoria somente leitura confirmou venues e disponibilidade pública; plano de importação por ID legado/venue [E09](#e09--agenda-e-legado-tagme). | **Nenhuma linha histórica exportada/importada.** Obter exportação autorizada por venue ou contrato de API autenticada. Resposta 401 foi respeitada; não confundir falta de acesso com histórico vazio. |
| **S5.4 — Dados estruturados para busca** | Em validação | JSON-LD factual e SSR incluídos/testados na página pública [E06](#e06--reserva-pública). | Verificar HTML publicado, URL canônica, rastreabilidade/indexabilidade e elegibilidade na ferramenta de validação. Presença de JSON-LD não garante indexação, posição nem resultado enriquecido. |

## 8. Sprint 6 — provar white label

| ID / item do plano | Estado | Entrega e evidência | Critério ainda aberto |
| --- | --- | --- | --- |
| **S6.1 — Onboarding executável por terceiro** | Depende de operação | Briefing, template, validador, checklist, donos por função, portões e reversão preparados [E08](#e08--onboarding-acessos-e-comercial). | Preencher dossiê real, delegar responsáveis, executar sem dependência diária de Ike e medir prazo. Preço e prazo reais continuam abertos; fixture sintética não aprova go-live. |
| **S6.2 — Um cliente externo operando** | Depende de operação | Critério do piloto e operação assistida documentados [E08](#e08--onboarding-acessos-e-comercial). | Selecionar/contratar escopo de cliente fora do grupo, cumprir onboarding, colocar agente no ar e registrar uso/aceite reais. Nenhum cliente externo está comprovado nesta execução. |
| **S6.3 — Preço com base em dados reais** | Depende de operação | Método de custo, rateio, margem, franquia e implantação; cálculo só com entradas válidas [E08](#e08--onboarding-acessos-e-comercial). | Obter período representativo conciliado e aprovar tabela, franquia, excedente e setup. Piso calculado não é decisão comercial; não há preço de tabela real aprovado. |
| **S6.4 — Proposta e objeções** | Entregue | Proposta utilizável como modelo e matriz de objeções, com alegações limitadas às provas [E08](#e08--onboarding-acessos-e-comercial). | Preencher cliente, escopo, valores, prazo e condições antes de emitir oferta. Material pronto não equivale a venda, contrato ou resultado comercial. |

## 9. Dados e decisões que faltam para a operação

Manter respostas nominais, telefones, documentos de clientes, faturas e
credenciais em armazenamento privado. Este repositório é público.

| Dependência | Entrega objetiva solicitada | Quem resolve / prova de saída |
| --- | --- | --- |
| Catálogo | Conferência de itens, preços, variantes e indisponibilidades dos três CSVs; registrar divergências sem corrigir por inferência | Ike/revisor operacional autorizado; aceite por versão/hash. O aceite exigido do Meet permanece explícito. |
| Agenda/capacidade | Meet e Frêneze: capacidade por ambiente e compartilhamento de mesas, turnos semanais, duração/ocupação, limites, antecedência e bloqueios. Madonna: confirmar regras atuais | Responsável de cada casa; matriz datada/aprovada e teste na mesma agenda usada pelo agente/painel. |
| Destino humano | Titular e suplente por unidade, responsabilidade, cobertura e canal seguro. Contato Meet tem fonte confirmada; responsabilidade Madonna ainda precisa de confirmação | Operação; cadastro + recebimento observado + assumir/responder/resolver. Nunca cadastrar sender do bot como humano. |
| Templates | Aprovação efetiva de confirmação/lembrete/retorno e, separadamente, template de alerta à equipe quando necessário | Meta/Twilio + operador do canal; status `approved` consultado e configuração por unidade. Não reutilizar template com outra finalidade. |
| Consentimento | Fonte, data, finalidade/evidência e operador; revogação respeitada | Operador autorizado; último evento auditável. Booleano legado, reserva ou conversa recebida não bastam. |
| Legado | Exportação de reservas e fila por venue, com ID, status e datas/fuso; manifesto e contagens em pasta privada | Administrador Tagme + engenharia; ensaio/diff por unidade antes de importar. |
| Receita/custos/preço | Documentos financeiros de duas casas; custos Twilio/modelo/infra/suporte no mesmo período; descontos/estornos/câmbio; decisão de margem e franquia | Financeiro/comercial; conciliação revisada e tabela aprovada. Não transformar OS ou valor marcado pago em faturamento total. |
| Acessos/recuperação | Dono, suplente, cofre e recuperação testada de cada recurso do inventário | Titulares das contas; prova privada datada com segundo responsável. |
| Primeiro cliente externo | Cliente real, escopo aceito, donos, briefing, acompanhamento e janela de aceite | Comercial/operação; piloto em uso fora do grupo e prazo medido. |

## 10. Ritual de operação e aceite do release

1. **Antes da publicação:** backup validado; aplicar migrações aditivas previstas;
   revisar contratos backend/frontend, auth e sequência de deploy. Registrar o
   commit efetivo de cada serviço. Preservar histórico em qualquer reversão.
2. **Após publicar:** conferir login, rejeição anônima das rotas privadas,
   isolamento entre unidades, catálogos e páginas públicas. Uma agenda não
   configurada deve continuar explicitamente não configurada. Não ativar mensagens
   junto do deploy.
3. **Antes de ativar prompts/régua:** registrar versões ativas, dono operacional,
   fonte de conteúdo, agenda ou continuidade aprovada e os gates específicos de
   consentimento/template/evento. Fazer dry-run; aceitação de API e entrega são
   estados diferentes. `unknown`/`dispatching` exigem conciliação antes de reenvio.
4. **Diariamente:** verificar frescor do backup (o comando `--status` sinaliza
   atraso acima de 36 horas), handoffs aguardando/sem aceitação comprovada, reservas
   pendentes de confirmação/desfecho e tentativas ambíguas da outbox. Definir
   responsável e suplente; este documento não cria um SLA numérico.
5. **Semanalmente:** WBR com período/fuso, versão do relatório, volume e cobertura,
   conversão por unidade, status de reserva, custos completos/legados separados,
   perdas registradas e lacunas. Sem denominador, dado ou conciliação, usar
   “não medido”/nulo; nunca zero inventado.

Backup atual: Mac local com FileVault, pastas privadas e restore descartável
comprovado. Depende de máquina/sessão/rede. Não inclui binários de Storage, segredos
ou configuração de todos os provedores. Um segundo destino privado independente
e teste de recuperação por suplente continuam necessários; não publicar dumps,
dados de clientes ou segredos em GitHub.

## 11. Índice de evidências

### E01 — catálogos e prompts

[Pacote de publicação](catalog-release-20260917/README.md),
[SELECTs da produção](catalog-release-20260917/production-proof.json),
[prompts finais inativos](catalog-release-20260917/prompt-final-drafts.json),
[Meet/manifesto](../sprint1/catalogos/README.md),
[Frêneze](../sprint1/catalogos/freneze/README.md),
[Madonna](../sprint1/catalogos/madonna/README.md).
Testes: [importação no restore](../../scripts/test_catalog_restore.py),
[menu indisponível](../../files/restaurant-ai/test_menu_availability.py).
Frêneze: a tentativa HTML retornou 403; fontes públicas referenciadas retornaram
200, com origem documentada. Não foi contornado acesso autenticado.

### E02 — backup e restauração

[Runbook/limites/job 03:15](BACKUP_E_RESTAURACAO.md),
[prova sanitizada](backup-restore-proof-20260917.json),
[testes offline](../../scripts/test_serena_backup.py).
O archive e a prova completa permanecem privados, fora do repositório.

### E03 — acesso e isolamento

[Contrato/rollout](../AUTH_ROLLOUT_2026-09-17.md),
[teste CRM com mesmo telefone em tenants distintos](../../files/restaurant-ai/test_crm_tenancy_contract.py).
Testes de autorização e contexto usam mocks; o contrato SQL foi validado com
rollback, sem ler clientes existentes ou enviar mensagens.

### E04 — instrumentação e relatório

[Contrato CTWA/custos](../sprint2/INSTRUMENTACAO_E_RELATORIO.md),
[prova de restore](../sprint2/VALIDACAO_INSTRUMENTACAO.json),
[relatório atual v2](../../files/restaurant-ai/commercial_report.py),
[testes](../../files/restaurant-ai/test_instrumentation.py).
O contrato inicial antecede o histórico de CRM e a etapa de proposta; o código v2
e E07 descrevem essas ampliações. Relatório usa status atual das reservas;
histórico prospectivo não reconstrói períodos anteriores à implantação.

### E05 — handoff

[Contrato e limites de entrega](../sprint1/handoff/CONFIABILIDADE.md),
[prova de restore + 43 testes offline](../sprint1/handoff/VALIDACAO_CONFIABILIDADE.json),
[testes de concorrência/estado](../../files/restaurant-ai/test_handoff_reliability_restore.py).
Zero mensagens reais nesses testes. Não há certificação de recebimento humano.

### E06 — reserva pública

[Contrato, compatibilidade e validação](../PUBLIC_RESERVATIONS_SPRINT5.md),
[serviço compartilhado](../../files/restaurant-ai/reservation_service.py),
[testes de API](../../files/restaurant-ai/test_public_reservations.py).
Ensaio de última vaga: uma criação e um conflito; mesma chave concorrente: uma
criação e um replay. Resultado da reserva pública é pendente de confirmação, sem
cobrança nem mensagem automática. QA visual de navegador não foi comprovado.

### E07 — CRM e histórico

[Estágios, perdas e desfechos](CRM_ESTAGIOS_E_DESFECHOS.md),
[prova de restore](crm-history-proof-20260917.json),
[testes de histórico](../../files/restaurant-ai/test_crm_history_restore.py).
Preserva contatos antigos e valores legados; não cria eventos históricos falsos.

### E08 — onboarding, acessos e comercial

[Pacote operacional e comercial](ONBOARDING_WHITE_LABEL.md),
[template](onboarding/template.json),
[validador](../../scripts/validate_onboarding.py),
[testes](../../scripts/test_validate_onboarding.py).
Validar declarações/formato não autentica evidências nem aprova go-live por si só.

### E09 — agenda e legado Tagme

[Auditoria e dependências](TAGME_LEGADO_E_TURNOS.md),
[prova pública sanitizada](tagme-audit-proof-20260917.json).
Disponibilidade observada não é capacidade física nem regra semanal permanente.
Sem exportação de dados pessoais nesta auditoria.

### E10 — régua e consentimento

[Gates, API, outbox e limites](../sprint2/REGUA_CONSENTIMENTO_OUTBOX.md),
[prova de restore + 33 testes offline](../sprint2/VALIDACAO_REGUA_OUTBOX.json),
[testes](../../files/restaurant-ai/test_outreach.py).
O pacote documentado cobre retorno/nurture. Confirmação, lembrete e scheduler
adicionais precisam de prova própria de integração/publicação. Nenhum estado
`sent` equivale a entregue/lido; erro/timeout não autoriza retry cego.

## 12. Fronteira do trimestre

Fila conversacional, novo produto de pagamentos/caução, integração PDV, app
próprio e abertura formal de nova vertical continuam fora dos 90 dias, conforme
seção 3.4 do Book. Preservar registros manuais de pagamento existentes não
significa entregar adquirência. Preparar conciliação offline não significa
integração com PDV. Não há promessa de resultado financeiro, retenção, prazo
externo ou SLA ainda não medido/aprovado.
