import json
import tempfile
import unittest
from pathlib import Path

from app.data_generation.config import GeneratorConfig
from app.data_generation.generator import generate_dataset
from app.data_generation.io import write_dataset


class DatasetIOTests(unittest.TestCase):
    def test_ground_truth_written_to_separate_tree(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=20))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_dir = root / "demo" / "n20"
            gt_dir = root / "ground_truth" / "demo" / "n20"
            write_dataset(bundle, dataset_dir, gt_dir)

            payments_raw = (dataset_dir / "payments.json").read_text()
            settlements_raw = (dataset_dir / "settlements.json").read_text()
            self.assertNotIn("condition", payments_raw)
            self.assertNotIn("condition", settlements_raw)

            gt = json.loads((gt_dir / "ground_truth.json").read_text())
            self.assertEqual(len(gt), 20)
            self.assertIn("condition", gt[0])

    def test_demo_and_eval_datasets_written_independently(self):
        demo_bundle = generate_dataset(GeneratorConfig(seed=42, num_records=20))
        eval_bundle = generate_dataset(GeneratorConfig(seed=1337, num_records=20))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_dataset(demo_bundle, root / "demo" / "n20", root / "ground_truth" / "demo" / "n20")
            write_dataset(eval_bundle, root / "eval" / "n20", root / "ground_truth" / "eval" / "n20")

            demo_payments = json.loads((root / "demo" / "n20" / "payments.json").read_text())
            eval_payments = json.loads((root / "eval" / "n20" / "payments.json").read_text())
            demo_ids = {p["transaction_id"] for p in demo_payments}
            eval_ids = {p["transaction_id"] for p in eval_payments}
            self.assertTrue(demo_ids.isdisjoint(eval_ids))


if __name__ == "__main__":
    unittest.main()
