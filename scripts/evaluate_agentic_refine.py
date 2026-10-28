#!/usr/bin/env python3
"""Offline-only GT comparison; never imported by the refine agent.

Each prediction and its GT are sampled with the same deterministic FPS
protocol.  These metrics are for reporting, not for selecting agent actions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch
from fpsample import fps_sampling

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.offline_metrics import _points
from utils.loss_util import Completionloss


def evaluate(prediction: Path, ground_truth: Path, count: int, seed: int) -> dict:
    pred, gt = _points(prediction), _points(ground_truth)
    count = min(count, len(pred), len(gt))
    if count < 1:
        raise ValueError("an empty point cloud cannot be evaluated")
    rng = np.random.default_rng(seed)
    pred_ids = fps_sampling(pred, count, start_idx=int(rng.integers(len(pred))))
    gt_ids = fps_sampling(gt, count, start_idx=int(rng.integers(len(gt))))
    a = torch.from_numpy(pred[pred_ids]).unsqueeze(0).float().cuda()
    b = torch.from_numpy(gt[gt_ids]).unsqueeze(0).float().cuda()
    result = {"prediction": str(prediction.resolve()), "ground_truth": str(ground_truth.resolve()),
              "sample_count": count, "seed": seed}
    with torch.no_grad():
        result["cd_l1"] = float(Completionloss(loss_func="cd_l1").get_loss(a, b).item())
        result["cd_l2"] = float(Completionloss(loss_func="cd_l2").get_loss(a, b).item())
        result["emd"] = float(Completionloss(loss_func="emd").get_loss(a, b).item())
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gt", type=Path, required=True)
    parser.add_argument("--prediction", type=Path, action="append", required=True)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--count", type=int, default=16_384)
    parser.add_argument("--seed", type=int, default=6_145)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.prediction) != len(args.label):
        parser.error("one --label is required for each --prediction")
    rows = {label: evaluate(path, args.gt, args.count, args.seed)
            for label, path in zip(args.label, args.prediction)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"ground_truth_used_by_agent": False, "results": rows}, indent=2) + "\n")
    print(json.dumps(rows, indent=2), flush=True)


if __name__ == "__main__":
    main()
