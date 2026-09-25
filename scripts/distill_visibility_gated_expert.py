#!/usr/bin/env python3
"""Transplant an observed expert surface field into an intact prior.

The aggressive carrier is a geometric teacher only on the physical Camera-1
visible surface where it improves agreement with the observation.  We inherit
that improvement as a dense surface patch rather than sparse point handles.
Auxiliary views may confirm targets, but cannot expose or directly move
Camera-1-hidden prior surfaces.  An embedded ARAP solve keeps accepted teacher
patches exact, propagates their motion through a finite surface band, and fixes
the remaining complete prior.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.deformation_graph import edge_strain, local_surface_graph
from src.multiview_partial_correspondence import save_virtual_overlay_board
from src.multiview_partial_evidence import load_manifest_projectors
from src.multiview_proximal_tto import (
    MultiViewProximalTTOConfig,
    _geodesic_trust_region,
    _median_spacing,
    _visible_ids,
    multiview_ordered_proposal_evidence,
)
from src.pointcloud_io import jsonable, load_points, write_compare, write_points
from src.posterior_deformation import _embedded_arap_posterior, _orthographic_coverage


def _remove_small_components(graph: sparse.csr_matrix, mask: np.ndarray) -> np.ndarray:
    ids = np.flatnonzero(mask)
    if not len(ids):
        return mask
    count, labels = csgraph.connected_components(graph[ids][:, ids], directed=False)
    sizes = np.bincount(labels, minlength=count)
    minimum = max(24, int(np.ceil(.0003 * len(mask))))
    output = np.zeros_like(mask)
    output[ids[sizes[labels] >= minimum]] = True
    return output


def _calibrate_teacher_motion(
    reference: np.ndarray,
    expert: np.ndarray,
    partial: np.ndarray,
    support: np.ndarray,
    *,
    spacing: float,
    steps: int,
    tolerance_spacing: float,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Stop each observed teacher trajectory at its first good surface fit.

    A single global teacher gain over-moves carrier points that already lie
    near the observation while under-serving large coherent residuals.  The
    ordered expert carrier provides a trajectory, not an unconditional target:
    among uniformly sampled positions on that trajectory we select the
    *earliest* point whose nearest observed-surface distance is within a
    spacing-normalized tolerance of the best point.  This is category-free and
    uses neither GT nor semantic part labels.
    """
    ids = np.flatnonzero(np.asarray(support, dtype=bool))
    if not len(ids):
        return np.empty((0, 3)), np.empty(0), {"points": 0}
    source = np.asarray(reference[ids], dtype=np.float64)
    motion = np.asarray(expert[ids] - reference[ids], dtype=np.float64)
    alphas = np.linspace(0.0, 1.0, max(int(steps), 2), dtype=np.float64)
    tree = cKDTree(partial)
    distances = np.empty((len(alphas), len(ids)), dtype=np.float64)
    for index, alpha in enumerate(alphas):
        distances[index] = tree.query(
            source + alpha * motion, k=1, workers=-1,
        )[0]
    best = np.min(distances, axis=0)
    tolerance = float(tolerance_spacing) * float(spacing)
    admissible = distances <= (best[None, :] + tolerance)
    # argmax is safe because every column contains its minimum.
    selected_index = np.argmax(admissible, axis=0)
    selected_alpha = alphas[selected_index]
    targets = source + selected_alpha[:, None] * motion
    initial = distances[0]
    final = distances[selected_index, np.arange(len(ids))]
    report = {
        "points": int(len(ids)),
        "steps": int(len(alphas)),
        "tolerance": tolerance,
        "alpha_p10": float(np.quantile(selected_alpha, .10)),
        "alpha_p50": float(np.quantile(selected_alpha, .50)),
        "alpha_p90": float(np.quantile(selected_alpha, .90)),
        "full_amplitude_fraction": float(np.mean(selected_alpha >= 1.0 - 1e-12)),
        "initial_residual_mean": float(np.mean(initial)),
        "selected_residual_mean": float(np.mean(final)),
    }
    return targets, selected_alpha, report


def _propagate_structural_cohort(
    reference: np.ndarray,
    metric: sparse.csr_matrix,
    core: np.ndarray,
    core_targets: np.ndarray,
    *,
    spacing: float,
    radius_spacing: float,
    minimum_motion_spacing: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Move the hidden side of a locally observed structure with its surface.

    Camera visibility exposes only the front layer of a tail, leg, armrest, or
    other thin structure.  Treating those samples as isolated handles leaves a
    duplicated back layer.  We therefore use rest-surface geodesics to assign
    nearby hidden samples to their closest *observed* teacher seed, and give
    them the same calibrated displacement.  The radius is finite and
    spacing-normalized, so unrelated and remote unobserved geometry stays
    fixed.  The subsequent embedded-ARAP solve smooths the piecewise field.
    """
    core_ids = np.flatnonzero(np.asarray(core, dtype=bool))
    if not len(core_ids) or float(radius_spacing) <= 0.0:
        return np.zeros(len(reference), dtype=bool), np.empty((0, 3)), np.empty(0), {
            "points": 0, "radius": 0.0,
        }
    radius = float(radius_spacing) * float(spacing)
    try:
        distance, _, source = csgraph.dijkstra(
            metric, directed=False, indices=core_ids, min_only=True,
            return_predecessors=True, limit=radius,
        )
    except TypeError:
        distance_matrix = csgraph.dijkstra(
            metric, directed=False, indices=core_ids, limit=radius,
        )
        nearest = np.argmin(distance_matrix, axis=0)
        distance = distance_matrix[nearest, np.arange(len(reference))]
        source = core_ids[nearest]
    core_displacement = core_targets - reference[core_ids]
    source_to_local = np.full(len(reference), -1, dtype=np.int64)
    source_to_local[core_ids] = np.arange(len(core_ids), dtype=np.int64)
    source = np.asarray(source, dtype=np.int64)
    valid_source = (source >= 0) & (source < len(reference))
    local_source = np.full(len(reference), -1, dtype=np.int64)
    local_source[valid_source] = source_to_local[source[valid_source]]
    seed_motion = np.zeros(len(reference), dtype=np.float64)
    mapped = local_source >= 0
    seed_motion[mapped] = np.linalg.norm(core_displacement[local_source[mapped]], axis=1)
    cohort = (
        np.isfinite(distance)
        & (distance > 0.0)
        & (distance <= radius)
        & mapped
        & (seed_motion >= float(minimum_motion_spacing) * float(spacing))
    )
    cohort_ids = np.flatnonzero(cohort)
    cohort_displacement = core_displacement[local_source[cohort_ids]]
    cohort_targets = reference[cohort_ids] + cohort_displacement
    # Confidence decays smoothly to zero at the finite geodesic boundary.
    cohort_confidence = np.square(np.clip(1.0 - distance[cohort_ids] / radius, 0., 1.))
    report = {
        "points": int(len(cohort_ids)),
        "radius": radius,
        "radius_spacing": float(radius_spacing),
        "minimum_motion": float(minimum_motion_spacing) * float(spacing),
        "distance_p50": float(np.median(distance[cohort_ids])) if len(cohort_ids) else 0.0,
        "motion_p50": float(np.median(np.linalg.norm(cohort_displacement, axis=1)))
        if len(cohort_ids) else 0.0,
    }
    return cohort, cohort_targets, cohort_confidence, report


def _fit_low_frequency_structural_motion(
    reference: np.ndarray,
    proposal: np.ndarray,
    partial: np.ndarray,
    graph: sparse.csr_matrix,
    target_ids: np.ndarray,
    targets: np.ndarray,
    target_weights: np.ndarray,
    stable: np.ndarray,
    *,
    maximum_expansion: float,
    minimum_improvement: float,
    minimum_hidden_coverage: float,
    minimum_edge_compression: float,
    maximum_edge_stretch: float,
    spacing: float,
) -> tuple[np.ndarray, dict]:
    """Recover expansion modes without copying hidden-side proposal collapse.

    A robust affine fit extracts the low-rank strain supported by calibrated
    observed trajectories.  Its polar stretch is projected onto the positive
    semidefinite expansion cone: data-supported length/span changes survive,
    whereas contractions that could erase unobserved complete geometry are
    discarded.  The transform is anchored at the least-moving reliable
    observations and the following local stage handles residual detail.
    """
    reference = np.asarray(reference, dtype=np.float64)
    proposal = np.asarray(proposal, dtype=np.float64)
    partial = np.asarray(partial, dtype=np.float64)
    target_ids = np.asarray(target_ids, dtype=np.int64)
    targets = np.asarray(targets, dtype=np.float64)
    target_weights = np.asarray(target_weights, dtype=np.float64)
    stable = np.asarray(stable, dtype=bool)
    if not len(target_ids) or graph.nnz == 0:
        return reference.copy(), {"active": False, "reason": "empty_graph_or_targets"}

    unique_ids, inverse = np.unique(target_ids, return_inverse=True)
    weight_sum = np.zeros(len(unique_ids), dtype=np.float64)
    displacement_sum = np.zeros((len(unique_ids), 3), dtype=np.float64)
    positive_weight = np.maximum(target_weights, 1e-3)
    np.add.at(weight_sum, inverse, positive_weight)
    np.add.at(
        displacement_sum,
        inverse,
        positive_weight[:, None] * (targets - reference[target_ids]),
    )
    target_displacement = displacement_sum / np.maximum(weight_sum[:, None], 1e-12)
    normalized_weight = weight_sum / max(float(np.median(weight_sum[weight_sum > 0.])), 1e-12)
    # The proposal and reference are the same ordered carrier.  Fitting their
    # complete ordered field makes the low-rank estimate insensitive to which
    # side of a thin structure happened to be visible in Camera-1.  Only its
    # expansion component can survive the projection below.
    source = reference
    destination = proposal
    homogeneous = np.column_stack((source, np.ones(len(source), dtype=np.float64)))
    robust_weight = np.ones(len(source), dtype=np.float64)
    affine = np.zeros((4, 3), dtype=np.float64)
    fit_residual = np.zeros(len(source), dtype=np.float64)
    for _ in range(8):
        square_root_weight = np.sqrt(np.maximum(robust_weight, 1e-6))[:, None]
        affine = np.linalg.lstsq(
            homogeneous * square_root_weight,
            destination * square_root_weight,
            rcond=None,
        )[0]
        fit_residual = np.linalg.norm(homogeneous @ affine - destination, axis=1)
        median = float(np.median(fit_residual))
        scale = max(
            1.4826 * float(np.median(np.abs(fit_residual - median))), 1e-9,
        )
        huber = np.minimum(1.0, 2.5 * scale / np.maximum(fit_residual, 1e-12))
        robust_weight = huber

    linear = affine[:3].T
    _, singular_values, right = np.linalg.svd(linear, full_matrices=False)
    expansion = np.clip(singular_values, 1.0, float(maximum_expansion))
    stretch = right.T @ np.diag(expansion) @ right
    motion = np.linalg.norm(proposal - reference, axis=1)
    # Use the reliable, least-moving observed region as the centre of the
    # expansion.  Do not hard-reset stable points after applying the affine
    # field: a point-wise reset introduces a discontinuity exactly where the
    # stable and moving structures meet (for example, torso-to-limb joints).
    # Anchoring the continuous field preserves the same evidence while keeping
    # every graph edge under one coherent low-frequency deformation.
    low_motion = motion <= float(np.quantile(motion, .40))
    anchor_support = stable & low_motion
    if int(anchor_support.sum()) < 32:
        anchor_support = low_motion
    anchor = np.median(source[anchor_support], axis=0)
    raw_candidate = anchor + (reference - anchor) @ stretch.T
    displacement = raw_candidate - reference

    initial_target_error = np.linalg.norm(
        reference[unique_ids] - (reference[unique_ids] + target_displacement), axis=1,
    )
    partial_tree_before = cKDTree(reference)
    partial_residual_before = partial_tree_before.query(partial, k=1, workers=-1)[0]
    median_before = float(np.median(partial_residual_before))
    tail_threshold = float(np.quantile(partial_residual_before, .90))
    tail_before = float(np.mean(partial_residual_before[partial_residual_before >= tail_threshold]))
    trace: list[dict] = []
    accepted: tuple[np.ndarray, dict] | None = None
    for alpha in (1.0, .85, .70, .55, .40, .25, .15):
        candidate = reference + float(alpha) * displacement
        target_error = np.linalg.norm(
            candidate[unique_ids] - (reference[unique_ids] + target_displacement), axis=1,
        )
        improvement = 1.0 - float(np.median(target_error)) / max(
            float(np.median(initial_target_error)), 1e-12,
        )
        coverage, per_view = _orthographic_coverage(reference, candidate, resolution=192)
        strain = edge_strain(reference, candidate, graph)
        partial_residual = cKDTree(candidate).query(partial, k=1, workers=-1)[0]
        median_after = float(np.median(partial_residual))
        tail_after = float(np.mean(partial_residual[partial_residual >= np.quantile(partial_residual, .90)]))
        tail_improvement = 1.0 - tail_after / max(tail_before, 1e-12)
        record = {
            "alpha": float(alpha),
            "target_improvement": float(improvement),
            "hidden_coverage_ratio": float(coverage),
            "hidden_coverage_per_view": per_view,
            "partial_residual_median_before": median_before,
            "partial_residual_median_after": median_after,
            "partial_residual_tail_mean_before": tail_before,
            "partial_residual_tail_mean_after": tail_after,
            "partial_residual_tail_improvement": float(tail_improvement),
            **strain,
        }
        trace.append(record)
        if (
            tail_improvement >= max(float(minimum_improvement), .05)
            and median_after <= median_before + 1.25 * float(spacing)
            and coverage >= float(minimum_hidden_coverage)
            and strain["edge_stretch_p01"] >= float(minimum_edge_compression)
            and strain["edge_stretch_p99"] <= float(maximum_edge_stretch)
        ):
            accepted = candidate, record
            break
    if accepted is None:
        return reference.copy(), {
            "active": False,
            "reason": "no_pareto_valid_low_frequency_update",
            "target_points": int(len(unique_ids)),
            "stable_points": int(stable.sum()),
            "raw_singular_values": singular_values.tolist(),
            "expansion_singular_values": expansion.tolist(),
            "line_search": trace,
        }
    candidate, accepted_record = accepted
    return candidate, {
        "active": True,
        "field": "expansion_only_low_rank_structural_motion",
        "target_points": int(len(unique_ids)),
        "stable_points": int(stable.sum()),
        "moved_points": int(np.sum(np.linalg.norm(candidate - reference, axis=1) > 1e-8)),
        "mean_displacement": float(np.linalg.norm(candidate - reference, axis=1).mean()),
        "maximum_displacement": float(np.linalg.norm(candidate - reference, axis=1).max(initial=0.)),
        "maximum_expansion": float(maximum_expansion),
        "raw_singular_values": singular_values.tolist(),
        "expansion_singular_values": expansion.tolist(),
        "robust_fit_residual_median": float(np.median(fit_residual)),
        "anchor": anchor.tolist(),
        "line_search": trace,
        **accepted_record,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--expert", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--multiview-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--residual-quantile", type=float, default=.10)
    parser.add_argument("--minimum-improvement-spacing", type=float, default=.25)
    parser.add_argument(
        "--teacher-visibility-dilation-spacing", type=float, default=0.0,
        help=(
            "Optional narrow rest-surface dilation of the physical Camera-1 "
            "visible set. It admits silhouette neighbours, not auxiliary-view "
            "visibility."
        ),
    )
    parser.add_argument("--transition-spacing", type=float, default=10.0)
    parser.add_argument("--transition-motion", type=float, default=1.25)
    parser.add_argument("--transition-diagonal", type=float, default=.04)
    parser.add_argument("--minimum-hidden-coverage", type=float, default=.92)
    parser.add_argument("--minimum-edge-compression", type=float, default=.35)
    parser.add_argument("--node-minimum-edge-compression", type=float, default=.20)
    parser.add_argument("--trajectory-steps", type=int, default=17)
    parser.add_argument("--trajectory-tolerance-spacing", type=float, default=.20)
    parser.add_argument("--cohort-radius-spacing", type=float, default=0.0)
    parser.add_argument("--cohort-minimum-motion-spacing", type=float, default=.75)
    parser.add_argument("--low-frequency-structural-motion", action="store_true")
    parser.add_argument("--low-frequency-maximum-expansion", type=float, default=1.35)
    args = parser.parse_args()

    reference = load_points(args.reference)
    expert = load_points(args.expert)
    partial = load_points(args.partial)
    if reference.shape != expert.shape:
        raise ValueError("reference and expert must be corresponding ordered carriers")
    views = load_manifest_projectors(args.multiview_manifest, resolution=512)
    if not views:
        raise ValueError("the manifest contains no projectors")

    graph, metric, _ = local_surface_graph(reference, neighbours=10, edge_ratio=1.85)
    spacing = _median_spacing(reference)
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    acquisition_visible = np.zeros(len(reference), dtype=bool)
    acquisition_visible[_visible_ids(reference, views[0])] = True
    teacher_eligible, _ = _geodesic_trust_region(
        metric, acquisition_visible,
        radius=float(args.teacher_visibility_dilation_spacing) * spacing,
    )

    camera_config = MultiViewProximalTTOConfig(
        minimum_view_votes=1,
        proposal_pixel_radius=7.0,
        proposal_depth_ratio=.12,
        minimum_normalized_improvement=.04,
    )
    camera_support, camera_stable, camera_confidence, camera_report = (
        multiview_ordered_proposal_evidence(
            partial, reference, expert, [views[0]], config=camera_config,
            support_eligibility=teacher_eligible,
        )
    )
    consensus_config = MultiViewProximalTTOConfig()
    consensus_support, consensus_stable, consensus_confidence, consensus_report = (
        multiview_ordered_proposal_evidence(
            partial, reference, expert, views, config=consensus_config,
            support_eligibility=teacher_eligible,
        )
    )
    partial_tree = cKDTree(partial)
    reference_distance = partial_tree.query(reference, k=1, workers=-1)[0]
    expert_distance = partial_tree.query(expert, k=1, workers=-1)[0]
    improvement = reference_distance - expert_distance

    # The collapsed expert's main strength is dense local surface agreement.
    # Retain that strength on the physical acquisition-visible carrier, plus
    # at most a narrow rest-surface dilation for z-buffer silhouette samples,
    # rather than merely at sparse mutual pairs. Visibility is deliberately
    # not inferred from auxiliary re-projections: those cameras re-view the
    # same single-view scan and cannot reveal a hidden prior side.
    residual_floor = float(np.quantile(
        reference_distance[acquisition_visible], args.residual_quantile,
    ))
    minimum_improvement = float(args.minimum_improvement_spacing) * spacing
    dense_camera_support = (
        teacher_eligible
        & (improvement > minimum_improvement)
        & (reference_distance >= residual_floor)
    )
    support = dense_camera_support | camera_support | consensus_support
    support &= teacher_eligible
    support &= improvement > minimum_improvement
    support &= reference_distance >= residual_floor
    support = _remove_small_components(graph, support)
    dense_camera_support &= support
    confidence = np.maximum(camera_confidence, consensus_confidence)
    dense_confidence = np.clip(
        improvement / np.maximum(reference_distance, spacing), 0., 1.,
    )
    confidence[dense_camera_support] = np.maximum(
        confidence[dense_camera_support], dense_confidence[dense_camera_support],
    )
    core_support = support.copy()
    core_ids = np.flatnonzero(core_support)
    if len(core_ids) < 32:
        raise RuntimeError("insufficient acquisition-visible expert support")

    core_targets, selected_alpha, calibration_report = _calibrate_teacher_motion(
        reference, expert, partial, core_support,
        spacing=spacing,
        steps=args.trajectory_steps,
        tolerance_spacing=args.trajectory_tolerance_spacing,
    )
    cohort, cohort_targets, cohort_confidence, cohort_report = (
        _propagate_structural_cohort(
            reference, metric, core_support, core_targets,
            spacing=spacing,
            radius_spacing=args.cohort_radius_spacing,
            minimum_motion_spacing=args.cohort_minimum_motion_spacing,
        )
    )
    support = core_support | cohort
    target_ids = np.r_[core_ids, np.flatnonzero(cohort)]
    target_positions = np.vstack([core_targets, cohort_targets])
    target_confidence = np.r_[
        np.maximum(confidence[core_ids], 1e-3),
        np.maximum(cohort_confidence, 1e-3),
    ]

    observed_low_frequency_stable = (
        (camera_stable | consensus_stable)
        | (acquisition_visible & (reference_distance < residual_floor))
        | (acquisition_visible & (improvement <= 0.))
    ) & ~core_support
    low_frequency_reference = reference.copy()
    low_frequency_report = {"active": False, "reason": "disabled"}
    if bool(args.low_frequency_structural_motion):
        low_frequency_reference, low_frequency_report = _fit_low_frequency_structural_motion(
            reference,
            expert,
            partial,
            graph,
            core_ids,
            core_targets,
            np.maximum(confidence[core_ids], 1e-3),
            observed_low_frequency_stable,
            maximum_expansion=float(args.low_frequency_maximum_expansion),
            # A global structural mode is only justified when it explains a
            # substantial part of the long-tail observation residual.  This
            # dimensionless gate keeps already-good priors on the local path
            # while allowing true span/length deficiencies to activate it.
            minimum_improvement=.15,
            minimum_hidden_coverage=float(args.minimum_hidden_coverage),
            minimum_edge_compression=float(args.minimum_edge_compression),
            maximum_edge_stretch=6.0,
            spacing=float(spacing),
        )

    requested = np.linalg.norm(
        target_positions - low_frequency_reference[target_ids], axis=1,
    )
    transition_radius = max(
        float(args.transition_spacing) * spacing,
        float(args.transition_motion) * float(np.quantile(requested, .75)),
    )
    transition_radius = min(
        transition_radius, float(args.transition_diagonal) * diagonal,
    )
    active, _ = _geodesic_trust_region(metric, support, radius=transition_radius)
    observed_stable = (
        (camera_stable | consensus_stable)
        | (acquisition_visible & (reference_distance < residual_floor))
        | (acquisition_visible & (improvement <= 0.))
    ) & ~support
    stable = observed_stable | ~active
    result, solve, _ = _embedded_arap_posterior(
        low_frequency_reference,
        target_ids,
        target_positions,
        target_confidence,
        stable,
        node_fraction=.04,
        minimum_nodes=2400,
        maximum_nodes=7000,
        skinning_neighbours=4,
        neighbours=10,
        edge_ratio=1.85,
        attachment_edge_ratio=2.8,
        data_weight=12.0,
        screening=.002,
        iterations=8,
        maximum_displacement=.35 * diagonal,
        minimum_improvement=.001,
        minimum_edge_compression=float(args.minimum_edge_compression),
        maximum_edge_stretch=25.0,
        minimum_hidden_coverage=float(args.minimum_hidden_coverage),
        coverage_resolution=192,
        bending_regularization=.12,
        coherent_component_targets=False,
        preserve_target_amplitude=True,
        hard_target_constraints=True,
        node_minimum_edge_compression=float(args.node_minimum_edge_compression),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_points(args.output_dir / "registered_prior_100k.ply", reference)
    write_points(args.output_dir / "expert_local_fit_100k.ply", expert)
    write_points(args.output_dir / "low_frequency_prior_100k.ply", low_frequency_reference)
    write_points(args.output_dir / "posterior_expert_distilled_100k.ply", result)
    write_points(args.output_dir / "expert_target_points.ply", reference[core_support])
    write_points(args.output_dir / "structural_cohort_points.ply", reference[cohort])
    write_points(args.output_dir / "calibrated_target_points.ply", target_positions)
    write_compare(
        args.output_dir / "partial_gray_posterior_expert_distilled_red.ply",
        partial, result,
    )
    save_virtual_overlay_board(
        args.output_dir / "posterior_expert_distilled_views.png",
        partial, result, frame_points=reference, views=6, resolution=384,
    )
    report = {
        "method": "residual_calibrated_structural_cohort_distillation",
        "inputs": {
            "reference": str(args.reference.resolve()),
            "expert": str(args.expert.resolve()),
            "partial": str(args.partial.resolve()),
            "multiview_manifest": str(args.multiview_manifest.resolve()),
        },
        "ground_truth_used": False,
        "category_or_part_rules_used": False,
        "acquisition_visible_points": int(acquisition_visible.sum()),
        "strict_acquisition_visible_points": int(acquisition_visible.sum()),
        "teacher_eligible_points": int(teacher_eligible.sum()),
        "teacher_visibility_dilation_spacing": float(
            args.teacher_visibility_dilation_spacing
        ),
        "dense_camera1_teacher_points": int(dense_camera_support.sum()),
        "core_teacher_points": int(core_support.sum()),
        "structural_cohort_points": int(cohort.sum()),
        "target_points": int(support.sum()),
        "active_transition_points": int(active.sum()),
        "fixed_complete_prior_points": int((~active).sum()),
        "spacing": float(spacing),
        "residual_floor": residual_floor,
        "minimum_improvement": minimum_improvement,
        "transition_radius": float(transition_radius),
        "minimum_hidden_coverage": float(args.minimum_hidden_coverage),
        "minimum_edge_compression": float(args.minimum_edge_compression),
        "node_minimum_edge_compression": float(args.node_minimum_edge_compression),
        "low_frequency_structural_motion": low_frequency_report,
        "trajectory_calibration": calibration_report,
        "structural_cohort": cohort_report,
        "camera1_evidence": camera_report,
        "multiview_consensus": consensus_report,
        "solve": solve,
    }
    (args.output_dir / "expert_distillation_report.json").write_text(
        json.dumps(jsonable(report), indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(jsonable({
        "output_dir": str(args.output_dir.resolve()),
        "target_points": int(support.sum()),
        "active_transition_points": int(active.sum()),
        "fixed_complete_prior_points": int((~active).sum()),
        "solve": solve,
    }), indent=2))


if __name__ == "__main__":
    main()
