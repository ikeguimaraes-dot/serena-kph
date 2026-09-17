# SERENA OS — BOOK MESTRE
## Estratégia, Produto e Plano Tático

**Versão 1.1 · 17 de setembro de 2026** — visão de 36 meses detalhada
Documento interno · KPH Participações / H. Roisin Consultoria

---

## COMO USAR ESTE DOCUMENTO

Três públicos, três caminhos de leitura:

| Se você é | Leia | Pode pular |
|---|---|---|
| **Ike / Fable / equipe de execução** | Partes II, III e VI + Anexos | Parte I (já sabe), Parte V |
| **Investidor ou sócio** | Sumário, Parte I, Parte IV, seção 6.1 | Partes II e III (detalhe técnico) |
| **Comercial / prospect white label** | Sumário, Parte V, seção 2.2 | Partes III e VI (interno) |

**Regra deste documento:** todo número aqui é verificado ou está marcado como pendente. Não há projeção apresentada como fato. Onde falta dado, está escrito `[DADO PENDENTE]` — e isso é informação, não lacuna a esconder.

---

## SUMÁRIO EXECUTIVO

A Serena OS é uma plataforma comercial de relacionamento e conversão para negócios de atendimento presencial, operada por agentes de IA sobre WhatsApp, com CRM, funil, agendamento e venda integrados numa base única.

**O que já existe e está em produção:** quatro agentes ativos atendendo clientes reais em quatro marcas — três restaurantes e uma clínica de estética. Motor técnico único, personas distintas, roteamento por número numa WhatsApp Business Account compartilhada. Agenda proprietária construída e rodando numa casa.

**O que a operação de quatro marcas provou:** o mesmo motor atende gastronomia e saúde estética sem reescrita. Isso não é hipótese de roadmap, é um agente em produção numa clínica que não é restaurante. É o ativo mais valioso do projeto e o que separa a Serena de um produto de nicho.

**O mercado tem incumbente com escala e agora com IA.** A Tagme opera +4.000 estabelecimentos, +400 cidades, integração nativa com a busca do Google e carteira com Fasano, Outback, Coco Bambu e Fogo de Chão. Cobra R$ 150/mês pelo cardápio digital e R$ 400/mês pela plataforma de hospitalidade completa. Em 2026 lançou o Foodster, produto de IA conversacional — ou seja, a tese de "agente que atende" não é mais território vazio.

**A aposta não é vencer o incumbente na função dele.** É ocupar o espaço que ele estruturalmente não ocupa: o incumbente é uma plataforma de restaurante que ganhou um módulo de IA; a Serena é uma plataforma de agente que começou em restaurante e já atravessou para outra vertical. O mercado de "negócio de agendamento com atendimento consultivo" é substancialmente maior que gastronomia.

**Estado honesto hoje:** a plataforma está em recuperação de um incidente de perda de banco. Duas das quatro casas operam em modo seguro, sem falar de produto específico. Há sete pendências de dado e três de código mapeadas e priorizadas. O plano de 90 dias fecha essas lacunas antes de qualquer movimento comercial — vender uma plataforma instável é o caminho mais rápido de destruir a tese.

---

# PARTE I — TESE E MERCADO

*Para investidor, sócio e board*

## 1.1 Diagnóstico externo — 6 dimensões

| # | Dimensão | Leitura |
|---|---|---|
| 1 | **Mercado** | Software de relacionamento e agendamento para negócio de atendimento presencial no Brasil. Regulação relevante: LGPD para base de clientes, e políticas da Meta para WhatsApp Business API — dependência de plataforma de terceiro é risco estrutural do setor inteiro, não só nosso |
| 2 | **Clientes** | Dois perfis: operação independente de médio porte (1 a 5 unidades, dono presente na decisão) e rede com padrão a defender. Vertical inicial: gastronomia. Vertical provada: estética/saúde |
| 3 | **Concorrência** | Incumbente nacional: Tagme/Foodster. Entrantes: ferramentas genéricas de agente de WhatsApp sem verticalização. Substituto real e mais forte que software: **o próprio funcionário respondendo no celular da casa** |
| 4 | **Posição atual** | Operador com produto próprio em produção, sem cliente externo pagante. Estágio: early-stage com produto validado internamente |
| 5 | **Resultados** | Quatro agentes em produção, quatro marcas. Volume de conversas, taxa de conversão em reserva e receita atribuída: `[DADO PENDENTE]` |
| 6 | **Potencial** | Não atingido. A plataforma atende as casas do próprio grupo e nenhuma casa externa. O produto existe; o negócio ainda não começou |

## 1.2 O incumbente — dado verificado

**Tagme** (Rio de Janeiro) — plataforma digital para restaurantes.

| Produto | Preço | Escopo |
|---|---|---|
| Menu Digital | R$ 150/mês | Cardápio, carta de vinhos, canais de captação, integração Google, banners |
| Hospitalidade | R$ 400/mês | Tudo acima + reserva + lista de espera + CRM |
| Add-on mensagens | + R$ 100/mês | Pacote de 2.000 mensagens → **R$ 0,05 por mensagem** |
| Foodster | Não publicado | IA conversacional, atendimento omnichannel, reserva, fila e cardápio |

**Escala declarada:** +4.000 estabelecimentos · +400 cidades · +8M pessoas/mês · +25M visualizações de cardápio/mês.

**Carteira de vitrine:** Fasano, Outback, Coco Bambu, Fogo de Chão, A Casa do Porco, Accor Hotels, Bráz, Bar Astor, Malta Beef Club, Giuseppe Grill.

**Arquitetura observada:** SSO centralizado em `apps.tagme.com.br/auth`, produtos em subdomínios independentes (`waitlist.`, `reservation-widget.`, `livemenu.app`). Camada do consumidor pública por `venueId`, camada de gestão atrás de autenticação. **Desenho a copiar** — produtos independentes com login único evitam que a queda de um derrube todos.

**Fragilidades observadas:**
- O FAQ promete "sem fidelidade, sem letras miúdas" no título e, quando perguntado sobre fidelidade, responde "consulte nosso time comercial". Prazo, integração e tempo de implantação: todas as respostas são "varia conforme a operação". Transparência prometida e não entregue
- Landing page e site do Foodster construídos em Lovable — marketing rápido e barato, e indício de que o Foodster é produto recente
- Um widget que o cliente preenche não aprende com a conversa. O dado de intenção — o que o cliente perguntou, o que recusou, por que desistiu — não existe num formulário

## 1.3 SWOT

**Forças**
- Motor único provado em duas verticais distintas, em produção
- Fundador é operador: cada erro do agente aparece no mesmo dia e é corrigido por quem sofre a consequência
- Propriedade total do canal, do prompt e do dado — nenhuma camada de terceiro entre a marca e o cliente
- Quatro marcas próprias como laboratório permanente e case de venda
- Agenda proprietária já construída, não dependente de API externa

**Fraquezas**
- Zero cliente externo pagante. Produto validado, negócio não
- Concentração crítica de conhecimento em uma pessoa e uma dupla de execução
- Fragilidade de infraestrutura comprovada: perda de projeto de banco com perda parcial de dado não recuperável
- Sem página pública de reserva — o tráfego de reserva ainda passa pelo incumbente
- Sem presença na busca do Google, que é justamente o canal de distribuição do incumbente
- Custo variável por conversa ainda não medido: `[DADO PENDENTE]`

**Oportunidades**
- White label multi-vertical: clínica, odontologia, estúdio, barbearia, hotelaria de pequeno porte — mercado maior que gastronomia e fora do foco do incumbente
- Fila de espera conversacional: o incumbente manda link de status, um agente conversa com quem espera. É o produto onde a vantagem do canal é maior
- Dado de intenção como ativo: nenhum widget captura por que o cliente não converteu
- Insatisfação com opacidade contratual do incumbente é brecha de posicionamento pronta

**Ameaças**
- Foodster: o incumbente já está no território, com 4.000 portas abertas para distribuir
- Dependência da Meta: mudança de política de WhatsApp Business API atinge o produto inteiro
- Dependência de um único provedor de modelo — custo e disponibilidade
- Conflito de posição: somos cliente do incumbente enquanto construímos o substituto
- Ferramentas genéricas de agente ficando boas o suficiente e baratas o suficiente

## 1.4 VRIO — onde está a vantagem real

| Recurso | Valioso | Raro | Difícil de imitar | Organizado | Veredito |
|---|---|---|---|---|---|
| Agente de WhatsApp com reserva | ✅ | ❌ | ❌ | ✅ | **Paridade** — o incumbente já tem |
| Agenda proprietária | ✅ | ❌ | ❌ | ⚠️ parcial | **Paridade** |
| Motor único multi-vertical provado | ✅ | ✅ | ⚠️ | ⚠️ parcial | **Vantagem temporária** |
| Operador com 4 marcas como laboratório | ✅ | ✅ | ✅ | ✅ | **Vantagem sustentável** |
| Dado de intenção conversacional acumulado | ✅ | ✅ | ✅ | ❌ ainda não | **Vantagem potencial — depende de captura** |

**Conclusão estratégica:** as duas vantagens reais não são funcionalidades — são a posição de operador e o dado de conversa. Qualquer plano que gaste o trimestre buscando paridade de funcionalidade com o incumbente está investindo na coluna errada.

## 1.5 Posicionamento

> **A Serena não é um sistema de reservas com IA. É a camada de relacionamento e conversão de um negócio de atendimento presencial — um time comercial que trabalha por mensagem, 24 horas, com a memória inteira do cliente na mão.**

**O que isso nega explicitamente:**
- Nega ser cardápio digital com chat acoplado
- Nega ser chatbot de atendimento — o objetivo é converter e fazer voltar, não reduzir custo de suporte
- Nega ser vertical de restaurante

**Para quem:** operação de atendimento presencial com ticket e margem que justificam relacionamento ativo, onde o dono perde receita por não responder rápido e não sabe quanto perdeu.

## 1.6 Modelo de negócio

**Três linhas de receita:**

1. **Assinatura por unidade** — plataforma e agente, mensal por casa
2. **Consumo de mensagem** — pacote acima da franquia, repassando custo variável com margem
3. **Implantação e onboarding** — taxa única: briefing, escrita de persona, carga de base, treinamento da equipe

A terceira linha é a que sustenta o caixa no início e a que o incumbente trata como custo. Para nós é produto, porque é onde a metodologia HOS entra.

**Referência de preço do mercado:** R$ 400/mês pela plataforma completa do incumbente, R$ 0,05 por mensagem no add-on. Definir preço abaixo disso é competir por custo com quem tem escala — caminho ruim. A precificação da Serena deve se apoiar em receita gerada, não em custo de software.

`[DECISÃO PENDENTE — IKE]` Preço de tabela por unidade, franquia de mensagens inclusa e taxa de implantação.

## 1.7 Unit economics — o que falta medir

Nenhuma decisão de preço ou de captação deve ser tomada antes destes cinco números. Todos são mensuráveis em 30 dias com a instrumentação do Sprint 2:

| Métrica | Como medir | Status |
|---|---|---|
| Custo por conversa | Token Anthropic + mensagem Twilio ÷ conversas | `[PENDENTE]` |
| Custo de infra por casa | Railway + Supabase + Vercel ÷ casas | `[PENDENTE]` |
| Taxa de conversão do agente | Reservas confirmadas ÷ conversas com intenção | `[PENDENTE]` |
| Receita atribuída por casa | Reservas via agente × ticket médio × taxa de comparecimento | `[PENDENTE]` |
| No-show com e sem agente | Campo de desfecho em `reservas` (Sprint 2) | `[PENDENTE]` |

**A conta que vende o produto:** se o agente converte X reservas/mês que não teriam acontecido, e o ticket médio é Y, a receita gerada é X·Y. A assinatura precisa ser fração pequena e óbvia disso. Sem esses números, a venda é promessa — e promessa não sustenta preço premium.

---

# PARTE II — O PRODUTO

*Para execução interna*

## 2.1 Arquitetura atual — verificada em 17/09/2026

```
Cliente (WhatsApp)
        │
        ▼
Twilio WhatsApp  ·  WABA única 1278165313813803
   números por casa, roteamento por número de destino
        │
        ▼  webhook único
FastAPI (Railway) · auto-deploy em push na main
   ├── build_prompt()  = header dinâmico + corpo versionado
   ├── array TOOLS     = disponibilidade, cardápio, proposta, handoff
   └── create_handoff() → handoff_sessions + Discord
        │
        ▼
Supabase PostgreSQL  (projeto czoakcsntfxmqfssubbe)
   ├── restaurants, serena_prompt_versions, business_hours
   ├── agenda_config, agenda_turnos, agenda_bloqueios, agenda_eventos
   ├── reservas, conversations, handoff_sessions
   ├── menu_items, faq_items, restaurant_ambientes
   └── team_members, midia_disponivel
        │
        ▼
Painel Next.js (Vercel) — operação e gestão
Monitoramento: UptimeRobot /health a cada minuto · Discord para alerta
```

**Ponto de arquitetura mais importante e menos documentado:** o prompt final é **header dinâmico + corpo versionado**. O header lê a tabela `restaurants` e `business_hours` a cada mensagem. O corpo é texto fixo em `serena_prompt_versions`. As duas fontes convivem — e se divergirem, o agente recebe sinais contraditórios no mesmo prompt. Toda mudança de dado operacional precisa ser feita nas duas ou em nenhuma.

## 2.2 Os oito módulos da plataforma

| # | Módulo | Função | Estado hoje |
|---|---|---|---|
| 1 | **Concierge** | Agente conversacional por marca, persona própria, motor comum | ✅ 4 em produção |
| 2 | **Agendamento** | Turnos, bloqueios, capacidade, eventos, reserva | ⚠️ construído, 1 de 4 casas configurada |
| 3 | **Catálogo** | Cardápio ou lista de serviços consultável pelo agente | ❌ base vazia, é o bloqueio principal |
| 4 | **Base de dados** | Cadastro de cliente, histórico, consentimento | ⚠️ conversas gravadas, cadastro não estruturado |
| 5 | **CRM** | Ficha do cliente, preferência, recorrência, valor acumulado | ❌ não existe |
| 6 | **Funil** | Estágio da conversa, origem, motivo de perda, desfecho | ❌ não existe — `ctwa_clid` e desfecho no Sprint 2 |
| 7 | **Disparo** | Mensagem ativa: confirmação, lembrete, retorno, campanha | ⚠️ templates D+1 a D+30 aprovados, sem motor de régua |
| 8 | **Venda** | Proposta de evento, caução, pré-pagamento, upsell | ⚠️ proposta determinística existe; pagamento não |

**Leitura honesta desta tabela:** a plataforma hoje é forte no módulo 1, parcial no 2, 7 e 8, e inexistente no 5 e 6. O que o mercado paga R$ 400/mês não é o módulo 1 — é o conjunto. **CRM e funil são a lacuna que separa "agente de WhatsApp" de "plataforma comercial".** E são exatamente o que nenhum widget de concorrente consegue fazer, porque eles não têm a conversa.

## 2.3 Modelo de dados — princípios

1. **Fonte única por informação.** Horário mora em `business_hours`. Preço mora em `menu_items`. O prompt referencia, não duplica. A duplicação de horário entre header e corpo é dívida técnica a pagar, não padrão a repetir
2. **Preço nunca é gerado pelo modelo.** Toda proposta lê valor do banco. A arquitetura anterior deixava o agente inventar preço — falha crítica de correção, já corrigida, nunca a repetir
3. **Vazio não é negativo.** Resultado vazio de consulta significa "não sei", jamais "não existe" ou "está lotado". Esta regra é lei de plataforma, tem que valer no prompt **e** no retorno da ferramenta
4. **Multi-tenant por `restaurant_id` desde a origem.** Toda tabela nova carrega o tenant. É o que torna o white label configuração, não fork
5. **Desfecho é obrigatório.** Reserva sem desfecho registrado é dado morto — não alimenta CRM, não mede no-show, não treina nada

## 2.4 White label — o que torna um entrante configuração e não projeto

Provado com o Instituto Levvai: agente Eva, vertical de estética, mesmo motor, zero reescrita de código.

**O pacote de onboarding padrão:** identidade e persona · dados do negócio · canais · catálogo · pagamento · regra de handoff e escalação · limites do que o agente não faz · módulo específico da vertical · validação jurídica · arquitetura · checklist de go-live.

**Aprendizado da Levvai que vira regra de produto:** em vertical de saúde existe assunto que o agente não toca — foto de corpo de paciente, queixa pós-procedimento, intercorrência. Esses casos escalam direto para a responsável clínica, não para o closer comercial. **Toda vertical tem sua fronteira de escalação, e defini-la é parte do onboarding, não detalhe de implementação.**

## 2.5 Doutrina operacional — as sete regras

Estas não são preferências. São consequências de erro já pago.

1. **A Serena nunca sai do ar.** Silêncio total é o pior cenário possível — pior que resposta imperfeita. Fallback de manutenção antes de qualquer outra coisa
2. **Toda escrita em banco acompanha o SELECT que prova.** Sem verificação, o item não está entregue
3. **Nunca reconstruir preço, cardápio, horário ou capacidade de memória ou estimativa.** Operar em modo seguro é melhor que operar com dado inventado. Vale igual para dado extraído por robô
4. **Comitado e deployado, verificado — não suposto.** "Deveria estar funcionando" não é reporte
5. **Vazio nunca vira negativa.** No prompt e na ferramenta
6. **Ao trocar infraestrutura, conferir todos os consumidores.** Não só o backend — painel, integração, cron
7. **Dado placeholder é pior que dado ausente.** Ausente quebra e alguém percebe; placeholder responde errado com cara de certo e fica meses no ar

---

# PARTE III — PLANO TÁTICO 90 DIAS

*Para execução interna*

## 3.1 A lógica das três ondas

O trimestre não tenta crescer. Tenta ficar confiável, instrumentado e independente — nessa ordem. Vender antes disso é vender risco.

| Onda | Dias | Objetivo |
|---|---|---|
| **1 — Estabilizar** | 1–30 | Fechar as lacunas do incidente. Nenhuma casa em modo seguro |
| **2 — Instrumentar** | 31–60 | Medir o que o produto faz. Sem número não há preço nem venda |
| **3 — Independer** | 61–90 | Cortar o cordão com o incumbente e provar o white label externo |

## 3.2 OKRs do trimestre

**OBJETIVO 1 — A plataforma é confiável o suficiente para ser vendida**
- KR1: 0 de 4 casas em modo seguro (hoje: 2)
- KR2: 100% das casas com catálogo carregado e consultável (hoje: 0%)
- KR3: 100% das casas com destino de handoff que chega em humano (hoje: 2 de 4, e nenhuma por WhatsApp)
- KR4: Rotina de backup de schema e prompt rodando fora da Supabase (hoje: inexistente)

**OBJETIVO 2 — Sabemos quanto o produto gera e quanto custa**
- KR1: Custo por conversa medido e publicado no WBR
- KR2: 100% das reservas com origem e desfecho registrados
- KR3: Taxa de conversão do agente medida por casa
- KR4: Receita atribuída ao agente calculada em pelo menos 2 casas

**OBJETIVO 3 — A Serena independe do incumbente**
- KR1: Página pública de reserva no ar, lendo a agenda própria
- KR2: 3 de 3 casas com agenda própria configurada (hoje: 1)
- KR3: Histórico de reserva e fila exportado do incumbente
- KR4: 1 cliente externo em operação assistida (não precisa ser pagante ainda)

## 3.3 Sprints

Ciclo de duas semanas. Portão de aprovação entre sprints — nada avança sem OK explícito.

### SPRINT 1 (dias 1–14) — Fechar o incidente
**Meta:** nenhuma casa mentindo para o cliente.

| Item | Dono | Pronto quando |
|---|---|---|
| Carga de catálogo do Meet & Eat (277 itens extraídos) | Claude | `menu_items` populada, SELECT de prova, conferência item a item aprovada pelo Ike |
| Extração do catálogo de Frêneze e Madonna | Fable + Ike | CSV nas mãos, 0 item sem preço não explicado |
| Sair do modo seguro nas duas casas | Claude | Prompt completo com cardápio, versionado, testado |
| Corrigir `lookup_menu` para base vazia | Fable | Retorna sinal explícito de indisponibilidade, nunca negativa |
| Cadastrar `team_members` de Madonna e Meet | Claude + Ike | Handoff chega em humano identificado |
| Reconciliar branch de produção com a main | Fable | Produção roda da main, rota de escalação clínica no ar e testada |
| Preencher `restaurants` com dado real | Claude + Ike | Nenhum campo placeholder nas 4 casas |
| Repor bloco de visão nas 3 casas | Claude | Agente reconhece imagem recebida |

**Risco do sprint:** a conferência do catálogo é manual e ninguém pode terceirizar. É o gargalo real, não o código.

### SPRINT 2 (dias 15–28) — Instrumentar
**Meta:** toda conversa e toda reserva deixam rastro.

| Item | Dono | Pronto quando |
|---|---|---|
| `ctwa_clid` em `conversations` e `reservas` | Fable | Origem de anúncio capturada — não é retroativo, cada dia sem isso é dado perdido |
| Campo de desfecho em `reservas` | Fable | compareceu / no-show / cancelada / concluída, com fluxo de atualização definido |
| Backup periódico de schema e prompts fora da Supabase | Fable | Restauração testada, não só backup gerado |
| Documento de titularidade de acessos | Claude + Ike | Cada recurso com conta, responsável e via de recuperação |
| Medição de custo por conversa | Claude | Número no WBR, por casa |
| Configurar `business_hours` e agenda de Frêneze e Meet | Claude + Ike | 3 de 3 casas com turno, capacidade e bloqueio |

### SPRINT 3 (dias 29–42) — CRM mínimo
**Meta:** a plataforma passa a lembrar do cliente.

| Item | Dono | Pronto quando |
|---|---|---|
| Tabela de cliente unificada por telefone, multi-tenant | Claude | Cadastro, histórico de visita, preferência, consentimento LGPD |
| Agente consulta ficha do cliente antes de responder | Fable | Cliente recorrente é reconhecido pelo nome e pela última visita |
| Painel de ficha do cliente | Fable | Vic e closers consultam sem SQL |
| Régua de mensagem ativa sobre os templates aprovados | Claude | Confirmação, lembrete e retorno disparando por evento, não manual |

### SPRINT 4 (dias 43–56) — Funil
**Meta:** saber onde a receita vaza.

| Item | Dono | Pronto quando |
|---|---|---|
| Estágio de conversa e motivo de perda | Claude + Fable | Toda conversa classificada; motivo de perda em lista fechada |
| Dashboard de funil no painel | Fable | Conversa → intenção → proposta → reserva → comparecimento |
| Taxa de conversão por casa e por persona no WBR | Claude | Número comparável semana a semana |
| Cálculo de receita atribuída ao agente | Claude | Duas casas com número fechado |

### SPRINT 5 (dias 57–70) — Cortar o cordão
**Meta:** o cliente reserva na nossa página, não na deles.

| Item | Dono | Pronto quando |
|---|---|---|
| Página pública de reserva (Next.js/Vercel) | Fable | Lê os mesmos turnos e bloqueios do agente, grava na mesma `reservas` — fonte única, sem risco de overbooking entre canais |
| Substituir o link do incumbente nos prompts | Claude | Agente manda link próprio |
| Exportar histórico de reserva e fila do incumbente | Ike + Fable | Dado na nossa base, migração não nasce cega |
| Dados estruturados para busca do Google | Fable | Página elegível para aparecer na busca — é a lacuna de distribuição |

**Este é o sprint de maior valor estratégico do trimestre.** Enquanto a reserva passa pelo incumbente, "independência" é parcial: tiramos o cardápio e entregamos o tráfego.

### SPRINT 6 (dias 71–90) — Provar o white label
**Meta:** alguém de fora do grupo operando.

| Item | Dono | Pronto quando |
|---|---|---|
| Onboarding como produto: briefing, prazo, checklist, preço | Claude + Ike | Documento que um terceiro executa sem o Ike na sala |
| 1 cliente externo em operação assistida | Ike | Agente no ar numa casa que não é do grupo |
| Precificação fechada com base em dado real | Claude + Ike | Tabela, franquia e taxa de implantação definidas |
| Material comercial a partir da Parte V | Claude | Proposta e matriz de objeções prontas |

## 3.4 O que fica fora deste trimestre — e por quê

Decisão explícita, para não virar discussão a cada semana:

- **Fila de espera conversacional** — é o produto de maior vantagem competitiva, mas é produto novo. Entra em 12 meses, não agora
- **Pagamento e caução** — exige decisão de adquirente, contrato e responsabilidade financeira. Não no mesmo trimestre da estabilização
- **Segunda vertical formal** — a Levvai já prova a tese; formalizar oferta para clínica antes de ter um cliente externo em gastronomia é dispersar
- **Integração com PDV** — depende de parceiro e é escopo de 12 meses
- **App próprio** — o WhatsApp é o canal. App é solução procurando problema

---

# PARTE IV — VISÃO 12 E 36 MESES

## 4.1 Doze meses

**Tese:** de plataforma que atende para plataforma que vende.

- Fila de espera conversacional — onde a vantagem do canal é maior e o incumbente só oferece link de status
- Motor de campanha segmentada sobre o CRM: reativação por tempo sem visita, aniversário, preferência de prato ou procedimento
- Pagamento e caução para evento — fecha o ciclo de venda dentro da conversa
- Oferta formal para a segunda vertical, com a Levvai como case
- Primeira dezena de clientes externos
- Integração com PDV e com sistema de gestão, para fechar o laço entre reserva, consumo e cliente

**Métrica North Star sugerida para o ciclo:** *receita atribuída ao agente por unidade por mês*. Não é conversa atendida, não é mensagem enviada, não é reserva criada. É dinheiro que entrou e que não teria entrado. É o único número que sustenta preço e sobrevive a questionamento de investidor.

## 4.2 Trinta e seis meses — visão

**Tese central:** a Serena se torna a camada de relacionamento e conversão de negócios de atendimento presencial no Brasil. Não um sistema que o restaurante usa — a infraestrutura pela qual o cliente e o negócio se falam, em qualquer setor onde alguém marca hora e é atendido por uma pessoa.

### 4.2.1 O estado desejado

Se der certo, em setembro de 2029 a frase que descreve a empresa é esta: *uma plataforma onde qualquer negócio de atendimento presencial liga o canal, carrega o catálogo e passa a ter um time comercial que trabalha por mensagem, com a memória inteira de cada cliente.* Gastronomia é a vertical de origem, não a identidade.

Três coisas precisam ser verdade nessa data, e só três:

1. **Entrar numa vertical nova é conteúdo, não engenharia.** Um setor novo custa briefing, persona, catálogo e fronteira de escalação — semanas, não trimestres
2. **O dado de intenção acumulado é inimitável.** Três anos de conversa real sobre o que o cliente pergunta, aceita, recusa e abandona, numa base que nenhum widget de concorrente consegue reconstruir porque ele nunca teve a conversa
3. **A plataforma não depende do grupo KPH para vender.** Marca própria, reputação própria, receita majoritária vinda de fora de casa

### 4.2.2 As três camadas de produto, na ordem

| Horizonte | Camada | O que a plataforma é |
|---|---|---|
| **Hoje → 12 meses** | Atendimento e conversão | Agente que responde, agenda e vende. Compete com widget e com funcionário no celular |
| **12 → 24 meses** | Relacionamento | CRM vivo, régua de campanha, reativação, recorrência. Compete com CRM genérico e com ninguém fazendo nada |
| **24 → 36 meses** | Inteligência de demanda | Previsão de ocupação, precificação por horário, diagnóstico de perda. Compete com intuição do dono |

A terceira camada é a que muda a natureza do negócio. Nas duas primeiras a Serena é ferramenta de operação e o cliente compara com o preço de outro software. Na terceira ela informa **decisão** — que dia abrir, que horário empurrar, qual prato tirar do cardápio, quanto cobrar no sábado. Quem vende decisão não é comparado por preço de licença.

### 4.2.3 Escada de verticais e critério de entrada

Não se entra numa vertical por oportunidade aparecida. Entra-se quando ela passa em quatro testes: cliente marca hora, atendimento é consultivo, existe catálogo consultável, e há fronteira clara de escalação para humano.

| Onda | Verticais | Por que nesta ordem |
|---|---|---|
| **Origem** | Restaurante, bar, casa de eventos | Onde estão as marcas próprias e o laboratório |
| **Segunda** | Estética, odontologia, fisioterapia, estúdio, barbearia | **Já provada** com a Levvai. Ticket alto, recorrência natural, agenda densa, dono presente |
| **Terceira** | Hotelaria de pequeno porte, clínica veterinária, imobiliária de locação | Mesma mecânica, ciclo de decisão mais longo |
| **A evitar** | Varejo puro, delivery, e-commerce | Não marcam hora, não têm atendimento consultivo. Mercado lotado de concorrente melhor posicionado |

**A vertical de saúde e estética é provavelmente maior que gastronomia**, com margem melhor e concorrência mais fraca em software de relacionamento. A tentação será tratá-la como diversificação. Ela pode virar o negócio principal — e essa possibilidade tem que estar sobre a mesa desde já, não ser descoberta por acidente em 2028.

### 4.2.4 O ativo de dado — o que ele destrava

Três anos de conversa real geram quatro coisas que dinheiro não compra:

- **Diagnóstico de perda:** por que o cliente não fechou, em volume e por padrão. Nenhuma ferramenta do mercado responde isso hoje
- **Benchmark setorial:** tempo de resposta, taxa de conversão e motivo de recusa por tipo de casa e faixa de ticket. Vira relatório vendável e vira argumento comercial
- **Previsão de demanda:** intenção conversacional antecede a reserva. Saber o que está sendo perguntado hoje é sinal de ocupação de amanhã
- **Qualidade composta:** cada conversa melhora prompt, régua e catálogo de todos os clientes da mesma vertical

**Condição para isso existir:** captura desde agora. `ctwa_clid`, desfecho de reserva e motivo de perda estão nos Sprints 2 e 4 justamente por isso — **nenhum dos três é retroativo.** Cada mês sem instrumentação é um mês que nunca volta para o ativo de 36 meses. Este é o único ponto onde o plano de 90 dias e a visão de 3 anos se tocam diretamente.

### 4.2.5 Evolução do modelo de receita

| Fase | Receita principal | Lógica de preço |
|---|---|---|
| Hoje → 12m | Implantação + assinatura por unidade | Custo de software comparado a concorrente |
| 12 → 24m | Assinatura + consumo de mensagem | Receita gerada comparada a assinatura paga |
| 24 → 36m | Assinatura por valor + inteligência como produto | Decisão informada, não licença de ferramenta |

A migração de "preço de software" para "preço de resultado" só é possível com o número de receita atribuída medido e auditável por cliente. É a razão pela qual a North Star de 12 meses é receita atribuída ao agente e não volume de conversa: **é a métrica que destrava a mudança de modelo de cobrança três anos depois.**

`[DECISÃO PENDENTE — IKE]` Se haverá take rate sobre transação (caução, pré-pagamento, evento). Muda a natureza regulatória do negócio e a conversa com adquirente.

### 4.2.6 Organização — as cadeiras e quando abrir

Hoje a operação inteira depende de uma pessoa decidindo e uma dupla executando. Isso funciona em 4 casas próprias e não funciona em 40 clientes externos. As cadeiras, na ordem em que doem:

| Cadeira | Abre quando | Entregas |
|---|---|---|
| **Produto e prompt** | 1º cliente externo | Persona, régua, catálogo, qualidade de resposta por vertical |
| **Customer success / onboarding** | 3º cliente externo | Implantação, treinamento, go-live, retenção |
| **Engenharia de plataforma** | 5º cliente externo | Multi-tenant, confiabilidade, plantão — hoje é a dependência mais perigosa |
| **Comercial** | Depois de 3 clientes fechados pelo fundador | Só se contrata vendedor depois que o fundador provou que vende |
| **Dado e inteligência** | 24 meses | Benchmark, previsão, relatório vendável |

**A regra que sustenta tudo isso:** o fundador não sai da cadeira de produto antes de existir alguém melhor nela. A vantagem de "operador que escreve o produto" morre no dia em que o produto passa a ser escrito por quem não opera.

**Governança:** três níveis — operação semanal (WBR), produto e roadmap mensal, sócios e capital trimestral. A separação entre KPH Participações e a plataforma precisa estar clara no papel antes de qualquer conversa de investimento.

### 4.2.7 Arquitetura de marca

Hoje a plataforma se confunde com o grupo. Em 36 meses precisa estar separada por três razões: dono de restaurante não compra software de restaurante concorrente; clínica não compra plataforma de grupo gastronômico; e valuation de software não convive com valuation de operação de restaurante no mesmo CNPJ.

A metodologia HOS permanece como ativo de consultoria e diferencial de implantação — é o que explica por que o onboarding é produto e não custo. Mas a plataforma vendida precisa de nome, site e reputação que não dependam de Meet & Eat, Madonna ou Frêneze.

### 4.2.8 Três cenários

| | **Profundidade** | **Amplitude** | **Consolidação** |
|---|---|---|---|
| Aposta | Poucas verticais, produto muito fundo | Muitas verticais, produto mais raso | Vender para quem já tem distribuição |
| Requer | Domínio absoluto da vertical | Capital e time comercial | Produto que funciona e dado que interessa |
| Ganha se | Cliente paga premium por profundidade | Aquisição fica barata e escalável | Incumbente precisa de IA e não quer construir |
| Perde se | Mercado pequeno demais | Vira commodity e briga por preço | Só há um comprador provável |
| **Encaixe hoje** | **Alto** — é o que a posição de operador permite | Baixo — exige capital que não existe | Real, mas é resultado, não estratégia |

**Recomendação:** cenário Profundidade em duas verticais — gastronomia e saúde estética. É o único que usa a vantagem que você realmente tem, em vez de comprar uma que você não tem. Amplitude só depois de um cliente externo provar retenção. Consolidação não é plano — é consequência de executar bem, e quem constrói para ser comprado costuma construir a coisa errada.

### 4.2.9 Riscos de horizonte longo

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Meta muda política de WhatsApp Business API | Alta em 3 anos | Camada de canal abstraída — trocar WhatsApp por outro canal não deve reescrever o produto |
| Provedor único de modelo: preço, disponibilidade ou política | Alta | Abstração de modelo, avaliação periódica de alternativa. Hoje é dependência total |
| Agente conversacional vira commodity de baixo custo | **Muito alta** | É por isso que o produto não pode terminar no agente. O fosso é CRM, dado e vertical — não a conversa |
| Incumbente empacota IA no plano de R$ 400 e mata o preço | Alta | Não competir na função. Vender resultado medido |
| Dependência do fundador | Certa hoje | Cadeiras de produto e engenharia, documentação como a que você já mantém |
| LGPD e uso de base de cliente | Média, impacto alto | Consentimento na estrutura de dado desde o Sprint 3, não como remendo depois |

**O risco número três é o mais provável e o mais fatal.** Em três anos, "agente que atende WhatsApp" custará quase nada e qualquer um terá um. A empresa que sobrevive é a que transformou conversa em dado e dado em decisão. Por isso os módulos 5 e 6 — CRM e funil — não são features de roadmap: são a condição de existir em 2029.

### 4.2.10 Marcos de verificação

Não metas de vaidade. Perguntas com resposta binária:

**12 meses** — Existe cliente externo pagando e renovando? A receita atribuída ao agente é mensurável e auditável por cliente? A segunda vertical tem oferta formal?

**24 meses** — A receita de fora do grupo é maior que a de dentro? Entrar numa vertical nova custa semanas? Existe alguém além do fundador escrevendo produto?

**36 meses** — A plataforma tem marca e reputação independentes? O dado gera relatório que o cliente pagaria para ler? A empresa sobrevive ao fundador tirando 30 dias?

### 4.2.11 Premissas que precisam ser verdadeiras

Se qualquer uma destas se provar falsa, a visão muda — e é melhor descobrir em 2027 que em 2029:

1. Negócio de atendimento presencial paga por relacionamento, não só por reserva
2. O agente gera receita incremental mensurável, não apenas transfere canal
3. O mesmo motor atende múltiplas verticais sem custo marginal alto de engenharia *(já parcialmente provada pela Levvai)*
4. Dado de intenção acumulado tem valor comercial para quem o gerou
5. Dono de operação independente compra de operador, não só de marca grande

**Critério de abandono:** se aos 12 meses não houver um cliente externo renovando e a receita atribuída medida, a tese de plataforma não se sustenta e a Serena deve ser tratada como vantagem competitiva interna do grupo KPH — o que é um resultado legítimo e valioso, só não é um negócio de software.

### 4.2.12 A decisão que precede tudo

`[DECISÃO PENDENTE — IKE]` **Qual é a ambição dos sócios?** Crescimento com capital de terceiro, geração de caixa sem diluição, construção de ativo para venda, ou vantagem competitiva interna do grupo? Cada resposta produz um plano de 36 meses diferente — e produz cadeiras, governança e modelo de receita diferentes.

Este documento assume a segunda hipótese: **crescimento financiado pela própria operação, sem pressa de captação, usando as casas próprias como laboratório e primeira receita.** É a que combina com o estágio atual e com a posição de operador. Se a ambição for outra, a Parte IV precisa ser reescrita antes da Parte III ser executada.

---

# PARTE V — SEÇÃO COMERCIAL

*Para venda do white label*

## 5.1 Cliente ideal

**Perfil:** operação de atendimento presencial, 1 a 5 unidades, dono ou sócio na decisão, ticket médio que suporta relacionamento ativo.

**Decisor:** proprietário ou sócio operador. Não é gerente de TI, não é comprador corporativo — é quem sente a perda.

**Dores reais, na ordem em que doem:**
1. Mensagem sem resposta em horário de pico, porque quem responde está servindo mesa
2. Não saber quantas reservas foram perdidas — a perda é invisível
3. Cliente fiel tratado como desconhecido a cada visita
4. Informação errada saindo da casa: horário, preço, disponibilidade
5. Base de clientes que existe no papel e não é usada para nada

**Sinal de desqualificação:** quem quer só reduzir custo de atendimento. A Serena não é economia de pessoal — é geração de receita. Vender como redução de custo entrega o cliente errado, que vai medir a coisa errada e cancelar.

## 5.2 A oferta

Três camadas, alinhadas com as três linhas de receita:

1. **Implantação** — briefing, persona, carga de catálogo e base, regra de escalação, treinamento da equipe, go-live acompanhado
2. **Plataforma** — agente, agendamento, catálogo, CRM, funil, painel
3. **Consumo** — franquia de mensagem inclusa, pacote adicional acima disso

`[DECISÃO PENDENTE — IKE]` Valores das três camadas.

## 5.3 Matriz de objeções

| Objeção | Resposta |
|---|---|
| "Já uso Tagme" | Não substitui o widget de imediato, convive. O widget é canal barato para quem já sabe o que quer; o agente pega quem tem dúvida, quem quer evento, quem some. A pergunta certa é quanto você perde hoje em mensagem sem resposta |
| "IA vai falar errado com meu cliente" | Por isso preço nunca é gerado pelo modelo, resultado vazio nunca vira negativa, e todo assunto sensível escala para humano. Essas regras não são promessa, são arquitetura — e cada uma existe porque já erramos e pagamos |
| "Meu cliente quer falar com gente" | Continua falando. O handoff é parte do produto, com fronteira definida por vertical. O agente cobre o que é repetitivo e entrega o resto pronto para o humano |
| "Quanto custa?" | Comparado ao quê? Se for a software, é caro. Se for a uma reserva perdida por semana, se paga no primeiro mês. Vamos medir na sua operação |
| "E se eu quiser sair?" | Sua base é sua, exportável, sem retenção de dado. Diferente do que você tem hoje |
| "Vocês são pequenos" | Somos operadores. Rodamos isso em quatro marcas próprias, e quem escreve o produto é quem sofre o erro no mesmo dia. Você não vai abrir ticket e esperar prioridade |

## 5.4 Prova, não promessa

O que se pode afirmar hoje, com verificação:
- Quatro agentes em produção, quatro marcas, dois setores distintos
- Motor único atendendo gastronomia e estética sem reescrita
- Agenda proprietária operando independente de API de terceiro
- Precificação determinística, com preço lido de banco

O que **não** se pode afirmar até o Sprint 4 fechar: qualquer número de conversão, receita ou economia. **Vender número que não medimos é o caminho mais rápido de perder a única vantagem que temos, que é ser operador que fala a verdade sobre operação.**

---

# PARTE VI — GOVERNANÇA E MÉTRICAS

## 6.1 Painel de indicadores

| Nível | Indicador | Cadência |
|---|---|---|
| **North Star** | Receita atribuída ao agente por unidade | Mensal |
| Produto | Conversas atendidas · taxa de handoff · tempo até primeira resposta | Semanal |
| Conversão | Conversa → intenção → proposta → reserva → comparecimento | Semanal |
| Qualidade | Taxa de resposta com informação errada · reclamação · NPS | Mensal |
| Custo | Custo por conversa · custo de infra por casa | Mensal |
| Confiabilidade | Uptime do webhook · incidente de silêncio · tempo de recuperação | Contínuo |

## 6.2 Divisão de responsabilidade

| Papel | Escopo | Não faz |
|---|---|---|
| **Ike** | Decide, aprova, fornece dado que só ele tem, define preço e escopo | Não executa código nem escreve conteúdo de banco |
| **Claude** | Conteúdo de banco, prompt, arquitetura, documentação, análise | Não executa na máquina local, não aprova a si mesmo |
| **Fable** | Código, deploy, migration, execução local | Não altera prompt nem conteúdo de banco por iniciativa própria |

**Limite de ambiente que precisa estar claro para todos:** o Claude roda em sandbox com rede restrita — alcança repositório de pacote, não alcança site externo. Execução local, extração autenticada e qualquer coisa que precise de navegador com internet aberta é do Fable ou do Ike. Isso não é limitação a contornar, é divisão de trabalho a respeitar.

## 6.3 Ritual semanal

**WBR de 45 minutos, toda semana, mesma pauta:**
1. Indicadores da semana, comparado com a anterior e com o mês
2. O que ficou abaixo da meta e o plano para corrigir
3. Bloqueios que precisam de decisão do Ike
4. Sprint: o que fechou, o que escorregou e por quê
5. Incidente da semana e o que mudou por causa dele

**Fechamento de sprint:** documento de handoff com estado verificado, escrita no banco com prova, pendências e decisões abertas. O handoff não é burocracia — é o que fez a recuperação do incidente ser possível.

---

# ANEXO A — ESTADO VERIFICADO EM 17/09/2026

**Banco de produção:** Supabase `czoakcsntfxmqfssubbe` · Transaction pooler, IPv4, porta 6543. O projeto anterior foi perdido e não existe mais.

| Casa | Agente | Estado do prompt | Catálogo | Agenda | Handoff |
|---|---|---|---|---|---|
| Meet & Eat | Camila | Modo seguro + horário, endereço, capacidade e link de reserva corrigidos | ❌ vazio (277 itens extraídos, aguardando carga) | ❌ sem turno | ⚠️ sem closer cadastrado |
| Madonna Cucina | Serena | Modo seguro + horário e endereço inseridos | ❌ vazio (sem URL de extração) | ✅ 1 config, 17 turnos | ⚠️ sem closer cadastrado |
| Frêneze | Stella | Completo, horário corrigido | ❌ vazio | ❌ sem turno | ✅ 1 closer |
| Instituto Levvai | Eva | Completo | n/a | n/a | ✅ 2 closers · rota de escalação clínica **não deployada** |

**Corrigido nesta sessão:** `business_hours` nas 4 casas (28 linhas) · horário no corpo do prompt de Frêneze, Meet e Madonna · endereço de Madonna e Meet · capacidade real do Meet (96/68/80 sentados, era 330 total) · `nome_agente` das 4 casas (estava nulo, com fallback que fazia Stella, Camila e Eva se apresentarem como Serena) · `restaurant_ambientes` do Meet · link de reserva e `tagme_venue_id` do Meet.

**Aberto:**
- `lookup_menu` devolve negativa seca quando a base está vazia — vazamento do modo seguro pelo lado da ferramenta
- Handoff grava em banco e notifica Discord, mas ninguém recebe WhatsApp
- Produção roda de branch, divergente da main; rota de escalação clínica está na main e não no ar
- Nome da variável do webhook do Discord a confirmar — se estiver errada, todo handoff é invisível
- `capacidade_maxima_reserva` = 8 nas 4 casas, contra mesas de até 12 no prompt

# ANEXO B — DECISÕES E DADOS PENDENTES DO IKE

| # | Item | Trava o quê |
|---|---|---|
| 1 | URL do Live Menu da Madonna | Catálogo da Madonna, Sprint 1 |
| 2 | CSV extraído do Meet (277 itens) | Carga do catálogo, Sprint 1 |
| 3 | WhatsApp da Vic e demais closers | Handoff de Madonna e Meet, Sprint 1 |
| 4 | Turnos de Frêneze e Meet: dia, horário, capacidade, intervalo | Agenda própria e página pública, Sprints 2 e 5 |
| 5 | `capacidade_maxima_reserva` por casa | Header do prompt das 4 casas |
| 6 | Nome comercial dos ambientes do Meet (Térreo/Bar Secreto vs Salão Prime/Secret) | Alinhamento agente × site |
| 7 | Telefone público e site por casa | Preenchimento de `restaurants` |
| 8 | Capacidade real de Madonna, Frêneze e Levvai | `restaurant_ambientes` |
| 9 | Preço de tabela, franquia e taxa de implantação | Parte V e Sprint 6 |
| 10 | Escopo confirmado: reserva primeiro, fila em 12 meses | Roadmap |
| 11 | Recarga automática de crédito Anthropic | Risco de silêncio do agente |
| 12 | Correção de horário e capacidade nos canais públicos | Site do Meet, Tripadvisor de Madonna e Meet, próximo release |

---

*Este documento tem uma função: quando alguém perguntar "o que é a Serena, como funciona e para onde vai", a resposta está aqui e é a mesma para todos. Ele se atualiza a cada fechamento de sprint. Onde estiver `[DADO PENDENTE]`, continua pendente até ter número medido — não até ter estimativa plausível.*