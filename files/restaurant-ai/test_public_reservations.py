"""HTTP contract with no real DB or outbound messaging."""
import os
import unittest
from uuid import uuid4
from unittest.mock import patch, AsyncMock, MagicMock
import httpx
with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-only', 'ADMIN_SECRET': 'test-secret'}):
    import main
import public_reservations as public
from reservation_service import BookingError


class PublicBookingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        public._hits.clear()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://local')
        self.body = {'name': 'Synthetic Customer', 'phone': '+5511999998765', 'date': '2027-01-02',
                     'people': 2, 'slot_id': str(uuid4()), 'idempotency_key': str(uuid4())}

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_public_insert_filtered_pending_and_replay(self):
        value = {'id': str(uuid4()), 'data': self.body['date'], 'hora_inicio': '19:00',
                 'posicoes': 2, 'cliente_phone': 'private', 'cliente_email': 'private', '_replayed': False}
        with patch('public_reservations.db.criar_reserva', AsyncMock(return_value=value)) as create:
            r = await self.client.post('/api/public/reservations/first', json=self.body)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()['status'], 'pending')
        self.assertNotIn('private', r.text)
        self.assertEqual(create.call_args.args[0]['restaurant_id'], 'first')
        self.assertEqual(r.headers['cache-control'], 'no-store')
        value['_replayed'] = True
        with patch('public_reservations.db.criar_reserva', AsyncMock(return_value=value)):
            r = await self.client.post('/api/public/reservations/first', json=self.body)
        self.assertEqual(r.status_code, 200)

    async def test_extra_scope_and_invalid_input_never_insert(self):
        with patch('public_reservations.db.criar_reserva', AsyncMock()) as create:
            for field, value in [('restaurant_id', 'other'), ('people', True), ('people', 0), ('slot_id', 'invalid'), ('idempotency_key', None), ('phone', ''), ('date', 'tomorrow')]:
                with self.subTest(field=field):
                    r = await self.client.post('/api/public/reservations/first', json={**self.body, field: value})
                    self.assertEqual(r.status_code, 422, r.text)
            create.assert_not_awaited()

    async def test_conflict_and_outage_never_report_success(self):
        for exc, status in [(BookingError('capacity', 'Escolha outro horário.', 409),409),
                            (BookingError('unconfigured', 'Confirme com a equipe.',503),503),
                            (RuntimeError('secret SQL/customer'),503)]:
            with patch('public_reservations.db.criar_reserva', AsyncMock(side_effect=exc)):
                r = await self.client.post('/api/public/reservations/first', json=self.body)
            self.assertEqual(r.status_code, status)
            self.assertNotIn('secret', r.text)
            self.assertNotIn('reservation_id', r.json())

    async def test_explicit_public_availability_and_private_adjacency(self):
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch('public_reservations.db.pool', return_value=pool), patch('public_reservations.availability', AsyncMock(return_value={'state':'unconfigured','slots':[]})):
            r = await self.client.get('/api/public/reservations/first?date=2027-01-02&people=2')
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['state'],'unconfigured')
        r = await self.client.delete('/api/public/reservations/first')
        self.assertEqual(r.status_code,405)
        r = await self.client.get('/api/agenda/first/reservas')
        self.assertIn(r.status_code,(401,503))

    async def test_limiter_stops_insert(self):
        value = {'id':str(uuid4()),'data':self.body['date'],'hora_inicio':'19:00','posicoes':2}
        with patch('public_reservations.time.time', return_value=1800), patch('public_reservations.db.criar_reserva', AsyncMock(return_value=value)) as create:
            for _ in range(120):
                r=await self.client.post('/api/public/reservations/first',json=self.body)
                self.assertEqual(r.status_code,201)
            r=await self.client.post('/api/public/reservations/first',json=self.body)
        self.assertEqual(r.status_code,429)
        self.assertEqual(create.await_count,120)


class ReservationLinkTests(unittest.TestCase):
    def test_link_uses_conversation_tenant_not_global_environment(self):
        import tools
        with patch.dict(os.environ, {'RESTAURANT_ID': 'wrong_house'}):
            self.assertIn('/reservar/levvai', tools.get_reservation_link('levvai', pessoas=2))
            self.assertNotIn('wrong_house', tools.get_reservation_link('freneze'))
