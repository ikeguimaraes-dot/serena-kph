# Exportação privada por unidade

Ferramenta local: `scripts/export_customer_data.py`. Escopo de portabilidade
operacional, em leitura. **Não é backup integral, restauração automática ou upload.**
Esta entrega foi testada somente com unidades sintéticas no banco restaurado;
nenhum cadastro real de produção foi exportado.

## Executar

Pré-requisito: Python 3.11 com asyncpg e configuração existente do backup em
`~/.config/serena-backup/config.json`, privada (0600), pertencente ao operador.
O script usa `database_url` e verifica `expected_project_ref`. Não recebe senha
na linha de comando nem registra a URL de conexão.

O padrão é **somente contagens**, sem arquivos e sem dados pessoais:

```bash
python3.11 scripts/export_customer_data.py --restaurant-id meet_and_eat
# Equivalente explícito:
python3.11 scripts/export_customer_data.py --restaurant-id meet_and_eat --dry-run
```

Para criar os arquivos, fornecer explicitamente um diretório absoluto **novo**:

```bash
python3.11 scripts/export_customer_data.py \
  --restaurant-id meet_and_eat \
  --output "$HOME/.local/share/serena-exports/meet-and-eat-AAAA-MM-DD" \
  --zip
```

O ID identifica exatamente uma unidade existente; não existe exportação global
ou expansão por telefone. O comando não foi executado contra produção nesta
entrega. É necessário executar como o responsável autorizado pela saída dos dados.

Destinos existentes, repositórios Git e pastas conhecidas de publicação ou nuvem
(`public`, `www`, `CloudStorage`, `Dropbox` etc.) são recusados. Diretório novo:
0700; arquivos: 0600. A proteção é por permissão local, não criptografia. Quem
receber/copiar o pacote fica responsável por preservar sua privacidade.

## Conteúdo e fronteira de unidade

| Arquivo JSONL | Filtro/vínculo |
|---|---|
| `contacts` | `restaurant_id` exato: cadastro, preferências, estágio, motivo, métricas registradas e flag de consentimento |
| `conversations` | `restaurant_id` exato: histórico textual, tipo de mídia, SIDs e origem disponíveis |
| `reservas` | `restaurant_id` exato: reservas da agenda atual, desfecho e origem registrados |
| `reservations` | `restaurant_id` exato: reservas da tabela legada, preservadas separadamente, sem deduplicação presumida |
| `ordens_servico` | `restaurant_id` exato: eventos, proposta, valores e execução registrados |
| `checklist_instancias` | Join pelo `os_id` com OS existente da unidade; o `restaurant_id` do arquivo é derivado desse vínculo e marcado em `schema.json` |
| `outreach_consent_events` | `restaurant_id` exato: evidência e revogações, sem inferir consentimento |
| `contact_stage_events` | `restaurant_id` do próprio evento; preserva histórico cujo contato foi excluído |
| `reservation_status_events` | `restaurant_id` do próprio evento; preserva histórico cuja reserva foi excluída |
| `handoff_sessions` | `restaurant_id` exato: motivo, atendimento e estado observado da notificação |
| `outreach_outbox` | `restaurant_id` exato: tentativas, aceite/erro e payload operacional; aceite não comprova entrega |

Checklists sem uma OS existente não recebem uma unidade por inferência. Não há
join por telefone que possa misturar casas. Eventos de auditoria são preservados
mesmo sem registro operacional pai porque já carregam seu próprio `restaurant_id`.

Tabelas **e colunas** usam uma lista explícita: colunas novas não entram
automaticamente. `schema.json` informa colunas presentes, opcionais ausentes e
colunas excluídas. Se uma tabela obrigatória não estiver pronta, a exportação falha
em vez de apresentar pacote parcial como completo.

Ficam fora: usuários/auth, credenciais, operadores, configuração da empresa,
prompts, IDs de integração de pagamento, URLs de mídia potencialmente assinadas
e objetos binários de Storage/Twilio. Não há chamada a esses provedores. O texto
das conversas e evidências pode conter informação sensível; o pacote é privado.

## Snapshot e integridade

Uma transação **REPEATABLE READ, READ ONLY** mantém as contagens, esquema e linhas
no mesmo snapshot, mesmo se outra conexão registrar atendimento durante a leitura.
Cada tabela é ordenada por ID; JSONL é UTF-8 gerado por `row_to_json` do Postgres.
Valores decimais mantêm representação numérica de origem; consumidores devem usar
tipos que preservem precisão. Timestamps incluem o deslocamento de fuso da origem.

O pacote contém:

- Um JSONL por tabela, inclusive arquivos vazios quando a contagem é zero.
- `schema.json`: tipos e nulabilidade das colunas exportadas, com derivados explícitos.
- `manifest.json`: formato, versão/hash do script, unidade, snapshot, contagens,
  hashes SHA-256, tamanhos e limites de escopo.
- `SHA256SUMS`: integridade dos JSONL, esquema e manifesto.
- `unit-export.zip`, se solicitado: cópia local compactada dos mesmos arquivos,
  também privada, sem caminhos absolutos dentro do ZIP.

Uma execução interrompida mantém `.incomplete`; esse pacote não deve ser entregue
como concluído. Não há sobrescrita ou reutilização automática da pasta. O script
não remove a origem nem muda consentimento, retenção ou acesso de nenhuma conta.

Para conferir uma exportação concluída no Mac:

```bash
cd "$HOME/.local/share/serena-exports/meet-and-eat-AAAA-MM-DD"
shasum -a 256 -c SHA256SUMS
```

## Validação executada

Testes offline verificam unidade explícita, permissões da configuração, bloqueio
de destinos e lista de colunas. O hook `scripts/test_export_restore.py` recusa
qualquer banco fora do cluster descartável do runner. Ele testa duas unidades com
o mesmo telefone, eventos órfãos, reservas legadas/checklists, alteração concorrente
em outra conexão, JSONL/esquema/manifesto/hashes/ZIP e proibição de sobrescrita.
As únicas linhas exportadas nesse ensaio são fixtures sintéticas; os arquivos são
apagados com o ambiente descartável. Prova resumida em
`private-export-proof-20260917.json`.

```bash
python3.11 -m unittest scripts.test_export_customer_data -v
```
