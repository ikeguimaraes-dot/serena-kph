import unittest
from unittest.mock import AsyncMock, patch
from decimal import Decimal
import database as db
import tools

class PromptSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_never_rounds_prices_or_implies_stock(self):
        with patch.object(db, 'get_menu_items', AsyncMock(return_value=[
            {'nome':'Carne Cruda','categoria':'Entradas','disponivel':True,'preco':Decimal('108.08')},
            {'nome':'Drink','categoria':'Bar','disponivel':True,'preco':None},
        ])):
            text=await db._get_menu_summary('test')
        self.assertNotIn('R$',text)
        self.assertIn('lookup_menu',text)
        self.assertIn('sem confirmação de estoque',text)

    async def test_unknown_hours_is_not_closed(self):
        with patch.object(db,'get_business_hours_for_date',AsyncMock(return_value={'aberto':None})):
            text=await tools.check_business_hours('test','2026-09-18')
        self.assertTrue(text.startswith('HORARIO_NAO_CONFIRMADO:'))
        self.assertNotIn(': fechado',text)

    async def test_known_closed_is_preserved(self):
        with patch.object(db,'get_business_hours_for_date',AsyncMock(return_value={'aberto':False,'especial':False})):
            self.assertIn(': fechado.',await tools.check_business_hours('test','2026-09-20'))
