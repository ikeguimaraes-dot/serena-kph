-- Supabase CLI scaffold. Additive, disabled by default, no messages/backfill.
-- Depends on consented_outreach_outbox and crm_loss_reason_history migrations.
SET lock_timeout = '5s';
ALTER TABLE public.outreach_rules
  ADD COLUMN IF NOT EXISTS template_variables jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS reminder_hours_before integer NOT NULL DEFAULT 24,
  ADD COLUMN IF NOT EXISTS reminder_window_minutes integer NOT NULL DEFAULT 240;
ALTER TABLE public.outreach_rules DROP CONSTRAINT IF EXISTS outreach_rules_stage_check;
ALTER TABLE public.outreach_rules ADD CONSTRAINT outreach_rules_stage_check
  CHECK (stage IN ('nurture_d3','d1','d3','d7','d30','reservation_confirmation','reservation_reminder'));
ALTER TABLE public.outreach_rules DROP CONSTRAINT IF EXISTS outreach_rules_reservation_window_check;
ALTER TABLE public.outreach_rules ADD CONSTRAINT outreach_rules_reservation_window_check
  CHECK (reminder_hours_before BETWEEN 1 AND 168 AND reminder_window_minutes BETWEEN 15 AND 1440
    AND reminder_window_minutes < reminder_hours_before*60 AND jsonb_typeof(template_variables)='object');
ALTER TABLE public.outreach_outbox DROP CONSTRAINT IF EXISTS outreach_outbox_stage_check;
ALTER TABLE public.outreach_outbox ADD CONSTRAINT outreach_outbox_stage_check
  CHECK (stage IN ('nurture_d3','d1','d3','d7','d30','reservation_confirmation','reservation_reminder'));
ALTER TABLE public.outreach_outbox DROP CONSTRAINT IF EXISTS outreach_outbox_object_type_check;
ALTER TABLE public.outreach_outbox ADD CONSTRAINT outreach_outbox_object_type_check
  CHECK (object_type IN ('conversation','ordem_servico','reservation'));
COMMENT ON COLUMN public.outreach_rules.template_variables IS
  'Explicit per-tenant template variable map to nome/data/hora/unidade. Required and verified live before reservation sends.';
COMMENT ON COLUMN public.outreach_rules.reminder_window_minutes IS
  'Default reminder window is 20-24 hours before date+time interpreted in America/Sao_Paulo; periodic poll every 15 minutes. No late replay.';
COMMENT ON TABLE public.outreach_outbox IS
  'One attempt per tenant/object/stage, including reservation reschedules. Provider SID is acceptance, never delivery proof.';
