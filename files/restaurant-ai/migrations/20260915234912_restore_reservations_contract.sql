SET lock_timeout = '5s';
ALTER TABLE public.reservas RENAME COLUMN user_phone TO cliente_phone;
ALTER TABLE public.reservas RENAME COLUMN nome TO cliente_nome;
ALTER TABLE public.reservas RENAME COLUMN origem TO canal;
ALTER TABLE public.reservas
 ADD COLUMN evento_id uuid REFERENCES public.agenda_eventos(id),
 ADD COLUMN cliente_email text,
 ADD COLUMN hora_inicio time,
 ADD COLUMN pagamento_status text DEFAULT 'nao_requerido',
 ADD COLUMN pagamento_valor numeric(10,2),
 ADD COLUMN stripe_payment_intent_id text,
 ADD COLUMN stripe_checkout_session_id text,
 ADD COLUMN confirmado_whatsapp boolean DEFAULT false,
 ADD COLUMN confirmado_email boolean DEFAULT false;
ALTER TABLE public.reservas DROP CONSTRAINT reservas_origem_check;
ALTER TABLE public.reservas ADD CONSTRAINT reservas_canal_check CHECK (canal IN ('whatsapp','painel','api','widget'));
CREATE INDEX ON public.reservas(cliente_phone);
CREATE INDEX ON public.reservas(evento_id);
ALTER TABLE public.contacts ALTER COLUMN estagio_kanban SET DEFAULT 'Novo Lead';
ALTER TABLE public.contacts DROP CONSTRAINT contacts_estagio_kanban_check;
ALTER TABLE public.contacts ADD CONSTRAINT contacts_estagio_kanban_check CHECK (
 estagio_kanban IN ('captacao','qualificado','proposta','fechado','perdido',
 'Novo Lead','Qualificado','Proposta Enviada','Confirmado','Realizado','Recorrente','Inativo')
);
ALTER TABLE public.serena_weekly_reports ALTER COLUMN restaurant_id DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS serena_weekly_reports_periodo ON public.serena_weekly_reports(semana_inicio,semana_fim);
