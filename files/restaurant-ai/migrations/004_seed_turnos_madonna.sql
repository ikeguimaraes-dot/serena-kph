-- Migration: 004_seed_turnos_madonna
-- Seed dos turnos reais da Madonna Cucina na agenda própria
-- restaurant_id = 'madonna_cucina' (confirmado via SELECT em restaurants)
-- Criado em: 2026-05-28

-- Capacidade: 40 posições (10 mesas 1-2px, 2 mesas 3-5px, 2 mesas 6px, 10 balcão)
-- Fechado: domingo
-- Meia-noite representada como 23:59 (TIME não suporta 24:00)

DO $$
DECLARE
    rid TEXT := 'madonna_cucina';
BEGIN

-- Limpa turnos existentes para evitar duplicatas em re-run
DELETE FROM agenda_turnos WHERE restaurant_id = rid;

-- ── Segunda (1) ───────────────────────────────────────────────
INSERT INTO agenda_turnos (restaurant_id, dia_semana, nome, hora_inicio, hora_fim, capacidade_posicoes_min, capacidade_posicoes_max)
VALUES (rid, 1, 'Jantar', '19:00', '23:30', 1, 44);

-- ── Terça (2) ─────────────────────────────────────────────────
INSERT INTO agenda_turnos (restaurant_id, dia_semana, nome, hora_inicio, hora_fim, capacidade_posicoes_min, capacidade_posicoes_max)
VALUES (rid, 2, 'Jantar', '19:00', '23:30', 1, 44);

-- ── Quarta (3) ────────────────────────────────────────────────
INSERT INTO agenda_turnos (restaurant_id, dia_semana, nome, hora_inicio, hora_fim, capacidade_posicoes_min, capacidade_posicoes_max)
VALUES (rid, 3, 'Jantar', '19:00', '23:30', 1, 44);

-- ── Quinta (4) — fecha à meia-noite ───────────────────────────
INSERT INTO agenda_turnos (restaurant_id, dia_semana, nome, hora_inicio, hora_fim, capacidade_posicoes_min, capacidade_posicoes_max)
VALUES (rid, 4, 'Jantar', '19:00', '23:59', 1, 44);

-- ── Sexta (5) — fecha à meia-noite ───────────────────────────
INSERT INTO agenda_turnos (restaurant_id, dia_semana, nome, hora_inicio, hora_fim, capacidade_posicoes_min, capacidade_posicoes_max)
VALUES (rid, 5, 'Jantar', '19:00', '23:59', 1, 44);

-- ── Sábado (6) — dois turnos ──────────────────────────────────
INSERT INTO agenda_turnos (restaurant_id, dia_semana, nome, hora_inicio, hora_fim, capacidade_posicoes_min, capacidade_posicoes_max)
VALUES (rid, 6, 'Almoço', '12:00', '16:00', 1, 44);

INSERT INTO agenda_turnos (restaurant_id, dia_semana, nome, hora_inicio, hora_fim, capacidade_posicoes_min, capacidade_posicoes_max)
VALUES (rid, 6, 'Jantar', '19:00', '23:59', 1, 44);

-- ── Config da agenda ──────────────────────────────────────────
INSERT INTO agenda_config (
    restaurant_id,
    antecedencia_minima_horas,
    antecedencia_maxima_dias,
    cancelamento_minimo_horas,
    permite_same_day,
    requer_pagamento
) VALUES (rid, 2, 60, 24, false, false)
ON CONFLICT (restaurant_id) DO UPDATE SET
    antecedencia_minima_horas  = EXCLUDED.antecedencia_minima_horas,
    antecedencia_maxima_dias   = EXCLUDED.antecedencia_maxima_dias,
    cancelamento_minimo_horas  = EXCLUDED.cancelamento_minimo_horas,
    permite_same_day           = EXCLUDED.permite_same_day,
    requer_pagamento           = EXCLUDED.requer_pagamento;

RAISE NOTICE 'Seed Madonna concluído: 7 turnos inseridos para restaurant_id=%', rid;

END $$;

-- Verificação: deve retornar 7 linhas
-- SELECT dia_semana, nome, hora_inicio, hora_fim, capacidade_posicoes_max
-- FROM agenda_turnos WHERE restaurant_id = 'madonna_cucina'
-- ORDER BY dia_semana, hora_inicio;
