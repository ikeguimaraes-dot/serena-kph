-- Migration: 003_agenda_propria
-- Agenda própria da Serena (independente do Tagme)
-- Criado em: 2026-05-26

-- Configuração da agenda por restaurante
CREATE TABLE IF NOT EXISTS agenda_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
    antecedencia_minima_horas INT DEFAULT 2,
    antecedencia_maxima_dias INT DEFAULT 60,
    cancelamento_minimo_horas INT DEFAULT 24,
    permite_same_day BOOLEAN DEFAULT false,
    requer_pagamento BOOLEAN DEFAULT false,
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(restaurant_id)
);

-- Turnos por dia da semana
CREATE TABLE IF NOT EXISTS agenda_turnos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
    dia_semana INT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6), -- 0=dom, 6=sab
    nome TEXT NOT NULL, -- "Almoço", "Jantar"
    hora_inicio TIME NOT NULL,
    hora_fim TIME NOT NULL,
    capacidade_posicoes_min INT DEFAULT 1,
    capacidade_posicoes_max INT NOT NULL,
    ativo BOOLEAN DEFAULT true,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Bloqueios de horário (feriados, manutenção, eventos privados)
CREATE TABLE IF NOT EXISTS agenda_bloqueios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
    data_inicio TIMESTAMPTZ NOT NULL,
    data_fim TIMESTAMPTZ NOT NULL,
    motivo TEXT,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Eventos especiais com configuração própria
CREATE TABLE IF NOT EXISTS agenda_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
    nome TEXT NOT NULL, -- "Dia dos Namorados 2026"
    data DATE NOT NULL,
    descricao TEXT,
    preco_por_pessoa NUMERIC(10,2),
    capacidade_total INT,
    hora_inicio TIME,
    hora_fim TIME,
    requer_pagamento BOOLEAN DEFAULT true,
    ativo BOOLEAN DEFAULT true,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Reservas
CREATE TABLE IF NOT EXISTS reservas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
    turno_id UUID REFERENCES agenda_turnos(id),
    evento_id UUID REFERENCES agenda_eventos(id),
    cliente_phone TEXT NOT NULL,
    cliente_nome TEXT NOT NULL,
    cliente_email TEXT,
    data DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    posicoes INT NOT NULL CHECK (posicoes > 0),
    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente','confirmada','cancelada','no_show')),
    canal TEXT DEFAULT 'whatsapp'
        CHECK (canal IN ('whatsapp','widget','painel')),
    observacoes TEXT,
    -- Pagamento
    pagamento_status TEXT DEFAULT 'nao_requerido'
        CHECK (pagamento_status IN ('nao_requerido','pendente','pago','reembolsado')),
    pagamento_valor NUMERIC(10,2),
    stripe_payment_intent_id TEXT,
    stripe_checkout_session_id TEXT,
    -- Confirmações
    confirmado_whatsapp BOOLEAN DEFAULT false,
    confirmado_email BOOLEAN DEFAULT false,
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_reservas_restaurant_data
    ON reservas(restaurant_id, data);
CREATE INDEX IF NOT EXISTS idx_reservas_cliente_phone
    ON reservas(cliente_phone);
CREATE INDEX IF NOT EXISTS idx_reservas_status
    ON reservas(status);
CREATE INDEX IF NOT EXISTS idx_turnos_restaurant_dia
    ON agenda_turnos(restaurant_id, dia_semana);

-- Trigger: atualiza atualizado_em nas reservas
CREATE OR REPLACE FUNCTION update_reservas_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_reservas_timestamp ON reservas;
CREATE TRIGGER trigger_reservas_timestamp
BEFORE UPDATE ON reservas
FOR EACH ROW EXECUTE FUNCTION update_reservas_timestamp();

-- Função: verifica disponibilidade para um turno em uma data
CREATE OR REPLACE FUNCTION verificar_disponibilidade(
    p_restaurant_id TEXT,
    p_data DATE,
    p_turno_id UUID,
    p_posicoes INT
) RETURNS JSONB AS $$
DECLARE
    v_turno agenda_turnos%ROWTYPE;
    v_posicoes_ocupadas INT;
    v_posicoes_disponiveis INT;
    v_bloqueio_existe BOOLEAN;
BEGIN
    -- Busca turno
    SELECT * INTO v_turno FROM agenda_turnos
    WHERE id = p_turno_id AND restaurant_id = p_restaurant_id AND ativo = true;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('disponivel', false, 'motivo', 'Turno não encontrado');
    END IF;

    -- Verifica bloqueio
    SELECT EXISTS(
        SELECT 1 FROM agenda_bloqueios
        WHERE restaurant_id = p_restaurant_id
        AND data_inicio::DATE <= p_data
        AND data_fim::DATE >= p_data
    ) INTO v_bloqueio_existe;

    IF v_bloqueio_existe THEN
        RETURN jsonb_build_object('disponivel', false, 'motivo', 'Data bloqueada');
    END IF;

    -- Conta posições ocupadas
    SELECT COALESCE(SUM(posicoes), 0) INTO v_posicoes_ocupadas
    FROM reservas
    WHERE restaurant_id = p_restaurant_id
    AND turno_id = p_turno_id
    AND data = p_data
    AND status IN ('pendente', 'confirmada');

    v_posicoes_disponiveis := v_turno.capacidade_posicoes_max - v_posicoes_ocupadas;

    IF v_posicoes_disponiveis < p_posicoes THEN
        RETURN jsonb_build_object(
            'disponivel', false,
            'motivo', 'Capacidade insuficiente',
            'posicoes_disponiveis', v_posicoes_disponiveis
        );
    END IF;

    RETURN jsonb_build_object(
        'disponivel', true,
        'posicoes_disponiveis', v_posicoes_disponiveis,
        'hora_inicio', v_turno.hora_inicio,
        'hora_fim', v_turno.hora_fim
    );
END;
$$ LANGUAGE plpgsql;
