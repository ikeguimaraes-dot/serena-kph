-- ============================================================
-- Sprint 3 — proposta_pricing (fonte de verdade de preços de proposta)
-- + extensão de ordens_servico para campos de proposta calculada
-- ⚠️  Rodar ANTES de ativar o tool calcular_proposta em produção.
-- ============================================================

-- ── 1. Tabela proposta_pricing ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS proposta_pricing (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id TEXT        NOT NULL REFERENCES restaurants(id),
    tipo          TEXT        NOT NULL CHECK (tipo IN ('plano', 'addon', 'ambiente')),
    tipo_evento   TEXT,       -- 'happy_hour' | 'evento' | NULL (ambientes)
    plano         TEXT,       -- 'classic' | 'premium' | 'standart' | NULL
    nome          TEXT        NOT NULL,  -- slug: 'mini_pratos', 'open_bar', 'rooftop'…
    valor         NUMERIC(10,2) NOT NULL, -- valor/pessoa (planos/addons) ou locação (ambiente)
    ativo         BOOLEAN     NOT NULL DEFAULT true,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- índice único que evita duplicatas ao re-rodar seed
CREATE UNIQUE INDEX IF NOT EXISTS idx_proposta_pricing_uniq
    ON proposta_pricing (
        restaurant_id,
        tipo,
        COALESCE(tipo_evento, ''),
        COALESCE(plano, ''),
        nome
    );

CREATE INDEX IF NOT EXISTS idx_proposta_pricing_lookup
    ON proposta_pricing (restaurant_id, tipo, tipo_evento, plano)
    WHERE ativo = true;

-- ── 2. Seed Meet & Eat — 13 linhas (MEET_TABELA_REGRAS_PROPOSTA) ──────────────
INSERT INTO proposta_pricing (restaurant_id, tipo, tipo_evento, plano, nome, valor) VALUES
-- Planos Happy Hour
('meet_and_eat', 'plano', 'happy_hour', 'classic',  'happy_hour_classic',  435.00),
('meet_and_eat', 'plano', 'happy_hour', 'premium',  'happy_hour_premium',  525.00),
-- Planos Evento
('meet_and_eat', 'plano', 'evento',     'standart', 'evento_standart',     345.00),
('meet_and_eat', 'plano', 'evento',     'classic',  'evento_classic',      435.00),
('meet_and_eat', 'plano', 'evento',     'premium',  'evento_premium',      555.00),
-- Add-ons Happy Hour (plano NULL = disponível em Classic e Premium)
('meet_and_eat', 'addon', 'happy_hour', NULL,       'mini_pratos',          75.00),
('meet_and_eat', 'addon', 'happy_hour', NULL,       'sobremesa',            45.00),
-- Add-ons Evento — Open Bar varia por plano
('meet_and_eat', 'addon', 'evento',     'standart', 'open_bar',            100.00),
('meet_and_eat', 'addon', 'evento',     'classic',  'open_bar',            150.00),
('meet_and_eat', 'addon', 'evento',     'premium',  'open_bar',            200.00),
-- Ambientes (locação fixa, independe de tipo/plano)
('meet_and_eat', 'ambiente', NULL, NULL, 'secret_bar',  15000.00),
('meet_and_eat', 'ambiente', NULL, NULL, 'rooftop',     25000.00),
('meet_and_eat', 'ambiente', NULL, NULL, 'salao_prime', 25000.00)
ON CONFLICT DO NOTHING;

-- ── 3. Extensão de ordens_servico para proposta calculada ─────────────────────
ALTER TABLE ordens_servico
    ADD COLUMN IF NOT EXISTS plano              TEXT,
    ADD COLUMN IF NOT EXISTS ambiente           TEXT,
    ADD COLUMN IF NOT EXISTS addons             JSONB,
    ADD COLUMN IF NOT EXISTS proposta_validade  TIMESTAMPTZ;

-- ── 4. Verificação ────────────────────────────────────────────────────────────
SELECT tipo, COUNT(*) AS n FROM proposta_pricing
WHERE restaurant_id = 'meet_and_eat'
GROUP BY tipo ORDER BY tipo;
