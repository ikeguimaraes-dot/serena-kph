"""Pricing regressions: source identities, variants, unknowns and monetary units."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from catalog_publish import normalize_tagme, normalize_shopfood, amount
from catalog import imported_item_text


def section(item):
    return [{'name':{'pt':'Bebidas'},'menuItems':[item]}]


class CatalogTests(unittest.TestCase):
    def test_cents_are_not_guessed_from_magnitude(self):
        self.assertEqual(amount(100,100),'1.00')
        self.assertEqual(amount(10808,100),'108.08')
        self.assertEqual(amount(349),'349.00')

    def test_variant_prices_are_never_collapsed(self):
        item={'_id':'drink','name':{'pt':'Dry Martini'},'price':4800,'options':[
            {'_id':'a','volume':'Bombay','price':4800},{'_id':'b','volume':'Hendricks','price':6200}]}
        row=normalize_tagme(section(item))[0]
        self.assertIsNone(row['preco'])
        rendered=imported_item_text(row)
        self.assertIn('Bombay: R$ 48,00',rendered)
        self.assertIn('Hendricks: R$ 62,00',rendered)
        self.assertNotIn('Preço de referência: R$ 48',rendered)

    def test_missing_zero_variant_is_not_free(self):
        row=normalize_tagme(section({'_id':'wine','name':{'pt':'Wine'},'options':[
            {'_id':'a','volume':'750 ml','price':0}]}))[0]
        rendered=imported_item_text(row)
        self.assertIsNone(row['preco'])
        self.assertNotIn('R$ 0,00',rendered)
        self.assertIn('sob consulta',rendered)

    def test_addons_and_disabled_children_preserved(self):
        row=normalize_tagme(section({'_id':'burger','name':{'pt':'Burger'},'price':8200,'options':[
            {'_id':'group','name':{'pt':'Adicional'},'min':0,'max':1,'sons':[
                {'_id':'a','name':{'pt':'Bacon'},'price':800},
                {'_id':'b','name':{'pt':'Salada'},'price':600,'disabled':True}]}]}))[0]
        rendered=imported_item_text(row)
        self.assertIn('R$ 82,00',rendered)
        self.assertIn('Bacon (+R$ 8,00)',rendered)
        self.assertNotIn('Salada',rendered)
        self.assertEqual(len(row['catalog_metadata']['source_options'][0]['sons']),2)

    def test_disabled_parent_propagates(self):
        row=normalize_tagme([{'name':'Oculto','disabled':True,'menus':section({'_id':'a','name':'Prato','price':100})}])[0]
        self.assertFalse(row['disponivel'])
        self.assertIn('Não oferecer',imported_item_text(row))

    def test_package_components_not_free_products(self):
        product={'id':1,'name':'Experiência','type':9,'price':0,'default_price':349,'active':True,'visible':True}
        details={'responses':[{'product_id':1,'http_status':200,'body':{'product':{'id':1,'product_composite_steps':[
            {'id':1,'name':'Entrada','minimum_quantity':1,'quantity':1,'complements':[
                {'id':2,'name':'Entrada A','price':0,'chargeable':False,'active':True},
                {'id':3,'name':'Entrada B','price':0,'chargeable':False,'active':True}]}]}}}]}
        row=normalize_shopfood([{'name':'Menu','products':[product]}],details)[0]
        rendered=imported_item_text(row)
        self.assertIn('Preço do conjunto: R$ 349,00',rendered)
        self.assertIn('incluído no conjunto',rendered)
        self.assertNotIn('R$ 0,00',rendered)

    def test_source_stock_is_not_promised(self):
        row=normalize_tagme(section({'_id':'a','name':'Prato','price':100}))[0]
        self.assertIn('disponibilidade no atendimento não foram confirmados',imported_item_text(row))

    def test_promotion_requires_explicit_adapter(self):
        with self.assertRaises(ValueError):
            normalize_tagme(section({'_id':'a','name':'Prato','price':100,'promoPriceEnabled':True}))

    def test_manual_item_contract_is_unchanged(self):
        self.assertIsNone(imported_item_text({'nome':'Manual','preco':10}))


if __name__=='__main__': unittest.main()
