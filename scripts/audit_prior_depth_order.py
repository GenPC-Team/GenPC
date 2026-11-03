#!/usr/bin/env python3
"""No-GT ordinal-depth evidence for reviewing an Image Gen semantic prior.

MoGe's monocular scale is free, so only the ordering of observed depths is
compared. This is evidence for the visual reviewer, not an automatic score for
selecting an output or an input to registration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.stats import spearmanr
import torch


def compare_depth_order(observed_gray: np.ndarray, predicted_z: np.ndarray,
                        foreground: np.ndarray, *, seed: int = 6145) -> dict:
    """Compare two camera-depth images on visible, supported interior pixels."""
    from scipy.ndimage import binary_erosion

    observed_gray = np.asarray(observed_gray, dtype=np.float64)
    predicted_z = np.asarray(predicted_z, dtype=np.float64)
    supported = np.asarray(foreground, dtype=bool)
    if observed_gray.shape != predicted_z.shape or supported.shape != observed_gray.shape:
        raise ValueError("depth maps and foreground must have identical shapes")
    valid = (observed_gray > 4) & supported & np.isfinite(predicted_z) & (predicted_z > 0)
    interior = binary_erosion(valid, iterations=2)
    if interior.sum() >= 512:
        valid = interior
    visible_count = int(valid.sum())
    result = {"visible_pixels": visible_count, "sampled_pixels": 0,
              "spearman_depth_order": None, "pairwise_order_accuracy": None,
              "depth_gray_span": None, "reliable": False}
    if visible_count < 512:
        return result
    gray = observed_gray[valid]
    z = predicted_z[valid]
    rng = np.random.default_rng(seed)
    if len(gray) > 4096:
        sample = rng.choice(len(gray), 4096, replace=False)
        gray, z = gray[sample], z[sample]
    # Saved depth is brighter for nearer physical points; MoGe +Z is farther.
    observed_distance = 255.0 - gray
    span = float(np.quantile(gray, .95) - np.quantile(gray, .05))
    result["sampled_pixels"] = len(gray)
    result["depth_gray_span"] = span
    if span < 16 or np.std(z) < 1e-6:
        return result
    rho = float(spearmanr(observed_distance, z).statistic)
    i = rng.integers(len(gray), size=8192)
    j = rng.integers(len(gray), size=8192)
    separated = np.abs(gray[i] - gray[j]) >= max(10.0, .08 * span)
    agreement = ((observed_distance[i] - observed_distance[j])
                 * (z[i] - z[j])) > 0
    result.update({"spearman_depth_order": rho,
                   "pairwise_order_accuracy": float(np.mean(agreement[separated]))
                   if separated.any() else None,
                   "reliable": bool(separated.sum() >= 512),
                   "compared_pairs": int(separated.sum())})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth", type=Path, required=True)
    parser.add_argument("--semantic", type=Path, required=True)
    parser.add_argument("--rgba", type=Path, required=True)
    parser.add_argument("--moge-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    from moge.model.v2 import MoGeModel

    depth = np.asarray(Image.open(args.depth).convert("L"), dtype=np.uint8)
    h, w = depth.shape
    semantic = np.asarray(Image.open(args.semantic).convert("RGB").resize(
        (w, h), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    rgba = Image.open(args.rgba).convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    model_path = args.moge_model / "model.pt" if args.moge_model.is_dir() else args.moge_model
    model = MoGeModel.from_pretrained(str(model_path)).to(args.device).eval()
    tensor = torch.from_numpy(semantic).to(args.device).permute(2, 0, 1)
    with torch.no_grad():
        if str(args.device).startswith("cuda"):
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                predicted = model.infer(tensor)
        else:
            predicted = model.infer(tensor)
    z = predicted["points"][..., 2].detach().float().cpu().numpy()
    valid = predicted["mask"].detach().cpu().numpy().astype(bool)
    result = compare_depth_order(depth, z, (alpha >= 128) & valid)
    result.update({"schema": "compagent.prior_depth_order.v1", "ground_truth_used": False,
                   "depth": str(args.depth.resolve()), "semantic": str(args.semantic.resolve()),
                   "rgba": str(args.rgba.resolve()), "moge_model": str(model_path.resolve()),
                   "interpretation": "diagnostic only; monocular depth has a free scale"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
