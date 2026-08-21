import unittest
from decimal import Decimal

from app.data_generation.config import GeneratorConfig
from app.data_generation.enums import GroundTruthCondition
from app.data_generation.generator import generate_dataset


class GeneratorTests(unittest.TestCase):
    def test_deterministic_generation(self):
        first = generate_dataset(GeneratorConfig(seed=42, num_records=100))
        second = generate_dataset(GeneratorConfig(seed=42, num_records=100))
        self.assertEqual([p.to_dict() for p in first.payments], [p.to_dict() for p in second.payments])
        self.assertEqual([s.to_dict() for s in first.settlements], [s.to_dict() for s in second.settlements])
        self.assertEqual([g.to_dict() for g in first.ground_truth], [g.to_dict() for g in second.ground_truth])

    def test_record_counts(self):
        for n in (100, 250, 500):
            bundle = generate_dataset(GeneratorConfig(seed=42, num_records=n))
            self.assertEqual(len(bundle.payments), n)
            self.assertEqual(len(bundle.ground_truth), n)

    def test_required_fields_present(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=50))
        payment = bundle.payments[0]
        for attr in (
            "id", "transaction_id", "order_id", "customer_reference",
            "amount", "currency", "payment_method", "payment_status", "created_at",
        ):
            self.assertTrue(hasattr(payment, attr))
        self.assertGreater(payment.amount, 0)

    def test_all_anomaly_types_present(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=250))
        found = {g.condition for g in bundle.ground_truth}
        self.assertEqual(found, set(GroundTruthCondition))

    def test_ground_truth_matches_payments_one_to_one(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=100))
        gt_keys = {g.payment_transaction_id for g in bundle.ground_truth}
        payment_keys = {p.transaction_id for p in bundle.payments}
        self.assertEqual(gt_keys, payment_keys)
        self.assertEqual(len(bundle.ground_truth), len(bundle.payments))

    def test_duplicate_settlement_anomaly(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=250))
        dup_cases = [g for g in bundle.ground_truth if g.condition == GroundTruthCondition.DUPLICATE_SETTLEMENT]
        self.assertGreater(len(dup_cases), 0)
        for gt in dup_cases:
            matching = [s for s in bundle.settlements if s.transaction_reference == gt.payment_transaction_id]
            self.assertEqual(len(matching), 2)
            self.assertNotEqual(matching[0].settlement_id, matching[1].settlement_id)

    def test_missing_settlement_anomaly(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=250))
        missing_cases = [g for g in bundle.ground_truth if g.condition == GroundTruthCondition.MISSING_SETTLEMENT]
        self.assertGreater(len(missing_cases), 0)
        for gt in missing_cases:
            matching = [s for s in bundle.settlements if s.transaction_reference == gt.payment_transaction_id]
            self.assertEqual(len(matching), 0)

    def test_amount_mismatch_anomaly(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=250))
        cases = [g for g in bundle.ground_truth if g.condition == GroundTruthCondition.AMOUNT_MISMATCH]
        self.assertGreater(len(cases), 0)
        for gt in cases:
            self.assertGreater(gt.expected_amount_difference, Decimal("0.00"))

    def test_invalid_reference_anomaly_not_self_referential(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=250))
        cases = [g for g in bundle.ground_truth if g.condition == GroundTruthCondition.INVALID_REFERENCE]
        self.assertGreater(len(cases), 0)
        payment_txn_ids = {p.transaction_id for p in bundle.payments}
        for gt in cases:
            settlement = next(s for s in bundle.settlements if s.settlement_id in gt.settlement_ids)
            self.assertNotEqual(settlement.transaction_reference, gt.payment_transaction_id)
            self.assertNotIn(settlement.transaction_reference, payment_txn_ids)

    def test_eval_dataset_differs_from_demo(self):
        demo = generate_dataset(GeneratorConfig(seed=42, num_records=100))
        eval_ds = generate_dataset(GeneratorConfig(seed=1337, num_records=100))
        self.assertNotEqual(
            [p.transaction_id for p in demo.payments],
            [p.transaction_id for p in eval_ds.payments],
        )
        self.assertNotEqual(
            [str(p.amount) for p in demo.payments],
            [str(p.amount) for p in eval_ds.payments],
        )

    def test_eval_dataset_reproducible(self):
        first = generate_dataset(GeneratorConfig(seed=1337, num_records=100))
        second = generate_dataset(GeneratorConfig(seed=1337, num_records=100))
        self.assertEqual([p.to_dict() for p in first.payments], [p.to_dict() for p in second.payments])


if __name__ == "__main__":
    unittest.main()
