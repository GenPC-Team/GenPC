"""Multi-view proximal test-time optimization for a complete prior carrier.

An observation-driven predictor may fit a partial scan very strongly but lose
global completeness.  This module treats that predictor as a proposal, not an
output.  Only ordered carrier motions that improve pixel and depth agreement
in multiple visible views become deformation targets.  A single ARAP solve
then absorbs those targets while stable observations and the immutable full
prior define the proximal trust region.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csgraph
from scipy.spatial import cKDTree

from src.deformation_graph import edge_strain, local_surface_graph
from src.posterior_deformation import _embedded_arap_posterior, _orthographic_coverage
from src.zbuffer import zbuffer_depth_with_indices


@dataclass(frozen=True)
class MultiViewProximalTTOConfig:
    acquisition_view_index: int = 0
    gate_support_by_acquisition_visibility: bool = True
    acquisition_visibility_dilation_spacing_multiplier: float = 2.0
    minimum_view_votes: int = 2
    proposal_pixel_radius: float = 6.0
    proposal_depth_ratio: float = .10
    stable_pixel_radius: float = 2.0
    stable_depth_ratio: float = .03
    minimum_normalized_improvement: float = .10
    support_residual_quantile: float = .50
    neighbours: int = 10
    edge_ratio: float = 1.85
    attachment_edge_ratio: float = 2.8
    data_weight: float = 8.0
    screening: float = .003
    bending_regularization: float = .08
    propagation_spacing_multiplier: float = 7.0
    propagation_motion_multiplier: float = 1.0
    maximum_propagation_diagonal_ratio: float = .012
    deformation_node_fraction: float = .03
    deformation_minimum_nodes: int = 1600
    deformation_maximum_nodes: int = 6000
    skinning_neighbours: int = 4
    arap_iterations: int = 6
    maximum_displacement_ratio: float = .20
    minimum_hidden_coverage: float = .91
    minimum_edge_compression: float = .40
    maximum_edge_stretch: float = 25.0
    coverage_resolution: int = 192
    outer_rounds: int = 4


def _median_spacing(points: np.ndarray) -> float:
    distances = cKDTree(np.asarray(points, dtype=np.float64)).query(
        points, k=2, workers=-1,
    )[0][:, 1]
    return max(float(np.median(distances[np.isfinite(distances)])), 1e-9)


def _geodesic_trust_region(
    metric_graph,
    support: np.ndarray,
    *,
    radius: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Expand observations only along the prior surface graph.

    Euclidean balls can leak from a thin appendage into a nearby body surface.
    Multi-source graph distance instead keeps the transition on the connected
    carrier structure.  The returned normalized distance is also useful as a
    smooth confidence coordinate for diagnostics.
    """
    support = np.asarray(support, dtype=bool)
    active = support.copy()
    normalized = np.full(len(support), np.inf, dtype=np.float64)
    seeds = np.flatnonzero(support)
    if not len(seeds):
        return active, normalized
    try:
        distance = csgraph.dijkstra(
            metric_graph, directed=False, indices=seeds, min_only=True,
        )
    except TypeError:
        # Compatibility path for older SciPy builds without ``min_only``.
        distance = np.min(
            csgraph.dijkstra(metric_graph, directed=False, indices=seeds), axis=0,
        )
    finite = np.isfinite(distance)
    active[finite] |= distance[finite] <= float(radius)
    normalized[finite] = distance[finite] / max(float(radius), 1e-12)
    return active, normalized


def _visible_ids(points: np.ndarray, projector) -> np.ndarray:
    uv, depth = projector.project(points)
    _, mask, indices = zbuffer_depth_with_indices(
        uv, depth, projector.image_shape, splat_radius=1,
    )
    return np.unique(indices[mask])


def multiview_ordered_proposal_evidence(
    partial: np.ndarray,
    current: np.ndarray,
    proposal: np.ndarray,
    projectors: list,
    *,
    config: MultiViewProximalTTOConfig,
    support_eligibility: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Find proposal motions supported by consistent pixel/depth improvement."""
    partial = np.asarray(partial, dtype=np.float64)
    current = np.asarray(current, dtype=np.float64)
    proposal = np.asarray(proposal, dtype=np.float64)
    if current.shape != proposal.shape:
        raise ValueError("current and proposal carriers must be ordered and shape-compatible")
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    count = len(current)
    if support_eligibility is None:
        support_eligibility = np.ones(count, dtype=bool)
    else:
        support_eligibility = np.asarray(support_eligibility, dtype=bool)
        if support_eligibility.shape != (count,):
            raise ValueError("support_eligibility must have one flag per carrier point")
    votes = np.zeros(count, dtype=np.int64)
    reverse_votes = np.zeros(count, dtype=np.int64)
    stable_votes = np.zeros(count, dtype=np.int64)
    improvement_sum = np.zeros(count, dtype=np.float64)
    reverse_improvement_sum = np.zeros(count, dtype=np.float64)
    valid_views = np.zeros(count, dtype=np.int64)
    per_view: list[dict] = []

    for view_index, projector in enumerate(projectors):
        partial_uv, partial_depth = projector.project(partial)
        current_uv, current_depth = projector.project(current)
        proposal_uv, proposal_depth = projector.project(proposal)
        partial_ids = _visible_ids(partial, projector)
        current_ids = _visible_ids(current, projector)
        proposal_ids = _visible_ids(proposal, projector)
        common = np.intersect1d(current_ids, proposal_ids, assume_unique=False)
        common = common[support_eligibility[common]]
        if not len(partial_ids) or not len(common):
            per_view.append({"view": int(view_index), "common_visible": 0, "votes": 0})
            continue
        tree = cKDTree(partial_uv[partial_ids])
        current_pixel, current_nearest = tree.query(current_uv[common], k=1, workers=-1)
        proposal_pixel, proposal_nearest = tree.query(proposal_uv[common], k=1, workers=-1)
        current_partial_ids = partial_ids[np.asarray(current_nearest, dtype=np.int64)]
        proposal_partial_ids = partial_ids[np.asarray(proposal_nearest, dtype=np.int64)]
        current_depth_error = np.abs(current_depth[common] - partial_depth[current_partial_ids])
        proposal_depth_error = np.abs(proposal_depth[common] - partial_depth[proposal_partial_ids])
        current_score = (
            current_pixel / max(float(config.proposal_pixel_radius), 1e-9)
            + current_depth_error / max(float(config.proposal_depth_ratio) * diagonal, 1e-9)
        )
        proposal_score = (
            proposal_pixel / max(float(config.proposal_pixel_radius), 1e-9)
            + proposal_depth_error / max(float(config.proposal_depth_ratio) * diagonal, 1e-9)
        )
        improvement = current_score - proposal_score
        proposal_consistent = (
            (proposal_pixel <= float(config.proposal_pixel_radius))
            & (proposal_depth_error <= float(config.proposal_depth_ratio) * diagonal)
            & (improvement >= float(config.minimum_normalized_improvement))
        )
        stable = (
            (current_pixel <= float(config.stable_pixel_radius))
            & (current_depth_error <= float(config.stable_depth_ratio) * diagonal)
        )
        valid_views[common] += 1
        votes[common] += proposal_consistent.astype(np.int64)
        stable_votes[common] += stable.astype(np.int64)
        improvement_sum[common] += np.where(proposal_consistent, improvement, 0.0)

        # Reverse transport recovers observations that lie outside the
        # current carrier support.  A partial sample votes for the ordered
        # proposal carrier that explains its pixel and depth better than the
        # current state.  Votes are binary per carrier and per view, so dense
        # scan regions cannot dominate the multi-view consensus.
        current_tree = cKDTree(current_uv[current_ids])
        proposal_tree = cKDTree(proposal_uv[proposal_ids])
        reverse_current_pixel, reverse_current_nearest = current_tree.query(
            partial_uv[partial_ids], k=1, workers=-1,
        )
        reverse_proposal_pixel, reverse_proposal_nearest = proposal_tree.query(
            partial_uv[partial_ids], k=1, workers=-1,
        )
        reverse_current_ids = current_ids[np.asarray(reverse_current_nearest, dtype=np.int64)]
        reverse_proposal_ids = proposal_ids[np.asarray(reverse_proposal_nearest, dtype=np.int64)]
        reverse_current_depth_error = np.abs(
            partial_depth[partial_ids] - current_depth[reverse_current_ids]
        )
        reverse_proposal_depth_error = np.abs(
            partial_depth[partial_ids] - proposal_depth[reverse_proposal_ids]
        )
        reverse_current_score = (
            reverse_current_pixel / max(float(config.proposal_pixel_radius), 1e-9)
            + reverse_current_depth_error
            / max(float(config.proposal_depth_ratio) * diagonal, 1e-9)
        )
        reverse_proposal_score = (
            reverse_proposal_pixel / max(float(config.proposal_pixel_radius), 1e-9)
            + reverse_proposal_depth_error
            / max(float(config.proposal_depth_ratio) * diagonal, 1e-9)
        )
        reverse_improvement = reverse_current_score - reverse_proposal_score
        reverse_consistent = (
            (reverse_proposal_pixel <= float(config.proposal_pixel_radius))
            & (reverse_proposal_depth_error <= float(config.proposal_depth_ratio) * diagonal)
            & (reverse_improvement >= float(config.minimum_normalized_improvement))
        )
        reverse_consistent &= support_eligibility[reverse_proposal_ids]
        reverse_ids = reverse_proposal_ids[reverse_consistent]
        if len(reverse_ids):
            unique_reverse_ids, reverse_inverse = np.unique(reverse_ids, return_inverse=True)
            best_reverse_improvement = np.full(len(unique_reverse_ids), -np.inf, dtype=np.float64)
            np.maximum.at(
                best_reverse_improvement,
                reverse_inverse,
                reverse_improvement[reverse_consistent],
            )
            reverse_votes[unique_reverse_ids] += 1
            reverse_improvement_sum[unique_reverse_ids] += best_reverse_improvement
        per_view.append({
            "view": int(view_index),
            "partial_visible": int(len(partial_ids)),
            "common_visible": int(len(common)),
            "votes": int(proposal_consistent.sum()),
            "reverse_votes": int(len(np.unique(reverse_ids))),
            "stable": int(stable.sum()),
        })

    forward_support = votes >= int(config.minimum_view_votes)
    reverse_support = reverse_votes >= int(config.minimum_view_votes)
    support = forward_support | reverse_support
    stable = stable_votes >= int(config.minimum_view_votes)
    support &= ~stable
    forward_confidence = improvement_sum / np.maximum(votes, 1)
    reverse_confidence = reverse_improvement_sum / np.maximum(reverse_votes, 1)
    confidence = np.maximum(forward_confidence, reverse_confidence)
    return support, stable, confidence, {
        "views": per_view,
        "support_points": int(support.sum()),
        "forward_support_points": int(forward_support.sum()),
        "reverse_support_points": int(reverse_support.sum()),
        "stable_points": int(stable.sum()),
        "acquisition_visible_eligible_points": int(support_eligibility.sum()),
        "vote_histogram": {
            str(level): int(np.count_nonzero(votes == level))
            for level in range(len(projectors) + 1)
        },
        "reverse_vote_histogram": {
            str(level): int(np.count_nonzero(reverse_votes == level))
            for level in range(len(projectors) + 1)
        },
    }


def optimize_multiview_proximal_posterior(
    reference: np.ndarray,
    partial: np.ndarray,
    predictor: np.ndarray,
    projectors: list,
    *,
    config: MultiViewProximalTTOConfig | None = None,
) -> tuple[np.ndarray, list[dict]]:
    """Run a compact predictor-corrector loop without GT or semantic parts."""
    config = config or MultiViewProximalTTOConfig()
    reference = np.asarray(reference, dtype=np.float64)
    partial = np.asarray(partial, dtype=np.float64)
    predictor = np.asarray(predictor, dtype=np.float64)
    if reference.shape != predictor.shape:
        raise ValueError("reference and predictor must be ordered carriers")
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    current = reference.copy()
    guard_graph, guard_metric, _ = local_surface_graph(
        reference, neighbours=int(config.neighbours), edge_ratio=float(config.edge_ratio),
    )
    spacing = _median_spacing(reference)
    support_eligibility = np.ones(len(reference), dtype=bool)
    acquisition_visible_points = len(reference)
    if bool(config.gate_support_by_acquisition_visibility):
        view_index = int(config.acquisition_view_index)
        if view_index < 0 or view_index >= len(projectors):
            raise ValueError("acquisition_view_index is outside the projector list")
        acquisition_visible = np.zeros(len(reference), dtype=bool)
        acquisition_visible[_visible_ids(reference, projectors[view_index])] = True
        acquisition_visible_points = int(acquisition_visible.sum())
        visibility_radius = (
            float(config.acquisition_visibility_dilation_spacing_multiplier) * spacing
        )
        support_eligibility, _ = _geodesic_trust_region(
            guard_metric, acquisition_visible, radius=visibility_radius,
        )
    trace: list[dict] = []
    for round_index in range(1, int(config.outer_rounds) + 1):
        support, stable, confidence, evidence = multiview_ordered_proposal_evidence(
            partial, current, predictor, projectors, config=config,
            support_eligibility=support_eligibility,
        )
        evidence["acquisition_visible_points"] = int(acquisition_visible_points)
        evidence["acquisition_gated_support"] = bool(
            config.gate_support_by_acquisition_visibility
        )
        partial_tree = cKDTree(partial)
        current_surface_distance = partial_tree.query(current, k=1, workers=-1)[0]
        predictor_surface_distance = partial_tree.query(predictor, k=1, workers=-1)[0]
        raw_support = support.copy()
        if np.any(raw_support):
            residual_floor = float(np.quantile(
                current_surface_distance[raw_support],
                float(config.support_residual_quantile),
            ))
            support &= current_surface_distance >= residual_floor
            support &= predictor_surface_distance < current_surface_distance
        else:
            residual_floor = 0.0
        evidence["raw_support_points"] = int(raw_support.sum())
        evidence["support_points"] = int(support.sum())
        evidence["support_residual_floor"] = float(residual_floor)
        target_ids = np.flatnonzero(support)
        if len(target_ids) < 32:
            trace.append({"round": round_index, "accepted": False, "reason": "insufficient_multiview_support", "evidence": evidence})
            break
        requested_motion = np.linalg.norm(
            predictor[target_ids] - current[target_ids], axis=1,
        )
        propagation_radius = max(
            float(config.propagation_spacing_multiplier) * spacing,
            float(config.propagation_motion_multiplier)
            * float(np.quantile(requested_motion, .75)),
        )
        propagation_radius = min(
            propagation_radius,
            float(config.maximum_propagation_diagonal_ratio) * diagonal,
        )
        active_band, graph_distance = _geodesic_trust_region(
            guard_metric, support, radius=propagation_radius,
        )
        # Observed stable samples and the carrier outside the residual's
        # structure-connected transition band define one proximal boundary.
        # This prevents global collapse without weakening supported endpoints.
        stable = stable | ~active_band
        weights = np.maximum(confidence[target_ids], 1e-3)
        candidate, solve, _ = _embedded_arap_posterior(
            current,
            target_ids,
            predictor[target_ids],
            weights,
            stable,
            node_fraction=float(config.deformation_node_fraction),
            minimum_nodes=int(config.deformation_minimum_nodes),
            maximum_nodes=int(config.deformation_maximum_nodes),
            skinning_neighbours=int(config.skinning_neighbours),
            neighbours=int(config.neighbours),
            edge_ratio=float(config.edge_ratio),
            attachment_edge_ratio=float(config.attachment_edge_ratio),
            data_weight=float(config.data_weight),
            screening=float(config.screening),
            iterations=int(config.arap_iterations),
            maximum_displacement=float(config.maximum_displacement_ratio) * diagonal,
            minimum_improvement=.001,
            minimum_edge_compression=float(config.minimum_edge_compression),
            maximum_edge_stretch=float(config.maximum_edge_stretch),
            minimum_hidden_coverage=.85,
            coverage_resolution=int(config.coverage_resolution),
            coherent_component_targets=True,
            bending_regularization=float(config.bending_regularization),
            preserve_target_amplitude=True,
            hard_target_constraints=False,
        )
        accepted = None
        trials: list[dict] = []
        for alpha in (1.0, .8, .6, .4, .25, .1):
            trial = current + float(alpha) * (candidate - current)
            coverage, coverage_views = _orthographic_coverage(
                reference, trial, resolution=int(config.coverage_resolution),
            )
            strain = edge_strain(reference, trial, guard_graph)
            record = {
                "alpha": float(alpha), "coverage": float(coverage),
                "coverage_views": coverage_views, **strain,
            }
            trials.append(record)
            if (
                coverage >= float(config.minimum_hidden_coverage)
                and strain["edge_stretch_p01"] >= float(config.minimum_edge_compression)
                and strain["edge_stretch_p99"] <= float(config.maximum_edge_stretch)
            ):
                accepted = trial, record
                break
        if accepted is None:
            trace.append({"round": round_index, "accepted": False, "reason": "proximal_trust_region_rejected", "evidence": evidence, "solve": solve, "trials": trials})
            break
        updated, accepted_record = accepted
        movement = np.linalg.norm(updated - current, axis=1)
        trace.append({
            "round": round_index, "accepted": True, "evidence": evidence,
            "solve": solve, "trust_region": accepted_record,
            "active_band_points": int(active_band.sum()),
            "propagation_radius": float(propagation_radius),
            "active_graph_distance_p95": float(np.quantile(
                graph_distance[active_band & np.isfinite(graph_distance)], .95,
            )),
            "movement_median": float(np.median(movement)),
            "movement_p95": float(np.quantile(movement, .95)),
            "movement_max": float(movement.max(initial=0.)),
        })
        current = updated
        if float(np.quantile(movement, .95)) < .25 * np.median(cKDTree(current).query(current, k=2, workers=-1)[0][:, 1]):
            break
    return current, trace
