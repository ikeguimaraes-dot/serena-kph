"""Contrato de consulta de catálogo: não confundir ausência de dado com negativa.

Testes locais com mocks; não conectam ao banco nem enviam mensagens.
Execute: python3.11 -m unittest test_menu_availability -v
"""

import io
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import database as db
import tools


class LookupMenuTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for attr, function in (("search", "search_menu_items"),
                               ("has_items", "has_menu_items"),
                               ("categories", "get_menu_categories")):
            patcher = patch.object(db, function, new_callable=AsyncMock)
            setattr(self, attr, patcher.start())
            self.addCleanup(patcher.stop)
        self.search.return_value = []
        self.has_items.return_value = False
        self.categories.return_value = []

    def assert_safe_unknown(self, result):
        self.assertIn("Não invente itens ou preços", result)
        self.assertIn("nem conclua que o item não existe", result)
        self.assertIn("ou que a casa está lotada", result)
        self.assertIn("ofereça atendimento humano", result)
        self.assertNotIn("R$", result)

    async def test_empty_catalog_is_explicitly_unavailable(self):
        result = await tools.lookup_menu("madonna_cucina", "risoto")

        self.assertTrue(result.startswith("CATALOGO_INDISPONIVEL:"))
        self.assert_safe_unknown(result)
        self.search.assert_awaited_once_with("madonna_cucina", "risoto", limit=5)
        self.has_items.assert_awaited_once_with("madonna_cucina")
        self.categories.assert_not_awaited()

    async def test_no_match_in_populated_catalog_is_not_an_empty_catalog(self):
        self.has_items.return_value = True
        self.categories.return_value = ["Entradas", "Bebidas"]

        result = await tools.lookup_menu("meet_and_eat", "risoto")

        self.assertTrue(result.startswith("SEM_CORRESPONDENCIA:"))
        self.assertIn("Categorias cadastradas: Entradas, Bebidas", result)
        self.assert_safe_unknown(result)
        self.has_items.assert_awaited_once_with("meet_and_eat")
        self.categories.assert_awaited_once_with("meet_and_eat")

    async def test_items_without_categories_still_mean_populated_catalog(self):
        self.has_items.return_value = True
        self.categories.return_value = []

        result = await tools.lookup_menu("levvai", "serviço desconhecido")

        self.assertTrue(result.startswith("SEM_CORRESPONDENCIA:"))
        self.assertNotIn("CATALOGO_INDISPONIVEL", result)
        self.assert_safe_unknown(result)

    async def test_success_preserves_stored_prices_and_availability(self):
        self.search.return_value = [
            {"nome": "Risoto", "preco": Decimal("79.90"), "disponivel": True,
             "descricao": " Cogumelos ", "categoria": "Pratos"},
            {"nome": "Bebida", "preco": Decimal("12.00"), "disponivel": False,
             "descricao": None, "categoria": None},
        ]

        result = await tools.lookup_menu("freneze", "")

        self.assertIn("Risoto — R$ 79,90 (disponível): Cogumelos", result)
        self.assertIn("Bebida — R$ 12,00 (indisponível)", result)
        self.assertEqual(len(result.splitlines()), 2)
        self.has_items.assert_not_awaited()
        self.categories.assert_not_awaited()

    async def test_missing_price_remains_under_consultation(self):
        self.search.return_value = [
            {"nome": "Procedimento", "preco": None, "disponivel": True,
             "descricao": None, "categoria": None},
        ]

        result = await tools.lookup_menu("levvai", "Procedimento")

        self.assertIn("Procedimento — preço sob consulta", result)
        self.assertNotIn("R$", result)

    async def test_database_error_is_not_empty_catalog_and_does_not_leak_details(self):
        sensitive_detail = "postgres://private-user:private-password@example.invalid/database"
        self.search.side_effect = RuntimeError(sensitive_detail)
        captured = io.StringIO()

        with redirect_stdout(captured):
            result = await tools.lookup_menu("freneze", "risoto")

        self.assertTrue(result.startswith("ERRO_CONSULTA_CATALOGO:"))
        self.assert_safe_unknown(result)
        self.assertNotIn(sensitive_detail, result + captured.getvalue())
        self.has_items.assert_not_awaited()

    async def test_catalog_existence_error_does_not_become_absence(self):
        self.has_items.side_effect = TimeoutError("database unavailable")

        with redirect_stdout(io.StringIO()):
            result = await tools.lookup_menu("meet_and_eat", "risoto")

        self.assertTrue(result.startswith("ERRO_CONSULTA_CATALOGO:"))
        self.assert_safe_unknown(result)
        self.categories.assert_not_awaited()

    async def test_category_lookup_error_remains_a_technical_error(self):
        self.has_items.return_value = True
        self.categories.side_effect = TimeoutError("database unavailable")

        with redirect_stdout(io.StringIO()):
            result = await tools.lookup_menu("meet_and_eat", "risoto")

        self.assertTrue(result.startswith("ERRO_CONSULTA_CATALOGO:"))
        self.assert_safe_unknown(result)


class CatalogExistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_existence_check_is_scoped_and_includes_uncategorized_unavailable_items(self):
        connection = MagicMock()
        connection.fetchval = AsyncMock(side_effect=[True, False])
        fake_pool = MagicMock()
        fake_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=connection)
        fake_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch.object(db, "pool", return_value=fake_pool):
            self.assertTrue(await db.has_menu_items("tenant-with-items"))
            self.assertFalse(await db.has_menu_items("empty-tenant"))

        for call, tenant in zip(connection.fetchval.await_args_list,
                                ["tenant-with-items", "empty-tenant"]):
            query, rid = call.args
            self.assertEqual(rid, tenant)
            self.assertIn("restaurant_id=$1", query)
            self.assertNotIn(tenant, query)
            self.assertNotIn("categoria", query)
            self.assertNotIn("disponivel", query)


if __name__ == "__main__":
    unittest.main()
