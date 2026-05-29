-- Migration 007: Kanban — novos estágios do funil comercial
-- Sprint 2 — migra valores antigos para o novo esquema lowercase

-- 1. Migra dados existentes para novos valores
UPDATE contacts SET estagio_kanban = 'captacao'    WHERE estagio_kanban IN ('Novo Lead', 'novo');
UPDATE contacts SET estagio_kanban = 'qualificado' WHERE estagio_kanban IN ('Qualificado', 'Confirmado', 'ativo');
UPDATE contacts SET estagio_kanban = 'proposta'    WHERE estagio_kanban = 'Proposta Enviada';
UPDATE contacts SET estagio_kanban = 'fechado'     WHERE estagio_kanban IN ('Realizado', 'Recorrente');
UPDATE contacts SET estagio_kanban = 'perdido'     WHERE estagio_kanban IN ('Inativo', 'inativo');

-- 2. Atualiza default da coluna
ALTER TABLE contacts ALTER COLUMN estagio_kanban SET DEFAULT 'captacao';

-- 3. Remove constraint antiga (se existir) e adiciona nova
ALTER TABLE contacts DROP CONSTRAINT IF EXISTS contacts_estagio_kanban_check;
ALTER TABLE contacts ADD CONSTRAINT contacts_estagio_kanban_check
  CHECK (estagio_kanban IN ('captacao','qualificado','proposta','fechado','perdido'));
