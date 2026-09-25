#!/usr/bin/env python3
"""Run the generic complete-prior posterior adapter on one registered case."""

from __future__ import annotations

import argparse
from dataclasses import asdict, fields
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pointcloud_io import jsonable, load_points, write_compare, write_points
from src.multiview_partial_correspondence import save_virtual_overlay_board
from src.multiview_partial_evidence import load_manifest_projectors
from src.posterior_adapter import PosteriorAdapter, PosteriorAdapterConfig
from src.posterior_visualization import save_support_overlay
from src.saved_camera import SavedCameraProjector, draw_projection_overlay


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--camera", type=Path, required=True)
    parser.add_argument("--semantic", type=Path, required=True)
    parser.add_argument(
        "--multiview-manifest", type=Path,
        help=(
            "Camera manifest providing four consistently reframed views for local "
            "observation assimilation; exact Camera-1 remains the transport view."
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--render-size", type=int, default=512)
    parser.add_argument("--padding", type=float, default=.15)
    parser.add_argument(
        "--output-profile", choices=("lean", "debug"), default="lean",
        help=(
            "lean keeps the final carrier and human-readable comparisons; "
            "debug additionally stores coarse fields, support masks, and OT arrays."
        ),
    )
    parser.add_argument(
        "--integrated-observation-fusion", action="store_true",
        help="Assimilate four-view partial evidence inside the smooth posterior field.",
    )
    parser.add_argument(
        "--config-json", type=Path,
        help=(
            "Optional JSON object overriding PosteriorAdapterConfig fields. "
            "Unknown keys are rejected and the resolved configuration is recorded."
        ),
    )
    args = parser.parse_args()

    prior, partial = load_points(args.prior), load_points(args.partial)
    projector = SavedCameraProjector.from_partial(
        partial, args.camera, padding=float(args.padding),
        image_shape=(int(args.render_size), int(args.render_size)), device=args.device,
    )
    config_values = {}
    if args.config_json is not None:
        config_values = json.loads(args.config_json.read_text(encoding="utf-8"))
        if not isinstance(config_values, dict):
            raise ValueError("--config-json must contain a JSON object")
        valid_fields = {field.name for field in fields(PosteriorAdapterConfig)}
        unknown = sorted(set(config_values) - valid_fields)
        if unknown:
            raise ValueError(f"unknown PosteriorAdapterConfig fields: {unknown}")
    if args.integrated_observation_fusion:
        config_values["integrated_observation_fusion"] = True
    config = PosteriorAdapterConfig(**config_values)
    adapter = PosteriorAdapter(config, device=args.device)
    view_projectors = None
    if args.multiview_manifest is not None:
        manifest_projectors = load_manifest_projectors(
            args.multiview_manifest, resolution=int(args.render_size),
        )
        if len(manifest_projectors) != 4:
            raise ValueError(
                "multiview posterior adaptation requires exactly four saved diagnostic views"
            )
        # Keep local assimilation in the consistently reframed diagnostic
        # camera family. The exact acquisition camera has a separate role in
        # structural transport below and must not silently replace one of the
        # four local views.
        view_projectors = manifest_projectors
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    posterior, info, masks = adapter.run(
        prior, partial, projector,
        view_projectors=view_projectors,
        # Exact physical Camera-1 is the structural correspondence authority.
        # The four consistently reframed views remain local assimilation views.
        transport_projectors=(projector,),
    )

    posterior_path = output / "posterior_prior_100k.ply"
    registered_comparison_path = output / "partial_gray_registered_red.ply"
    posterior_comparison_path = output / "partial_gray_posterior_red.ply"
    saved_view_path = output / "posterior_saved_view_projection.png"
    virtual_views_path = output / "posterior_virtual_views.png"
    write_points(posterior_path, posterior)
    write_compare(registered_comparison_path, partial, prior)
    write_compare(posterior_comparison_path, partial, posterior)
    draw_projection_overlay(
        saved_view_path, args.semantic,
        partial, posterior, projector,
    )
    save_virtual_overlay_board(
        virtual_views_path, partial, posterior,
        frame_points=prior,
    )
    output_paths = {
        "posterior": posterior_path,
        "registered_comparison": registered_comparison_path,
        "posterior_comparison": posterior_comparison_path,
        "saved_view": saved_view_path,
        "virtual_views": virtual_views_path,
    }
    if args.output_profile == "debug":
        coarse_path = output / "coarse_prior_100k.ply"
        support_path = output / "posterior_support_status.png"
        transport_path = output / "partial_ot_pairs.npy"
        field_path = output / "posterior_field.npz"
        write_points(coarse_path, prior + masks["coarse_displacement"])
        status_masks = {
            "locked": masks["supported_stable"],
            "editable": masks["supported_residual"],
            "protected": masks["unsupported"],
            "moved": masks["moved"],
        }
        save_support_overlay(
            support_path, args.semantic, prior, status_masks, projector,
        )
        pair_table = np.c_[
            masks["transport_partial_ids"], masks["transport_prior_ids"],
            masks["transport_weights"], masks["transport_costs"],
        ]
        np.save(transport_path, pair_table)
        np.savez_compressed(
            field_path, means=posterior.astype(np.float32),
            **{key: value for key, value in masks.items() if not key.startswith("transport_")},
        )
        output_paths.update({
            "coarse": coarse_path,
            "support_status": support_path,
            "transport_pairs": transport_path,
            "field": field_path,
        })
    record = {
        "method": "structure_aware_partial_ot_complete_gaussian_posterior",
        "strict_zero_shot": True,
        "ground_truth_cd_emd_used": False,
        "category_or_part_rules_used": False,
        "transport_policy": "exact_camera1",
        "output_profile": str(args.output_profile),
        "posterior_config": asdict(config),
        "posterior_config_source": (
            str(args.config_json.resolve()) if args.config_json is not None else None
        ),
        "inputs": {
            "prior": str(args.prior.resolve()), "partial": str(args.partial.resolve()),
            "camera": str(args.camera.resolve()), "semantic": str(args.semantic.resolve()),
            "multiview_manifest": (
                str(args.multiview_manifest.resolve())
                if args.multiview_manifest is not None else None
            ),
        },
        "estimate": info,
        "outputs": {key: str(path.resolve()) for key, path in output_paths.items()},
    }
    (output / "posterior_info.json").write_text(
        json.dumps(jsonable(record), indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(jsonable({"output_dir": output.resolve(), "estimate": info}), indent=2))


if __name__ == "__main__":
    main()
