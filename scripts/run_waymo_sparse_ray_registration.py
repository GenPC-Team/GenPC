#!/usr/bin/env python3
"""Run the opt-in sparse-LiDAR MoGe ray-surface registration adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import open3d as o3d
from scipy.ndimage import binary_dilation
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bidirectional_cycle_registration import visible_score
from src.moge_camera import MoGeProjector
from src.pointcloud_io import jsonable, load_points, write_compare, write_points
from src.ray_consistent_registration import apply_transform
from src.saved_camera import SavedCameraProjector, draw_projection_overlay, world_to_camera_axes
from src.sparse_moge_assimilation import (
    assimilate_native_moge_surface,
    calibrate_camera_ray_depth_gauge,
)
from src.sparse_lidar_prior_router import select_sparse_prior_candidate
from src.sparse_ray_registration import (
    camera_anchored_indexed_similarity,
    moge_to_saved_raster_convention,
    sparse_partial_to_moge_refine,
)
from src.two_camera_moge_bridge import (
    apply_image_affine,
    foreground_bbox,
    partial_uv_to_image_pixels,
    transferred_partial_to_moge_matches,
)


def _compact_visible(value: dict) -> dict:
    compact = {
        "objective": float(value["objective"]),
        "visible_3d": float(value["geometric"]["objective"]),
        "pair_count": int(len(value["geometric"]["partial_ids"])),
        "projection": {key: float(item) for key, item in value["projection"].items()},
    }
    # Missing LiDAR pixels are unknown, not free space.  Selection therefore
    # uses the one-sided observed surface and coverage terms without penalising
    # complete-prior pixels that have no sparse return.
    compact["sparse_observation_objective"] = float(
        .70 * compact["visible_3d"]
        + .25 * (1.0 - compact["projection"]["coverage"])
        + .05 * compact["projection"]["visible_depth_normalized"]
    )
    return compact


def _write_three_clouds(path: Path, partial: np.ndarray, initial: np.ndarray, refined: np.ndarray) -> None:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.concatenate((partial, initial, refined), axis=0))
    colors = np.concatenate((
        np.tile([.55, .55, .55], (len(partial), 1)),
        np.tile([.10, .35, .95], (len(initial), 1)),
        np.tile([.95, .10, .10], (len(refined), 1)),
    ))
    cloud.colors = o3d.utility.Vector3dVector(colors)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_point_cloud(str(path), cloud):
        raise IOError(path)


def run_case(
    bridge_info_path: Path,
    pixal_prior_path: Path,
    output_dir: Path,
    *,
    mainline_candidate_path: Path | None = None,
) -> dict:
    bridge_info_path = Path(bridge_info_path)
    bridge = json.loads(bridge_info_path.read_text(encoding="utf-8"))
    partial = load_points(Path(bridge["partial"]))
    moge = load_points(Path(bridge["camera2"]["native_moge"]))
    prior = load_points(pixal_prior_path)
    point_uv = np.load(bridge["point_uv"])
    source_mask = cv2.imread(bridge["camera1"]["semantic_mask"], cv2.IMREAD_GRAYSCALE)
    target_mask = cv2.imread(bridge["camera2"]["pixal_mask"], cv2.IMREAD_GRAYSCALE)
    if source_mask is None or target_mask is None:
        raise FileNotFoundError("bridge source/target mask is missing")
    if len(point_uv) != len(partial):
        raise ValueError("point_uv and partial point count differ")
    native_info = json.loads(Path(bridge["camera2"]["pixal_native_info"]).read_text(encoding="utf-8"))
    moge_info = native_info["moge"]
    native_projector = MoGeProjector(
        np.asarray(moge_info["output_keys"]["intrinsics"], dtype=np.float64),
        tuple(moge_info["image_hw"]), device="cpu",
    )
    moge_pixels, _ = native_projector.project(moge)
    camera1 = SavedCameraProjector.from_partial(
        partial, bridge["camera1"]["saved_camera"], padding=.15,
        image_shape=source_mask.shape, device="cpu",
    )
    saved_camera = torch.load(
        bridge["camera1"]["saved_camera"], map_location="cpu", weights_only=False,
    )
    camera_axes = world_to_camera_axes(saved_camera)
    camera1_to_camera2 = np.asarray(bridge["camera1_to_camera2"]["transform"], dtype=np.float64)
    flip_y = bool(bridge["point_uv_contract"]["flip_y"])
    camera1_pixels, valid = partial_uv_to_image_pixels(
        point_uv, source_mask.shape, flip_y=flip_y,
    )
    rounded = np.rint(camera1_pixels).astype(np.int64)
    inside = (
        valid
        & (rounded[:, 0] >= 0) & (rounded[:, 0] < source_mask.shape[1])
        & (rounded[:, 1] >= 0) & (rounded[:, 1] < source_mask.shape[0])
    )
    dilated_source = binary_dilation(
        source_mask > 0, structure=np.ones((5, 5), dtype=bool),
    )
    object_supported = np.zeros(len(partial), dtype=bool)
    object_supported[inside] = dilated_source[rounded[inside, 1], rounded[inside, 0]]
    valid &= object_supported
    mapped = apply_image_affine(camera1_pixels, camera1_to_camera2)
    target_bbox = foreground_bbox(target_mask)
    target_bbox_diagonal = float(np.linalg.norm(target_bbox[2:] - target_bbox[:2]))
    inherited_moge_to_partial = np.load(
        bridge_info_path.with_name("two_camera_pixal_moge_native_moge_to_partial.npy")
    )
    # Re-estimate the initial bridge from foreground-supported observations.
    # The generic bridge intentionally accepts every valid UV; this sparse
    # adapter must prevent background/clutter samples from being compressed
    # into the completed object's target bounding box.
    support_matches, support_match_info = transferred_partial_to_moge_matches(
        point_uv, source_mask.shape, camera1_to_camera2, moge_pixels,
        max_pixel_distance=3.0, flip_y=flip_y,
    )
    support_matches = support_matches[
        object_supported[support_matches[:, 0].astype(np.int64)]
    ]
    convention_step, convention = moge_to_saved_raster_convention(
        flip_saved_uv_y=flip_y,
    )
    convention_moge = apply_transform(moge, convention_step)
    if len(support_matches) >= 6:
        initial_moge_to_partial, support_fit = camera_anchored_indexed_similarity(
            convention_moge, partial, support_matches, camera_axes,
            diagonal=max(float(np.linalg.norm(np.ptp(partial[object_supported], axis=0))), 1e-8),
        )
        support_initial_used = True
    else:
        # With fewer than six indexed pairs the camera-anchored similarity is
        # under-constrained.  Keep the complete legacy bridge in its original
        # coordinate contract instead of feeding an improper convention factor
        # to a solver that is intentionally restricted to proper Sim(3).
        convention_step = np.eye(4, dtype=np.float64)
        convention_moge = moge
        convention = {
            "method": "legacy_bridge_fallback",
            "reason": "fewer_than_six_foreground_supported_pixel_matches",
            "flip_saved_uv_y": flip_y,
            "estimated_from_geometry": False,
        }
        initial_moge_to_partial = inherited_moge_to_partial
        support_fit = {
            "reason": "too_few_foreground_supported_pixel_matches",
            "fallback": "inherited_bridge_original_coordinate_contract",
        }
        support_initial_used = False
    refined_moge_to_partial, refinement = sparse_partial_to_moge_refine(
        convention_moge, partial, mapped, valid, moge_pixels, initial_moge_to_partial,
        target_mask_bbox_diagonal=target_bbox_diagonal,
    )
    pixal_to_moge = np.asarray(native_info["prior_to_native_moge"], dtype=np.float64)
    prior_native_moge_raw = apply_transform(prior, pixal_to_moge)
    prior_native_moge, ray_gauge_step, ray_gauge = calibrate_camera_ray_depth_gauge(
        prior_native_moge_raw, moge, native_projector,
    )
    assimilated_native, assimilation_pairs, assimilation = assimilate_native_moge_surface(
        prior_native_moge, moge, native_projector,
    )
    convention_assimilated = apply_transform(assimilated_native, convention_step)
    convention_prior = apply_transform(prior_native_moge, convention_step)
    calibrated_pixal_to_moge = ray_gauge_step @ pixal_to_moge
    total_initial_moge_to_partial = initial_moge_to_partial @ convention_step
    total_refined_moge_to_partial = refined_moge_to_partial @ convention_step
    initial_transform = total_initial_moge_to_partial @ calibrated_pixal_to_moge
    proposed_refined_transform = total_refined_moge_to_partial @ calibrated_pixal_to_moge
    initial = apply_transform(convention_assimilated, initial_moge_to_partial)
    proposed_refined = apply_transform(convention_assimilated, refined_moge_to_partial)
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-8)
    visible_before = _compact_visible(visible_score(
        partial, initial, camera1, diagonal, pixel_radius=5.,
    ))
    visible_proposed = _compact_visible(visible_score(
        partial, proposed_refined, camera1, diagonal, pixel_radius=5.,
    ))
    refinement_accepted = bool(
        visible_proposed["sparse_observation_objective"]
        < .995 * visible_before["sparse_observation_objective"]
    )
    if refinement_accepted:
        selected_moge_to_partial = refined_moge_to_partial
        refined_transform = proposed_refined_transform
        refined = proposed_refined
        visible_after = visible_proposed
    else:
        selected_moge_to_partial = initial_moge_to_partial
        refined_transform = initial_transform
        refined = initial
        visible_after = visible_before
    aligned_moge = apply_transform(convention_moge, selected_moge_to_partial)
    total_selected_moge_to_partial = selected_moge_to_partial @ convention_step
    refinement["selection"] = {
        "accepted": refinement_accepted,
        "criterion": "one_sided_sparse_observation_objective",
        "minimum_relative_improvement": .005,
        "before": visible_before["sparse_observation_objective"],
        "proposed": visible_proposed["sparse_observation_objective"],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "moge_camera_convention.npy", convention_step)
    np.save(output_dir / "convention_moge_to_partial.npy", selected_moge_to_partial)
    np.save(output_dir / "moge_to_partial.npy", total_selected_moge_to_partial)
    np.save(output_dir / "native_camera_ray_gauge.npy", ray_gauge_step)
    np.save(output_dir / "pixal_to_native_moge_calibrated.npy", calibrated_pixal_to_moge)
    np.save(output_dir / "pixal_to_partial.npy", refined_transform)
    np.save(output_dir / "sparse_ray_partial_ids.npy", refinement.pop("final_partial_ids"))
    np.save(output_dir / "sparse_ray_moge_ids.npy", refinement.pop("final_moge_ids"))
    np.save(output_dir / "native_moge_assimilation_pairs.npy", assimilation_pairs)
    write_points(output_dir / "native_moge_assimilated_prior_100k.ply", assimilated_native)
    write_points(output_dir / "camera_convention_prior_100k.ply", convention_prior)
    write_points(output_dir / "native_moge_calibrated_prior_100k.ply", prior_native_moge)
    write_points(output_dir / "registered_prior_100k.ply", refined)
    write_points(output_dir / "proposed_sparse_refined_prior_100k.ply", proposed_refined)
    write_points(output_dir / "aligned_native_moge.ply", aligned_moge)
    write_points(output_dir / "object_supported_partial.ply", partial[object_supported])
    write_compare(output_dir / "partial_gray_aligned_moge_red.ply", partial, aligned_moge)
    write_compare(output_dir / "partial_gray_registered_red.ply", partial, refined)
    _write_three_clouds(output_dir / "partial_gray_initial_blue_refined_red.ply", partial, initial, refined)
    _write_three_clouds(
        output_dir / "native_moge_gray_raw_blue_calibrated_red.ply",
        moge, prior_native_moge_raw, prior_native_moge,
    )
    semantic = Path(bridge["camera1"]["semantic_mask"]).with_name("img.png")
    if not semantic.is_file():
        semantic = Path(bridge["camera1"]["semantic_mask"])
    draw_projection_overlay(
        output_dir / "initial_saved_view.png", semantic, partial, initial, camera1,
    )
    draw_projection_overlay(
        output_dir / "refined_saved_view.png", semantic, partial, refined, camera1,
    )
    candidates = {"sparse_dense_bridge": refined}
    if mainline_candidate_path is not None:
        candidates["frozen_mainline"] = load_points(mainline_candidate_path)
    selected_name, selected, routing = select_sparse_prior_candidate(
        partial, convention_prior, candidates, camera1,
    )
    write_points(output_dir / "complete_100k.ply", selected)
    write_compare(output_dir / "partial_gray_complete_red.ply", partial, selected)
    draw_projection_overlay(
        output_dir / "selected_saved_view.png", semantic, partial, selected, camera1,
    )
    record = {
        "method": "waymo_camera_ray_gauge_sparse_partial_to_dense_moge_registration",
        "strict_zero_shot": True,
        "ground_truth_cd_emd_used": False,
        "mainline_modified": False,
        "inputs": {
            "bridge_info": str(bridge_info_path.resolve()),
            "partial": bridge["partial"],
            "pixal_prior": str(Path(pixal_prior_path).resolve()),
            "native_moge": bridge["camera2"]["native_moge"],
        },
        "refinement": refinement,
        "native_camera_ray_gauge": ray_gauge,
        "camera_coordinate_convention": convention,
        "native_moge_assimilation": assimilation,
        "sparse_candidate_routing": routing,
        "sparse_object_support": {
            "mask_dilation_pixels": 2,
            "supported_points": int(object_supported.sum()),
            "support_fraction": float(object_supported.mean()),
            "pixel_matches_before_support_filter": int(len(support_match_info.get("mapped_partial_pixels", []))),
            "pixel_matches_after_support_filter": int(len(support_matches)),
            "support_filtered_initial_used": bool(support_initial_used),
            "support_filtered_initial_fit": support_fit,
        },
        "visible_before": visible_before,
        "visible_proposed": visible_proposed,
        "visible_after": visible_after,
        "outputs": {
            "registered_prior": str((output_dir / "registered_prior_100k.ply").resolve()),
            "comparison": str((output_dir / "partial_gray_registered_red.ply").resolve()),
            "before_after": str((output_dir / "partial_gray_initial_blue_refined_red.ply").resolve()),
            "native_gauge_comparison": str(
                (output_dir / "native_moge_gray_raw_blue_calibrated_red.ply").resolve()
            ),
            "selected": str((output_dir / "complete_100k.ply").resolve()),
            "selected_comparison": str(
                (output_dir / "partial_gray_complete_red.ply").resolve()
            ),
        },
    }
    (output_dir / "sparse_ray_registration_info.json").write_text(
        json.dumps(jsonable(record), indent=2), encoding="utf-8",
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge-info", type=Path, required=True)
    parser.add_argument("--pixal-prior", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mainline-candidate", type=Path)
    args = parser.parse_args()
    record = run_case(
        args.bridge_info,
        args.pixal_prior,
        args.output_dir,
        mainline_candidate_path=args.mainline_candidate,
    )
    print(json.dumps(jsonable({
        "output": record["outputs"]["registered_prior"],
        "selected": record["outputs"]["selected"],
        "selected_route": record["sparse_candidate_routing"]["selected"],
        "accepted_levels": record["refinement"]["accepted_levels"],
        "visible_before": record["visible_before"],
        "visible_after": record["visible_after"],
    }), indent=2))


if __name__ == "__main__":
    main()
