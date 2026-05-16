-- ============================================================
-- Sprint 1 CRM — fix trigger + view contacts_enriched
-- Apenas migrações aditivas: nenhuma tabela existente é alterada.
-- ============================================================

-- 1. Coluna aditiva: total_handoffs (não existia)
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS total_handoffs INT DEFAULT 0;

-- 2. Corrige upsert_contact_on_message — a versão anterior referenciava
--    colunas inexistentes (phone, restaurant_id, total_conversations).
--    Schema real usa: celular, frequencia_visitas, ultima_visita.
CREATE OR REPLACE FUNCTION upsert_contact_on_message()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO contacts (celular, frequencia_visitas, ultima_visita)
    VALUES (NEW.user_phone, 1, NOW()::date)
    ON CONFLICT (celular)
    DO UPDATE SET
        frequencia_visitas = contacts.frequencia_visitas + 1,
        ultima_visita      = GREATEST(COALESCE(contacts.ultima_visita, NOW()::date), NOW()::date);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Garante que o trigger existe e aponta para a função corrigida
DROP TRIGGER IF EXISTS trigger_upsert_contact ON conversations;
CREATE TRIGGER trigger_upsert_contact
AFTER INSERT ON conversations
FOR EACH ROW
WHEN (NEW.role = 'user')
EXECUTE FUNCTION upsert_contact_on_message();

-- 4. View enriquecida com dados de conversas e handoffs
CREATE OR REPLACE VIEW contacts_enriched AS
SELECT
    c.*,
    MAX(conv.created_at)    AS last_message_at,
    COUNT(DISTINCT h.id)    AS handoff_count,
    CASE
        WHEN c.frequencia_visitas >= 3 THEN 'recorrente'
        ELSE NULL
    END AS frequency_tag
FROM contacts c
LEFT JOIN conversations conv  ON conv.user_phone  = c.celular
LEFT JOIN handoff_sessions h  ON h.user_phone     = c.celular
GROUP BY c.id;
