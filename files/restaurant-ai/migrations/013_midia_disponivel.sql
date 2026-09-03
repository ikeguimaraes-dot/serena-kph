-- Sprint 1 · Mídia Etapa 3 (envio)
-- Tabela de mídia disponível para envio pelo agente.
-- A IA escolhe por chave; a URL real fica aqui. Nunca envia URL livre.
-- Conteúdo (chaves + arquivos) populado pelo Clau via MCP, não pelo código.

CREATE TABLE IF NOT EXISTS midia_disponivel (
  id            uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  restaurant_id text        NOT NULL,
  chave         text        NOT NULL,
  url           text        NOT NULL,
  descricao     text        NOT NULL,
  mime_type     text        NOT NULL DEFAULT 'application/pdf',
  ativo         boolean     NOT NULL DEFAULT true,
  created_at    timestamptz DEFAULT (now() AT TIME ZONE 'America/Sao_Paulo'),
  UNIQUE(restaurant_id, chave)
);

CREATE INDEX IF NOT EXISTS idx_midia_disponivel_rid_chave
  ON midia_disponivel(restaurant_id, chave);
