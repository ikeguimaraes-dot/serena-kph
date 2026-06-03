-- ═══════════════════════════════════════════════════════════════
-- Migration 010 — Checklists D-7 e D-0
-- Executa no Supabase SQL Editor (uma vez).
-- ═══════════════════════════════════════════════════════════════

-- Tabela de templates (itens padrão por tipo)
CREATE TABLE IF NOT EXISTS checklist_templates (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo      VARCHAR(10)  NOT NULL,           -- 'd7' | 'd0'
    ordem     INT          NOT NULL DEFAULT 0,
    item      TEXT         NOT NULL,
    ativo     BOOL         NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Tabela de instâncias (checklist vinculado a uma OS)
CREATE TABLE IF NOT EXISTS checklist_instancias (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    os_id         UUID         NOT NULL REFERENCES ordens_servico(id) ON DELETE CASCADE,
    tipo          VARCHAR(10)  NOT NULL,       -- 'd7' | 'd0'
    ordem         INT          NOT NULL DEFAULT 0,
    item          TEXT         NOT NULL,
    concluido     BOOL         NOT NULL DEFAULT FALSE,
    concluido_em  TIMESTAMPTZ,
    concluido_por TEXT,
    criado_em     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checklist_os_tipo
    ON checklist_instancias(os_id, tipo);

-- ── Templates D-7 ──────────────────────────────────────────────
INSERT INTO checklist_templates (tipo, ordem, item) VALUES
    ('d7', 1, 'Confirmar número de convidados com o cliente'),
    ('d7', 2, 'Confirmar cardápio definitivo'),
    ('d7', 3, 'Verificar restrições alimentares dos convidados'),
    ('d7', 4, 'Confirmar decoração e fornecedores externos'),
    ('d7', 5, 'Briefing com cozinha sobre o evento'),
    ('d7', 6, 'Confirmar músico / DJ / entretenimento'),
    ('d7', 7, 'Checar reserva de mesa e layout do salão'),
    ('d7', 8, 'Enviar confirmação final ao cliente');

-- ── Templates D-0 ──────────────────────────────────────────────
INSERT INTO checklist_templates (tipo, ordem, item) VALUES
    ('d0', 1, 'Mise en place completo'),
    ('d0', 2, 'Equipe briefada sobre o evento'),
    ('d0', 3, 'Mesa montada e decoração no lugar'),
    ('d0', 4, 'Flores e ornamentação conferidos'),
    ('d0', 5, 'Música configurada e testada'),
    ('d0', 6, 'Protocolo de boas-vindas ao cliente confirmado'),
    ('d0', 7, 'Cozinha alinhada com horário de entrada do grupo'),
    ('d0', 8, 'Responsável pelo evento presente no local');
