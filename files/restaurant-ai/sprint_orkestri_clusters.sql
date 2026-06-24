-- ============================================================
-- SPRINT ORKESTRI — clusters de propostas
-- STATUS: APLICADO em 24/06/2026 (ALTER aditivo, reversível).
-- Não toca contacts/reservas/prompts. status real = 'pending' (não 'pendente').
-- ============================================================

-- Etapa 1 — colunas de clustering em orkestri_learning
-- ROLLBACK:
--   ALTER TABLE orkestri_learning
--     DROP COLUMN IF EXISTS cluster_tema, DROP COLUMN IF EXISTS cluster_rank,
--     DROP COLUMN IF EXISTS obsoleta, DROP COLUMN IF EXISTS obsoleta_motivo;
ALTER TABLE orkestri_learning
  ADD COLUMN IF NOT EXISTS cluster_tema    TEXT,     -- categoria do grupo (tagme, lead_score, ...)
  ADD COLUMN IF NOT EXISTS cluster_rank    INTEGER DEFAULT 0,   -- 1 = mais recente/relevante; >1 = duplicata
  ADD COLUMN IF NOT EXISTS obsoleta        BOOLEAN DEFAULT FALSE, -- marcada pelo agente de clustering
  ADD COLUMN IF NOT EXISTS obsoleta_motivo TEXT;     -- ex: "evento expirado 12/06", "duplicata de mais recente"
