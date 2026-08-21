"""Regenerate the demo/dev datasets and the held-out evaluation dataset.

Usage (from repo root):
    PYTHONPATH=backend python scripts/generate_data.py
"""
from pathlib import Path

from app.data_generation.config import GeneratorConfig
from app.data_generation.generator import generate_dataset
from app.data_generation.io import write_dataset

DEMO_SEED = 42
EVAL_SEED = 1337  # distinct from DEMO_SEED so eval never overlaps demo
DEMO_COUNTS = (100, 250, 500)
EVAL_COUNT = 250

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    for n in DEMO_COUNTS:
        bundle = generate_dataset(GeneratorConfig(seed=DEMO_SEED, num_records=n))
        write_dataset(
            bundle,
            dataset_dir=DATA_ROOT / "demo" / f"n{n}",
            ground_truth_dir=DATA_ROOT / "ground_truth" / "demo" / f"n{n}",
        )
        print(f"demo n={n}: {len(bundle.payments)} payments, {len(bundle.settlements)} settlements")

    eval_bundle = generate_dataset(GeneratorConfig(seed=EVAL_SEED, num_records=EVAL_COUNT))
    write_dataset(
        eval_bundle,
        dataset_dir=DATA_ROOT / "eval" / f"n{EVAL_COUNT}",
        ground_truth_dir=DATA_ROOT / "ground_truth" / "eval" / f"n{EVAL_COUNT}",
    )
    print(f"eval n={EVAL_COUNT}: {len(eval_bundle.payments)} payments, {len(eval_bundle.settlements)} settlements")


if __name__ == "__main__":
    main()
