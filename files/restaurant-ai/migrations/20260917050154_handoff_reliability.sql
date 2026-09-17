-- Created with Supabase CLI. No backfill, deletions, new destinations or sends.
SET lock_timeout='5s';
ALTER TABLE public.handoff_sessions
  ADD COLUMN IF NOT EXISTS assumed_at timestamptz,
  ADD COLUMN IF NOT EXISTS first_human_response_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_reply_message_sid text,
  ADD COLUMN IF NOT EXISTS notification_status jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS handoff_open_contact
  ON public.handoff_sessions(restaurant_id,user_phone,id DESC)
  WHERE status IN ('aguardando','em_atendimento');
ALTER TABLE public.conversations ADD COLUMN IF NOT EXISTS provider_message_sid text;
CREATE UNIQUE INDEX IF NOT EXISTS conversations_provider_message_sid_unique
  ON public.conversations(restaurant_id,provider_message_sid)
  WHERE provider_message_sid IS NOT NULL;
COMMENT ON COLUMN public.handoff_sessions.first_human_response_at IS
  'First human reply accepted with a provider SID and persisted. Does not certify delivery. No historical backfill.';
COMMENT ON COLUMN public.handoff_sessions.notification_status IS
  'Per-channel observed acceptance, unconfirmed or skipped. Pending after interruption requires manual reconciliation; never certifies delivery.';
