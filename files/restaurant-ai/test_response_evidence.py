import unittest
from response_evidence import check_prices

SOURCE = 'Carne Cruda [Entradas]\nPreço de referência: R$ 108,08.'
class EvidenceTests(unittest.TestCase):
    def test_observed_rounding_is_replaced_with_exact_source(self):
        self.assertIn('R$ 108,08',check_prices('R$ 108 — corte na ponta da faca.',[SOURCE]))
    def test_exact_price_preserves_answer(self):
        response='A Carne Cruda custa R$ 108,08.'
        self.assertEqual(check_prices(response,[SOURCE]),response)
    def test_missing_price_never_becomes_free(self):
        self.assertNotIn('R$',check_prices('Esse vinho custa R$ 0,00.',['Vinho: preço sob consulta']))
    def test_variants_preserve_labels(self):
        source='Caipirinha [Bar]\nPreço por variante (não usar o menor preço para outra escolha): Tradicional: R$ 38,00; Premium: R$ 58,00'
        result=check_prices('Custa R$ 40.',[source])
        self.assertIn('Tradicional: R$ 38,00; Premium: R$ 58,00',result)
    def test_proposal_exact_amount_preserved(self):
        self.assertEqual(check_prices('Total R$ 1.200,50.', ['Total R$ 1.200,50.']),'Total R$ 1.200,50.')
    def test_decimal_dot_is_not_mistaken_for_thousands(self):
        self.assertEqual(check_prices('R$ 108.08',[SOURCE]),'R$ 108.08')
        self.assertNotEqual(check_prices('R$ 10808',[SOURCE]),'R$ 10808')
