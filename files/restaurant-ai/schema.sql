-- ============================================================
-- SCHEMA COMPLETO — Restaurant AI
-- Execute no Supabase: SQL Editor > New Query > Cole e rode
-- ============================================================

-- Restaurantes (fonte de verdade — saiu do código)
CREATE TABLE IF NOT EXISTS restaurants (
    id                          TEXT PRIMARY KEY,
    nome                        TEXT NOT NULL,
    whatsapp_number             TEXT UNIQUE NOT NULL,
    endereco                    TEXT DEFAULT '',
    descricao                   TEXT DEFAULT '',
    capacidade_maxima_reserva   INTEGER DEFAULT 8,
    antecedencia_minima_horas   INTEGER DEFAULT 2,
    capacidade_total            INTEGER DEFAULT 80,
    ativo                       BOOLEAN DEFAULT true,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- Horários de funcionamento
CREATE TABLE IF NOT EXISTS business_hours (
    id              BIGSERIAL PRIMARY KEY,
    restaurant_id   TEXT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    dia             TEXT NOT NULL,
    horario         TEXT NOT NULL,
    fechado         BOOLEAN DEFAULT false
);

-- Cardápio
CREATE TABLE IF NOT EXISTS menu_items (
    id              BIGSERIAL PRIMARY KEY,
    restaurant_id   TEXT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    categoria       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    descricao       TEXT DEFAULT '',
    preco           DECIMAL(10,2),
    disponivel      BOOLEAN DEFAULT true,
    ordem           INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- FAQ por restaurante
CREATE TABLE IF NOT EXISTS faq_items (
    id              BIGSERIAL PRIMARY KEY,
    restaurant_id   TEXT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    chave           TEXT NOT NULL,
    resposta        TEXT NOT NULL,
    ordem           INTEGER DEFAULT 0
);

-- Histórico de conversas
CREATE TABLE IF NOT EXISTS conversations (
    id              BIGSERIAL PRIMARY KEY,
    user_phone      TEXT NOT NULL,
    restaurant_id   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conv ON conversations(user_phone, restaurant_id, created_at);

-- Reservas
CREATE TABLE IF NOT EXISTS reservations (
    id              TEXT PRIMARY KEY,
    user_phone      TEXT NOT NULL,
    restaurant_id   TEXT NOT NULL,
    nome            TEXT NOT NULL,
    data            TEXT NOT NULL,
    hora            TEXT NOT NULL,
    pessoas         INTEGER NOT NULL,
    observacoes     TEXT DEFAULT '',
    status          TEXT DEFAULT 'confirmada'
                    CHECK (status IN ('confirmada','cancelada','concluida','no_show')),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_res_slot ON reservations(restaurant_id, data, hora, status);
CREATE INDEX IF NOT EXISTS idx_res_data ON reservations(restaurant_id, data);

-- Sessões de handoff (atendimento humano)
CREATE TABLE IF NOT EXISTS handoff_sessions (
    id              BIGSERIAL PRIMARY KEY,
    user_phone      TEXT NOT NULL,
    restaurant_id   TEXT NOT NULL,
    motivo          TEXT DEFAULT '',
    status          TEXT DEFAULT 'aguardando'
                    CHECK (status IN ('aguardando','em_atendimento','resolvido')),
    atendente_nome  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_handoff ON handoff_sessions(restaurant_id, status, created_at DESC);

-- Membros da equipe
CREATE TABLE IF NOT EXISTS team_members (
    id              BIGSERIAL PRIMARY KEY,
    restaurant_id   TEXT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    whatsapp        TEXT NOT NULL,
    role            TEXT DEFAULT 'atendente' CHECK (role IN ('atendente','gerente','admin')),
    ativo           BOOLEAN DEFAULT true
);
