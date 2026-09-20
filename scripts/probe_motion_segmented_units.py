#!/usr/bin/env python3
"""Probe category-free motion-segmented rigid posterior units.

The existing residual-field probe made a local point set move and blended its
motion through a graph collar.  That is suitable for a soft shape correction,
but it bends a rigid appendage when only part of it has direct observations.

This diagnostic instead builds a hierarchy of intrinsic surface regions from
the registered complete carrier.  Multi-view positive correspondences fit a
small set of proper SE(3) hypotheses.  A hypothesis selects complete regions
that it explains, and every selected region receives the same proper motion.
The carrier is never resampled, deleted, or concatenated with partial points.

This is deliberately an opt-in probe.  It uses no category, part label, world
axis, ground truth, CD, or EMD.  It is not a mainline module.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.sparse.linalg import eigsh
from scipy.spatial import cKDTree

from fpsample import fps_sampling

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
    _median_spacing,
    _residual_rigid_consensus_targets,
)


@dataclass(frozen=True)
class Region:
    """A node in a topology-only hierarchy of carrier proxy cells."""

    node_ids: np.ndarray
    depth: int
    parent: int | None


def _proxy_nodes(points: np.ndarray, count: int) -> tuple[np.ndarray, np.ndarray]:
    """Return FPS proxy nodes and one intrinsic proxy assignment per carrier."""
    count = min(max(32, int(count)), len(points))
    node_ids = np.asarray(fps_sampling(points.astype(np.float32), count, start_idx=0), dtype=np.int64)
    owner = cKDTree(points[node_ids]).query(points, k=1, workers=-1)[1].astype(np.int64)
    return node_ids, owner


def _coarsen_graph(graph: sparse.csr_matrix, owner: np.ndarray, node_count: int) -> sparse.csr_matrix:
    """Coarsen a local surface graph without Euclidean shortcuts."""
    rows, cols = sparse.triu(graph, k=1).nonzero()
    values = np.asarray(graph[rows, cols]).reshape(-1)
    source, target = owner[rows], owner[cols]
    keep = source != target
    source, target, values = source[keep], target[keep], values[keep]
    result = sparse.coo_matrix(
        (np.r_[values, values], (np.r_[source, target], np.r_[target, source])),
        shape=(int(node_count), int(node_count)),
        dtype=np.float64,
    ).tocsr()
    result.sum_duplicates()
    return result


def _balanced_fiedler_split(graph: sparse.csr_matrix, node_ids: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Split one proxy region by its intrinsic normalized-cut direction."""
    node_ids = np.asarray(node_ids, dtype=np.int64)
    if len(node_ids) < 8:
        return None
    local = graph[node_ids][:, node_ids].tocsr()
    components, labels = csgraph.connected_components(local, directed=False)
    detached = np.empty(0, dtype=np.int64)
    if components > 1:
        sizes = np.bincount(labels, minlength=components)
        largest = int(np.argmax(sizes))
        left = node_ids[labels == largest]
        right = node_ids[labels != largest]
        if len(left) >= 4 and len(right) >= 4:
            return left, right
        # Small isolated proxy cells are sampling artifacts, not a semantic
        # part boundary.  Retain them in the hierarchy but compute the
        # spectral direction on the physically meaningful major component.
        detached = right
        node_ids = left
        local = graph[node_ids][:, node_ids].tocsr()
    degree = np.asarray(local.sum(axis=1)).reshape(-1)
    if np.count_nonzero(degree > 1e-12) < 8:
        return None
    laplacian = sparse.diags(degree) - local
    try:
        values, vectors = eigsh(
            laplacian,
            k=2,
            M=sparse.diags(np.maximum(degree, 1e-12)),
            which="SM",
            tol=2e-3,
            maxiter=max(128, 8 * len(node_ids)),
        )
    except Exception:
        return None
    direction = np.asarray(vectors[:, np.argsort(values)[1]], dtype=np.float64)
    order = np.argsort(direction)
    # Median split gives a deterministic non-degenerate hierarchy and does
    # not assume how many appendages an object has.
    cut = len(order) // 2
    left, right = node_ids[order[:cut]], node_ids[order[cut:]]
    if len(detached):
        left = np.r_[left, detached]
    if min(len(left), len(right)) < 4:
        return None
    return left, right


def _region_hierarchy(graph: sparse.csr_matrix, *, max_depth: int, minimum_nodes: int) -> list[Region]:
    """Build a coarse-to-fine intrinsic partition hierarchy."""
    regions: list[Region] = [
        Region(np.arange(graph.shape[0], dtype=np.int64), depth=0, parent=None)
    ]
    frontier = [0]
    while frontier:
        parent_id = frontier.pop(0)
        parent = regions[parent_id]
        if parent.depth >= int(max_depth) or len(parent.node_ids) < 2 * int(minimum_nodes):
            continue
        split = _balanced_fiedler_split(graph, parent.node_ids)
        if split is None:
            continue
        for child in split:
            child_id = len(regions)
            regions.append(Region(child, depth=parent.depth + 1, parent=parent_id))
            frontier.append(child_id)
    return regions


def _region_point_membership(owner: np.ndarray, regions: list[Region], node_count: int) -> list[np.ndarray]:
    """Return dense carrier ids for each proxy region."""
    membership: list[np.ndarray] = []
    for region in regions:
        mask = np.zeros(node_count, dtype=bool)
        mask[region.node_ids] = True
        membership.append(np.flatnonzero(mask[owner]).astype(np.int64))
    return membership


def _boundary_ratio(graph: sparse.csr_matrix, owner: np.ndarray, node_ids: np.ndarray) -> float:
    """Return a scale-free cut salience for one proxy region."""
    inside = np.zeros(graph.shape[0], dtype=bool)
    inside[node_ids] = True
    rows, cols = sparse.triu(graph, k=1).nonzero()
    cut = inside[rows] != inside[cols]
    internal = inside[rows] & inside[cols]
    return float(cut.sum() / max(int(internal.sum()), 1))


def _tree_ancestors(regions: list[Region], region_id: int) -> list[int]:
    chain = []
    while region_id is not None:
        chain.append(int(region_id))
        region_id = regions[region_id].parent
    return chain


def _select_motion_units(
    *,
    prior: np.ndarray,
    partial: np.ndarray,
    graph: sparse.csr_matrix,
    regions: list[Region],
    memberships: list[np.ndarray],
    owner: np.ndarray,
    model: dict[str, np.ndarray],
    stable_ids: np.ndarray,
    positive_after_ids: np.ndarray,
    minimum_gain: float,
    maximum_unit_fraction: float,
    minimum_density_multiplier: float,
) -> tuple[list[np.ndarray], dict]:
    """Select complete, transform-explained structural units.

    Each unit is one hierarchy region.  We never select only the observed
    subset of the unit: that is precisely what caused a blade/leg to bend in
    the previous collar field.  A coarse region is preferred when it preserves
    strong positive evidence while excluding stable support; the ranking uses
    only normalized gain, visibility-valid support, and intrinsic cut cost.
    """
    rotation = np.asarray(model["rotation"], dtype=np.float64)
    translation = np.asarray(model["translation"], dtype=np.float64)
    moved = prior @ rotation.T + translation
    tree = cKDTree(partial)
    before = tree.query(prior, k=1, workers=-1)[0]
    after = tree.query(moved, k=1, workers=-1)[0]
    seed_ids = np.asarray(model["carrier_ids"], dtype=np.int64)
    stable = np.zeros(len(prior), dtype=bool)
    stable[np.asarray(stable_ids, dtype=np.int64)] = True
    positive_after = np.zeros(len(prior), dtype=bool)
    positive_after[np.asarray(positive_after_ids, dtype=np.int64)] = True
    # A point is evidence for *this* motion only if the same physical partial
    # observation becomes materially closer after applying it.  Merely being
    # visible after the transform is insufficient: that was allowing a broad
    # body region to inherit a local motion.
    positive_after &= after < .75 * np.maximum(before, 1e-12)
    global_positive_density = float(positive_after.mean())
    # Every seed belongs to one leaf.  Ascend its hierarchy path and retain
    # only the largest region whose stable evidence is still weak and whose
    # direct observations are improved by this same motion.
    node_to_regions: dict[int, list[int]] = {}
    for region_id, region in enumerate(regions):
        for node in region.node_ids:
            node_to_regions.setdefault(int(node), []).append(region_id)
    candidates: dict[int, dict] = {}
    global_scale = max(float(np.median(before[positive_after])) if np.any(positive_after) else 0., 1e-9)
    for carrier_id in seed_ids:
        node = int(owner[int(carrier_id)])
        available = node_to_regions.get(node, [])
        # The deepest region containing the seed defines the branch path.
        if not available:
            continue
        leaf = max(available, key=lambda item: regions[item].depth)
        for region_id in _tree_ancestors(regions, leaf):
            if region_id == 0:
                continue
            ids = memberships[region_id]
            if len(ids) < 32:
                continue
            if len(ids) / len(prior) > float(maximum_unit_fraction):
                continue
            positive = positive_after[ids]
            seed = np.isin(ids, seed_ids, assume_unique=False)
            if int(seed.sum()) < max(3, int(math.ceil(.02 * len(seed_ids)))):
                continue
            if int(positive.sum()) < max(4, int(math.ceil(.002 * len(ids)))):
                continue
            if float(positive.mean()) < float(minimum_density_multiplier) * global_positive_density:
                continue
            stable_fraction = float(stable[ids].mean())
            if stable_fraction > .12:
                continue
            support_ids = ids[positive]
            gain = 1. - float(np.median(after[support_ids])) / max(float(np.median(before[support_ids])), 1e-12)
            if gain < float(minimum_gain):
                continue
            salience = _boundary_ratio(graph, owner, regions[region_id].node_ids)
            # Prefer a large compatible region over a local point island, but
            # only up to the retained positive evidence.  This prevents the
            # unchanged body from winning merely because it contains more
            # points than the residual structure.
            evidence_density = float(positive.mean())
            score = gain * math.log1p(len(support_ids)) * (1. - stable_fraction)
            score /= 1. + .5 * salience
            old = candidates.get(region_id)
            record = {
                "region_id": int(region_id), "depth": int(regions[region_id].depth),
                "carrier_points": int(len(ids)), "seed_points": int(seed.sum()),
                "positive_points": int(positive.sum()), "positive_density": evidence_density,
                "stable_fraction": stable_fraction, "gain": float(gain),
                "boundary_ratio": float(salience), "score": float(score),
            }
            if old is None or record["score"] > old["score"]:
                candidates[region_id] = record
    # Candidates form a tree, hence overlap only through ancestry.  Keep the
    # highest score; ties prefer the larger compatible unit to prevent a
    # partial movement along a thin physical structure.
    accepted: list[np.ndarray] = []
    selected_records: list[dict] = []
    occupied = np.zeros(len(prior), dtype=bool)
    for record in sorted(candidates.values(), key=lambda item: (item["score"], item["carrier_points"]), reverse=True):
        ids = memberships[record["region_id"]]
        overlap = float(occupied[ids].mean())
        if overlap > .05:
            continue
        accepted.append(ids)
        selected_records.append({**record, "overlap_fraction": overlap})
        occupied[ids] = True
    return accepted, {
        "candidate_regions": int(len(candidates)),
        "selected_regions": selected_records,
        "selected_points": int(occupied.sum()),
        "positive_scale": float(global_scale),
        "motion_improving_positive_density": float(global_positive_density),
    }


def _proper_models(
    prior: np.ndarray,
    partial: np.ndarray,
    anchors: np.ndarray,
    *,
    diagonal: float,
    spacing: float,
    trials: int,
    maximum_models: int,
) -> tuple[list[dict[str, np.ndarray]], dict, np.ndarray]:
    """Fit residual proper-SE(3) hypotheses from one-to-one positive evidence."""
    partial_ids, prior_ids = anchors[:, 0], anchors[:, 1]
    residual = np.linalg.norm(partial[partial_ids] - prior[prior_ids], axis=1)
    residual_scale = max(float(np.quantile(residual, .50)), float(spacing))
    weights = np.clip(np.exp(-.5 * np.square(residual / max(3. * residual_scale, 1e-12))), .20, 1.)
    _, _, info, _, raw_models = _residual_rigid_consensus_targets(
        prior[prior_ids], partial[partial_ids], weights,
        partial_spacing=float(spacing), diagonal=float(diagonal),
        hard_quantile=.85, trials=int(trials), maximum_models=int(maximum_models),
        minimum_improvement=.25, weight_multiplier=2.5,
    )
    models: list[dict[str, np.ndarray]] = []
    for model in raw_models:
        local_ids = np.asarray(model["anchor_ids"], dtype=np.int64)
        models.append({
            "rotation": np.asarray(model["rotation"], dtype=np.float64),
            "translation": np.asarray(model["translation"], dtype=np.float64),
            "carrier_ids": prior_ids[local_ids].astype(np.int64),
            "partial_ids": partial_ids[local_ids].astype(np.int64),
        })
    return models, info, residual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--proxy-nodes", type=int, default=768)
    parser.add_argument("--partition-depth", type=int, default=5)
    parser.add_argument("--partition-minimum-nodes", type=int, default=12)
    parser.add_argument("--neighbours", type=int, default=10)
    parser.add_argument("--edge-ratio", type=float, default=1.85)
    parser.add_argument("--trials", type=int, default=4096)
    parser.add_argument("--maximum-models", type=int, default=4)
    parser.add_argument("--minimum-unit-gain", type=float, default=.20)
    parser.add_argument("--maximum-unit-fraction", type=float, default=.20)
    parser.add_argument("--minimum-density-multiplier", type=float, default=1.5)
    args = parser.parse_args()

    prior, partial = load_points(args.prior), load_points(args.partial)
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    spacing = _median_spacing(partial)
    views = load_manifest_projectors(args.manifest, resolution=int(args.resolution))
    config = ObservationAnchoredFusionConfig(
        num_views=4, pixel_radius=1.0, cross_view_pixel_radius=2.0,
        cross_view_depth_ratio=.075, anchor_residual_ratio=.075,
    )
    positive, evidence = positive_multiview_pairs(partial, prior, views, config=config, diagonal=diagonal)
    anchors, assignment = collision_free_anchor_pairs(
        positive, partial, prior, max_residual=.075 * diagonal,
    )
    if len(anchors) < 96:
        raise RuntimeError("insufficient collision-free positive multiview correspondences")
    models, consensus, residual = _proper_models(
        prior, partial, anchors, diagonal=diagonal, spacing=spacing,
        trials=int(args.trials), maximum_models=int(args.maximum_models),
    )
    graph, _, graph_edges = local_surface_graph(
        prior, neighbours=int(args.neighbours), edge_ratio=float(args.edge_ratio),
    )
    node_ids, owner = _proxy_nodes(prior, int(args.proxy_nodes))
    proxy_graph = _coarsen_graph(graph, owner, len(node_ids))
    regions = _region_hierarchy(
        proxy_graph, max_depth=int(args.partition_depth), minimum_nodes=int(args.partition_minimum_nodes),
    )
    memberships = _region_point_membership(owner, regions, len(node_ids))
    stable_ids = anchors[:, 1][residual <= np.quantile(residual, .22)]
    candidate = prior.copy()
    moved = np.zeros(len(prior), dtype=bool)
    records: list[dict] = []
    for model_id, model in enumerate(models):
        transformed = prior @ model["rotation"].T + model["translation"]
        positive_after, post_evidence = positive_multiview_pairs(
            partial, transformed, views, config=config, diagonal=diagonal,
        )
        post_anchors, post_assignment = collision_free_anchor_pairs(
            positive_after, partial, transformed, max_residual=.10 * diagonal,
        )
        units, selection = _select_motion_units(
            prior=prior, partial=partial, graph=proxy_graph, regions=regions,
            memberships=memberships, owner=owner, model=model, stable_ids=stable_ids,
            positive_after_ids=post_anchors[:, 1] if len(post_anchors) else np.empty(0, dtype=np.int64),
            minimum_gain=float(args.minimum_unit_gain),
            maximum_unit_fraction=float(args.maximum_unit_fraction),
            minimum_density_multiplier=float(args.minimum_density_multiplier),
        )
        local_mask = np.zeros(len(prior), dtype=bool)
        for ids in units:
            local_mask[ids] = True
        # Stable support is an exact no-motion set.  A selected unit containing
        # it is rejected by _select_motion_units; this assignment is a final
        # numerical guard rather than a second decision rule.
        local_mask[np.asarray(stable_ids, dtype=np.int64)] = False
        available = local_mask & ~moved
        candidate[available] = transformed[available]
        moved |= available
        angle = math.degrees(math.acos(float(np.clip((np.trace(model["rotation"]) - 1.) * .5, -1., 1.))))
        records.append({
            "model_id": int(model_id), "rotation_degrees": float(angle),
            "translation_norm": float(np.linalg.norm(model["translation"])),
            "post_transform_evidence": post_evidence,
            "post_transform_assignment": post_assignment,
            "selection": selection,
            "applied_points": int(available.sum()),
        })
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    write_points(output / "motion_segmented_rigid_prior_100k.ply", candidate)
    write_compare(output / "partial_gray_motion_segmented_rigid_red.ply", partial, candidate)
    write_compare(output / "partial_gray_before_red.ply", partial, prior)
    save_virtual_overlay_board(output / "before_virtual_views.png", partial, prior, frame_points=prior)
    save_virtual_overlay_board(output / "after_virtual_views.png", partial, candidate, frame_points=prior)
    np.savez_compressed(
        output / "motion_segmented_units.npz", means=candidate.astype(np.float32),
        moved=moved, owner=owner, proxy_node_ids=node_ids,
    )
    before = np.linalg.norm(prior[anchors[:, 1]] - partial[anchors[:, 0]], axis=1)
    after = np.linalg.norm(candidate[anchors[:, 1]] - partial[anchors[:, 0]], axis=1)
    info = {
        "method": "multiview_motion_segmented_rigid_units",
        "strict_zero_shot": True,
        "ground_truth_cd_emd_used": False,
        "category_or_part_rules_used": False,
        "inputs": {"prior": str(args.prior.resolve()), "partial": str(args.partial.resolve())},
        "parameters": {
            "proxy_nodes": int(len(node_ids)), "partition_depth": int(args.partition_depth),
            "partition_minimum_nodes": int(args.partition_minimum_nodes),
            "minimum_unit_gain": float(args.minimum_unit_gain),
            "maximum_unit_fraction": float(args.maximum_unit_fraction),
            "minimum_density_multiplier": float(args.minimum_density_multiplier),
        },
        "evidence": evidence, "assignment": assignment, "consensus": consensus,
        "surface_graph_edges": int(graph_edges), "hierarchy_regions": int(len(regions)),
        "models": records, "stable_points": int(len(np.unique(stable_ids))),
        "moved_points": int(moved.sum()),
        "median_anchor_residual_before": float(np.median(before)),
        "median_anchor_residual_after": float(np.median(after)),
        "edge_strain": edge_strain(prior, candidate, graph),
    }
    (output / "motion_segmented_info.json").write_text(json.dumps(jsonable(info), indent=2) + "\n")
    print(json.dumps(jsonable({"output_dir": output.resolve(), **info}), indent=2))


if __name__ == "__main__":
    main()
