#!/usr/bin/env python3
"""Iterative posterior re-linearization for a fixed complete prior carrier.

This is the fixed post-registration stage of the mainline. It does not train
a generator or learn sample-specific weights. Each round uses
the same frozen, class-free :class:`PosteriorAdapter` to recompute partial OT
and four-view evidence from the current 100k carrier.  The resulting sequence
is analogous to a damped test-time optimization loop: residuals are
re-linearized after every update rather than amplified once from the initial
prior.

All rounds, including the unmodified registration state, are written to disk
for visual review.  Ground truth, CD, EMD, category labels and part labels are
not read.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, fields, replace
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bidirectional_cycle_registration import visible_score
from src.multiview_partial_correspondence import save_virtual_overlay_board
from src.multiview_partial_evidence import load_manifest_projectors
from src.observation_anchored_fusion import (
    ObservationAnchoredFusionConfig,
    collision_free_anchor_pairs,
    positive_multiview_pairs,
)
from src.pointcloud_io import jsonable, load_points, write_compare, write_points
from src.carrier_protection import project_reference_carrier_protection
from src.posterior_adapter import PosteriorAdapter, PosteriorAdapterConfig
from src.saved_camera import SavedCameraProjector, draw_projection_overlay


def _load_config(path: Path | None) -> PosteriorAdapterConfig:
    values: dict = {}
    if path is not None:
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, dict):
            raise ValueError("--config-json must contain a JSON object")
        known = {field.name for field in fields(PosteriorAdapterConfig)}
        unknown = sorted(set(values) - known)
        if unknown:
            raise ValueError(f"unknown PosteriorAdapterConfig fields: {unknown}")
    values["integrated_observation_fusion"] = True
    return PosteriorAdapterConfig(**values)


def _round_evidence(partial: np.ndarray, carrier: np.ndarray, view_projectors) -> dict:
    """Summarize only positive four-view evidence for an audit/stop signal."""
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    config = ObservationAnchoredFusionConfig(
        num_views=4,
        pixel_radius=1.0,
        cross_view_pixel_radius=2.0,
        cross_view_depth_ratio=.03,
        anchor_residual_ratio=.03,
    )
    pairs, positive_info = positive_multiview_pairs(
        partial, carrier, view_projectors, config=config, diagonal=diagonal,
    )
    anchors, assignment = collision_free_anchor_pairs(
        pairs, partial, carrier, max_residual=.03 * diagonal,
    )
    if len(anchors) == 0:
        return {
            "positive_evidence": positive_info,
            "assignment": assignment,
            "anchor_count": 0,
            "residual_median": None,
            "residual_p90": None,
        }
    residual = np.linalg.norm(partial[anchors[:, 0]] - carrier[anchors[:, 1]], axis=1)
    return {
        "positive_evidence": positive_info,
        "assignment": assignment,
        "anchor_count": int(len(anchors)),
        "residual_median": float(np.median(residual)),
        "residual_p90": float(np.quantile(residual, .90)),
    }


def _write_round(
    directory: Path,
    *,
    partial: np.ndarray,
    carrier: np.ndarray,
    semantic: Path,
    projector,
    initial: np.ndarray,
    record: dict,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_points(directory / "posterior_prior_100k.ply", carrier)
    write_compare(directory / "partial_gray_posterior_red.ply", partial, carrier)
    draw_projection_overlay(
        directory / "posterior_saved_view_projection.png",
        semantic, partial, carrier, projector,
    )
    save_virtual_overlay_board(
        directory / "posterior_virtual_views.png", partial, carrier,
        frame_points=initial,
    )
    (directory / "round_info.json").write_text(
        json.dumps(jsonable(record), indent=2) + "\n", encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--camera", type=Path, required=True)
    parser.add_argument("--semantic", type=Path, required=True)
    parser.add_argument("--multiview-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config-json", type=Path)
    parser.add_argument("--outer-rounds", type=int, default=3)
    parser.add_argument(
        "--update-strength", type=float, default=1.0,
        help=(
            "Shared dimensionless multiplier for the assimilation data weight and "
            "per-round displacement cap.  One exactly preserves the base config."
        ),
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--transport-all-views", action="store_true",
        help=(
            "Use all four saved cameras inside Partial OT. The default keeps "
            "Camera-1-only transport for backward-compatible mainline runs."
        ),
    )
    parser.add_argument("--render-size", type=int, default=512)
    parser.add_argument("--padding", type=float, default=.15)
    parser.add_argument(
        "--support-projection-strength", type=float, default=1.0,
        help="Category-free data-weight multiplier for residual-supported prior protection.",
    )
    parser.add_argument(
        "--support-continuation-hops", type=int, default=0,
        help=(
            "Optional finite rest-graph continuation for positive residual motion; "
            "zero keeps the default embedded-ARAP projection."
        ),
    )
    parser.add_argument(
        "--support-hard-target-constraints", action="store_true",
        help="Use exact, multi-view residual targets as ARAP graph constraints.",
    )
    parser.add_argument(
        "--support-coherent-raw-field", action="store_true",
        help=(
            "Keep only residual-dense, graph-coherent raw posterior motion "
            "before reference-carrier protection."
        ),
    )
    parser.add_argument(
        "--support-local-motion-selection", action="store_true",
        help=(
            "Select high local-motion positive anchors after removing the raw "
            "proposal's global Sim(3) drift."
        ),
    )
    parser.add_argument(
        "--support-motion-smoothing-steps", type=int, default=0,
        help=(
            "Optional graph-median smoothing passes on positive local-motion evidence "
            "before finite continuation; zero keeps raw evidence motion."
        ),
    )
    parser.add_argument(
        "--support-componentwise-similarity", action="store_true",
        help=(
            "Project coherent positive-evidence graph components onto local proper "
            "Sim(3) motions before smoothing and finite continuation."
        ),
    )
    parser.add_argument(
        "--support-component-similarity-core-hops", type=int, default=0,
        help=(
            "Rest-graph hops used to extend each coherent positive Sim(3) motion "
            "across its local carrier surface before smooth continuation."
        ),
    )
    parser.add_argument(
        "--support-component-similarity-gain", type=float, default=1.0,
        help=(
            "Dimensionless proper-Sim(3) extrapolation gain for coherent "
            "positive-evidence components; one preserves the inferred motion."
        ),
    )
    parser.add_argument(
        "--reference-prior-protection", action="store_true",
        help=(
            "Line-search each outer update against the registered complete carrier, "
            "preserving no-GT surface coverage and graph connectivity."
        ),
    )
    parser.add_argument(
        "--reference-protection-incremental-update", action="store_true",
        help=(
            "Apply each protected local update from the current re-linearized carrier, "
            "while retaining the registered prior as the immutable integrity reference."
        ),
    )
    parser.add_argument(
        "--reference-maximum-edge-stretch", type=float,
        help=(
            "Optional robust p99 rest-edge stretch budget for the experimental "
            "complete-prior guard; unset reuses the posterior configuration."
        ),
    )
    parser.add_argument(
        "--slender-rigidity-projection", action="store_true",
        help=(
            "Enable the existing covariance-and-graph-based rigid projection for "
            "automatically detected elongated structures in this diagnostic run."
        ),
    )
    args = parser.parse_args()
    if args.outer_rounds < 1:
        raise ValueError("--outer-rounds must be positive")
    if not 0. < args.update_strength <= 2.0:
        raise ValueError("--update-strength must lie in (0, 2]")
    if float(args.support_projection_strength) <= 0.:
        raise ValueError("--support-projection-strength must be positive")
    if int(args.support_continuation_hops) < 0:
        raise ValueError("--support-continuation-hops must be non-negative")
    if int(args.support_motion_smoothing_steps) < 0:
        raise ValueError("--support-motion-smoothing-steps must be non-negative")
    if int(args.support_component_similarity_core_hops) < 0:
        raise ValueError("--support-component-similarity-core-hops must be non-negative")
    if float(args.support_component_similarity_gain) <= 0.:
        raise ValueError("--support-component-similarity-gain must be positive")
    if args.reference_maximum_edge_stretch is not None and float(args.reference_maximum_edge_stretch) <= 1.:
        raise ValueError("--reference-maximum-edge-stretch must exceed one")

    initial = load_points(args.prior)
    partial = load_points(args.partial)
    projector = SavedCameraProjector.from_partial(
        partial, args.camera, padding=float(args.padding),
        image_shape=(int(args.render_size), int(args.render_size)), device=args.device,
    )
    views = load_manifest_projectors(args.multiview_manifest, resolution=int(args.render_size))
    if len(views) != 4:
        raise ValueError("iterative posterior re-linearization requires exactly four saved views")
    base = _load_config(args.config_json)
    # A single scalar uniformly changes only the same local assimilation update
    # already present in the baseline.  It does not widen correspondence gates
    # or change the prior/partial graph topology.
    config = replace(
        base,
        assimilation_data_weight=float(base.assimilation_data_weight) * float(args.update_strength),
        assimilation_displacement_ratio=min(
            float(base.assimilation_displacement_ratio) * float(args.update_strength), .20,
        ),
        slender_rigidity_projection=bool(args.slender_rigidity_projection),
    )
    config.validate()

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    current = initial.copy()
    rounds: list[dict] = []
    initial_evidence = _round_evidence(partial, current, views)
    initial_score = visible_score(partial, current, projector, max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9))
    _write_round(
        output / "round_00_registered",
        partial=partial, carrier=current, semantic=args.semantic, projector=projector,
        initial=initial,
        record={"round": 0, "state": "registered_prior", "four_view": initial_evidence,
                "camera1": initial_score},
    )
    best_round, best_key = 0, (
        float(initial_evidence["residual_median"])
        if initial_evidence["residual_median"] is not None else math.inf
    )

    for index in range(1, int(args.outer_rounds) + 1):
        adapter = PosteriorAdapter(config, device=args.device)
        updated, estimate, masks = adapter.run(
            current, partial, projector,
            view_projectors=views,
            transport_projectors=views if args.transport_all_views else (projector,),
        )
        reference_protection = {"active": False, "reason": "disabled"}
        if bool(args.reference_prior_protection):
            positive_support = np.asarray(masks["supported_residual"], dtype=bool)
            if bool(args.support_local_motion_selection):
                positive_support |= np.asarray(masks["assimilation_anchor"], dtype=bool)
            updated, reference_protection = project_reference_carrier_protection(
                initial, updated,
                neighbours=int(config.fine_neighbours),
                edge_ratio=float(config.fine_edge_ratio),
                minimum_hidden_coverage=float(config.minimum_hidden_coverage),
                minimum_edge_compression=float(config.minimum_edge_compression),
                maximum_edge_stretch=float(
                    config.maximum_edge_stretch
                    if args.reference_maximum_edge_stretch is None
                    else args.reference_maximum_edge_stretch
                ),
                coverage_resolution=int(config.coverage_resolution),
                # Only reliable *residual* support is allowed to retain its
                # full raw displacement.  Matched observation anchors are
                # already explained and remain implicit prior-protection
                # boundary conditions rather than being pulled again.
                positive_evidence_mask=positive_support,
                fallback_carrier=current,
                update_reference=current if bool(args.reference_protection_incremental_update) else None,
                deformation_config=config,
                support_data_weight_scale=float(args.support_projection_strength),
                support_continuation_hops=int(args.support_continuation_hops),
                support_hard_target_constraints=bool(args.support_hard_target_constraints),
                support_coherent_raw_field=bool(args.support_coherent_raw_field),
                support_local_motion_selection=bool(args.support_local_motion_selection),
                support_motion_smoothing_steps=int(args.support_motion_smoothing_steps),
                support_componentwise_similarity=bool(args.support_componentwise_similarity),
                support_component_similarity_core_hops=int(args.support_component_similarity_core_hops),
                support_component_similarity_gain=float(args.support_component_similarity_gain),
            )
        evidence = _round_evidence(partial, updated, views)
        camera1 = visible_score(
            partial, updated, projector,
            max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9),
        )
        movement = np.linalg.norm(updated - current, axis=1)
        row = {
            "round": index,
            "state": "posterior_relinearized",
            "four_view": evidence,
            "camera1": camera1,
            "movement_median": float(np.median(movement)),
            "movement_p95": float(np.quantile(movement, .95)),
            "movement_max": float(movement.max(initial=0.)),
            "estimate": estimate,
            "reference_prior_protection": reference_protection,
        }
        _write_round(
            output / f"round_{index:02d}",
            partial=partial, carrier=updated, semantic=args.semantic, projector=projector,
            initial=initial, record=row,
        )
        candidate_key = evidence["residual_median"]
        if candidate_key is not None and float(candidate_key) < best_key:
            best_round, best_key = index, float(candidate_key)
        rounds.append(row)
        current = updated

    summary = {
        "method": "test_time_residual_relinearization_fixed_posterior_adapter",
        "strict_zero_shot": True,
        "ground_truth_cd_emd_used": False,
        "category_or_part_rules_used": False,
        "inputs": {
            "prior": str(args.prior.resolve()), "partial": str(args.partial.resolve()),
            "camera": str(args.camera.resolve()), "semantic": str(args.semantic.resolve()),
            "multiview_manifest": str(args.multiview_manifest.resolve()),
        },
        "config_source": str(args.config_json.resolve()) if args.config_json else None,
        "resolved_config": asdict(config),
        "outer_rounds": int(args.outer_rounds),
        "update_strength": float(args.update_strength),
        "transport_all_views": bool(args.transport_all_views),
        "reference_prior_protection": bool(args.reference_prior_protection),
        "reference_protection_incremental_update": bool(args.reference_protection_incremental_update),
        "reference_maximum_edge_stretch": (
            None if args.reference_maximum_edge_stretch is None
            else float(args.reference_maximum_edge_stretch)
        ),
        "slender_rigidity_projection": bool(args.slender_rigidity_projection),
        "support_projection_strength": float(args.support_projection_strength),
        "support_continuation_hops": int(args.support_continuation_hops),
        "support_hard_target_constraints": bool(args.support_hard_target_constraints),
        "support_coherent_raw_field": bool(args.support_coherent_raw_field),
        "support_local_motion_selection": bool(args.support_local_motion_selection),
        "support_motion_smoothing_steps": int(args.support_motion_smoothing_steps),
        "support_componentwise_similarity": bool(args.support_componentwise_similarity),
        "support_component_similarity_core_hops": int(args.support_component_similarity_core_hops),
        "support_component_similarity_gain": float(args.support_component_similarity_gain),
        "round_00": {"four_view": initial_evidence, "camera1": initial_score},
        "rounds": rounds,
        "best_no_gt_observation_round": int(best_round),
        "best_no_gt_observation_median": best_key if math.isfinite(best_key) else None,
        "selection_note": (
            "Recorded no-GT evidence only; every round is retained for visual review. "
            "No ground truth or offline metric selected an output."
        ),
    }
    (output / "tto_summary.json").write_text(
        json.dumps(jsonable(summary), indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(jsonable({
        "output_dir": output.resolve(),
        "best_no_gt_observation_round": best_round,
        "best_no_gt_observation_median": best_key if math.isfinite(best_key) else None,
    }), indent=2))


if __name__ == "__main__":
    main()
