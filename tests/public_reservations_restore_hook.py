#!/usr/bin/env python3.11
"""Runs ONLY against the backup tool's disposable local socket database.
Creates synthetic tenants in the disposable restore; no live access/messages.
"""
import asyncio
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'files' / 'restaurant-ai'))
import asyncpg
from reservation_service import BookingError, create_booking, availability, TZ, normalize_phone, update_booking_status, create_manual_booking


async def main():
    assert os.environ.get('PGDATABASE') == 'serena_restore'
    assert os.environ.get('PGHOST', '').startswith('/tmp/serena-restore-')
    pool = await asyncpg.create_pool(host=os.environ['PGHOST'], port=int(os.environ['PGPORT']),
                                   user=os.environ['PGUSER'], database='serena_restore', min_size=2, max_size=5)
    async with pool.acquire() as c:
        await c.execute((ROOT/'supabase/migrations/20260917043836_public_reservation_idempotency.sql').read_text())
        rid, other, unknown = ['sprint5_' + uuid4().hex[:12] for _ in range(3)]
        day = datetime.now(TZ).date() + timedelta(days=3)
        for i, tenant in enumerate((rid, other, unknown)):
            await c.execute('INSERT INTO restaurants(id,nome,whatsapp_number,capacidade_maxima_reserva,ativo) VALUES($1,$2,$3,8,true)', tenant, 'Synthetic booking test', '+990' + str(i) + uuid4().hex[:10])
        for tenant in (rid, other):
            await c.execute('INSERT INTO agenda_config(restaurant_id,permite_same_day) VALUES($1,true)', tenant)
        slots = []
        for tenant in (rid, other):
            slots.append(await c.fetchval("INSERT INTO agenda_turnos(restaurant_id,dia_semana,nome,hora_inicio,hora_fim,capacidade_posicoes_max) VALUES($1,$2,'Test','19:00','21:00',3) RETURNING id", tenant, (day.weekday()+1)%7))
        r = await availability(c, unknown, day, 2)
        assert r['state'] == 'unconfigured' and r['slots'] == []
        r = await availability(c, rid, day + timedelta(days=1), 2)
        assert r['state'] == 'unconfigured' and r['slots'] == []
        r = await availability(c, rid, day, 2)
        assert r['state'] == 'available' and r['slots'][0]['available']
        assert 'cliente_phone' not in str(r) and 'capacidade' not in str(r)

    def payload(**changes):
        base = dict(restaurant_id=rid, cliente_nome='Synthetic Customer', cliente_phone='+5511999998765',
                    data=str(day), posicoes=1, turno_id=str(slots[0]), canal='widget')
        return {**base, **changes}

    async def rejected(code, **changes):
        try:
            await create_booking(pool, payload(**changes))
        except BookingError as exc:
            assert exc.code == code, (exc.code, code)
        else:
            raise AssertionError('Expected rejection: ' + code)

    await rejected('invalid_phone', cliente_phone='no phone')
    await rejected('invalid_phone', cliente_phone='11111111111')
    await rejected('invalid_people', posicoes=True)
    await rejected('invalid_date', data='2026-02-30')
    await rejected('past_date', data=str(day-timedelta(days=10)))
    await rejected('outside_window', data=str(day+timedelta(days=100)))
    await rejected('invalid_slot', turno_id=str(slots[1]))
    await rejected('invalid_restaurant', restaurant_id='../escape')
    await rejected('invalid_slot_day', data=str(day+timedelta(days=1)))
    await rejected('invalid_time', hora_inicio='20:00')
    await rejected('unconfigured', restaurant_id=unknown)
    await rejected('unconfigured', turno_id=None)
    await rejected('unconfigured', pagamento_status='pendente')
    assert normalize_phone('(11) 99999-8765') == '+5511999998765'

    # Last place: independent connections contend on the same database lock.
    initial_booking = await create_booking(pool, payload(posicoes=2))
    outcomes = await asyncio.gather(create_booking(pool, payload(_idempotency_key=str(uuid4()))),
                                    create_booking(pool, payload(_idempotency_key=str(uuid4()))), return_exceptions=True)
    assert sum(isinstance(x, dict) for x in outcomes) == 1
    assert sum(isinstance(x, BookingError) and x.code == 'capacity' for x in outcomes) == 1
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT SUM(posicoes) FROM reservas WHERE restaurant_id=$1 AND status IN('pendente','confirmada')",rid) == 3
        result = await availability(c, rid, day, 1)
        assert result['state'] == 'unavailable'
        await c.execute("UPDATE reservas SET status='cancelada' WHERE restaurant_id=$1",rid)

    # Reopening a cancelled reservation must not bypass the capacity lock.
    await create_booking(pool, payload(posicoes=3))
    try:
        await update_booking_status(pool, initial_booking['id'], rid, 'confirmada')
    except BookingError as exc:
        assert exc.code == 'capacity'
    else:
        raise AssertionError('Reactivation overbooked')
    async with pool.acquire() as c:
        await c.execute("UPDATE reservas SET status='cancelada' WHERE restaurant_id=$1", rid)

    # Concurrent double-click: same key yields one insert and the same response.
    key = str(uuid4())
    results = await asyncio.gather(*[create_booking(pool, payload(_idempotency_key=key)) for _ in range(2)])
    assert results[0]['id'] == results[1]['id']
    assert sorted(x['_replayed'] for x in results) == [False, True]
    await rejected('idempotency_conflict', _idempotency_key=key, cliente_nome='Changed Name')
    # Same UUID on a separate tenant is not another tenant's result.
    second = await create_booking(pool, payload(restaurant_id=other, turno_id=str(slots[1]), _idempotency_key=key))
    assert second['id'] != results[0]['id']
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT COUNT(*) FROM reservas WHERE restaurant_id=$1 AND status='pendente'", rid) == 1
        await c.execute("UPDATE reservas SET status='cancelada' WHERE restaurant_id=$1",rid)
        start = datetime.combine(day, datetime.min.time(), TZ)
        block = await c.fetchval('INSERT INTO agenda_bloqueios(restaurant_id,data_inicio,data_fim) VALUES($1,$2,$3) RETURNING id',rid,start,start+timedelta(days=1))
    await rejected('blocked')
    async with pool.acquire() as c:
        await c.execute('DELETE FROM agenda_bloqueios WHERE id=$1',block)
        await c.execute('UPDATE agenda_config SET requer_pagamento=true WHERE restaurant_id=$1',rid)
    await rejected('unconfigured')
    async with pool.acquire() as c:
        await c.execute('UPDATE agenda_config SET requer_pagamento=false WHERE restaurant_id=$1',rid)
        # Published events in this schema can retain default tipo='reserva'.
        event = await c.fetchval("INSERT INTO agenda_eventos(restaurant_id,nome,data,ativo) VALUES($1,'Synthetic event',$2,true) RETURNING id",rid,day)
    await rejected('unconfigured')
    async with pool.acquire() as c:
        await c.execute('DELETE FROM agenda_eventos WHERE id=$1', event)
        await c.execute('UPDATE agenda_turnos SET capacidade_posicoes_max=20 WHERE id=$1', slots[0])
        # Shared write limit is enforced even when public API runs on two workers.
        await c.execute('DELETE FROM public_reservation_rate_limits')
    for _ in range(5):
        await create_booking(pool, payload(_idempotency_key=str(uuid4())))
    await rejected('rate_limit', _idempotency_key=str(uuid4()))
    async with pool.acquire() as c:
        # No client role may access idempotency results or limiter buckets.
        for role in ('anon','authenticated'):
            for table in ('public_reservation_requests','public_reservation_rate_limits'):
                assert not await c.fetchval("SELECT has_table_privilege($1,$2,'SELECT')",role,'public.'+table)
                assert await c.fetchval('SELECT relrowsecurity FROM pg_class WHERE oid=$1::regclass','public.'+table)
    # Authenticated legacy operations remain available without inventing slots
    # or charging anything. They still validate tenant ownership and capacity.
    manual = await create_manual_booking(pool, payload(restaurant_id=unknown, turno_id=None,
        hora_inicio='19:30', canal='painel', pagamento_status='pendente', pagamento_valor='125.50'))
    assert manual['turno_id'] is None and str(manual['hora_inicio']) == '19:30:00'
    assert str(manual['pagamento_valor']) == '125.50' and manual['pagamento_status'] == 'pendente'
    assert manual['status'] == 'pendente'
    async with pool.acquire() as c:
        manual_event = await c.fetchval("INSERT INTO agenda_eventos(restaurant_id,nome,data,capacidade_total,ativo) VALUES($1,'Legacy synthetic event',$2,1,true) RETURNING id",unknown,day)
    event_payload = payload(restaurant_id=unknown,turno_id=None,evento_id=manual_event,hora_inicio='20:00',canal='painel')
    event_booking = await create_manual_booking(pool,event_payload)
    assert event_booking['evento_id'] == manual_event
    try:
        await create_manual_booking(pool,event_payload)
    except BookingError as exc:
        assert exc.code == 'capacity'
    else:
        raise AssertionError('Manual event capacity was bypassed')
    try:
        await create_manual_booking(pool,{**event_payload,'restaurant_id':other})
    except BookingError as exc:
        assert exc.code == 'invalid_event'
    else:
        raise AssertionError('Cross-tenant event accepted')
    async with pool.acquire() as c:
        await c.execute("UPDATE reservas SET status='cancelada' WHERE id=$1",manual['id'])
    reopened = await update_booking_status(pool,manual['id'],unknown,'confirmada')
    assert reopened['status'] == 'confirmada'
    print('PASS: local restored-schema booking, invalid-input/config/event contracts, last-place race, concurrent dedup, cross-tenant keys, reactivation capacity, closure/payment/event rules, shared write limiter, client-role ACL/RLS and private manual/payment/event compatibility.')
    await pool.close()


if __name__ == '__main__':
    asyncio.run(main())
