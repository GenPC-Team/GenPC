#!/usr/bin/env python3
"""Probe a category-free residual-consensus structural rigid field.

This diagnostic does not read GT or metrics.  It first estimates local proper
SE(3) consensus motions from four-view collision-free partial evidence.  For
each motion, an s-t minimum cut separates its transform-supported source from
low-residual stable support on the prior surface graph.  The selected source
side is the smallest structurally coherent carrier region that can inherit the
motion; a short graph collar keeps its attachment continuous.

The script is deliberately an opt-in probe.  It is not part of the default
pipeline until it improves distinct identities with one frozen configuration.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import igraph as ig
import numpy as np
from scipy.sparse import csgraph
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.deformation_graph import edge_strain, local_surface_graph
from src.multiview_partial_correspondence import save_virtual_overlay_board
from src.multiview_partial_evidence import load_manifest_projectors
from src.observation_anchored_fusion import (
    ObservationAnchoredFusionConfig,
    collision_free_anchor_pairs,
    positive_multiview_pairs,
)
from src.pointcloud_io import jsonable, load_points, write_compare, write_points
from src.posterior_adapter import (
    PosteriorAdapterConfig,
    _median_spacing,
    _residual_rigid_consensus_targets,
    partial_optimal_transport,
)


def _motion_consistent_core(
    prior: np.ndarray,
    partial: np.ndarray,
    graph,
    model: dict[str, np.ndarray],
    seed_ids: np.ndarray,
    post_transform_support_ids: np.ndarray,
    *,
    tolerance: float,
) -> tuple[list[np.ndarray], dict[str, int | float]]:
    """Close a motion over independently observed, transform-consistent parts.

    A sparse scan often breaks one physical structure into several connected
    components in a thresholded surface graph.  Keeping only the component
    containing the RANSAC seed silently discards another wing, leg, handle,
    or blade that supports the *same* proper motion.  This closure includes a
    disconnected component only when the transformed prior independently has
    collision-free multi-view evidence there.  It therefore propagates a
    motion by geometry and observation, never by object identity, symmetry,
    or a predefined part count.
    """
    rotation = np.asarray(model["rotation"], dtype=np.float64)
    translation = np.asarray(model["translation"], dtype=np.float64)
    transformed = prior @ rotation.T + translation
    partial_tree = cKDTree(partial)
    before_distance = partial_tree.query(prior, k=1, workers=-1)[0]
    after_distance = partial_tree.query(transformed, k=1, workers=-1)[0]
    supported = after_distance <= tolerance
    seed_ids = np.asarray(seed_ids, dtype=np.int64)
    post_transform_support_ids = np.asarray(post_transform_support_ids, dtype=np.int64)
    seed_ids = seed_ids[supported[seed_ids]]
    if not len(seed_ids):
        return [], {
            "transform_supported_points": int(supported.sum()),
            "seed_points": 0,
            "post_transform_support_points": int(len(post_transform_support_ids)),
            "selected_components": 0,
            "closure_components": 0,
        }
    supported_ids = np.flatnonzero(supported)
    supported_graph = graph[supported_ids][:, supported_ids].tocsr()
    component_count, labels = csgraph.connected_components(supported_graph, directed=False)
    lookup = np.full(len(prior), -1, dtype=np.int64)
    lookup[supported_ids] = np.arange(len(supported_ids), dtype=np.int64)
    seed_labels = np.unique(labels[lookup[seed_ids]])
    post_transform_support_ids = post_transform_support_ids[supported[post_transform_support_ids]]
    support_labels = labels[lookup[post_transform_support_ids]] if len(post_transform_support_ids) else np.empty(0, dtype=np.int64)
    component_size = np.bincount(labels, minlength=component_count)
    component_observations = np.bincount(support_labels, minlength=component_count)
    component_before = np.bincount(
        labels, weights=before_distance[supported_ids], minlength=component_count,
    ) / np.maximum(component_size, 1)
    component_after = np.bincount(
        labels, weights=after_distance[supported_ids], minlength=component_count,
    ) / np.maximum(component_size, 1)
    component_gain = 1. - component_after / np.maximum(component_before, 1e-12)
    # The floor scales only with observed evidence.  It suppresses chance
    # nearest-neighbour contact while retaining an independently visible thin
    # branch at a different sampling density.
    minimum_observations = max(8, int(math.ceil(.005 * len(post_transform_support_ids))))
    observation_density = component_observations / np.maximum(component_size, 1)
    closure_labels = np.flatnonzero(
        (component_observations >= minimum_observations)
        & (observation_density >= .0125)
        # A closure component must be genuinely explained by this motion,
        # rather than merely remain close because it was already aligned or
        # lies on a broad symmetric body surface.
        & (component_gain >= .25)
    )
    selected_labels = np.unique(np.r_[seed_labels, closure_labels])
    components = [
        supported_ids[labels == label].astype(np.int64, copy=False)
        for label in selected_labels
    ]
    return components, {
        "transform_supported_points": int(supported.sum()),
        "seed_points": int(len(seed_ids)),
        "post_transform_support_points": int(len(post_transform_support_ids)),
        "minimum_component_observations": int(minimum_observations),
        "selected_components": int(len(selected_labels)),
        "closure_components": int(len(np.setdiff1d(closure_labels, seed_labels))),
        "closure_gain_median": float(np.median(component_gain[closure_labels]))
        if len(closure_labels) else 0.,
    }


def _min_cut_region(
    graph,
    core: np.ndarray,
    stable_ids: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """Select the source-side structural region with an affinity graph cut."""
    count = graph.shape[0]
    stable_ids = np.setdiff1d(stable_ids, core, assume_unique=False)
    if len(core) < 16 or len(stable_ids) < 16:
        return np.empty(0, dtype=np.int64), {"active": False, "reason": "insufficient_terminals"}
    rows, cols = graph.nonzero()
    upper = rows < cols
    rows, cols = rows[upper], cols[upper]
    capacities = np.asarray(graph[rows, cols]).reshape(-1)
    terminal_capacity = float(capacities.sum() + 1.)
    source_vertex, sink_vertex = count, count + 1
    edge_list = list(zip(rows.tolist(), cols.tolist()))
    edge_list += [(source_vertex, int(node)) for node in core]
    edge_list += [(sink_vertex, int(node)) for node in stable_ids]
    flow_graph = ig.Graph(n=count + 2, edges=edge_list, directed=False)
    result = flow_graph.st_mincut(
        source_vertex, sink_vertex,
        capacity=capacities.tolist() + [terminal_capacity] * (len(core) + len(stable_ids)),
    )
    source_partition, _ = result.partition
    region = np.asarray([node for node in source_partition if node < count], dtype=np.int64)
    return region, {
        "active": True,
        "method": "prior_affinity_st_min_cut",
        "core_points": int(len(core)),
        "stable_terminals": int(len(stable_ids)),
        "region_points": int(len(region)),
        "region_fraction": float(len(region) / count),
        "cut_value": float(result.value),
        "cut_edges": int(len(result.cut)),
    }


def _graph_collar(graph, region: np.ndarray, *, steps: int) -> np.ndarray:
    weight = np.zeros(graph.shape[0], dtype=np.float64)
    weight[region] = 1.
    frontier = weight > 0.
    for step in range(int(steps)):
        reached = np.asarray(graph @ frontier.astype(np.float64)).reshape(-1) > 0.
        reached &= weight <= 0.
        if not np.any(reached):
            break
        weight[reached] = float(steps - step) / float(steps + 1)
        frontier = reached
    return weight


def _field_integrity(
    reference: np.ndarray,
    candidate: np.ndarray,
    graph,
    *,
    minimum_edge_compression: float,
    maximum_edge_stretch: float,
) -> tuple[bool, dict[str, float]]:
    """Reject a proposed structural field if it tears or collapses the prior.

    This intentionally checks only quantities available at test time.  The
    edge ratios are normalized by the fixed carrier graph, so their limits do
    not encode an object class, coordinate axis, or absolute scene scale.
    """
    strain = edge_strain(reference, candidate, graph)
    passed = (
        float(strain["edge_stretch_p01"]) >= float(minimum_edge_compression)
        and float(strain["edge_stretch_p99"]) <= float(maximum_edge_stretch)
    )
    return passed, strain


def _kinematic_pivot_path(
    prior: np.ndarray,
    metric,
    core: np.ndarray,
    rotation: np.ndarray,
    translation: np.ndarray,
    *,
    spacing: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, int | float | bool]]:
    """Connect a rotating residual core to its data-derived near-fixed locus.

    A local proper SE(3) with non-negligible rotation has a fixed locus (an
    axis in the usual case).  If a thin observed branch is cut away from this
    locus, applying the transform through a collar bends or tears it.  We
    therefore retain the shortest *prior-surface* path from the moving core
    to its near-fixed locus.  This is a kinematic property of any articulated
    substructure; it contains no assumption about a limb, rotor, or object
    category.
    """
    core = np.asarray(core, dtype=np.int64)
    angle = math.degrees(math.acos(float(np.clip(
        (np.trace(rotation) - 1.) * .5, -1., 1.,
    ))))
    displacement = np.linalg.norm(prior @ rotation.T + translation - prior, axis=1)
    core_motion = float(np.median(displacement[core])) if len(core) else 0.
    fixed_limit = max(2.0 * float(spacing), .20 * core_motion)
    fixed_ids = np.flatnonzero(displacement <= fixed_limit).astype(np.int64)
    if angle < 5.0 or len(core) < 8 or len(fixed_ids) < 8:
        return core, fixed_ids, {
            "active": False, "rotation_degrees": float(angle),
            "fixed_locus_points": int(len(fixed_ids)), "path_points": 0,
        }
    distances, nearest = cKDTree(prior[fixed_ids]).query(prior[core], k=1, workers=-1)
    source_local = int(np.argmax(distances))
    source = int(core[source_local])
    target = int(fixed_ids[int(nearest[source_local])])
    _, predecessor = csgraph.dijkstra(
        metric, directed=False, indices=source, return_predecessors=True,
    )
    path: list[int] = []
    current = target
    while current >= 0 and current != source:
        path.append(int(current))
        current = int(predecessor[current])
    if current == source:
        path.append(source)
    else:
        path = []
    augmented = np.unique(np.r_[core, np.asarray(path, dtype=np.int64)])
    return augmented, fixed_ids, {
        "active": bool(path), "rotation_degrees": float(angle),
        "fixed_locus_points": int(len(fixed_ids)), "path_points": int(len(path)),
        "fixed_limit": float(fixed_limit),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--neighbours", type=int, default=10)
    parser.add_argument("--edge-ratio", type=float, default=1.85)
    parser.add_argument("--collar-steps", type=int, default=8)
    parser.add_argument("--hard-quantile", type=float, default=.85)
    parser.add_argument("--trials", type=int, default=4096)
    parser.add_argument("--maximum-models", type=int, default=4)
    parser.add_argument("--anchor-source", choices=("pixel", "transport"), default="pixel")
    parser.add_argument("--transport-inlier-tolerance-ratio", type=float, default=.006)
    parser.add_argument("--minimum-model-improvement", type=float, default=.25)
    parser.add_argument("--minimum-edge-compression", type=float, default=.55)
    parser.add_argument("--maximum-edge-stretch", type=float, default=3.0)
    args = parser.parse_args()

    prior, partial = load_points(args.prior), load_points(args.partial)
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    partial_spacing = _median_spacing(partial)
    views = load_manifest_projectors(args.manifest, resolution=int(args.resolution))
    pair_config = ObservationAnchoredFusionConfig(
        num_views=4, pixel_radius=1.0, cross_view_pixel_radius=2.0,
        cross_view_depth_ratio=.075, anchor_residual_ratio=.075,
    )
    if args.anchor_source == "pixel":
        positive_pairs, evidence = positive_multiview_pairs(
            partial, prior, views, config=pair_config, diagonal=diagonal,
        )
        anchors, assignment = collision_free_anchor_pairs(
            positive_pairs, partial, prior, max_residual=.075 * diagonal,
        )
        stable_ids_from_transport = np.empty(0, dtype=np.int64)
    else:
        # This source is deliberately broader than same-pixel matching, but
        # remains constrained by all camera views, depth, normals, and local
        # covariance.  Piecewise-rigid graph validation below is still the
        # only mechanism that may move the carrier.
        transport = partial_optimal_transport(
            prior, partial, views[0],
            config=PosteriorAdapterConfig(
                allow_broad_structural_transport=True,
                maximum_3d_ratio=.50,
                maximum_screen_ratio=.48,
                maximum_depth_ratio=.50,
                partial_samples=4_096,
                prior_samples=8_192,
            ),
            device="cuda", view_projectors=views,
        )
        anchors = np.column_stack((transport.partial_ids, transport.prior_ids)).astype(np.int64)
        evidence = {"method": "broad_multiview_camera_structure_transport", **transport.diagnostics}
        assignment = {
            "transport_pairs": int(len(anchors)),
            "transport_cost_median": float(np.median(transport.costs)) if len(transport.costs) else None,
        }
        stable_ids_from_transport = np.flatnonzero(transport.stable_prior_mask)
    if len(anchors) < 96:
        raise RuntimeError("insufficient collision-free multiview anchors")
    partial_ids, prior_ids = anchors[:, 0], anchors[:, 1]
    residual = np.linalg.norm(partial[partial_ids] - prior[prior_ids], axis=1)
    residual_scale = max(float(np.quantile(residual, .50)), partial_spacing)
    weights = np.clip(np.exp(-.5 * np.square(residual / (3. * residual_scale))), .20, 1.)
    _, _, consensus, _, models = _residual_rigid_consensus_targets(
        prior[prior_ids], partial[partial_ids], weights,
        partial_spacing=partial_spacing, diagonal=diagonal,
        hard_quantile=float(args.hard_quantile), trials=int(args.trials),
        maximum_models=int(args.maximum_models), minimum_improvement=.25,
        weight_multiplier=2.5,
        inlier_tolerance_ratio=float(args.transport_inlier_tolerance_ratio),
    )
    graph, metric, _ = local_surface_graph(
        prior, neighbours=int(args.neighbours), edge_ratio=float(args.edge_ratio),
    )
    stable_anchor = residual <= np.quantile(residual, .22)
    stable_ids = np.unique(np.r_[prior_ids[stable_anchor], stable_ids_from_transport])
    best_priority = np.full(len(prior), -np.inf, dtype=np.float64)
    best_weight = np.zeros(len(prior), dtype=np.float64)
    best_displacement = np.zeros_like(prior)
    model_records: list[dict] = []
    support_tolerance = max(3. * partial_spacing, .006 * diagonal)
    # A proposed transform is admitted one at a time.  This guards against an
    # apparently good local fit whose support would force an incompatible
    # motion through its attachment after it is combined with other fields.
    # The same test is used for a limb, handle, blade, wheel, or tail.
    consensus_records = list(consensus.get("models", []))
    ordered_models = sorted(
        enumerate(models),
        key=lambda item: float(consensus_records[item[0]].get("score", 0.))
        if item[0] < len(consensus_records) else 0.,
        reverse=True,
    )
    accepted_models = 0
    for model_id, model in ordered_models:
        rotation = np.asarray(model["rotation"], dtype=np.float64)
        translation = np.asarray(model["translation"], dtype=np.float64)
        transformed = prior @ rotation.T + translation
        transformed_pairs, transformed_evidence = positive_multiview_pairs(
            partial, transformed, views, config=pair_config, diagonal=diagonal,
        )
        transformed_anchors, transformed_assignment = collision_free_anchor_pairs(
            transformed_pairs, partial, transformed,
            max_residual=.075 * diagonal,
        )
        seed_ids = prior_ids[np.asarray(model["anchor_ids"], dtype=np.int64)]
        core_components, core_info = _motion_consistent_core(
            prior, partial, graph, model, seed_ids,
            transformed_anchors[:, 1] if len(transformed_anchors) else np.empty(0, dtype=np.int64),
            tolerance=support_tolerance,
        )
        displacement = transformed - prior
        component_records: list[dict] = []
        accepted_components = 0
        # Min-cut each independently observed component separately.  A single
        # transform can therefore close over several sparse branches, while a
        # bad branch is rejected locally instead of forcing the whole object
        # to move with it.
        for component_id, core in enumerate(core_components):
            kinematic_core, fixed_ids, kinematic_info = _kinematic_pivot_path(
                prior, metric, core, rotation, translation, spacing=partial_spacing,
            )
            region, cut_info = _min_cut_region(graph, kinematic_core, stable_ids)
            if not cut_info.get("active"):
                component_records.append({
                    "component_id": component_id, **kinematic_info, **cut_info,
                })
                continue
            weight = _graph_collar(graph, region, steps=int(args.collar_steps))
            priority = weight * math.sqrt(float(len(model["source"])))
            replace = priority > best_priority
            proposal_priority = best_priority.copy()
            proposal_weight = best_weight.copy()
            proposal_displacement = best_displacement.copy()
            proposal_priority[replace] = priority[replace]
            proposal_weight[replace] = weight[replace]
            proposal_displacement[replace] = displacement[replace]
            proposal_weight[stable_ids] = 0.
            proposal = prior + proposal_weight[:, None] * proposal_displacement
            core_before = cKDTree(partial).query(prior[core], k=1, workers=-1)[0]
            core_after = cKDTree(partial).query(proposal[core], k=1, workers=-1)[0]
            improvement = 1. - float(np.median(core_after)) / max(float(np.median(core_before)), 1e-12)
            integrity_passed, proposal_strain = _field_integrity(
                prior, proposal, graph,
                minimum_edge_compression=float(args.minimum_edge_compression),
                maximum_edge_stretch=float(args.maximum_edge_stretch),
            )
            accepted = bool(
                improvement >= float(args.minimum_model_improvement) and integrity_passed
            )
            if accepted:
                best_priority = proposal_priority
                best_weight = proposal_weight
                best_displacement = proposal_displacement
                accepted_components += 1
            component_records.append({
                "component_id": component_id,
                **kinematic_info,
                **cut_info,
                "collar_points": int((weight > 0.).sum()),
                "median_surface_distance_before": float(np.median(core_before)),
                "median_surface_distance_after": float(np.median(core_after)),
                "surface_improvement": float(improvement),
                "integrity": proposal_strain,
                "accepted": accepted,
                "rejection_reason": None if accepted else (
                    "insufficient_surface_improvement"
                    if improvement < float(args.minimum_model_improvement)
                    else "structural_integrity"
                ),
            })
        anchor_local = np.asarray(model["anchor_ids"], dtype=np.int64)
        model_prior_ids = prior_ids[anchor_local]
        model_partial_ids = partial_ids[anchor_local]
        model_before = np.linalg.norm(prior[model_prior_ids] - partial[model_partial_ids], axis=1)
        current = prior + best_weight[:, None] * best_displacement
        model_after = np.linalg.norm(current[model_prior_ids] - partial[model_partial_ids], axis=1)
        improvement = 1. - float(np.median(model_after)) / max(float(np.median(model_before)), 1e-12)
        accepted = bool(accepted_components)
        if accepted:
            accepted_models += 1
        model_records.append({
            "model_id": model_id,
            **core_info,
            "post_transform_evidence": transformed_evidence,
            "post_transform_assignment": transformed_assignment,
            "components": component_records,
            "accepted_components": int(accepted_components),
            "rotation_degrees": float(math.degrees(math.acos(np.clip(
                (np.trace(rotation) - 1.) * .5, -1., 1.,
            )))),
            "translation_norm": float(np.linalg.norm(translation)),
            "model_median_residual_before": float(np.median(model_before)),
            "model_median_residual_after": float(np.median(model_after)),
            "model_improvement": float(improvement),
            "accepted": accepted,
            "rejection_reason": None if accepted else "no_structurally_safe_component",
        })
    # Stable support remains exactly fixed.  The collar has already produced
    # a continuous transition for the remaining carrier.
    best_weight[stable_ids] = 0.
    candidate = prior + best_weight[:, None] * best_displacement
    strain = edge_strain(prior, candidate, graph)
    before = np.linalg.norm(prior[prior_ids] - partial[partial_ids], axis=1)
    after = np.linalg.norm(candidate[prior_ids] - partial[partial_ids], axis=1)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    write_points(output / "structural_rigid_prior_100k.ply", candidate)
    write_compare(output / "partial_gray_structural_rigid_red.ply", partial, candidate)
    write_compare(output / "partial_gray_before_red.ply", partial, prior)
    save_virtual_overlay_board(output / "before_virtual_views.png", partial, prior, frame_points=prior)
    save_virtual_overlay_board(output / "after_virtual_views.png", partial, candidate, frame_points=prior)
    np.savez_compressed(
        output / "structural_rigid_field.npz",
        means=candidate.astype(np.float32), weight=best_weight.astype(np.float32),
        displacement=best_displacement.astype(np.float32), stable=stable_ids,
    )
    record = {
        "method": "residual_consensus_structural_graph_cut_rigid_field",
        "strict_zero_shot": True,
        "ground_truth_cd_emd_used": False,
        "category_or_part_rules_used": False,
        "inputs": {"prior": str(args.prior.resolve()), "partial": str(args.partial.resolve())},
        "evidence": evidence,
        "assignment": assignment,
        "consensus": consensus,
        "models": model_records,
        "accepted_models": int(accepted_models),
        "acceptance": {
            "minimum_model_improvement": float(args.minimum_model_improvement),
            "minimum_edge_compression": float(args.minimum_edge_compression),
            "maximum_edge_stretch": float(args.maximum_edge_stretch),
        },
        "stable_points": int(len(stable_ids)),
        "moved_points": int((best_weight > 0.).sum()),
        "median_anchor_residual_before": float(np.median(before)),
        "median_anchor_residual_after": float(np.median(after)),
        "stable_motion_max": float(np.linalg.norm(candidate[stable_ids] - prior[stable_ids], axis=1).max(initial=0.)),
        "edge_strain": strain,
    }
    (output / "field_info.json").write_text(json.dumps(jsonable(record), indent=2) + "\n")
    print(json.dumps(jsonable({"output_dir": output.resolve(), **record}), indent=2))


if __name__ == "__main__":
    main()
