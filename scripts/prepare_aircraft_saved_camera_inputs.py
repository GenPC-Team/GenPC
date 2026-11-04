#!/usr/bin/env python3
"""Rasterize the 40 aircraft partial scans in their recorded projection views.

Only each 2,048-point partial and its camera JSON are read. The denser saved
depth scan and complete GT are excluded from inference preparation.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil

import kaolin as kal
import numpy as np
import torch

from prepare_custom_saved_camera_inputs import prepare


ROOT = Path(__file__).resolve().parents[1]


def prepare_aircraft(data_root: Path, output_root: Path, sample: str,
                     resolution: int) -> dict:
    partial = data_root / "partial" / f"{sample}.ply"
    metadata_path = data_root / "metadata" / f"{sample}.json"
    if not partial.is_file() or not metadata_path.is_file():
        raise FileNotFoundError(f"missing aircraft partial or camera: {sample}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    extrinsic = np.asarray(metadata["extrinsic_world_to_camera"], dtype=np.float64)
    if extrinsic.shape != (4, 4):
        raise ValueError(f"{sample}: invalid extrinsic")
    source = output_root / "source" / sample / "partial_data" / "single_scan"
    source.mkdir(parents=True, exist_ok=True)
    shutil.copy2(partial, source / f"{sample}_partial.ply")
    shutil.copy2(metadata_path, source / "camera.json")
    camera = kal.render.camera.Camera.from_args(
        eye=torch.as_tensor(metadata["eye"], dtype=torch.float32),
        at=torch.as_tensor(metadata["target"], dtype=torch.float32),
        up=torch.as_tensor(-extrinsic[1, :3], dtype=torch.float32),
        fov=math.radians(float(metadata["fov_degrees"])),
        width=int(metadata["image_size"]),
        height=int(metadata["image_size"]),
        device="cpu",
    )
    view = camera.view_matrix()[0].detach().numpy()
    expected = extrinsic.copy()
    expected[1:3] *= -1  # Kaolin looks along -Z and uses up-positive image Y.
    if not np.allclose(view, expected, atol=2e-5):
        raise ValueError(f"{sample}: Kaolin camera disagrees with saved projection")
    torch.save(camera, source / "camera.pth")
    record = prepare(source, output_root / sample, resolution=resolution)
    record["source_aircraft_metadata"] = str(metadata_path.resolve())
    record["denser_depth_scan_used"] = False
    record["ground_truth_used"] = False
    (output_root / sample / "fixed_camera_preparation.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8",
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data" / "aircraft")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--samples", nargs="*")
    args = parser.parse_args()
    samples = args.samples or sorted(path.stem for path in
                                     (args.data_root / "partial").glob("*.ply"))
    records = [prepare_aircraft(args.data_root, args.output_root, sample,
                                args.resolution) for sample in samples]
    (args.output_root / "preparation_index.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({"prepared": len(records), "output_root": str(args.output_root.resolve())}))


if __name__ == "__main__":
    main()
