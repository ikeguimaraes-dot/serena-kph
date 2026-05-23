-- ============================================================
-- MIGRATION — Módulo CRM (contacts)
-- Execute no Supabase: SQL Editor > New Query > Cole e rode
-- Depende de: schema-supabase.sql (tabela reservations)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- pra gen_random_uuid()

-- ------------------------------------------------------------
-- TABELA PRINCIPAL
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contacts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    celular                 TEXT UNIQUE NOT NULL,
    nome                    TEXT,
    sobrenome               TEXT,
    email                   TEXT,
    data_nascimento         DATE,
    endereco                TEXT,
    tipo_aparelho           TEXT CHECK (tipo_aparelho IN ('iOS','Android') OR tipo_aparelho IS NULL),
    canal_entrada           TEXT,
    ocasiao                 TEXT[] DEFAULT '{}',
    restricoes_alimentares  TEXT[] DEFAULT '{}',
    frequencia_visitas      INTEGER DEFAULT 0,
    ticket_medio            NUMERIC(10,2),
    ultima_visita           DATE,
    tier                    TEXT DEFAULT 'Bronze'
                            CHECK (tier IN ('Bronze','Prata','Ouro')),
    tags                    TEXT[] DEFAULT '{}',
    opt_in_marketing        BOOLEAN DEFAULT false,
    estagio_kanban          TEXT DEFAULT 'Novo Lead'
                            CHECK (estagio_kanban IN (
                                'Novo Lead','Qualificado','Proposta Enviada',
                                'Confirmado','Realizado','Recorrente','Inativo'
                            )),
    notas                   TEXT,
    criado_em               TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contacts_celular       ON contacts(celular);
CREATE INDEX IF NOT EXISTS idx_contacts_tier          ON contacts(tier);
CREATE INDEX IF NOT EXISTS idx_contacts_kanban        ON contacts(estagio_kanban);
CREATE INDEX IF NOT EXISTS idx_contacts_ultima_visita ON contacts(ultima_visita);
CREATE INDEX IF NOT EXISTS idx_contacts_ocasiao       ON contacts USING GIN (ocasiao);
CREATE INDEX IF NOT EXISTS idx_contacts_tags          ON contacts USING GIN (tags);

-- ------------------------------------------------------------
-- FUNÇÃO: calcula tier a partir da frequência
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION contacts_calc_tier(freq INTEGER)
RETURNS TEXT AS $$
BEGIN
    IF freq >= 7 THEN RETURN 'Ouro';
    ELSIF freq >= 3 THEN RETURN 'Prata';
    ELSE RETURN 'Bronze';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ------------------------------------------------------------
-- TRIGGER 1: atualizado_em automático em qualquer UPDATE
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION contacts_touch_atualizado_em()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contacts_touch ON contacts;
CREATE TRIGGER trg_contacts_touch
    BEFORE UPDATE ON contacts
    FOR EACH ROW
    EXECUTE FUNCTION contacts_touch_atualizado_em();

-- ------------------------------------------------------------
-- TRIGGER 2: recalcula tier quando frequencia_visitas muda
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION contacts_sync_tier()
RETURNS TRIGGER AS $$
BEGIN
    NEW.tier := contacts_calc_tier(NEW.frequencia_visitas);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contacts_tier ON contacts;
CREATE TRIGGER trg_contacts_tier
    BEFORE INSERT OR UPDATE OF frequencia_visitas ON contacts
    FOR EACH ROW
    EXECUTE FUNCTION contacts_sync_tier();

-- ------------------------------------------------------------
-- TRIGGER 3: sync com reservations
-- Quando uma reservation é criada com status='confirmada' OU
-- é atualizada pra 'concluida', upserta contact e incrementa.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION contacts_sync_from_reservation()
RETURNS TRIGGER AS $$
DECLARE
    should_count BOOLEAN;
    visit_date DATE;
BEGIN
    -- Conta como visita realizada quando status vira 'concluida',
    -- ou quando a reserva é criada já confirmada (pra servir de semente de cadastro).
    IF TG_OP = 'INSERT' THEN
        should_count := (NEW.status = 'confirmada' OR NEW.status = 'concluida');
    ELSE
        should_count := (NEW.status = 'concluida' AND (OLD.status IS DISTINCT FROM 'concluida'));
    END IF;

    -- Converte texto DD/MM/YYYY pra DATE; se falhar, usa hoje.
    BEGIN
        visit_date := to_date(NEW.data, 'DD/MM/YYYY');
    EXCEPTION WHEN OTHERS THEN
        visit_date := CURRENT_DATE;
    END;

    -- Upsert por celular (user_phone). Cria contato Novo Lead na 1ª reserva.
    INSERT INTO contacts (celular, nome, frequencia_visitas, ultima_visita, estagio_kanban)
    VALUES (
        NEW.user_phone,
        NEW.nome,
        CASE WHEN should_count THEN 1 ELSE 0 END,
        CASE WHEN should_count THEN visit_date ELSE NULL END,
        CASE WHEN NEW.status = 'concluida' THEN 'Realizado'
             WHEN NEW.status = 'confirmada' THEN 'Confirmado'
             ELSE 'Novo Lead' END
    )
    ON CONFLICT (celular) DO UPDATE SET
        nome = COALESCE(contacts.nome, NEW.nome),
        frequencia_visitas = contacts.frequencia_visitas
            + CASE WHEN should_count THEN 1 ELSE 0 END,
        ultima_visita = CASE
            WHEN should_count THEN GREATEST(COALESCE(contacts.ultima_visita, visit_date), visit_date)
            ELSE contacts.ultima_visita
        END,
        estagio_kanban = CASE
            -- Promove recorrente se já passou pelo funil e tem 3+ visitas
            WHEN should_count AND contacts.frequencia_visitas + 1 >= 3
                 AND contacts.estagio_kanban IN ('Realizado','Confirmado')
                THEN 'Recorrente'
            WHEN NEW.status = 'concluida' THEN 'Realizado'
            WHEN NEW.status = 'confirmada'
                 AND contacts.estagio_kanban IN ('Novo Lead','Qualificado','Proposta Enviada')
                THEN 'Confirmado'
            ELSE contacts.estagio_kanban
        END;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reservations_sync_contact ON reservations;
CREATE TRIGGER trg_reservations_sync_contact
    AFTER INSERT OR UPDATE OF status ON reservations
    FOR EACH ROW
    EXECUTE FUNCTION contacts_sync_from_reservation();

-- ------------------------------------------------------------
-- FUNÇÃO: marca como Inativo contatos sem visita há 45+ dias
-- Chamar via cron (pg_cron) ou manualmente pelo backend.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION contacts_mark_inactive(threshold_days INT DEFAULT 45)
RETURNS INTEGER AS $$
DECLARE
    affected INT;
BEGIN
    UPDATE contacts
    SET estagio_kanban = 'Inativo'
    WHERE estagio_kanban <> 'Inativo'
      AND (
        (ultima_visita IS NOT NULL AND ultima_visita < CURRENT_DATE - threshold_days)
        OR (ultima_visita IS NULL AND criado_em < NOW() - (threshold_days || ' days')::interval)
      );
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- OPCIONAL: pg_cron diário (requer extensão pg_cron habilitada no Supabase)
-- Descomente se for usar cron nativo em vez de endpoint backend.
-- ------------------------------------------------------------
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
-- SELECT cron.schedule(
--     'contacts_mark_inactive_daily',
--     '0 3 * * *',  -- 03:00 UTC todo dia
--     $$SELECT contacts_mark_inactive(45);$$
-- );

-- ------------------------------------------------------------
-- SEED opcional: backfill de contacts a partir de reservations existentes
-- Descomente na primeira execução se já houver reservations no banco.
-- ------------------------------------------------------------
-- INSERT INTO contacts (celular, nome, frequencia_visitas, ultima_visita, estagio_kanban)
-- SELECT
--     user_phone,
--     MAX(nome),
--     COUNT(*) FILTER (WHERE status IN ('confirmada','concluida')),
--     MAX(to_date(data, 'DD/MM/YYYY')) FILTER (WHERE status IN ('confirmada','concluida')),
--     CASE
--         WHEN COUNT(*) FILTER (WHERE status = 'concluida') >= 3 THEN 'Recorrente'
--         WHEN COUNT(*) FILTER (WHERE status = 'concluida') >= 1 THEN 'Realizado'
--         WHEN COUNT(*) FILTER (WHERE status = 'confirmada') >= 1 THEN 'Confirmado'
--         ELSE 'Novo Lead'
--     END
-- FROM reservations
-- GROUP BY user_phone
-- ON CONFLICT (celular) DO NOTHING;
