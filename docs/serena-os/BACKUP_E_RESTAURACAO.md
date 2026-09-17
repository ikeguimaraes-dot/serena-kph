# Backup externo e teste de restauração

## Resultado verificado em 17/09/2026

- Origem: Supabase `czoakcsntfxmqfssubbe`, PostgreSQL **17.6**, pooler de sessão IPv4, porta **5432**.
- Ferramentas locais: PostgreSQL **17.11**, Python 3.11 e `asyncpg==0.31.0`.
- Backup lógico real, fora do Supabase e fora do Git: **64 tabelas, 988 linhas e 4 versões de prompt** no primeiro snapshot.
- Restauração real em PostgreSQL local descartável: **todas as tabelas com contagem e conteúdo idênticos** ao snapshot. Duração: **11,68 segundos**.
- Ensaio integrado adicional: **739 itens** (Meet 276, Madonna 253, Frêneze 210),
  reimportação idempotente, edição manual preservada, preços validados e rollback.
  Restauração + ensaio: **43,03 segundos**. Nove testes offline de proteção também passaram.
- O cluster de ensaio foi encerrado e removido. Nenhuma escrita de recuperação foi executada na produção.
- Rotina diária **ativada para 03:15 no fuso local da máquina** em 17/09/2026.
  `launchctl print gui/501/com.serena.backup` confirmou o serviço carregado;
  plist validado e com permissão 0600. `RunAtLoad=false` foi preservado.

Provas sem dados pessoais: `docs/serena-os/backup-restore-proof-20260917.json`.
Arquivo completo privado: `~/.local/share/serena-backups/20260917T042832.111509Z/restore-proof.json`.

## O que está protegido

O arquivo `database.dump` é um archive PostgreSQL custom, restaurável por `pg_restore`.
Inclui schema e dados de `public`, `auth`, `storage` e `supabase_migrations`: prompts,
restaurantes, catálogos, agenda, reservas, conversas, handoffs, contatos, usuários Auth,
funções, sequências, índices, constraints, políticas RLS e grants.

Cada diretório também contém:

- `schema.sql`: estrutura SQL separada para inspeção e recuperação.
- `manifest.json`: versão do servidor, nomes dos schemas/roles/extensões, hashes SHA-256
  e tamanhos dos arquivos, contagens e hashes de conteúdo por tabela.
- `restore-proof.json`: resultado do restore executado, sem conteúdo de clientes.
- Logs privados de diagnóstico; falhas não são confundidas com backup validado.

**Limites:** arquivos binários dos buckets não estão no dump (apenas metadados), nem
segredos/configuração de Railway/Twilio/Vercel, schema interno Realtime ou chaves de
criptografia Vault. Isso não é um clone completo dos serviços gerenciados Supabase.
Uma recuperação em novo projeto ainda exige recriar as configurações dos serviços,
verificar extensões, credenciais, publicação Realtime e integrações.

## Consistência e proteção

O processo exporta um snapshot PostgreSQL em transação `REPEATABLE READ READ ONLY`.
Tanto os dumps quanto as contagens/hashes usam esse snapshot: mensagens que chegam
enquanto o backup roda não causam falso resultado diferente no restore.
`pg_dump` usa timeout de 10 segundos para adquirir locks; não executa DDL em produção.

O arquivo de configuração fica em `~/.config/serena-backup/config.json` com modo
**0600**. Pastas privadas usam **0700**. O código recusa destino dentro de repositório
Git, credencial legível por outros usuários, projeto diferente do esperado e pooler
de transação na porta 6543. Credenciais são passadas ao PostgreSQL pelo ambiente do
processo, nunca em argumentos, plist ou arquivos versionados.

Os dumps não têm senha própria. A máquina verificada está com **FileVault ativo**;
permissões de arquivo e criptografia de disco protegem a cópia local. Qualquer futura
cópia para outra mídia/nuvem deve preservar acesso privado e criptografia.

Restauração automatizada nunca aceita URL de destino: cria um cluster novo sob
`/tmp/serena-restore-*`, usando socket Unix em pasta privada, **sem escutar TCP**.
As roles necessárias às policies/grants são recriadas localmente como `NOLOGIN`,
sem copiar senhas ou privilégios administrativos do provedor. Os objetos são
restaurados com `--no-owner`, em transação única e com `--exit-on-error`.

## Execução manual

Não cole a URL do banco na linha de comando ou no Git. A configuração privada já
está preparada nesta máquina; em outra, crie um JSON 0600 com `database_url`,
`expected_project_ref`, `pg_bin`, `backup_root` e `retention_days`.

```bash
# Novo backup + restauração local + validação completa.
/usr/local/bin/python3.11 scripts/serena_backup.py \
  --config "$HOME/.config/serena-backup/config.json"

# Verificar integridade e idade do último backup validado.
# Retorna status 2 quando ultrapassa 36 horas.
/usr/local/bin/python3.11 scripts/serena_backup.py \
  --config "$HOME/.config/serena-backup/config.json" --status

# Repetir restauração de um archive existente, sempre em cluster local novo.
/usr/local/bin/python3.11 scripts/serena_backup.py \
  --config "$HOME/.config/serena-backup/config.json" \
  --backup "$HOME/.local/share/serena-backups/20260917T042832.111509Z"
```

Somente após o restore passar, `last-success.json` é atualizado e a retenção executa.
Mantêm-se 30 dias de cópias validadas e **pelo menos as duas últimas**, mesmo após uma
interrupção longa. Backups falhos/parciais não são usados para remover backups bons;
devem ser inspecionados e removidos manualmente quando não forem mais úteis.
Uma trava impede execuções simultâneas.

## Agendamento diário ativo — procedimento de reinstalação

`prepare_backup_launchd.py` copia o programa para um caminho estável fora do worktree
(`~/.local/lib/serena-backup/serena_backup.py`) e gera um plist concreto:

```bash
/usr/local/bin/python3.11 scripts/prepare_backup_launchd.py \
  --config "$HOME/.config/serena-backup/config.json"
plutil -lint "$HOME/.local/share/serena-backups/prepared/com.serena.backup.plist"
```

A preparação e ativação foram executadas e o plist passou na validação. Em uma
reinstalação, depois de conferir a configuração privada, executar:

```bash
mkdir -p "$HOME/Library/LaunchAgents"
cp "$HOME/.local/share/serena-backups/prepared/com.serena.backup.plist" \
  "$HOME/Library/LaunchAgents/com.serena.backup.plist"
chmod 600 "$HOME/Library/LaunchAgents/com.serena.backup.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.serena.backup.plist"
launchctl print "gui/$(id -u)/com.serena.backup"
```

O job usa `RunAtLoad=false`; começa no próximo horário agendado. Para um ensaio
imediato depois da ativação: `launchctl kickstart gui/$(id -u)/com.serena.backup`.
Para desativar: `launchctl bootout gui/$(id -u)/com.serena.backup`.

Logs ficam em `~/.local/share/serena-backups/launchd.stdout.log` e
`launchd.stderr.log`, ambos privados. Verifique `--status` no ritual operacional.
Não há envio de mensagens ou alertas externos configurado por este trabalho.

**Limitação operacional:** a rotina depende deste Mac, da sessão do usuário e de
acesso à internet. Máquina desligada/offline não garante backup diário. A cópia está
fora do Supabase, mas ainda precisa de um segundo destino privado independente do
Mac e de execução sempre ativa para oferecer cobertura contínua. Nenhum serviço
pago ou destino público foi criado.

## Ensaios de mudanças sobre o restore

`--restore-hook caminho/teste.py` executa um teste adicional após comprovar a
fidelidade do backup, antes de remover o cluster. O processo recebe apenas o
ambiente local necessário e as variáveis `PGHOST` (socket), `PGPORT`, `PGUSER` e
`PGDATABASE=serena_restore`; não recebe segredos do banco de produção.
O hook pode testar migrations/importações no clone e reverter suas alterações.
Resultado e hash do script ficam na prova; stdout fica em `restore-hook.log` privado.

## Compatibilidade e referências

O `pg_dump` 16 instalado anteriormente não pode ler o servidor 17. Usamos os
binários 17 por caminho explícito, sem substituir a versão 16 nem iniciar um
serviço permanente. O Homebrew local é anterior ao formato atual de post-install;
foi necessário concluir os links de recursos `lib/postgresql@17` e
`share/postgresql@17`. `pg_dump`, `initdb`, `postgres`, `psql` e `pg_restore` foram
verificados pela execução real.

- [Supabase: backup e restore via CLI](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)
- [PostgreSQL: pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)
- [PostgreSQL: pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html)
