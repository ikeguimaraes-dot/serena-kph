-- Additive instrumentation. Created with `supabase migration new`.
-- Apply before enabling the new webhook/report code. No historical attribution.
SET lock_timeout = '5s';

ALTER TABLE public.conversations
  ADD COLUMN IF NOT EXISTS source_message_sid text,
  ADD COLUMN IF NOT EXISTS ctwa_clid text;
CREATE UNIQUE INDEX IF NOT EXISTS conversations_inbound_source_sid_unique
  ON public.conversations (restaurant_id, source_message_sid)
  WHERE role = 'user' AND source_message_sid IS NOT NULL;
CREATE INDEX IF NOT EXISTS conversations_ctwa_lookup
  ON public.conversations (restaurant_id, user_phone, created_at DESC, id DESC)
  WHERE role = 'user' AND ctwa_clid IS NOT NULL;

ALTER TABLE public.reservas
  ADD COLUMN IF NOT EXISTS ctwa_clid text,
  ADD COLUMN IF NOT EXISTS ctwa_source_message_sid text,
  ADD COLUMN IF NOT EXISTS ctwa_source_created_at timestamptz,
  ADD COLUMN IF NOT EXISTS ctwa_attribution_rule text;

-- Audited restore has 'concluida', whereas the application already writes
-- 'realizada'. Widen the existing constraint; preserve all historical values.
ALTER TABLE public.reservas DROP CONSTRAINT IF EXISTS reservas_status_check;
ALTER TABLE public.reservas ADD CONSTRAINT reservas_status_check
  CHECK (status IN ('pendente','confirmada','cancelada','concluida','realizada','no_show'));

-- Attribution: latest non-empty inbound referral from the SAME tenant and phone,
-- received during the 7 days before reservation creation. Snapshot at INSERT only.
-- Trigger also covers reservations created by the panel/widget, not just agent tools.
CREATE OR REPLACE FUNCTION public.attribute_reserva_ctwa()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
DECLARE
  referral record;
  reservation_time timestamptz := COALESCE(NEW.criado_em, CURRENT_TIMESTAMP);
BEGIN
  IF NEW.ctwa_clid IS NULL THEN
    SELECT c.ctwa_clid, c.source_message_sid, c.created_at INTO referral
    FROM public.conversations c
    WHERE c.restaurant_id = NEW.restaurant_id
      AND c.user_phone = NEW.cliente_phone
      AND c.role = 'user'
      AND NULLIF(btrim(c.ctwa_clid), '') IS NOT NULL
      AND c.created_at <= reservation_time
      AND c.created_at >= reservation_time - INTERVAL '7 days'
    ORDER BY c.created_at DESC, c.id DESC LIMIT 1;
    IF FOUND THEN
      NEW.ctwa_clid := referral.ctwa_clid;
      NEW.ctwa_source_message_sid := referral.source_message_sid;
      NEW.ctwa_source_created_at := referral.created_at;
      NEW.ctwa_attribution_rule := 'last_nonempty_referral_same_tenant_phone_7d_v1';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.attribute_reserva_ctwa() FROM PUBLIC;
DROP TRIGGER IF EXISTS reservas_attribute_ctwa ON public.reservas;
CREATE TRIGGER reservas_attribute_ctwa
  BEFORE INSERT ON public.reservas
  FOR EACH ROW EXECUTE FUNCTION public.attribute_reserva_ctwa();

ALTER TABLE public.serena_metrics
  ADD COLUMN IF NOT EXISTS source_message_sid text,
  ADD COLUMN IF NOT EXISTS modelo_observado text,
  ADD COLUMN IF NOT EXISTS usage_json jsonb,
  ADD COLUMN IF NOT EXISTS tokens_cache_creation bigint,
  ADD COLUMN IF NOT EXISTS tokens_cache_read bigint,
  ADD COLUMN IF NOT EXISTS tokens_cache_write_5m bigint,
  ADD COLUMN IF NOT EXISTS tokens_cache_write_1h bigint,
  ADD COLUMN IF NOT EXISTS custo_input_usd numeric(18,10),
  ADD COLUMN IF NOT EXISTS custo_output_usd numeric(18,10),
  ADD COLUMN IF NOT EXISTS custo_cache_write_5m_usd numeric(18,10),
  ADD COLUMN IF NOT EXISTS custo_cache_write_1h_usd numeric(18,10),
  ADD COLUMN IF NOT EXISTS custo_cache_read_usd numeric(18,10),
  ADD COLUMN IF NOT EXISTS custo_total_usd numeric(18,10),
  ADD COLUMN IF NOT EXISTS tarifa_versao text,
  ADD COLUMN IF NOT EXISTS custo_status text;
COMMENT ON COLUMN public.serena_metrics.custo_usd IS
  'Historical legacy input/output-only estimate. Never backfilled by CTWA/cache instrumentation.';
COMMENT ON COLUMN public.serena_metrics.custo_total_usd IS
  'Observed main-agent call usage priced with recorded first-party rate version, including cache. NULL when usage/model is incomplete; not an invoice.';
COMMENT ON COLUMN public.reservas.ctwa_clid IS
  'Referral snapshot at creation, same tenant/phone, last non-empty click within 7d; no historical backfill.';
