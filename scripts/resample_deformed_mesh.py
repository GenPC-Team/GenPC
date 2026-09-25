#!/usr/bin/env python3
"""Smoothly transfer carrier deformation to a mesh and resample its surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.deformation_aware_mesh import sample_expansion_compensation, transfer_carrier_deformation_to_mesh
from src.multiview_diagnostics import _load_world_mesh, apply_transform, estimate_ordered_similarity
from src.pointcloud_io import load_points, write_compare, write_points


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", type=Path, required=True)
    parser.add_argument("--source-carrier", type=Path, required=True)
    parser.add_argument("--registered-carrier", type=Path, required=True)
    parser.add_argument("--deformed-carrier", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--partial", type=Path)
    parser.add_argument("--point-count", type=int, default=125_000)
    parser.add_argument("--seed", type=int, default=6145)
    parser.add_argument("--interpolation-neighbours", type=int, default=8)
    parser.add_argument("--smoothing-steps", type=int, default=4)
    parser.add_argument("--smoothing-weight", type=float, default=.25)
    parser.add_argument("--expansion-point-ratio", type=float, default=.25)
    args = parser.parse_args()

    source = load_points(args.source_carrier)
    registered = load_points(args.registered_carrier)
    deformed = load_points(args.deformed_carrier)
    source_mesh = _load_world_mesh(args.mesh)
    mesh, report = transfer_carrier_deformation_to_mesh(
        source_mesh, source, registered, deformed,
        interpolation_neighbours=int(args.interpolation_neighbours),
        smoothing_steps=int(args.smoothing_steps),
        smoothing_weight=float(args.smoothing_weight),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    mesh.export(args.output_dir / "posterior_deformed_mesh.glb")
    np.random.seed(int(args.seed))
    points, _ = trimesh.sample.sample_surface(mesh, int(args.point_count))
    write_points(args.output_dir / "posterior_mesh_resampled.ply", points)
    transform, _ = estimate_ordered_similarity(source, registered)
    registered_mesh = source_mesh.copy()
    registered_mesh.vertices = apply_transform(registered_mesh.vertices, transform)
    expansion_count = int(round(float(args.expansion_point_ratio) * len(deformed)))
    expansion_points, expansion_report = sample_expansion_compensation(
        registered_mesh, mesh, count=expansion_count, seed=int(args.seed),
    )
    carrier_dense = np.concatenate((deformed, expansion_points), axis=0)
    write_points(args.output_dir / "posterior_carrier_mesh_densified.ply", carrier_dense)
    if args.partial is not None:
        write_compare(
            args.output_dir / "partial_gray_posterior_mesh_red.ply",
            load_points(args.partial), points,
        )
        write_compare(
            args.output_dir / "partial_gray_posterior_carrier_dense_red.ply",
            load_points(args.partial), carrier_dense,
        )
    report.update({
        "sampled_points": int(len(points)), "seed": int(args.seed),
        "carrier_preserving_densification": expansion_report,
        "carrier_preserving_output_points": int(len(carrier_dense)),
    })
    (args.output_dir / "mesh_resampling_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
