-- Hotfix 6 — Multi-tenant proof: insere segunda casa fictícia (Meet & Eat).
-- Idempotente. Depois disso o seletor de unidade no painel mostra 2 entradas.
--
-- Pra cadastrar uma 3ª casa de verdade (Meet & Eat real ou outra bandeira):
--   1) Repete este pattern (INSERT em restaurants + business_hours)
--   2) Configura o número WhatsApp do Twilio (TWILIO_FROM_NUMBER aponta pra ele
--      OU adiciona como sender adicional no console Twilio)
--   3) Restaurant.whatsapp_number deve bater com o sender — get_restaurant_by_whatsapp
--      é o lookup que o webhook usa pra rotear mensagem → restaurant.

INSERT INTO restaurants (id, nome, whatsapp_number, endereco, descricao, ativo)
VALUES (
    'meet_and_eat',
    'Meet & Eat',
    '+5511000000000',
    'São Paulo, SP',
    'Segunda casa KPH — slot reservado para multi-tenant proof.',
    true
)
ON CONFLICT (id) DO NOTHING;

-- Business hours — espelha Madonna (segunda a sábado abre, domingo fecha).
INSERT INTO business_hours (restaurant_id, dia, horario, fechado) VALUES
  ('meet_and_eat', 'Segunda', '19h as 23h',              false),
  ('meet_and_eat', 'Terca',   '19h as 23h',              false),
  ('meet_and_eat', 'Quarta',  '19h as 23h',              false),
  ('meet_and_eat', 'Quinta',  '19h as 23h',              false),
  ('meet_and_eat', 'Sexta',   '19h as 00h',              false),
  ('meet_and_eat', 'Sabado',  '12h as 16h e 19h as 00h', false),
  ('meet_and_eat', 'Domingo', 'Fechado',                 true)
ON CONFLICT DO NOTHING;
