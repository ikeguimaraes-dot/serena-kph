SET lock_timeout = '5s';
DO $$
DECLARE definition text;
BEGIN
 SELECT pg_get_functiondef('public.contacts_sync_from_reservation()'::regprocedure) INTO definition;
 definition := replace(replace(definition, 'NEW.user_phone', 'NEW.cliente_phone'), 'NEW.nome', 'NEW.cliente_nome');
 EXECUTE definition;
END $$;

-- The backend connects as postgres; the browser only reads its own operator
-- profile and authorized learning records directly. Other data goes through FastAPI.
DO $$
DECLARE relation record;
BEGIN
 FOR relation IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', relation.tablename);
  IF relation.tablename NOT IN ('operadores','orkestri_learning') THEN
   EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', relation.tablename);
  END IF;
 END LOOP;
END $$;
REVOKE ALL ON public.operadores, public.orkestri_learning FROM anon, authenticated;
GRANT SELECT ON public.operadores, public.orkestri_learning TO authenticated;
CREATE POLICY learning_operator_read ON public.orkestri_learning FOR SELECT TO authenticated
 USING (EXISTS (SELECT 1 FROM public.operadores op
 WHERE op.id=(SELECT auth.uid())
 AND (op.role='admin' OR op.restaurante_id=orkestri_learning.restaurant_id)));
ALTER VIEW public.vw_os_regua SET (security_invoker=true);
REVOKE ALL ON public.vw_os_regua FROM anon, authenticated;

ALTER FUNCTION public.fn_reservas_touch() SET search_path=public,pg_temp;
ALTER FUNCTION public.contacts_touch() SET search_path=public,pg_temp;
ALTER FUNCTION public.contacts_sync_from_reservation() SET search_path=public,pg_temp;
ALTER FUNCTION public.contacts_calc_tier(integer) SET search_path=public,pg_temp;
ALTER FUNCTION public.verificar_disponibilidade(text,date,uuid,integer) SET search_path=public,pg_temp;
-- Internal functions are not public REST endpoints.
DO $$
DECLARE fn record;
BEGIN
 FOR fn IN SELECT oid::regprocedure AS signature FROM pg_proc
 WHERE pronamespace='public'::regnamespace AND proname IN
 ('fn_reservas_touch','contacts_touch','contacts_sync_from_reservation',
 'contacts_calc_tier','contacts_mark_inactive','verificar_disponibilidade') LOOP
  EXECUTE format('ALTER FUNCTION %s SET search_path=public,pg_temp', fn.signature);
  EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC,anon,authenticated', fn.signature);
 END LOOP;
END $$;
