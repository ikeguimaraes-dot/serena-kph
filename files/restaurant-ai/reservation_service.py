"""One authoritative booking path for the panel, agent and public page.

No outbound communications. Read availability is indicative; INSERT always locks
and repeats the checks on the same connection/transaction (READ COMMITTED).
"""
from datetime import date, datetime, timedelta
import hashlib
import json
import re
from uuid import UUID
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from reservation_links import OFFICIAL_RESERVATION_URLS

TZ = ZoneInfo('America/Sao_Paulo')


class BookingError(ValueError):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def booking_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise BookingError('invalid_date', 'Informe uma data válida no formato AAAA-MM-DD.')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise BookingError('invalid_date', 'Informe uma data válida.')


def party_size(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000:
        raise BookingError('invalid_people', 'Informe uma quantidade válida de pessoas.')
    return value


def valid_tenant(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise BookingError('invalid_restaurant', 'Unidade inválida.')
    return value


def valid_uuid(value, field='slot'):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise BookingError(f'invalid_{field}', 'Selecione um horário válido.' if field == 'slot' else 'Identificador do pedido inválido.')


def normalize_phone(value):
    if not isinstance(value, str) or len(value) > 40:
        raise BookingError('invalid_phone', 'Informe um telefone válido com DDD.')
    raw = value.removeprefix('whatsapp:').strip()
    if re.search(r'[^\d+\s().-]', raw) or ('+' in raw and not raw.startswith('+')) or raw.count('+') > 1:
        raise BookingError('invalid_phone', 'Informe um telefone válido com DDD.')
    digits = re.sub(r'\D', '', raw)
    if not raw.startswith('+') and len(digits) in (10, 11):
        digits = '55' + digits
    if not 10 <= len(digits) <= 15 or digits.startswith('0') or len(set(digits)) < 3:
        raise BookingError('invalid_phone', 'Informe um telefone válido com DDD e código do país.')
    return '+' + digits


def safe_url(value):
    if not value:
        return None
    candidate = str(value).strip()
    if not candidate.startswith(('http://', 'https://')):
        candidate = 'https://' + candidate
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    return candidate if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password else None


async def restaurant_and_config(c, rid):
    rid = valid_tenant(rid)
    restaurant = await c.fetchrow('SELECT * FROM restaurants WHERE id=$1 AND ativo=true', rid)
    if not restaurant:
        raise BookingError('not_found', 'Unidade não encontrada.', 404)
    config = await c.fetchrow('SELECT * FROM agenda_config WHERE restaurant_id=$1', rid)
    return dict(restaurant), dict(config) if config else None


def check_date_config(restaurant, config, day, people, now):
    if day < now.date():
        raise BookingError('past_date', 'Escolha uma data a partir de hoje.')
    if not config:
        raise BookingError('unconfigured', 'A agenda online ainda não está configurada. Confirme com a equipe.', 503)
    if config.get('requer_pagamento'):
        raise BookingError('unconfigured', 'Esta reserva precisa de atendimento da equipe.', 503)
    if not config.get('permite_same_day') and day == now.date():
        raise BookingError('same_day', 'Para reservas hoje, confirme diretamente com a equipe.', 409)
    horizon = config.get('antecedencia_maxima_dias')
    minimum = config.get('antecedencia_minima_horas')
    if horizon is None or minimum is None or horizon < 0 or minimum < 0:
        raise BookingError('unconfigured', 'As regras da agenda precisam ser confirmadas com a equipe.', 503)
    if day > now.date() + timedelta(days=horizon):
        raise BookingError('outside_window', 'A data está fora do período de reservas online.', 409)
    maximum = restaurant.get('capacidade_maxima_reserva')
    if maximum and people > maximum:
        raise BookingError('group_request', 'Para este tamanho de grupo, confirme com a equipe.', 409)


async def check_slot(c, rid, day, slot_id, people, now=None):
    """Private result may contain capacity; public router returns only booleans."""
    day, people, slot_id = booking_date(day), party_size(people), valid_uuid(slot_id)
    now = now or datetime.now(TZ)
    restaurant, config = await restaurant_and_config(c, rid)
    check_date_config(restaurant, config, day, people, now)
    slot = await c.fetchrow('SELECT * FROM agenda_turnos WHERE id=$1 AND restaurant_id=$2 AND ativo=true', slot_id, rid)
    if not slot:
        raise BookingError('invalid_slot', 'Este horário não pertence à agenda desta unidade.', 422)
    if slot['dia_semana'] != (day.weekday() + 1) % 7:
        raise BookingError('invalid_slot_day', 'Este horário não está configurado para a data escolhida.', 422)
    start = datetime.combine(day, slot['hora_inicio'], TZ)
    end = datetime.combine(day, slot['hora_fim'], TZ)
    if end <= start:
        end += timedelta(days=1)
    if start < now + timedelta(hours=config['antecedencia_minima_horas']):
        raise BookingError('lead_time', 'Este horário não atende à antecedência mínima. Confirme com a equipe.', 409)
    if people < slot['capacidade_posicoes_min']:
        raise BookingError('party_minimum', 'Para esta quantidade de pessoas, confirme com a equipe.', 409)
    if slot['capacidade_posicoes_max'] <= 0:
        raise BookingError('unconfigured', 'A capacidade deste horário precisa ser confirmada com a equipe.', 503)
    blocked = await c.fetchval('''SELECT EXISTS(SELECT 1 FROM agenda_bloqueios
        WHERE restaurant_id=$1 AND data_inicio < $3 AND data_fim > $2)''', rid, start, end)
    if blocked:
        raise BookingError('blocked', 'Este horário está bloqueado para reservas online.', 409)
    special = await c.fetchval('''SELECT EXISTS(SELECT 1 FROM agenda_eventos
        WHERE restaurant_id=$1 AND ativo=true
        AND (tipo='evento_especial' OR (reserva_id IS NULL AND nome IS NOT NULL))
        AND COALESCE(data, (data_hora AT TIME ZONE 'America/Sao_Paulo')::date)=$2)''', rid, day)
    if special:
        raise BookingError('unconfigured', 'Esta data tem uma programação especial. Confirme a reserva com a equipe.', 503)
    occupied = await c.fetchval('''SELECT COALESCE(SUM(posicoes),0) FROM reservas
        WHERE restaurant_id=$1 AND turno_id=$2 AND data=$3 AND status IN ('pendente','confirmada')''', rid, slot_id, day)
    remaining = slot['capacidade_posicoes_max'] - occupied
    if remaining < people:
        raise BookingError('capacity', 'Não há lugares suficientes neste horário. Escolha outro horário ou fale com a equipe.', 409)
    return {'slot': dict(slot), 'remaining': remaining}


async def availability(c, rid, day, people, now=None):
    day, people = booking_date(day), party_size(people)
    restaurant, config = await restaurant_and_config(c, rid)
    now = now or datetime.now(TZ)
    fallback = {'url': OFFICIAL_RESERVATION_URLS.get(rid) or safe_url(restaurant.get('site')), 'phone': restaurant.get('telefone') or restaurant.get('whatsapp_number'),
                'message': 'Confirme a disponibilidade diretamente com a equipe.'}
    output = {'restaurant': {'id': rid, 'name': restaurant['nome'], 'description': restaurant.get('descricao'),
                             'address': restaurant.get('endereco'), 'website': safe_url(restaurant.get('site')),
                             'phone': fallback['phone']},
              'date': day.isoformat(), 'people': people, 'state': 'unconfigured', 'slots': [], 'fallback': fallback}
    try:
        check_date_config(restaurant, config, day, people, now)
    except BookingError as exc:
        if exc.status == 422:
            raise
        output['state'] = 'unconfigured' if exc.code == 'unconfigured' else 'unavailable'
        output['message'] = exc.message
        return output
    slots = await c.fetch('''SELECT id, hora_inicio, hora_fim FROM agenda_turnos
        WHERE restaurant_id=$1 AND dia_semana=$2 AND ativo=true ORDER BY hora_inicio''', rid, (day.weekday() + 1) % 7)
    if not slots:
        output['message'] = 'Ainda não há horários configurados para esta data. Confirme com a equipe.'
        return output
    unknown = False
    for slot in slots:
        try:
            await check_slot(c, rid, day, slot['id'], people, now)
            available, reason = True, None
        except BookingError as exc:
            available, reason = False, exc.code
            unknown = unknown or exc.code == 'unconfigured'
        output['slots'].append({'id': str(slot['id']), 'start': str(slot['hora_inicio'])[:5],
                                'end': str(slot['hora_fim'])[:5], 'available': available, 'reason': reason})
    output['state'] = 'available' if any(s['available'] for s in output['slots']) else ('unconfigured' if unknown else 'unavailable')
    output['message'] = ('Escolha um horário para registrar sua reserva.' if output['state'] == 'available'
                         else 'Confirme com a equipe ou escolha outra data.')
    return output


async def create_booking(pool, data):
    rid = valid_tenant(data.get('restaurant_id'))
    day, people = booking_date(data.get('data')), party_size(data.get('posicoes'))
    if not data.get('turno_id'):
        raise BookingError('unconfigured', 'Selecione um horário configurado ou confirme com a equipe.', 503)
    slot_id = valid_uuid(data.get('turno_id'))
    phone = normalize_phone(data.get('cliente_phone'))
    name = data.get('cliente_nome')
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 120:
        raise BookingError('invalid_name', 'Informe seu nome (2 a 120 caracteres).')
    name = name.strip()
    if data.get('evento_id') or data.get('pagamento_status', 'nao_requerido') != 'nao_requerido' or data.get('pagamento_valor'):
        raise BookingError('unconfigured', 'Reservas de eventos ou com pagamento precisam de atendimento da equipe.', 503)
    key = valid_uuid(data['_idempotency_key'], 'idempotency_key') if data.get('_idempotency_key') else None
    fingerprint = hashlib.sha256(json.dumps([rid, str(slot_id), str(day), people, phone, name], ensure_ascii=False).encode()).hexdigest()
    async with pool.acquire() as c:
        async with c.transaction(isolation='read_committed'):
            if key:
                # Lock order is idempotency then slot, including payload mismatch requests.
                await c.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', f'booking-key:{rid}:{key}')
                previous = await c.fetchrow('''SELECT request_hash, response FROM public_reservation_requests
                    WHERE restaurant_id=$1 AND idempotency_key=$2''', rid, key)
                if previous:
                    if previous['request_hash'] != fingerprint:
                        raise BookingError('idempotency_conflict', 'Este identificador já foi usado para outro pedido.', 409)
                    response = previous['response']
                    response = json.loads(response) if isinstance(response, str) else dict(response)
                    return {**response, '_replayed': True}
            await c.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', f'booking-slot:{rid}:{day}:{slot_id}')
            checked = await check_slot(c, rid, day, slot_id, people)
            start = checked['slot']['hora_inicio']
            requested_time = data.get('hora_inicio')
            if requested_time and str(requested_time)[:5] != str(start)[:5]:
                raise BookingError('invalid_time', 'O horário informado não corresponde ao turno selecionado.')
            if key:
                # Shared, atomic per-tenant/phone limit; no IP or phone stored in bucket.
                bucket = datetime.now(TZ).replace(second=0, microsecond=0)
                bucket = bucket.replace(minute=(bucket.minute // 10) * 10)
                bucket_key = hashlib.sha256(f'{rid}:{phone}'.encode()).hexdigest()
                count = await c.fetchval('''INSERT INTO public_reservation_rate_limits (key_hash,bucket,attempts)
                    VALUES($1,$2,1) ON CONFLICT(key_hash,bucket) DO UPDATE
                    SET attempts=public_reservation_rate_limits.attempts+1 RETURNING attempts''', bucket_key, bucket)
                if count > 5:
                    raise BookingError('rate_limit', 'Muitas solicitações. Aguarde alguns minutos ou fale com a equipe.', 429)
            row = await c.fetchrow('''INSERT INTO reservas
                (restaurant_id,turno_id,cliente_phone,cliente_nome,cliente_email,data,hora_inicio,posicoes,canal,observacoes,status,pagamento_status)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'pendente','nao_requerido') RETURNING *''',
                rid, slot_id, phone, name, data.get('cliente_email'), day, start, people,
                data.get('canal', 'whatsapp'), data.get('observacoes') or '')
            result = dict(row)
            if key:
                response = {'id': str(row['id']), 'status': row['status'], 'data': str(day), 'hora_inicio': str(start), 'posicoes': people}
                await c.execute('''INSERT INTO public_reservation_requests
                    (restaurant_id,idempotency_key,request_hash,reservation_id,response) VALUES($1,$2,$3,$4,$5::jsonb)''',
                    rid, key, fingerprint, row['id'], json.dumps(response))
                result = response
            return {**result, '_replayed': False} if key else result


def is_legacy_booking(data):
    return (not data.get('turno_id') or bool(data.get('evento_id')) or
            data.get('pagamento_status', 'nao_requerido') != 'nao_requerido' or bool(data.get('pagamento_valor')))


async def capacity_locks(c, rid, day, slot_id=None, event_id=None):
    # One lock order across manual creation and reactivation avoids deadlocks.
    if event_id:
        await c.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', f'booking-event:{rid}:{day}:{event_id}')
    await c.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', f'booking-slot:{rid}:{day}:{slot_id}')


async def check_manual_capacity(c, rid, day, slot_id, event_id, people, start_time):
    """Legacy operator flow: keep paid/events/unslotted requests, enforce ownership
    and any configured capacity without inventing a slot or initiating payment.
    """
    await restaurant_and_config(c, rid)  # validates active tenant, not its public eligibility
    if event_id:
        event = await c.fetchrow('SELECT * FROM agenda_eventos WHERE id=$1 AND restaurant_id=$2', event_id, rid)
        if not event:
            raise BookingError('invalid_event', 'Evento não encontrado nesta unidade.')
        if event['data'] and event['data'] != day:
            raise BookingError('invalid_event_date', 'A data não corresponde ao evento selecionado.')
        if event['capacidade_total'] is not None and event['capacidade_total'] > 0:
            occupied = await c.fetchval("SELECT COALESCE(SUM(posicoes),0) FROM reservas WHERE restaurant_id=$1 AND evento_id=$2 AND data=$3 AND status IN ('pendente','confirmada')", rid, event_id, day)
            if occupied + people > event['capacidade_total']:
                raise BookingError('capacity', 'A capacidade configurada para este evento foi atingida.', 409)
    end_time = None
    if slot_id:
        slot = await c.fetchrow('SELECT * FROM agenda_turnos WHERE id=$1 AND restaurant_id=$2 AND ativo=true',slot_id,rid)
        if not slot:
            raise BookingError('invalid_slot', 'Horário não encontrado nesta unidade.')
        if slot['dia_semana'] != (day.weekday()+1)%7:
            raise BookingError('invalid_slot_day', 'O turno não corresponde à data escolhida.')
        occupied = await c.fetchval("SELECT COALESCE(SUM(posicoes),0) FROM reservas WHERE restaurant_id=$1 AND turno_id=$2 AND data=$3 AND status IN ('pendente','confirmada')",rid,slot_id,day)
        if occupied + people > slot['capacidade_posicoes_max']:
            raise BookingError('capacity', 'Não há lugares suficientes neste turno.',409)
        start_time, end_time = slot['hora_inicio'], slot['hora_fim']
    start = datetime.combine(day, start_time, TZ)
    end = datetime.combine(day, end_time, TZ) if end_time else start + timedelta(seconds=1)
    if end <= start:
        end += timedelta(days=1)
    if await c.fetchval('SELECT EXISTS(SELECT 1 FROM agenda_bloqueios WHERE restaurant_id=$1 AND data_inicio < $3 AND data_fim > $2)',rid,start,end):
        raise BookingError('blocked', 'O horário está bloqueado nesta unidade.',409)


async def create_manual_booking(pool, data):
    """Only the authenticated private endpoint opts into this compatibility path.
    Public and agent requests cannot opt into it through a JSON body flag.
    """
    from decimal import Decimal, InvalidOperation
    from datetime import time
    rid, day, people = valid_tenant(data.get('restaurant_id')), booking_date(data.get('data')), party_size(data.get('posicoes'))
    phone = normalize_phone(data.get('cliente_phone'))
    name = data.get('cliente_nome')
    if not isinstance(name,str) or not 2 <= len(name.strip()) <= 120:
        raise BookingError('invalid_name', 'Informe o nome do titular (2 a 120 caracteres).')
    try:
        raw_time = data.get('hora_inicio')
        start = time.fromisoformat(raw_time) if isinstance(raw_time,str) else raw_time
        if not isinstance(start,time) or start.tzinfo:
            raise ValueError()
    except (ValueError,TypeError):
        raise BookingError('invalid_time', 'Informe um horário válido.')
    slot_id = valid_uuid(data['turno_id']) if data.get('turno_id') else None
    event_id = valid_uuid(data['evento_id'], 'event') if data.get('evento_id') else None
    payment_status = data.get('pagamento_status') or 'nao_requerido'
    if not isinstance(payment_status,str) or not 1 <= len(payment_status) <= 40:
        raise BookingError('invalid_payment', 'Estado de pagamento inválido.')
    value = data.get('pagamento_valor')
    try:
        value = Decimal(str(value)) if value is not None else None
        if value is not None and (not value.is_finite() or value < 0):
            raise ValueError()
    except (InvalidOperation,ValueError):
        raise BookingError('invalid_payment', 'Valor de pagamento inválido.')
    async with pool.acquire() as c:
        async with c.transaction(isolation='read_committed'):
            await capacity_locks(c,rid,day,slot_id,event_id)
            await check_manual_capacity(c,rid,day,slot_id,event_id,people,start)
            row = await c.fetchrow("""INSERT INTO reservas
                (restaurant_id,turno_id,evento_id,cliente_phone,cliente_nome,cliente_email,data,hora_inicio,posicoes,canal,observacoes,pagamento_status,pagamento_valor)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING *""",
                rid,slot_id,event_id,phone,name.strip(),data.get('cliente_email'),day,start,people,
                data.get('canal','painel'),data.get('observacoes') or '',payment_status,value)
            return dict(row)


async def update_booking_status(pool, reservation_id, rid, status):
    """Reactivation consumes capacity too; use the exact same capacity locks."""
    async with pool.acquire() as c:
        async with c.transaction(isolation='read_committed'):
            original = await c.fetchrow('SELECT * FROM reservas WHERE id=$1 AND restaurant_id=$2', valid_uuid(reservation_id, 'reservation'), valid_tenant(rid))
            if not original:
                return None
            await capacity_locks(c,rid,original['data'],original['turno_id'],original['evento_id'])
            current = await c.fetchrow('SELECT * FROM reservas WHERE id=$1 AND restaurant_id=$2 FOR UPDATE', original['id'], rid)
            if not current:
                return None
            if status in ('pendente','confirmada') and current['status'] not in ('pendente','confirmada'):
                if is_legacy_booking(dict(current)):
                    await check_manual_capacity(c,rid,current['data'],current['turno_id'],current['evento_id'],current['posicoes'],current['hora_inicio'])
                else:
                    await check_slot(c, rid, current['data'], current['turno_id'], current['posicoes'])
            row = await c.fetchrow('UPDATE reservas SET status=$3 WHERE id=$1 AND restaurant_id=$2 RETURNING *', current['id'], rid, status)
            return dict(row)
