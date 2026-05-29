-- Migration 006: lead_score em contacts
-- Seguro: usa IF NOT EXISTS, sem DROP

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS lead_score TEXT
  CHECK (lead_score IN ('quente','morno','frio'));

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS lead_score_at TIMESTAMPTZ;
