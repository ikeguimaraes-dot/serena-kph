-- Backend-only idempotency; no customer records exposed through the Data API.
CREATE TABLE IF NOT EXISTS public.public_reservation_requests (
    restaurant_id text NOT NULL REFERENCES public.restaurants(id),
    idempotency_key uuid NOT NULL,
    request_hash text NOT NULL,
    reservation_id uuid NOT NULL REFERENCES public.reservas(id),
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_id,idempotency_key)
);
ALTER TABLE public.public_reservation_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.public_reservation_requests FROM PUBLIC, anon, authenticated;
CREATE TABLE IF NOT EXISTS public.public_reservation_rate_limits (
    key_hash text NOT NULL,
    bucket timestamptz NOT NULL,
    attempts integer NOT NULL,
    PRIMARY KEY (key_hash,bucket)
);
ALTER TABLE public.public_reservation_rate_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.public_reservation_rate_limits FROM PUBLIC, anon, authenticated;
-- Backend uses its existing Postgres connection, never an anonymous API key.
-- Rate buckets older than 24h may be deleted by operational maintenance.
