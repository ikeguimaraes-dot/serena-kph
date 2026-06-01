-- Migration 009: Régua pós-evento + NPS + LTV base
-- Aplicar no Supabase SQL Editor

-- 1. Campos de régua na tabela ordens_servico
ALTER TABLE ordens_servico
  ADD COLUMN IF NOT EXISTS regua_d1_enviado_em   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS regua_d3_enviado_em   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS regua_d7_enviado_em   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS regua_d30_enviado_em  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS nps_score             SMALLINT CHECK (nps_score BETWEEN 1 AND 10),
  ADD COLUMN IF NOT EXISTS nps_respondido_em     TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS evento_realizado_em   TIMESTAMPTZ;

-- 2. LTV base em contacts
ALTER TABLE contacts
  ADD COLUMN IF NOT EXISTS ltv_total   NUMERIC(10,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_eventos INTEGER DEFAULT 0;

-- 3. View auxiliar: OS prontas para régua
CREATE OR REPLACE VIEW vw_os_regua AS
SELECT
  os.id,
  os.restaurant_id,
  os.contact_id,
  os.titulo,
  os.valor_total,
  os.status,
  os.evento_realizado_em,
  os.regua_d1_enviado_em,
  os.regua_d3_enviado_em,
  os.regua_d7_enviado_em,
  os.regua_d30_enviado_em,
  os.nps_score,
  c.telefone,
  c.nome AS contact_nome
FROM ordens_servico os
JOIN contacts c ON c.id = os.contact_id
WHERE os.status = 'realizado';

-- 4. Índice para job diário (performance)
CREATE INDEX IF NOT EXISTS idx_os_status_realizado
  ON ordens_servico(status, evento_realizado_em)
  WHERE status = 'realizado';
