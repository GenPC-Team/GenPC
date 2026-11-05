"""Offline-only CD-L1 and EMD evaluation.

Inference never imports this module, so ground truth cannot influence view
selection, registration, posterior adaptation, or stopping.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import open3d as o3d
import torch
from fpsample import fps_sampling

from utils.loss_util import Completionloss


def _points(path: Path) -> np.ndarray:
    points = np.asarray(o3d.io.read_point_cloud(str(path)).points, dtype=np.float32)
    if not len(points):
        raise ValueError(f"Point cloud is empty: {path}")
    return points


def evaluate_cd_emd(
    prediction: Path,
    ground_truth: Path,
    *,
    count: int = 16_384,
    seed: int = 6_145,
) -> tuple[float, float]:
    """Measure a frozen completion with deterministic FPS sampling."""
    return evaluate_cd_emd_repeated(prediction, ground_truth, count=count, seed=seed, repeats=1)[0]


def evaluate_cd_emd_repeated(
    prediction: Path,
    ground_truth: Path,
    *,
    count: int = 16_384,
    seed: int = 6_145,
    repeats: int = 3,
) -> list[tuple[float, float]]:
    """Repeat approximate EMD on the exact same deterministic FPS samples.

    Sampling and the metric definitions match ``evaluate_cd_emd``. Only
    repeated CPU sampling work is avoided; each EMD auction still runs anew.
    """
    if repeats < 1:
        raise ValueError("repeats must be positive")
    pred, gt = _points(prediction), _points(ground_truth)
    count = min(int(count), len(pred), len(gt))
    if count <= 0:
        raise ValueError("Cannot evaluate an empty point cloud")
    rng = np.random.default_rng(int(seed) % (2**32))
    pred_ids = fps_sampling(pred, count, start_idx=int(rng.integers(0, len(pred))))
    gt_ids = fps_sampling(gt, count, start_idx=int(rng.integers(0, len(gt))))
    pred_tensor = torch.from_numpy(pred[pred_ids]).unsqueeze(0).float().cuda()
    gt_tensor = torch.from_numpy(gt[gt_ids]).unsqueeze(0).float().cuda()
    measurements = []
    for _ in range(repeats):
        cd = Completionloss(loss_func="cd_l1").get_loss(gen=pred_tensor, gt=gt_tensor)
        emd = Completionloss(loss_func="emd").get_loss(gen=pred_tensor, gt=gt_tensor)
        measurements.append((float(cd.item()), float(emd.item())))
    return measurements
