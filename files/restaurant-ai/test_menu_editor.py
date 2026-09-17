"""Menu editor regressions: money semantics and tenant authorization, no external IO."""
import os
import unittest
from unittest.mock import patch, AsyncMock
import httpx
from pydantic import ValidationError
from models import MenuItemCreate, MenuItemUpdate
with patch.dict(os.environ, {'ANTHROPIC_API_KEY':'test-only','ADMIN_SECRET':'test-secret'}):
    import main


class MenuEditorTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_price_and_omitted_price_are_distinct(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://local') as client:
            with patch.dict(os.environ, {'ADMIN_SECRET':'test-secret'}), patch('api_access.resource_tenant',AsyncMock(return_value='first')), patch('main.db.update_menu_item',AsyncMock(return_value=True)) as update:
                for payload in [{'preco':None}, {'preco':0}, {'preco':49.9}, {'descricao':'Novo texto'}]:
                    r=await client.patch('/api/menu/1?rid=first',json=payload,headers={'x-admin-secret':'test-secret'})
                    self.assertEqual(r.status_code,200,r.text)
                    update.assert_awaited_with(1,payload)

    async def test_cross_unit_and_anonymous_edit_never_write(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://local') as client:
            with patch.dict(os.environ, {'ADMIN_SECRET':'test-secret'}), patch('api_access.resource_tenant',AsyncMock(return_value='second')), patch('main.db.update_menu_item',AsyncMock()) as update:
                for headers,status in [({},401),({'x-admin-secret':'test-secret'},404)]:
                    r=await client.patch('/api/menu/1?rid=first',json={'preco':1},headers=headers)
                    self.assertEqual(r.status_code,status,r.text)
                update.assert_not_awaited()

    def test_price_validation_preserves_unknown_and_rejects_invalid_money(self):
        for model,required in [(MenuItemCreate,{'nome':'Teste','categoria':'Entradas'}),(MenuItemUpdate,{})]:
            for value in [-1,float('inf'),float('nan')]:
                with self.subTest(model=model.__name__,value=value), self.assertRaises(ValidationError):
                    model(**required,preco=value)
            for value in [None,0,49.9]:
                self.assertEqual(model(**required,preco=value).preco,value)
