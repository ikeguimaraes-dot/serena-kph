-- Emergency schema compatibility with the deployed Serena backend.
-- Existing rows and recovered prompts are preserved.
SET lock_timeout = '5s';
ALTER TABLE public.serena_prompt_versions RENAME COLUMN prompt TO prompt_completo;
ALTER TABLE public.serena_prompt_versions ADD COLUMN metricas_pos_deploy jsonb;

ALTER TABLE public.restaurants
 ADD COLUMN nome_agente text,
 ADD COLUMN personalidade text,
 ADD COLUMN tom_voz text,
 ADD COLUMN idioma text DEFAULT 'pt-BR',
 ADD COLUMN telefone text,
 ADD COLUMN site text,
 ADD COLUMN horario_atendimento text,
 ADD COLUMN horario_funcionamento jsonb,
 ADD COLUMN donts text,
 ADD COLUMN tagme_venue_id text,
 ADD COLUMN team_whatsapp text;

ALTER TABLE public.agenda_eventos
 ADD COLUMN nome text,
 ADD COLUMN data date,
 ADD COLUMN preco_por_pessoa numeric(10,2),
 ADD COLUMN capacidade_total integer,
 ADD COLUMN hora_inicio time,
 ADD COLUMN hora_fim time,
 ADD COLUMN hora_evento time,
 ADD COLUMN dia_semana_label text,
 ADD COLUMN enquadramento text,
 ADD COLUMN adversario text,
 ADD COLUMN requer_pagamento boolean DEFAULT true,
 ADD COLUMN ativo boolean DEFAULT false,
 ALTER COLUMN titulo DROP NOT NULL,
 ALTER COLUMN data_hora DROP NOT NULL;
UPDATE public.agenda_eventos SET nome=titulo, data=(data_hora AT TIME ZONE 'America/Sao_Paulo')::date WHERE nome IS NULL;

CREATE TABLE public.experiencias (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 restaurant_id text NOT NULL REFERENCES public.restaurants(id),
 nome text NOT NULL, descricao text DEFAULT '', datas text DEFAULT '',
 valores text DEFAULT '', link text DEFAULT '', ativo boolean DEFAULT true,
 ordem integer DEFAULT 0, valor numeric(10,2), valor_consumo numeric(10,2),
 regra_consumo text, tipo_mesa text,
 criado_em timestamptz DEFAULT now(), atualizado_em timestamptz DEFAULT now()
);
CREATE TABLE public.evento_experiencias (
 evento_id uuid NOT NULL REFERENCES public.agenda_eventos(id) ON DELETE CASCADE,
 experiencia_id uuid NOT NULL REFERENCES public.experiencias(id) ON DELETE CASCADE,
 PRIMARY KEY (evento_id, experiencia_id)
);
CREATE TABLE public.restaurant_ambientes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 restaurant_id text NOT NULL REFERENCES public.restaurants(id),
 nome text NOT NULL, capacidade integer, num_mesas integer, pessoas_por_mesa integer,
 ativo boolean DEFAULT true, horario_proprio jsonb, imagem_url text, ordem integer DEFAULT 0,
 criado_em timestamptz DEFAULT now(), atualizado_em timestamptz DEFAULT now()
);
ALTER TABLE public.experiencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evento_experiencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.restaurant_ambientes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.experiencias, public.evento_experiencias, public.restaurant_ambientes FROM anon, authenticated;
CREATE INDEX ON public.experiencias(restaurant_id);
CREATE INDEX ON public.restaurant_ambientes(restaurant_id);
CREATE INDEX ON public.evento_experiencias(experiencia_id);

ALTER TABLE public.contacts
 ADD COLUMN sobrenome text, ADD COLUMN data_nascimento date,
 ADD COLUMN endereco text, ADD COLUMN tipo_aparelho text, ADD COLUMN canal_entrada text,
 ADD COLUMN ocasiao text[] DEFAULT '{}', ADD COLUMN restricoes_alimentares text[] DEFAULT '{}',
 ADD COLUMN ticket_medio numeric(10,2), ADD COLUMN tier text DEFAULT 'Bronze',
 ADD COLUMN opt_in_marketing boolean DEFAULT false;

ALTER TABLE public.serena_metrics
 ALTER COLUMN direction SET DEFAULT 'outbound',
 ADD COLUMN conversation_id integer,
 ADD COLUMN tokens_input integer, ADD COLUMN tokens_output integer,
 ADD COLUMN custo_usd numeric(10,6), ADD COLUMN latencia_ms integer,
 ADD COLUMN tools_chamadas text[], ADD COLUMN handoff_acionado boolean DEFAULT false,
 ADD COLUMN handoff_motivo text, ADD COLUMN handoff_categoria text,
 ADD COLUMN cliente_pediu_humano boolean DEFAULT false,
 ADD COLUMN serena_admitiu_nao_saber boolean DEFAULT false,
 ADD COLUMN conversa_resolvida boolean, ADD COLUMN enviou_link_tagme boolean DEFAULT false,
 ADD COLUMN intencao_detectada text, ADD COLUMN horario_conversa timestamptz DEFAULT now(),
 ADD COLUMN duracao_segundos integer, ADD COLUMN num_mensagens integer,
 ADD COLUMN prompt_versao_id integer, ADD COLUMN criado_em timestamptz DEFAULT now();

ALTER TABLE public.serena_weekly_reports
 ADD COLUMN total_conversas integer, ADD COLUMN relatorio_json jsonb,
 ADD COLUMN criado_em timestamptz DEFAULT now();
