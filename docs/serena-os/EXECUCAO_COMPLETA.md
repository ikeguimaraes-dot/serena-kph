# Serena OS — fechamento da execução técnica

**17/09/2026.** Autorização: executar o Book Mestre v1.1 preservando a operação.
Os checkouts originais foram preservados; alterações passaram por branches isoladas,
testes, publicação e conferência. A implantação técnica avançou nos seis sprints;
os resultados operacionais de 90 dias ainda dependem dos itens abaixo.

## Publicado e conferido

- **Painel:** https://madonna-painel.vercel.app. Commit `551c0f4`,
  [PR #5](https://github.com/ikeguimaraes-dot/restaurant-ai-painel/pull/5),
  Vercel `dpl_2i5yJFWx3SYqZNS2YMmNsmjq6Nuu` **READY**, alias de produção atualizado.
- **Backend:** [PR #43](https://github.com/ikeguimaraes-dot/serena-kph/pull/43),
  main `bdea71119779c6dc711ac6b9a8c213b9f8eedc2a`, Railway
  `0d93de0b-ff1f-46a8-b75c-8718f4c30d9d` **SUCCESS**. Este é o release funcional
  comprovado; commits posteriores de prova/documentação não alteram o runtime.
- **Contas:** Ike, administrador; Vic, atendimento; ambas existem, vinculadas ao
  operador e com e-mail confirmado. A API da Vic retornou 200 para CRM/consentimento
  e 403 para administração de régua/prompts. Isso não substitui ensaio de login
  interativo com o usuário.
- **Catálogo:** 739 itens em produção — Meet 276, Madonna 253, Frêneze 210.
  Fontes/hashes e variantes preservados; aprovação humana item a item pendente.
- **Prompts ativos:** Meet `v15-catalogo-agenda`, Madonna `v14-catalogo-agenda`,
  Frêneze `v4-catalogo-agenda`. Levvai continua `v1`, com rota clínica preservada.
  Ativação por unidade e SELECT de IDs/hashes conferidos; versões anteriores mantidas.
- **CRM e funil:** ficha por telefone/unidade, acesso operacional da Vic, estágios,
  motivo de perda, histórico prospectivo de mudanças/desfechos, origem CTWA e WBR.
  Relatório v3 mostra cobertura/custo e versão de prompt efetivamente observada.
  Custo por contato é nulo quando faltam métricas; receita não é fabricada.
- **Reserva própria:** `/reservar/{unidade}`, agenda compartilhada com painel/agente,
  controle de capacidade e idempotência. Madonna retornou cinco horários disponíveis
  em 19/09; domingo sem turno fica desconhecido. Meet/Frêneze mantêm continuidade
  pelos links oficiais enquanto faltam regras reais de agenda.
- **Handoff:** estado durável, prevenção de duplicidade e autoenvio, resposta humana
  vinculada ao aceite do provedor. Não há prova de recebimento humano nas quatro casas.
- **Régua:** confirmação, lembrete, retorno, consentimento auditável e scheduler
  implementados. Seis regras de confirmação/lembrete configuradas **desativadas**.
  Templates Meta em `pending`; envio/scheduler globais desligados; outbox com zero.
- **Portabilidade e comercial:** exportador privado de 11 tabelas por unidade,
  conciliação offline de recebimentos, pacote de onboarding, proposta e objeções.
  Nenhum dado real exportado ao repositório público.

## Validação

- 61 testes backend integrados; exportador com 4 testes offline; visão com 7 testes.
- 27 testes de frontend, ESLint do relatório e build Next.js de 17 páginas passaram.
- Ensaios em PostgreSQL restaurado verificaram isolamento entre unidades, corrida
  pela última vaga, replay idempotente, histórico, régua, custo e snapshot de exportação.
- Leitura em produção: saúde e login 200; APIs privadas sem sessão 401; páginas
  públicas/JSON-LD e relatórios das quatro unidades 200; permissões da Vic conferidas.
- Testes reais de modelo, sem persistência/envio: Madonna **R$ 108,08** para Carne
  Cruda e Frêneze **R$ 349,00** para Experiência, ambos fiéis à fonte. Agenda desconhecida
  retorna confirmação pendente e link próprio. Levvai respondeu como Eva.
- Visão: três chamadas reais reconheceram formas/cores de fixture sintética sem
  inventar preço ou disponibilidade; custo observado **US$ 0,07653975**.
  Cobre compreensão da imagem no motor; download por Twilio não foi ensaiado.
- Não havia navegador disponível para QA visual; contratos e renderização React
  foram verificados, sem alegar inspeção visual ou teste de entrega no WhatsApp.

**Backup final restaurado:** 71 tabelas, 1.746 linhas e 10 versões de prompt,
com conjunto de tabelas, contagens e hashes iguais ao snapshot. Arquivo privado
`20260917T052650.483645Z`; rotina diária local às 03:15. Depende do Mac conectado;
ainda não é cópia externa sempre disponível, nem inclui binários do Storage.

## O que ainda exige operação

1. Conferência humana dos catálogos e confirmação de dados ausentes das casas.
2. Turnos, capacidade e regras reais de Meet/Frêneze; aceite da agenda Madonna.
3. Responsáveis/suplentes e recebimento comprovado de handoff, especialmente Madonna/Meet.
4. Aprovação Meta dos templates, consentimentos com evidência e ativação coordenada da régua.
5. Exportação autorizada do legado Tagme: API protegida retornou 401, respeitado.
6. Inventário nominal de titularidade, recuperação por suplente e segundo destino de backup.
7. Receita documentada de duas casas, período de custos representativo, preço aprovado
   e um cliente externo real. Ferramentas entregues não comprovam esses resultados.

A revisão Supabase não encontrou ERROR de segurança. Permanece aviso anterior de
[proteção contra senhas vazadas desabilitada](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).
As 33 informações de RLS sem policy correspondem a tabelas privadas operadas pelo backend.

## Evidências e continuidade

- [Matriz dos 30 itens](OPERACAO_E_PENDENCIAS.md).
- [Verificação de produção](production-verification-final-20260917.json).
- [Ativação e regras desativadas](prompt-activation-final-20260917.json).
- [Catálogo carregado](catalog-release-20260917/production-proof.json).
- [Visão real](vision-readonly-proof-20260917.json) e [backup final](backup-final-proof-20260917.json).
- [Régua e reversão](REGUA_RESERVA_E_AGENDAMENTO.md), [exportação privada](EXPORTACAO_PRIVADA_POR_UNIDADE.md),
  [conciliação financeira](../sprint4/CONCILIACAO_OFFLINE.md), [onboarding](ONBOARDING_WHITE_LABEL.md).

Para reverter conteúdo, ativar a versão anterior apenas da unidade afetada pelo
endpoint administrativo, sem apagar histórico. Para runtime, Railway/Vercel mantêm
releases anteriores. Interromper a régua por regra/env; não apagar tentativas para
forçar reenvio. Não restaurar backup sobre produção sem plano concreto de recuperação.
Pagamento/caução novo, fila conversacional, PDV, app e oferta formal de saúde
continuam fora do trimestre, conforme o Book.
