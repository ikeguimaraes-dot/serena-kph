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
        self.assertEqual(create.call_args.kwargs, {})
        self.assertEqual(r.headers['cache-control'], 'no-store')
        value['_replayed'] = True
        with patch('public_reservations.db.criar_reserva', AsyncMock(return_value=value)):
            r = await self.client.post('/api/public/reservations/first', json=self.body)
        self.assertEqual(r.status_code, 200)

    async def test_only_authenticated_private_endpoint_opts_into_legacy(self):
        payload = {'cliente_nome':'Synthetic','cliente_phone':'+5511999998765','data':'2027-01-02',
                   'hora_inicio':'19:30','posicoes':2,'pagamento_status':'pendente','pagamento_valor':'125.50'}
        with patch.dict(os.environ, {'ADMIN_SECRET':'test-secret'}), patch('main.db.criar_reserva', AsyncMock(return_value={'id':'synthetic'})) as create:
            denied = await self.client.post('/api/agenda/first/reservas',json=payload)
            self.assertEqual(denied.status_code,401)
            create.assert_not_awaited()
            accepted = await self.client.post('/api/agenda/first/reservas',json=payload,headers={'x-admin-secret':'test-secret'})
            self.assertEqual(accepted.status_code,201,accepted.text)
            self.assertEqual(create.call_args.kwargs, {'allow_legacy':True})

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


class AvailabilityToolContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_schedule_prohibits_available_and_full_claims(self):
        import tools
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        for result in ({'state': 'unconfigured', 'message': 'Sem turnos configurados'}, RuntimeError('database offline')):
            mocked = AsyncMock(side_effect=result) if isinstance(result, Exception) else AsyncMock(return_value=result)
            with patch('tools.db.pool', return_value=pool), patch('reservation_service.availability', mocked):
                reply = await tools.verificar_disponibilidade('meet_and_eat', '2027-01-02', 4)
            self.assertIn('AGENDA_UNCONFIGURED', reply)
            self.assertIn('DISPONIBILIDADE DESCONHECIDA', reply)
            self.assertIn('não prometa espaço, vagas, mesa ou reserva', reply)
            self.assertIn('não diga que está lotado', reply)
            self.assertIn('62ffd74ddaf31500126b3e29', reply)
