# Serena OS — matriz dos 30 itens e pendências

**Corte: 17/09/2026, após publicação e backup final.** Referência: [Book Mestre](BOOK_MESTRE_v1.1_2026-09-17.md).
Provas, commits, deploys e limites: [fechamento da execução](EXECUCAO_COMPLETA.md).

A coluna entregue descreve código, configuração ou artefato comprovado. A coluna
aberta descreve o aceite que ainda impede declarar 100% dos 90 dias concluídos.
Uma implantação não equivale a catálogo aprovado, mensagem recebida, venda ou receita.

| Item | Escopo | Entregue/comprovado | Aceite ainda aberto |
|---|---|---|---|
| S1.1 | Catálogo Meet | 276 itens carregados e fontes verificadas. | Aceite humano item a item. |
| S1.2 | Catálogos Frêneze/Madonna | 210 e 253 itens extraídos, carregados e versionados. | Conferência operacional e estoque. |
| S1.3 | Saída do modo seguro | Meet v15/Madonna v14 ativos; preço real consultado. | Monitorar conversas reais e divergências. |
| S1.4 | Consulta vazia segura | Contrato publicado; base vazia/erro não vira negativa de produto. | Monitoramento contínuo. |
| S1.5 | Equipe e handoff | Estado/concorrência/resposta/isolamento publicados. | Titular/suplente/canal e recebimento humano comprovado. |
| S1.6 | Main e clínica | Main reconciliada, deploy SUCCESS, rota clínica preservada; Eva respondeu no teste readonly. | Ensaio operacional de recebimento clínico autorizado. |
| S1.7 | Dados das quatro casas | Dados confirmados de sites/telefones/limites aplicados; ausências preservadas. | Completar fontes de Madonna, telefone Frêneze e regras operacionais. |
| S1.8 | Visão nas três casas | Prompts ativos; 3/3 chamadas multimodais reais passaram. | Download de anexo Twilio não foi ensaiado. |
| S2.1 | CTWA | Captura e atribuição prospectiva por unidade/SID/janela publicadas. | Novos eventos reais elegíveis; sem origem retroativa inventada. |
| S2.2 | Desfecho | API/UI e histórico prospectivo de status publicados. | Operador registrar realizado/cancelado/no-show reais. |
| S2.3 | Backup e restore | 71 tabelas/1.746 linhas/10 prompts restaurados; job diário 03:15. | Segundo destino privado e execução independente do Mac. |
| S2.4 | Titularidade | Inventário/checklist e limites documentados. | Dono/suplente/cofre e ensaio de recuperação reais. |
| S2.5 | Custo no WBR | v3 publicado com cobertura e versão observada; lacunas viram null. | Período representativo, Twilio/faturas/câmbio/infra conciliados. |
| S2.6 | Três agendas | Madonna existente preservada; páginas com continuidade oficial. | Configurar Meet/Frêneze com capacidades/turnos reais. |
| S3.1 | Ficha por telefone/unidade | CRM, preferências e consentimento auditável publicados. | Higiene e desfechos reais; consentimento não é presumido. |
| S3.2 | Consulta da ficha pelo agente | Contexto e testes de isolamento por unidade implementados. | Reconhecimento de última visita depende de registro real. |
| S3.3 | Ficha para Vic | Menu/API liberados ao atendimento; CRM/consentimento 200, administração 403. | Aceite de uso interativo pela equipe. |
| S3.4 | Régua por evento | Motor/scheduler completos; seis regras de reserva preparadas desativadas. | Templates Meta pending; evidência de consentimento e ativação operacional. |
| S4.1 | Estágio/motivo de perda | Validação de motivo e histórico publicados; legado preservado. | Classificação real pela equipe, sem perda por inatividade automática. |
| S4.2 | Funil | Conversas/intenção/proposta/reserva/desfecho no relatório determinístico publicado. | Revisão operacional dos denominadores e preenchimento de desfechos. |
| S4.3 | Conversão/persona | Conversão por unidade e métricas por versão efetivamente registrada no WBR. | Série longitudinal; sem reserva atribuída à versão por inferência. |
| S4.4 | Receita em duas casas | Conciliação offline com documentos, Decimal, estornos e completude. | Recebimentos reais conciliados nas duas casas; causalidade não comprovada. |
| S5.1 | Reserva própria | Página/API publicadas, capacidade compartilhada e idempotência testadas. | Configuração real de cada casa; inventário externo Tagme não é sincronizado. |
| S5.2 | Links próprios | Ativos nos três prompts, páginas publicadas e fallback oficial mantido. | Concluir configuração das agendas. |
| S5.3 | Histórico e fila legados | Auditoria pública e processo de migração preparados; exportador Serena privado pronto. | Exportação Tagme autorizada; zero linhas de legado importadas. |
| S5.4 | Busca | SSR/JSON-LD e páginas 200 conferidos nas quatro unidades. | Indexação/elegibilidade externa não garantidas. |
| S6.1 | Onboarding por terceiro | Briefing, validador, responsabilidades/checklist e reversão entregues. | Execução real com responsáveis e prazo medido. |
| S6.2 | Cliente externo | Critérios de piloto/operação assistida documentados. | Selecionar, contratar, implantar e comprovar cliente fora do grupo. |
| S6.3 | Preço por dados | Método de custo/margem/franquia e cálculo com dados válidos. | Custos conciliados e decisão comercial de preço. |
| S6.4 | Proposta/objeções | Modelo comercial e matriz de objeções entregues. | Preencher cliente, escopo, valores e condições antes de oferta. |

## Dependências imediatas

- **Ike/operação:** conferir catálogo, turnos/capacidades, titulares/suplentes e contatos.
- **Meta/Twilio:** decisão dos templates e do nome/verificação empresarial no ticket existente.
  A correção do backend não comprova conclusão desse processo externo.
- **Operação/dados:** exportação autenticada Tagme, documentos de recebimentos e classificação real.
- **Gestão:** titularidade/recuperação, segundo destino de backup, preços e cliente externo.

Nenhuma dessas pendências autoriza preencher valores fictícios ou enviar campanhas
sem a evidência necessária. O sistema novo opera com fallback nas lacunas.

## Guias para continuidade

- [Catálogos e provas](catalog-release-20260917/production-proof.json).
- [Handoff](../sprint1/handoff/CONFIABILIDADE.md) e [CRM/desfechos](CRM_ESTAGIOS_E_DESFECHOS.md).
- [Instrumentação](../sprint2/INSTRUMENTACAO_E_RELATORIO.md) e [cobertura/versão v3](../sprint2/VALIDACAO_CUSTO_VERSAO.json).
- [Reserva pública](../PUBLIC_RESERVATIONS_SPRINT5.md), [Tagme/turnos](TAGME_LEGADO_E_TURNOS.md).
- [Régua](REGUA_RESERVA_E_AGENDAMENTO.md), [templates](reservation-template-proof-20260917.json).
- [Exportação privada](EXPORTACAO_PRIVADA_POR_UNIDADE.md), [conciliação](../sprint4/CONCILIACAO_OFFLINE.md).
- [Onboarding/proposta/precificação](ONBOARDING_WHITE_LABEL.md).

As contagens de testes entre pacotes se sobrepõem e não devem ser somadas.
Não houve QA visual no navegador nem certificação ponta a ponta de envio WhatsApp.
Fila conversacional, novo pagamento/caução, PDV, app e oferta formal de saúde seguem
fora dos 90 dias. Os checkouts originais permanecem preservados.
