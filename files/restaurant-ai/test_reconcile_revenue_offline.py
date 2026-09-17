"""Synthetic offline tests. No database, network, messages, or payment provider."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from reconcile_revenue_offline import ContractError, HEADERS, load_operations, load_receipts, main, reconcile

FIXTURES = Path(__file__).parent / "tests" / "fixtures"


class ReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.operations = load_operations((FIXTURES / "reconciliation_operations.synthetic.json").read_text())
        self.receipts = load_receipts((FIXTURES / "reconciliation_receipts.synthetic.csv").read_text())

    def run_report(self, operations=None, receipts=None):
        return reconcile(self.operations if operations is None else operations, self.receipts if receipts is None else receipts,
                         restaurant_id="synthetic_unit_a", start=date(2026, 9, 1), end=date(2026, 9, 8))

    def test_closed_cash_uses_real_movements_and_preserves_refund_and_cancelled_status(self):
        report = self.run_report()
        self.assertEqual(report["status"], "complete")
        totals = report["totais_fechados_brl"]
        self.assertEqual(totals["recebimentos_liquidos_validos"], "340.25")
        self.assertEqual(totals["conciliado_total"], "290.25")
        self.assertEqual(totals["conciliado_atribuicao_assistida"], "90.05")
        self.assertEqual(totals["conciliado_sem_interacao_elegivel"], "200.20")
        self.assertEqual(totals["sem_vinculo_operacional"], "50.00")
        self.assertEqual(report["contagens"]["estornos_validos"], 1)
        self.assertEqual(report["estados_operacionais_atual_export_por_movimento"]["cancelada"], 2)
        self.assertIsNone(report["receita_incremental_brl"])

    def test_same_receipt_cannot_be_counted_twice_even_outside_period(self):
        duplicate = copy.deepcopy(self.receipts[0])
        duplicate["occurred_at"] = "2027-01-01T00:00:00Z"
        self.receipts.append(duplicate)
        with self.assertRaisesRegex(ContractError, "DUPLICATE_RECEIPTS_IDENTITY"):
            self.run_report()

    def test_cross_tenant_blocked_in_each_input_even_with_same_phone_or_reference(self):
        for source in ("entities", "interactions", "receipts"):
            with self.subTest(source=source):
                operations, receipts = copy.deepcopy(self.operations), copy.deepcopy(self.receipts)
                (receipts if source == "receipts" else operations[source])[0]["restaurant_id"] = "synthetic_unit_b"
                with self.assertRaisesRegex(ContractError, "CROSS_TENANT"):
                    self.run_report(operations, receipts)

    def test_duplicate_entity_or_interaction_does_not_pick_arbitrary_identity(self):
        for key in ("entities", "interactions"):
            operations = copy.deepcopy(self.operations)
            operations[key].append(copy.deepcopy(operations[key][0]))
            with self.assertRaisesRegex(ContractError, "DUPLICATE_"):
                self.run_report(operations)

    def test_unknown_reference_and_ambiguous_double_reference_stay_unreconciled(self):
        self.receipts[0]["reservation_id"] = "not-in-export"
        self.receipts[1]["reservation_id"] = "synthetic-reservation-a"
        report = self.run_report()
        self.assertEqual(report["somas_observadas_brl"]["nao_conciliado"], "300.30")
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(all(value is None for value in report["totais_fechados_brl"].values()))

    def test_decimal_arithmetic_never_uses_binary_float_or_estimated_entity_value(self):
        self.receipts = [copy.deepcopy(self.receipts[0]), copy.deepcopy(self.receipts[0])]
        self.receipts[0]["amount_brl"] = "0.10"
        self.receipts[1].update(transaction_id="distinct-id", amount_brl="0.20")
        self.operations["entities"][0]["estimated_value_brl"] = 99999999.99
        self.assertEqual(self.run_report()["totais_fechados_brl"]["recebimentos_liquidos_validos"], "0.30")

    def test_bad_money_or_missing_evidence_is_quarantined_not_coerced_to_zero(self):
        for amount in ("", "NaN", "Infinity", "1,50", "1.005", "1e2", "-", 1.5):
            receipts = [dict(self.receipts[0], amount_brl=amount)]
            report = self.run_report(receipts=receipts)
            self.assertEqual(report["status"], "incomplete")
            self.assertIsNone(report["somas_observadas_brl"]["recebimentos_liquidos_validos"])
        for field in ("evidence_ref", "transaction_id", "restaurant_id"):
            report = self.run_report(receipts=[dict(self.receipts[0], **{field: ""})])
            self.assertIsNone(report["somas_observadas_brl"]["recebimentos_liquidos_validos"])

    def test_later_refund_does_not_rewrite_earlier_cash_period(self):
        self.receipts.append(dict(self.receipts[2], transaction_id="later-refund", amount_brl="-500.00", occurred_at="2026-09-08T00:00:00-03:00"))
        report = self.run_report()
        self.assertEqual(report["totais_fechados_brl"]["recebimentos_liquidos_validos"], "340.25")
        self.assertEqual(report["contagens"]["fora_do_periodo"], 1)

    def test_latest_conversation_wins_and_future_or_older_than_seven_days_cannot_attribute(self):
        self.assertEqual(self.run_report()["totais_fechados_brl"]["conciliado_sem_interacao_elegivel"], "200.20")
        for stamp in ("2026-09-02T12:00:00-03:00", "2026-09-02T13:00:00-03:00", "2026-08-26T11:59:59-03:00"):
            operations = copy.deepcopy(self.operations)
            operations["interactions"][0]["occurred_at"] = stamp
            report = self.run_report(operations)
            self.assertEqual(report["totais_fechados_brl"]["conciliado_atribuicao_assistida"], "0.00")
        self.operations["interactions"][0]["occurred_at"] = "2026-08-26T12:00:00-03:00"
        self.assertEqual(self.run_report()["totais_fechados_brl"]["conciliado_atribuicao_assistida"], "90.05")

    def test_missing_coverage_or_missing_phone_never_means_known_no_assistance(self):
        self.operations["sources"]["interactions"]["complete"] = False
        self.operations["interactions"] = []
        report = self.run_report()
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["somas_observadas_brl"]["conciliado_atribuicao_desconhecida"], "290.25")
        self.assertIsNone(report["somas_observadas_brl"]["conciliado_sem_interacao_elegivel"])
        self.setUp()
        self.operations["entities"][0]["customer_phone"] = ""
        report = self.run_report()
        self.assertEqual(report["somas_observadas_brl"]["conciliado_atribuicao_desconhecida"], "90.05")
        self.assertEqual(report["somas_observadas_brl"]["conciliado_total"], "290.25")

    def test_partial_source_retains_observed_amounts_but_never_publishes_closed_totals(self):
        for field, value in (("complete", False), ("source_ref", ""), ("as_of", "2026-09-07T00:00:00-03:00"), ("window_start", "2026-09-03T00:00:00-03:00")):
            operations = copy.deepcopy(self.operations)
            operations["sources"]["receipts"][field] = value
            report = self.run_report(operations)
            self.assertEqual(report["status"], "incomplete")
            self.assertEqual(report["somas_observadas_brl"]["recebimentos_liquidos_validos"], "340.25")
            self.assertTrue(all(value is None for value in report["totais_fechados_brl"].values()))

    def test_empty_unknown_set_is_null_but_explicitly_closed_empty_set_is_zero(self):
        self.assertEqual(self.run_report(receipts=[])["totais_fechados_brl"]["recebimentos_liquidos_validos"], "0.00")
        self.operations["sources"] = {}
        report = self.run_report(receipts=[])
        self.assertIsNone(report["somas_observadas_brl"]["recebimentos_liquidos_validos"])

    def test_missing_timestamp_does_not_escape_period_completeness_checks(self):
        self.receipts[0]["occurred_at"] = "2026-09-02T12:00:00"
        report = self.run_report()
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["contagens"]["invalidos_periodo_desconhecido"], 1)

    def test_ambiguous_tied_human_agent_conversations_cannot_be_decided_by_input_order(self):
        self.operations["interactions"].append(dict(self.operations["interactions"][0], id="same-time-human", agent_assisted=False))
        report = self.run_report()
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["somas_observadas_brl"]["conciliado_atribuicao_desconhecida"], "90.05")
        self.assertTrue(any(item["code"] == "AMBIGUOUS_LAST_INTERACTION" for item in report["diagnosticos"]))

    def test_invalid_interaction_export_cannot_prove_absence_of_assistance(self):
        self.operations["interactions"][0]["occurred_at"] = "missing time"
        report = self.run_report()
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["somas_observadas_brl"]["conciliado_atribuicao_desconhecida"], "290.25")

    def test_negative_only_period_stays_negative_without_fabricating_original_sale(self):
        report = self.run_report(receipts=[self.receipts[2]])
        self.assertEqual(report["totais_fechados_brl"]["conciliado_atribuicao_assistida"], "-10.05")
        self.assertEqual(report["totais_fechados_brl"]["recebimentos_liquidos_validos"], "-10.05")

    def test_phone_match_is_exact_not_inferred_from_name_or_partial_number(self):
        self.operations["interactions"][0]["customer_phone"] = "+999000000009"
        report = self.run_report()
        self.assertEqual(report["totais_fechados_brl"]["conciliado_atribuicao_assistida"], "0.00")
        self.assertEqual(report["totais_fechados_brl"]["conciliado_sem_interacao_elegivel"], "290.25")

    def test_aggregate_output_contains_no_phone_receipt_ids_evidence_or_free_text(self):
        self.operations["entities"][0]["status"] = "customer secret name"
        report = self.run_report()
        serialized = json.dumps(report)
        for forbidden in ("+999000000001", "synthetic-tx-a", "synthetic-reservation-a", "synthetic://receipt", "customer secret name"):
            self.assertNotIn(forbidden, serialized)
        self.assertIn("desconhecido", report["estados_operacionais_atual_export_por_movimento"])

    def test_output_is_deterministic_when_inputs_are_reordered(self):
        expected = self.run_report()
        self.operations["entities"].reverse()
        self.operations["interactions"].reverse()
        self.receipts.reverse()
        self.assertEqual(self.run_report(), expected)

    def test_parsers_reject_ambiguous_json_and_csv_headers(self):
        with self.assertRaisesRegex(ContractError, "DUPLICATE_JSON_KEY"):
            load_operations('{"restaurant_id":"one","restaurant_id":"two"}')
        with self.assertRaisesRegex(ContractError, "INVALID_RECEIPT_HEADERS"):
            load_receipts("transaction_id,amount_brl\na,10.00\n")

    def test_cli_outputs_only_status_and_does_not_replace_an_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "aggregate.json"
            args = ["--operations", str(FIXTURES / "reconciliation_operations.synthetic.json"), "--receipts", str(FIXTURES / "reconciliation_receipts.synthetic.csv"), "--restaurant-id", "synthetic_unit_a", "--start", "2026-09-01", "--end", "2026-09-08", "--output", str(output)]
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(main(args), 0)
                self.assertEqual(main(args), 1)
            self.assertEqual(json.loads(stdout.getvalue()), {"status": "complete", "diagnostic_count": 0})
            self.assertEqual(stderr.getvalue().strip(), "INVALID_LOCAL_INPUT_OR_OUTPUT")
            self.assertIn("input_sha256", json.loads(output.read_text()))


if __name__ == "__main__":
    unittest.main()
