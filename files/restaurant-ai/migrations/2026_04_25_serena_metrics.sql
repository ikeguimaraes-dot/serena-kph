-- Onda 8 — Instrumentação Serena
-- Captura métricas por turno + versionamento de prompt + relatórios semanais.
-- Idempotente: pode rodar múltiplas vezes (CREATE TABLE IF NOT EXISTS).

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── serena_metrics ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS serena_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id INTEGER,
    user_phone TEXT,
    restaurant_id TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    custo_usd NUMERIC(10,6),
    latencia_ms INTEGER,
    tools_chamadas TEXT[],
    handoff_acionado BOOLEAN DEFAULT FALSE,
    handoff_motivo TEXT,
    handoff_categoria TEXT,
    cliente_pediu_humano BOOLEAN DEFAULT FALSE,
    serena_admitiu_nao_saber BOOLEAN DEFAULT FALSE,
    conversa_resolvida BOOLEAN,
    enviou_link_tagme BOOLEAN DEFAULT FALSE,
    intencao_detectada TEXT,
    horario_conversa TIMESTAMPTZ DEFAULT NOW(),
    duracao_segundos INTEGER,
    num_mensagens INTEGER,
    prompt_versao_id INTEGER,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_conv      ON serena_metrics(conversation_id);
CREATE INDEX IF NOT EXISTS idx_metrics_categoria ON serena_metrics(handoff_categoria);
CREATE INDEX IF NOT EXISTS idx_metrics_horario   ON serena_metrics(horario_conversa DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_phone     ON serena_metrics(user_phone, horario_conversa DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_tools     ON serena_metrics USING GIN (tools_chamadas);


-- ── serena_prompt_versions ────────────────────────────────────
CREATE TABLE IF NOT EXISTS serena_prompt_versions (
    id SERIAL PRIMARY KEY,
    versao TEXT NOT NULL,
    prompt_completo TEXT NOT NULL,
    changelog TEXT,
    ativa BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    metricas_pos_deploy JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_uniq_active
    ON serena_prompt_versions(ativa) WHERE ativa = TRUE;


-- ── serena_weekly_reports ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS serena_weekly_reports (
    id SERIAL PRIMARY KEY,
    semana_inicio DATE NOT NULL,
    semana_fim DATE NOT NULL,
    total_conversas INTEGER,
    relatorio_json JSONB,
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (semana_inicio, semana_fim)
);

CREATE INDEX IF NOT EXISTS idx_weekly_periodo
    ON serena_weekly_reports(semana_inicio DESC);
