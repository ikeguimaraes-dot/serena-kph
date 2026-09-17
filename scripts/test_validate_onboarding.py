"""Offline safeguards for onboarding readiness and cost math; no production access."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("onboarding", HERE / "validate_onboarding.py")
onboarding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboarding)


class OnboardingTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "fixtures/onboarding/synthetic_complete.json").read_text())

    def test_cost_math_and_timing_are_explicit_synthetic_examples(self):
        report = onboarding.validate(self.data)
        self.assertEqual(report["structure_errors"], [])
        self.assertEqual(report["pricing"]["subscription_floor_brl"], "200.00")
        self.assertEqual(report["pricing"]["overage_floor_per_message_brl"], "0.100000")
        self.assertEqual(report["pricing"]["setup_floor_brl"], "120.00")
        self.assertEqual(report["pricing"]["status"], "synthetic_example")
        self.assertEqual(report["elapsed_hours"], {"onboarding": 48.0, "engineering": 2.0})
        self.assertEqual(report["blockers"], ["Synthetic dossier: never eligible for production"])

    def test_fixture_cannot_pass_by_flipping_the_synthetic_flag(self):
        self.data["synthetic"] = False
        self.assertFalse(onboarding.validate(self.data)["ready_from_declared_evidence"])

    def test_missing_costs_do_not_create_a_price(self):
        self.data["measurements"]["llm_cost_brl"] = None
        self.assertEqual(onboarding.validate(self.data)["pricing"], {"status": "pending"})

    def test_invalid_margins_and_nonfinite_costs_do_not_divide(self):
        for value in [1, -0.1, "NaN", "Infinity", True]:
            with self.subTest(value=value):
                data = copy.deepcopy(self.data)
                data["commercial"]["target_margin"] = value
                self.assertEqual(onboarding.validate(data)["pricing"], {"status": "pending"})

    def test_private_secrets_are_rejected_without_echoing_values(self):
        self.data["channels"]["auth_token"] = "DO-NOT-PRINT-SECRET"
        report = onboarding.validate(self.data)
        self.assertTrue(report["structure_errors"])
        self.assertNotIn("DO-NOT-PRINT-SECRET", json.dumps(report))

    def test_credential_url_is_rejected(self):
        self.data["catalog"]["source_ref"] = "postgres://name:secret@private.example/db"
        self.assertTrue(onboarding.validate(self.data)["structure_errors"])

    def test_handoff_acceptance_without_receipt_blocks(self):
        self.data["handoff"]["received_by_human"] = False
        self.assertTrue(any("receipt must be proved" in item for item in onboarding.validate(self.data)["blockers"]))

    def test_clinical_route_requires_specific_owner(self):
        self.data["business"]["vertical"] = "aesthetics"
        report = onboarding.validate(self.data)
        self.assertTrue(any("Clinical owner" in item for item in report["blockers"]))
        self.assertTrue(any("Clinical escalation" in item for item in report["blockers"]))

    def test_clinical_risk_is_required_even_for_another_vertical(self):
        self.data["business"]["vertical"] = "other"
        self.data["business"]["clinical_risk"] = True
        report = onboarding.validate(self.data)
        self.assertTrue(any("Clinical owner" in item for item in report["blockers"]))

    def test_real_capacity_and_recovery_evidence_cannot_be_omitted(self):
        self.data["agenda"]["capacity_evidence_ref"] = None
        self.data["access_inventory"][0]["recovery_tested_at"] = None
        report = onboarding.validate(self.data)
        self.assertTrue(any("capacity_evidence_ref" in item for item in report["blockers"]))
        self.assertTrue(any("Recovery test date" in item for item in report["blockers"]))

    def test_below_floor_price_requires_explicit_exception(self):
        self.data["commercial"]["subscription_price_brl"] = 1
        report = onboarding.validate(self.data)
        self.assertTrue(any("below the cost floor" in item for item in report["blockers"]))

    def test_invalid_chronology_is_an_error(self):
        self.data["milestones"]["pilot_live_at"] = "2026-09-01T00:00:00Z"
        self.assertTrue(onboarding.validate(self.data)["structure_errors"])

    def test_blank_template_is_valid_draft_and_not_ready(self):
        template = json.loads((HERE.parent / "docs/serena-os/onboarding/template.json").read_text())
        report = onboarding.validate(template)
        self.assertEqual(report["structure_errors"], [])
        self.assertTrue(report["blockers"])
        self.assertFalse(report["ready_from_declared_evidence"])


if __name__ == "__main__":
    unittest.main()
