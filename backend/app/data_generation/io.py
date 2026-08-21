"""Write a generated dataset to disk.

Ground truth is written to a physically separate directory tree from
payments/settlements so it's obvious it must never be shipped to the
reconciliation engine's normal input path.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.data_generation.generator import DatasetBundle


def write_dataset(bundle: DatasetBundle, dataset_dir: Path, ground_truth_dir: Path) -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    ground_truth_dir.mkdir(parents=True, exist_ok=True)

    payload = bundle.to_dict()
    (dataset_dir / "payments.json").write_text(json.dumps(payload["payments"], indent=2))
    (dataset_dir / "settlements.json").write_text(json.dumps(payload["settlements"], indent=2))

    gt_payload = bundle.ground_truth_to_dict()
    (ground_truth_dir / "ground_truth.json").write_text(json.dumps(gt_payload["ground_truth"], indent=2))
