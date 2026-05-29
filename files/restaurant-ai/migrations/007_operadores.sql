-- Migration 007: Tabela de operadores
-- Mapeia auth.users.id → perfil interno (nome, restaurante, role)
-- Executar no Supabase SQL Editor como superuser

CREATE TABLE IF NOT EXISTS operadores (
  id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email       TEXT NOT NULL,
  nome        TEXT NOT NULL,
  restaurante_id TEXT REFERENCES restaurants(id),
  role        TEXT NOT NULL DEFAULT 'atendente'
              CHECK (role IN ('admin', 'atendente')),
  criado_em   TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para lookup por restaurante
CREATE INDEX IF NOT EXISTS idx_operadores_restaurante
  ON operadores(restaurante_id);

-- Row Level Security: operador só vê o próprio perfil
ALTER TABLE operadores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "operador_ve_proprio_perfil"
  ON operadores FOR SELECT
  USING (auth.uid() = id);

-- Seed: perfil inicial do Ike
-- (Rodar DEPOIS de criar o usuário no Supabase Auth)
-- INSERT INTO operadores (id, email, nome, restaurante_id, role)
-- VALUES (
--   (SELECT id FROM auth.users WHERE email = 'henrique@kph.com.br'),
--   'henrique@kph.com.br',
--   'Ike',
--   1,
--   'admin'
-- );
