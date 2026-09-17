"""Run against DATABASE_URL; all test data is rolled back. Never sends messages."""
import ast
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

import asyncpg
import database as db


class TransactionPool:
    def __init__(self, connection):
        self.connection = connection
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self):
        async with self.lock:
            yield self.connection

    def __getattr__(self, name):
        async def serialized(*args, **kwargs):
            async with self.lock:
                return await getattr(self.connection, name)(*args, **kwargs)
        return serialized


async def run():
    connection = await asyncpg.connect(os.environ['DATABASE_URL'], ssl='require')
    transaction = connection.transaction()
    await transaction.start()
    db._pool = TransactionPool(connection)
    phone = '+recovery-test-' + os.urandom(6).hex()
    try:
        for rid in ('freneze', 'levvai', 'madonna_cucina', 'meet_and_eat'):
            restaurant = await db.get_restaurant_full(rid)
            assert restaurant and (await db.get_active_prompt(rid))['prompt_completo']
            assert isinstance(await db._build_eventos_block(rid), str)
        await db.ensure_contact(phone, 'Recovery test', 'freneze')
        await db.ensure_contact(phone, 'Recovery test', 'freneze')
        await db.ensure_contact(phone, 'Recovery test', 'levvai')
        assert await connection.fetchval('SELECT count(*) FROM contacts WHERE celular=$1', phone) == 2
        await db.save_message(phone, 'freneze', 'user', 'Test')
        await db.save_message(phone, 'freneze', 'assistant', 'Test response')
        assert len(await db.get_history(phone, 'freneze')) == 2
        metric_id = await db.record_serena_metric({'user_phone': phone, 'restaurant_id': 'freneze'})
        await db.update_serena_metric_categoria(metric_id, 'outros')
        turn = await connection.fetchrow('SELECT * FROM agenda_turnos WHERE ativo=true LIMIT 1')
        assert turn
        target = date.today() + timedelta(days=7)
        while (target.weekday() + 1) % 7 != turn['dia_semana']:
            target += timedelta(days=1)
        availability = await db.check_disponibilidade(turn['restaurant_id'], target.isoformat(), str(turn['id']), 1)
        assert availability['disponivel'] is True
        reservation = await db.criar_reserva({
            'restaurant_id': turn['restaurant_id'], 'turno_id': turn['id'],
            'cliente_phone': phone, 'cliente_nome': 'Recovery test',
            'data': target, 'hora_inicio': turn['hora_inicio'], 'posicoes': 1,
        })
        assert reservation['cliente_phone'] == phone
        assert await db.get_reservas_por_phone(turn['restaurant_id'], phone)
        assert await db.get_contact_reservations(phone)
        tree = ast.parse(Path(__file__).with_name('main.py').read_text())
        nps = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_tentar_capturar_nps')
        namespace = {}
        exec(compile(ast.Module(body=[nps], type_ignores=[]), 'main.py', 'exec'), namespace)
        assert await namespace['_tentar_capturar_nps'](phone, '9') is False
        class HTTPException(Exception):
            def __init__(self, status_code, detail):
                self.status_code = status_code
        health = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'health')
        health.decorator_list = []
        namespace = {'db': db, 'asyncio': asyncio, 'HTTPException': HTTPException}
        exec(compile(ast.Module(body=[health], type_ignores=[]), 'main.py', 'exec'), namespace)
        assert (await namespace['health']())['status'] == 'ok'
        saved_pool = db._pool
        db._pool = None
        try:
            await namespace['health']()
            raise AssertionError('Health must reject a missing database pool')
        except HTTPException as error:
            assert error.status_code == 503
        finally:
            db._pool = saved_pool
        print('PASS: four prompts, event context, scoped contacts, conversations, metrics, reservations and NPS')
    finally:
        await transaction.rollback()
        db._pool = None
        await connection.close()
        print('All test data rolled back')


if __name__ == '__main__':
    asyncio.run(run())
