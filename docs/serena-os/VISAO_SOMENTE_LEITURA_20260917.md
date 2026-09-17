# Validação real de visão — 17/09/2026

## Resultado

Os três drafts reconheceram uma imagem PNG sintética de 640 × 320 pixels: círculo vermelho à esquerda, quadrado azul ao centro e triângulo verde à direita, sobre fundo branco. As respostas afirmaram explicitamente que a imagem não contém informação de preço, cardápio ou disponibilidade da casa.

| Unidade | Prompt consultado | Estado no momento da leitura | Resultado factual | Preço/estoque inventado |
|---|---:|---|---|---|
| Meet & Eat | 10 | Inativo | Três pares forma/cor corretos | Não |
| Madonna Cucina | 9 | Inativo | Três pares forma/cor corretos | Não |
| Frêneze | 8 | Inativo | Três pares forma/cor corretos | Não |

Foram **três chamadas reais** ao modelo, uma por unidade, sem chamadas a ferramentas. Custo observado na usage: **US$ 0,07653975**, incluindo cache quando informado. Não é uma projeção de custo de produção.

## Caminho e isolamento

- Fonte de código congelada em `27d21eda3b0507c6bf0cc803310c00625df6ba18`, em worktree isolada.
- Entrada direta em `RestaurantAgent._run(..., read_only=True)` com bloco `image/png` base64. O header dinâmico e o corpo de cada draft seguem o caminho de override de `test_turn`, sem contexto CRM nem histórico de cliente.
- Configuração da casa e draft foram lidos por SELECT em transação PostgreSQL `READ ONLY`. A conexão foi encerrada **antes** de chamar o modelo.
- `process()` ficou proibido no processo de validação; dispatcher real de ferramentas e funções assíncronas do banco também foram substituídos por bloqueios. Nenhum deles foi necessário para as respostas.
- Zero leitura de registros de clientes, mensagens outbound, reservas, handoffs reais ou gravações no aplicativo. Apenas artefatos locais de prova foram escritos.
- Credencial Anthropic foi lida do Railway somente em memória. A conexão usou a configuração privada de backup. Nenhuma credencial integra os artefatos ou o Git.

A semântica do modo de transação foi conferida na [documentação oficial do PostgreSQL](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-DEFAULT-TRANSACTION-READ-ONLY). O harness ainda fecha a conexão e bloqueia o dispatcher para não depender somente dessa proteção.

## Evidência e testes

- Resumo sanitizado e hashes dos drafts: [vision-readonly-proof-20260917.json](vision-readonly-proof-20260917.json).
- Prova completa local: `~/.local/share/serena-recovery/vision-readonly-20260917/vision-proof.json`, modo **0600**, pasta **0700**.
- Fixture PNG no mesmo diretório privado, também **0600**. Foi desenhada do zero por código, sem fotografia, pessoa ou conteúdo de cliente.
- Harness: `scripts/validate_vision_readonly.py`. Rodá-lo novamente exige execução explícita e consome API; não faz parte de startup ou cron.
- Testes offline: `test_agent_vision_readonly.py` confirma que o bloco base64 chega intacto ao `_run` e permanece no follow-up, enquanto uma ferramenta de criação solicitada pelo modelo é bloqueada. Somados a `test_agent_readonly.py`, são sete testes, sem chamadas reais ao modelo.

```bash
cd files/restaurant-ai
python3.11 -m unittest test_agent_vision_readonly test_agent_readonly -v
```

## Limites da prova

Esta validação isola a compreensão de imagem com os drafts indicados. Não testa download de mídia pelo WhatsApp/Twilio, o `process()` de produção, OCR complexo, identificação de pratos reais, preços a partir de fotos, segurança clínica ou todo o estilo de resposta de cada marca. Os prompts não foram ativados nem alterados por esta execução.
