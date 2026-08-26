-- Sprint Mídia ETAPA 2: adiciona colunas de mídia inbound à tabela conversations.
-- media_url  → URL do objeto no Supabase Storage (bucket privado serena-midia-entrada)
-- media_type → MIME type do arquivo (ex: image/jpeg, application/pdf)
-- Ambas nullable — mensagens de texto puro não têm mídia.

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS media_url  TEXT,
    ADD COLUMN IF NOT EXISTS media_type TEXT;

-- Prova: verificar que as colunas existem
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'conversations'
  AND column_name IN ('media_url', 'media_type')
ORDER BY column_name;
