-- Migration: 005_turnos_v2_madonna
-- Substitui 7 turnos por 17 turnos com janelas de 1h30–2h
-- Tempo médio de permanência: 1h30. Turnos sobrepostos não existem.
-- Criado em: 2026-05-28

-- Remove turnos anteriores (tabela reservas ainda zerada)
DELETE FROM agenda_turnos WHERE restaurant_id = 'madonna_cucina';

-- Segunda (1) e Terça (2) e Quarta (3) — 2 turnos
INSERT INTO agenda_turnos (restaurant_id, dia_semana, nome, hora_inicio, hora_fim, capacidade_posicoes_min, capacidade_posicoes_max) VALUES
  ('madonna_cucina', 1, 'Jantar 1', '19:00', '20:30', 1, 44),
  ('madonna_cucina', 1, 'Jantar 2', '21:00', '22:30', 1, 44),
  ('madonna_cucina', 2, 'Jantar 1', '19:00', '20:30', 1, 44),
  ('madonna_cucina', 2, 'Jantar 2', '21:00', '22:30', 1, 44),
  ('madonna_cucina', 3, 'Jantar 1', '19:00', '20:30', 1, 44),
  ('madonna_cucina', 3, 'Jantar 2', '21:00', '22:30', 1, 44),
-- Quinta (4) e Sexta (5) — 3 turnos
  ('madonna_cucina', 4, 'Jantar 1', '19:00', '20:30', 1, 44),
  ('madonna_cucina', 4, 'Jantar 2', '21:00', '22:30', 1, 44),
  ('madonna_cucina', 4, 'Jantar 3', '22:30', '00:00', 1, 44),
  ('madonna_cucina', 5, 'Jantar 1', '19:00', '20:30', 1, 44),
  ('madonna_cucina', 5, 'Jantar 2', '21:00', '22:30', 1, 44),
  ('madonna_cucina', 5, 'Jantar 3', '22:30', '00:00', 1, 44),
-- Sábado (6) — almoço 2 turnos + jantar 3 turnos
  ('madonna_cucina', 6, 'Almoço 1', '12:00', '13:30', 1, 44),
  ('madonna_cucina', 6, 'Almoço 2', '14:00', '16:00', 1, 44),
  ('madonna_cucina', 6, 'Jantar 1', '19:00', '20:30', 1, 44),
  ('madonna_cucina', 6, 'Jantar 2', '21:00', '22:30', 1, 44),
  ('madonna_cucina', 6, 'Jantar 3', '22:30', '00:00', 1, 44);

-- Verificação: deve retornar 17 linhas
-- SELECT dia_semana, nome, hora_inicio, hora_fim FROM agenda_turnos
-- WHERE restaurant_id = 'madonna_cucina' ORDER BY dia_semana, hora_inicio;
