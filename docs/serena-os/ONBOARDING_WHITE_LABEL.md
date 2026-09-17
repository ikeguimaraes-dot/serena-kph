# Onboarding Serena OS e operação assistida

Versão 1, 17/09/2026. Pacote executável local para o Sprint 6 e inventário de
titularidade do Sprint 2. Referência: Book Mestre v1.1, seções 2.4, 3.3, 5 e 6.

**Entregue:** briefing estruturado, sequência de implantação, portões com prova,
inventário sem segredos, método de custo/preço, proposta e matriz de objeções.
**Ainda não comprovado:** cliente externo operando, prazo de onboarding real,
custo representativo por unidade, preço/franquia aprovados e recuperação de todas
as contas por um segundo responsável. Este pacote não cria um cliente fictício em
produção nem transforma essas pendências em conclusão do Sprint 6.

## 1. Como executar sem depender do fundador durante cada etapa

1. Designar uma pessoa nominal para negócio, operação, engenharia, dados e
   comercial. As decisões comerciais finais continuam com Ike enquanto ele não
   delegar formalmente. Uma pessoa pode acumular papéis; nenhum fica sem dono.
2. Copiar [`onboarding/template.json`](onboarding/template.json) para uma pasta
   privada fora do Git, com diretório 0700 e arquivo 0600. Preencher referências
   aos documentos/evidências; senhas e tokens ficam no cofre escolhido pela equipe.
3. Validar o rascunho, resolver os bloqueios de conteúdo e executar a checklist.
4. Rodar a validação de go-live. A aprovação humana confere as evidências e o
   escopo; o validador local só valida as declarações e a consistência matemática.
5. Registrar identificador do release, prova de cada escrita por tenant e
   responsável pelo piloto. Engenharia executa a implantação coordenada; este
   script não toca banco, APIs, contas nem produção.

```bash
python3 scripts/validate_onboarding.py /pasta/privada/cliente.json --mode draft
python3 scripts/validate_onboarding.py /pasta/privada/cliente.json --mode go-live
python3 -m unittest scripts/test_validate_onboarding.py -v
```

Saída: `structure_errors`, `blockers`, cálculo de preço quando houver dados,
horas observadas entre marcos e `ready_from_declared_evidence`. Exit 0: rascunho
estruturalmente válido, ou go-live sem bloqueio declarado; exit 1: go-live pendente;
exit 2: arquivo/estrutura inválidos. Exit 0 em rascunho **não aprova implantação**.
Referências sintéticas `fixture://`, domínio `example.invalid` e `synthetic=true`
impedem go-live. O programa não resolve os links nem autentica os documentos.

### Contrato do dossiê local (schema_version = 1)

| Seção | Conteúdo que o responsável fornece |
|---|---|
| `business` | tenant único, razão social, marca, vertical, classificação explícita de risco clínico, endereço, URL oficial, fuso IANA e fonte dos dados |
| `owners` | responsáveis nominais por negócio, operação, engenharia, dados e comercial |
| `persona` | nome do agente, tom, idioma, limites, prompt versionado, regra de imagem e fontes únicas |
| `scope` | módulos incluídos/excluídos e referência ao escopo aceito do piloto |
| `channels` | número E.164, referências do remetente/WABA e aprovação do nome de exibição |
| `catalog` | origem, contagem, SHA-256, revisor, prova e conclusão da revisão operacional |
| `agenda` | modo próprio ou link externo explicitamente aceito; prova de turnos/capacidade/bloqueios ou identidade do link |
| `handoff` | titular/suplente, limites, destino, prova de recebimento humano e rota clínica quando aplicável |
| `data_policy` | referências de consentimento, aviso de privacidade, retenção e procedimento de exportação |
| `access_inventory` | recursos, conta/referência, titular, suplente, via de recuperação, cofre e teste datado |
| `measurements` | período, volumes, custos comparáveis em reais, implantação e documentos de origem |
| `commercial` | franquia, período de cobrança, margem, tributos, preços finais e decisão do responsável |
| `go_live` | checks datados com dono/evidência, dono da operação assistida e plano de reversão |
| `milestones` | briefing concluído, início/fim da engenharia e início real do piloto |

Campos nulos significam pendência. Não preencher telefone público a partir do
remetente técnico, capacidade a partir de horário, estoque a partir de existência
no catálogo, ou consentimento a partir de uma mensagem recebida. Nenhuma credencial
entra no dossiê; o validador rejeita nomes comuns de campos secretos e URLs com senha.
Isso é uma barreira adicional, não um detector universal de segredos.
Verticais no schema: `gastronomy`, `health`, `aesthetics`, `dentistry` ou `other`.
`clinical_risk=true` exige rota clínica mesmo em `other`.

## 2. Briefing de conteúdo e fronteiras

O responsável de operação entrega os seguintes anexos, identificados no dossiê:

- Identidade: grafia comercial, pronúncia, agente/persona, tom, idioma, endereço,
  acessibilidade e contato público confirmado. A marca do cliente e a titularidade
  do portfólio Meta são campos distintos.
- Atendimento: perguntas frequentes, objetivo de conversão, saudações, uso de
  imagens, respostas de manutenção, pedidos que exigem humano e prioridades.
- Catálogo: fonte oficial datada, produtos/serviços, preço/variantes, adicionais,
  restrições, indisponibilidades e revisão por alguém da operação. Preço ausente
  não vira gratuito; item existente não comprova estoque.
- Agenda: regras por dia/ambiente, capacidade física e comercial confirmadas,
  duração/intervalo, tamanho de grupo, antecedência, tolerância, datas especiais,
  bloqueios e regra de conflito. Horário de funcionamento não é turno de reserva.
- Handoff: pessoa primária e suplente por tenant, cobertura, canal e prova de
  recebimento. Aceite Twilio não é entrega; ausência de resposta exige fallback
  persistido e acompanhamento no painel.
- Clínica: contato clínico responsável e fronteira explícita para intercorrência,
  pós-procedimento e imagem sensível. A rota comercial não substitui a clínica.
- Dados: responsável pelas decisões de consentimento, finalidade, acesso,
  retenção, exportação e término do serviço. Registrar documento revisado pelo
  responsável adequado; o checklist técnico não certifica conformidade jurídica.

## 3. Checklist com critério de saída

| Etapa / responsável | Execução | Pronto quando |
|---|---|---|
| 0. Negócio / comercial | Qualificar cliente externo real; nomear donos; registrar escopo | Cliente, finalidade e limites aceitos; nenhuma promessa fora do produto comprovado |
| 1. Operação | Reunir briefing e anexos; registrar `briefing_complete_at` | Campos operacionais reais e fontes localizáveis; lacunas explícitas |
| 2. Engenharia + titular das contas | Conferir inventário e permissões mínimas | Segundo responsável consegue recuperar cada conta; teste documentado sem expor segredos |
| 3. Conteúdo + operação | Preparar catálogo, persona e limites | Catálogo revisado; fonte única de preço/horário; nova versão de prompt identificada |
| 4. Engenharia | Validar em banco restaurado isolado, usando tenant sintético só no ambiente de teste | Isolamento, permissões, agenda concorrente e rollback testados |
| 5. Engenharia + operação | Revisar diff por tenant e aplicar lote autorizado | SELECTs comprovam cada escrita; nenhuma alteração em outra unidade |
| 6. Operação + engenharia | Testar canal e handoff num cenário autorizado com destinatário designado | Resposta real e recebimento humano comprovados; fallback exercitado |
| 7. Dados + operação | Revisar política de dados e saída; treinar operador e suplente | Operadores conseguem achar atendimento, assumir, atualizar desfecho e escalar |
| 8. Comercial | Fechar preço após custos e decisão de franquia/margem | Valores explícitos aprovados; exceção abaixo do piso documentada |
| 9. Responsáveis de operação e engenharia | Conferir checks e rodar `--mode go-live` | Evidências datadas conferidas, plano de reversão e acompanhamento definidos |
| 10. Operação assistida | Registrar `pilot_live_at`, acompanhar casos e fechar incidentes | Cliente externo real usando; período acompanhado e aceite documentados |

Critérios do piloto devem ser acordados antes da ativação: janela observada,
volume efetivo, falhas de informação, recebimentos de handoff, desfechos registrados,
latência e disponibilidade medidas. Não existe meta/SLA numérico aprovado neste
pacote. Se o volume for insuficiente, registrar amostra insuficiente.

Reversão: preservar o tenant e seu histórico; reativar a versão anterior validada
do prompt e o caminho de manutenção/atendimento humano; desfazer apenas o release
problemático conforme seu runbook. Nunca apagar tenant ou restaurar o banco inteiro
como resposta automática a um erro de conteúdo de uma unidade.

### Prazo: medição e dependências

O prazo comercial de onboarding está **pendente de uma implantação externa medida**.
Não há evidência para prometer “em X dias”. Registrar tempo corrido desde briefing
completo até piloto e horas efetivas de cada executor separadamente. O validador
calcula tempo corrido; não transforma espera de Meta/cliente em horas faturáveis.

Dependências externas: verificação/registro do canal, nome de exibição, materiais
da casa, catálogo, capacidade, responsáveis e decisão comercial. Cada bloqueio
deve ter dono, início, resolução e impacto na data planejada.

Como evidência técnica limitada, houve restauração local de 64 tabelas, 988 linhas
e 4 prompts em 17/09/2026; a execução com teste dos três catálogos levou 43,03s.
Isso mede esse ensaio de recuperação, não onboarding, RTO contratado nem restauração
completa de produção. O exemplo de 48h nas fixtures é inteiramente sintético.

## 4. Titularidade e recuperação: inventário inicial sem segredos

O inventário abaixo identifica recursos observados. Acesso funcional nesta sessão
não prova titularidade legal, MFA, suplência ou recuperação. Essas colunas seguem
pendentes até prova nominal. Ike coordena a designação; não foi presumido titular
de toda conta apenas porque a sessão local está autenticada.

| Recurso / identificação observada | Evidência | Pendência de titularidade e recuperação |
|---|---|---|
| GitHub `ikeguimaraes-dot/serena-kph` | remote e histórico de commits/PRs | titular legal, segundo admin, cofre, recuperação/MFA testados |
| Railway `restaurant-ai`, ambiente `production` | CLI autenticada e deploys observados | dono da organização, suplente, cobrança, recuperação e contingência |
| Supabase `czoakcsntfxmqfssubbe` | leitura do banco e dump/restauração | dono da organização, segundo admin, recuperação da conta e inventário de consumidores |
| Vercel / `madonna-painel.vercel.app` | painel e release registrados na execução | equipe titular, suplente, recuperação e configuração de domínio |
| Twilio / conta “Restaurant AI” | console apresentado e integração do backend | Account SID no inventário privado, titular, billing, suplente e recuperação |
| Meta / portfólio Meet & Eat `512879226454180` | telas do usuário; verificação informada como em análise | conclusão da verificação, admins e recuperação; não confundir com nome do sender |
| Anthropic / modelo do agente | integração existente no backend | organização, titular, limites, crédito/recarga e recuperação comprovados |
| Discord / notificação de handoff | variável presente e rota implementada | canal/dono/suplente no inventário privado e recebimento humano comprovado |
| Tagme / venues Meet, Frêneze e Madonna | links e configuração pública auditados | conta de gestão, exportação autorizada por venue e recuperação da conta |
| Backup / job local `com.serena.backup` | dump/restore e ativação registrados | segundo operador, acesso ao Mac, armazenamento externo adicional e teste sem fundador |
| Domínios e monitoramento | citados no plano; titularidade não auditada | registrador, DNS, UptimeRobot, dono, suplente, recuperação e alertas testados |

Campos privados por recurso: conta/organização, dono nominal, suplente,
referência no cofre, canal de recuperação, prova datada e próxima revisão. Não
guardar senha, código de recuperação ou token no Git, chat, relatório ou fixture.
O backup atual é local ao Mac e depende de sessão/máquina/rede disponíveis; não
é cópia geograficamente independente. O dump não inclui binários do Storage.

## 5. Preço e franquia: fórmula sem valor inventado

**Decisão aberta — Ike/comercial:** preço por unidade, franquia, taxa de implantação,
preço excedente, margem, período de cobrança e exceções. Não foi escolhido um
preço de tabela com base em concorrente ou fixture.

Medir no mesmo período e por tenant, com documentos de origem:

- `L`: custo do modelo, incluindo entrada/saída/cache, em reais.
- `W`: custo de mensagens/canal, em reais, reconciliado com faturamento.
- `I` e `S`: infraestrutura e suporte alocados, regra de rateio registrada.
- `N`: conversas sob uma definição estável; `M`: mensagens faturáveis; não misturar
  sessões, requisições ou mensagens recebidas não cobradas no denominador.
- `D`: dias inclusivos do período; `B`: dias do período de cobrança decidido.
- `H`, `R`, `O`: horas efetivas de implantação, custo-hora carregado e custos
  diretos únicos. Evitar dupla contagem com suporte/infra.
- `Q`, `g`, `t`: franquia de mensagens, margem-alvo sobre receita e taxa efetiva
  validada pelo financeiro. Todos são decisões explícitas, não defaults.

Conversão de moeda, créditos, descontos, estornos e impostos da fatura precisam
de memória de cálculo. Crédito promocional não torna custo recorrente zero.
Guardar regra de rateio e definição de conversa junto das `evidence_refs`.

```text
custo variável por conversa = (L + W) / N
custo variável médio por mensagem = (L + W) / M
custo fixo no período de cobrança = (I + S) × B / D
piso da assinatura = [custo fixo + Q × custo variável por mensagem] / (1 - g - t)
piso por mensagem excedente = custo variável por mensagem / (1 - g - t)
piso da implantação = (H × R + O) / (1 - g - t)
```

Exigir `g + t < 1` e volumes positivos. A média pressupõe manutenção da composição
de mensagens/modelos/tipos de conversa observada; ela deve ser recalculada se o
uso mudar. O cálculo é piso de sustentabilidade sob essas premissas, não preço
automaticamente recomendado nem garantia de margem futura. Valor ao cliente e
escopo determinam a proposta final; qualquer preço abaixo do piso exige exceção
documentada. Não se promete retorno financeiro sem medição atribuível.

## 6. Proposta comercial pronta para preenchimento

**Cliente/unidade:** `[PENDENTE]` · **Responsável:** `[PENDENTE]`
**Escopo aceito:** agente com identidade da marca, catálogo de fonte confirmada,
canal WhatsApp, handoff e módulos que constarem no dossiê validado. Agenda própria
só entra após validação operacional; link externo pode permanecer durante piloto
se explicitamente aceito. Painel, CRM/funil e régua entram apenas no escopo cuja
versão e funcionamento forem demonstrados ao cliente.

**Implantação:** briefing, persona, carga de dados revisados, testes isolados,
treinamento e go-live acompanhado, conforme checklist. **Prazo:** `[PENDENTE DE
BRIEFING, DEPENDÊNCIAS E MEDIÇÃO]`. **Preço/franquia/excedente/implantação:**
`[PENDENTE DE CUSTOS E DECISÃO COMERCIAL]`. **Suporte, janela de acompanhamento,
renovação e saída:** `[PENDENTE DE ACORDO ESCRITO]`.

**Provas disponíveis:** quatro configurações de agentes/prompts no mesmo backend;
agenda própria já configurada na Madonna; lookup com tratamento explícito de base
vazia; recuperação de banco ensaiada; catálogo de 739 itens testado em restauração
isolada. A presença de código ou teste isolado não certifica entrega de mensagem,
revisão operacional de todos os itens ou go-live de outro cliente.

**Fora da oferta atual:** pagamento/caução, integração PDV, fila conversacional,
app próprio, receita incremental garantida, uptime contratado e prazo externo
garantido. Esses itens não são apresentados como já entregues.

### Matriz de objeções com alegações limitadas à evidência

| Objeção | Resposta utilizável |
|---|---|
| “Já uso Tagme.” | Podemos manter seu link oficial enquanto validamos catálogo e atendimento. A migração de agenda depende dos turnos/capacidade e a de histórico exige exportação autorizada. |
| “A IA pode informar preço errado.” | O catálogo consulta dados de origem e há tratamento para base indisponível. Revisão operacional, testes e acompanhamento continuam necessários; não prometemos ausência total de erros. |
| “Quero atendimento humano.” | Definimos responsável e suplente e só consideramos o handoff pronto após prova de recebimento. A entrega final depende também dos canais e cobertura combinados. |
| “Quanto custa e quanto retorna?” | O preço depende do escopo, dos custos medidos e da franquia aprovada. Retorno/conversão serão medidos no piloto; ainda não há número auditável a prometer. |
| “E se eu sair?” | Exportação, formatos, retenção e término devem constar do acordo e ser testados. O ensaio de backup atual não prova um procedimento completo de saída por cliente. |
| “Vocês conseguem recuperar meus dados?” | Um dump externo ao Supabase foi restaurado com contagens e hashes conferidos. A rotina atual depende do Mac e não cobre objetos binários; o SLA e a arquitetura contratados precisam ser definidos. |
| “Vocês já atendem clientes externos?” | O plano usa quatro marcas do grupo como operação inicial. O primeiro cliente externo e sua retenção ainda precisam ser comprovados. |
| “Funciona para clínica?” | Há configuração e rota de escalação clínica para a Levvai no mesmo motor. Cada nova clínica exige fronteira clínica, responsável e validação próprios; isso não certifica adequação universal. |

## 7. Critério de conclusão deste sprint

O pacote documental e o validador são entregas concluíveis agora. O Sprint 6 só
fecha integralmente quando existir cliente externo real em operação assistida,
prazo medido, custos reconciliados e preço/franquia/implantação aprovados. Evidência
sintética é usada apenas para testar o instrumento e nunca para fechar esses itens.
