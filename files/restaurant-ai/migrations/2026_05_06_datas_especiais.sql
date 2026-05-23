-- Onda 11 — Datas especiais (calendário de exceções ao funcionamento padrão)
-- Idempotente.

CREATE TABLE IF NOT EXISTS datas_especiais (
    id SERIAL PRIMARY KEY,
    restaurant_id TEXT REFERENCES restaurants(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    nome TEXT NOT NULL,
    aberto BOOLEAN DEFAULT true,
    horario_especial TEXT,
    observacao TEXT,
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (restaurant_id, data)
);

CREATE INDEX IF NOT EXISTS idx_datas_especiais_data
    ON datas_especiais(restaurant_id, data);

-- Dia das Mães 2026 — domingo aberto excepcionalmente.
INSERT INTO datas_especiais (restaurant_id, data, nome, aberto, observacao)
VALUES (
    'madonna_cucina',
    '2026-05-10',
    'Dia das Mães',
    true,
    'Domingo aberto excepcionalmente. Reservas via Tagme com prioridade.'
)
ON CONFLICT (restaurant_id, data) DO NOTHING;
