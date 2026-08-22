"""Tests for the Stress / Dirty Data evaluation benchmark (Part B).

Split into two groups: pure noise-injection/reproducibility tests
(no DB) and API integration tests (needs the razorrecon_test
database, same pattern as test_api.py/test_evaluation.py).
"""
import os
import unittest
from decimal import Decimal

from app.evaluation.loader import load_eval_dataset
from app.evaluation.stress import NoiseConfig, apply_noise, summarize_noise


class NoiseReproducibilityTests(unittest.TestCase):
    def setUp(self):
        self.baseline = load_eval_dataset(name="n250")

    def test_same_seed_produces_byte_identical_noise_log(self):
        _, log1 = apply_noise(self.baseline, NoiseConfig(seed=9001))
        _, log2 = apply_noise(self.baseline, NoiseConfig(seed=9001))
        self.assertEqual(log1, log2)

    def test_same_seed_produces_identical_noisy_settlements(self):
        noisy1, _ = apply_noise(self.baseline, NoiseConfig(seed=9001))
        noisy2, _ = apply_noise(self.baseline, NoiseConfig(seed=9001))
        for s1, s2 in zip(
            sorted(noisy1.settlements, key=lambda s: s.settlement_id),
            sorted(noisy2.settlements, key=lambda s: s.settlement_id),
        ):
            self.assertEqual(s1.transaction_reference, s2.transaction_reference)
            self.assertEqual(s1.settled_amount, s2.settled_amount)
            self.assertEqual(s1.settled_at, s2.settled_at)

    def test_different_seed_produces_different_noise(self):
        _, log_a = apply_noise(self.baseline, NoiseConfig(seed=9001))
        _, log_b = apply_noise(self.baseline, NoiseConfig(seed=424242))
        self.assertNotEqual(log_a, log_b)

    def test_payment_records_are_never_perturbed(self):
        noisy, _ = apply_noise(self.baseline, NoiseConfig(seed=9001))
        self.assertEqual(
            [p.transaction_id for p in noisy.payments],
            [p.transaction_id for p in self.baseline.payments],
        )
        self.assertEqual(noisy.payments, self.baseline.payments)

    def test_ground_truth_is_untouched(self):
        noisy, _ = apply_noise(self.baseline, NoiseConfig(seed=9001))
        self.assertEqual(noisy.ground_truth, self.baseline.ground_truth)

    def test_settled_amounts_stay_positive(self):
        noisy, _ = apply_noise(self.baseline, NoiseConfig(seed=9001))
        for s in noisy.settlements:
            self.assertGreater(s.settled_amount, Decimal("0"))

    def test_source_dataset_on_disk_is_not_mutated(self):
        # Applying noise must never write back to data/eval/n250/ —
        # reload from disk and confirm it's still the clean baseline.
        apply_noise(self.baseline, NoiseConfig(seed=9001))
        reloaded = load_eval_dataset(name="n250")
        self.assertEqual(
            {s.settlement_id: s.transaction_reference for s in reloaded.settlements},
            {s.settlement_id: s.transaction_reference for s in self.baseline.settlements},
        )


class NoiseSummaryTests(unittest.TestCase):
    def test_summary_counts_match_log(self):
        baseline = load_eval_dataset(name="n250")
        _, log = apply_noise(baseline, NoiseConfig(seed=9001))
        summary = summarize_noise(log)

        self.assertEqual(summary["total_settlements"], len(log))
        self.assertEqual(
            summary["affected_settlements"], sum(1 for entry in log if entry["noise_applied"])
        )
        total_noise_events = sum(len(entry["noise_applied"]) for entry in log)
        self.assertEqual(sum(summary["noise_type_counts"].values()), total_noise_events)

    def test_zero_rate_config_produces_no_noise(self):
        baseline = load_eval_dataset(name="n250")
        quiet_config = NoiseConfig(
            seed=1,
            timestamp_offset_rate=0.0,
            delayed_timestamp_rate=0.0,
            rounding_diff_rate=0.0,
            reference_truncation_rate=0.0,
            missing_prefix_rate=0.0,
            case_whitespace_rate=0.0,
            duplicate_misalignment_rate=0.0,
        )
        noisy, log = apply_noise(baseline, quiet_config)
        self.assertEqual(summarize_noise(log)["affected_settlements"], 0)
        self.assertEqual(
            [s.transaction_reference for s in sorted(noisy.settlements, key=lambda s: s.settlement_id)],
            [s.transaction_reference for s in sorted(baseline.settlements, key=lambda s: s.settlement_id)],
        )


if __name__ == "__main__":
    unittest.main()
