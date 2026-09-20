#!/usr/bin/env python3
"""Probe residual-driven metric and coherent-motion posterior deformation.

This is deliberately separate from the released PosteriorAdapter.  It tests
the non-rigid half of a residual-motion posterior: four-view positive
prior-to-partial correspondences provide a sparse 3D displacement field, and
the field is projected onto intrinsic low-frequency modes of the complete
carrier.  It can therefore express a continuous extent change without naming
an axis, category, or part.  A second residual pass detects only those local
supports whose error is explained by one proper SE(3), then moves the complete
support by that shared motion.  This lets a blade, limb, handle, or tail move
as a unit instead of being bent by a pointwise attraction.

The probe never reads ground truth, CD, EMD, object names, or a manually
specified region.  It preserves the ordered carrier and writes diagnostics
only; it is not part of the mainline pipeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy import sparse
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
    PosteriorAdapterConfig,
    _augment_attachment_edges,
    _median_spacing,
    _orthographic_coverage,
    _proper_rigid_transform,
    _residual_rigid_consensus_targets,
    partial_optimal_transport,
)
from src.saved_camera import SavedCameraProjector


def _fps(points: np.ndarray, count: int) -> np.ndarray:
    count = min(max(64, int(count)), len(points))
    if count == len(points):
        return np.arange(len(points), dtype=np.int64)
    return np.asarray(fps_sampling(points.astype(np.float32), count, start_idx=0), dtype=np.int64)


def _low_frequency_basis(graph: sparse.csr_matrix, modes: int) -> tuple[np.ndarray, np.ndarray]:
    """Return normalized-Laplacian modes without assuming a global axis."""
    count = graph.shape[0]
    degree = np.asarray(graph.sum(axis=1)).reshape(-1)
    inverse = 1.0 / np.sqrt(np.maximum(degree, 1e-12))
    normalized = sparse.eye(count, format="csr") - sparse.diags(inverse) @ graph @ sparse.diags(inverse)
    k = min(max(2, int(modes)), count - 2)
    values, vectors = eigsh(normalized, k=k, which="SM", tol=2e-3, maxiter=max(1024, 10 * count))
    order = np.argsort(values)
    return np.asarray(values[order], dtype=np.float64), np.asarray(vectors[:, order], dtype=np.float64)


def _node_displacements(
    nodes: np.ndarray,
    graph: sparse.csr_matrix,
    prior: np.ndarray,
    target_prior_ids: np.ndarray,
    targets: np.ndarray,
    stable_prior_ids: np.ndarray,
    *,
    modes: int,
    regularization: float,
    stable_weight: float,
) -> tuple[np.ndarray, dict]:
    """Fit a smooth metric residual field in an intrinsic spectral basis."""
    tree = cKDTree(nodes)
    node_ids = tree.query(prior[target_prior_ids], k=1, workers=-1)[1].astype(np.int64)
    displacement = np.asarray(targets, dtype=np.float64) - prior[target_prior_ids]
    residual = np.linalg.norm(displacement, axis=1)
    residual_scale = max(float(np.quantile(residual, .50)), 1e-12)
    # Residual support is the data term.  The confidence is scale-normalized
    # and contains no component, category, or coordinate-axis prior.
    weights = np.clip(residual / residual_scale, .25, 2.5)
    node_target = np.zeros((len(nodes), 3), dtype=np.float64)
    node_weight = np.zeros(len(nodes), dtype=np.float64)
    np.add.at(node_target, node_ids, displacement * weights[:, None])
    np.add.at(node_weight, node_ids, weights)
    observed = node_weight > 0.
    node_target[observed] /= node_weight[observed, None]

    stable_ids = tree.query(prior[stable_prior_ids], k=1, workers=-1)[1].astype(np.int64)
    stable_node_weight = np.zeros(len(nodes), dtype=np.float64)
    np.add.at(stable_node_weight, stable_ids, 1.)
    if np.any(stable_node_weight):
        stable_node_weight *= float(stable_weight) * max(float(np.median(node_weight[observed])), 1.)
    total_weight = node_weight + stable_node_weight

    values, basis = _low_frequency_basis(graph, modes)
    # A frequency penalty lets the residual determine *which* intrinsic
    # direction stretches while suppressing high-frequency bending.
    weighted_basis = basis * total_weight[:, None]
    system = basis.T @ weighted_basis + float(regularization) * np.diag(np.maximum(values, 1e-5))
    rhs = basis.T @ (total_weight[:, None] * node_target)
    coefficients = np.linalg.solve(system + 1e-8 * np.eye(system.shape[0]), rhs)
    return basis @ coefficients, {
        "basis_modes": int(basis.shape[1]),
        "basis_eigenvalues": values.tolist(),
        "observed_nodes": int(observed.sum()),
        "stable_nodes": int(np.count_nonzero(stable_node_weight)),
        "median_residual": float(np.median(residual)),
    }


def _interpolate(nodes: np.ndarray, node_displacement: np.ndarray, points: np.ndarray) -> np.ndarray:
    k = min(4, len(nodes))
    distance, index = cKDTree(nodes).query(points, k=k, workers=-1)
    distance = np.atleast_2d(distance)
    index = np.atleast_2d(index)
    if k == 1:
        return node_displacement[index[:, 0]]
    weight = 1.0 / np.maximum(distance, 1e-8) ** 2
    weight /= weight.sum(axis=1, keepdims=True)
    return np.einsum("nk,nki->ni", weight, node_displacement[index])


def _affine_residual_diagnostic(source: np.ndarray, target: np.ndarray) -> dict:
    """Describe residual metric content for audit, never for a class rule."""
    if len(source) < 8:
        return {"active": False, "reason": "insufficient_pairs"}
    centre = source.mean(axis=0)
    design = np.c_[source - centre, np.ones(len(source))]
    solution, *_ = np.linalg.lstsq(design, target - target.mean(axis=0), rcond=None)
    affine = solution[:3].T
    singular = np.linalg.svd(affine, compute_uv=False)
    return {
        "active": True,
        "singular_values": singular.tolist(),
        "anisotropy": float(singular.max() / max(singular.min(), 1e-12)),
        "non_isometry": float(np.linalg.norm(affine.T @ affine - np.eye(3), ord="fro")),
    }


def _metric_model_selection(
    source: np.ndarray,
    target: np.ndarray,
    *,
    partial_spacing: float,
) -> dict:
    """Choose rigid-only versus metric posterior evidence without semantics.

    The low-frequency field is deliberately reserved for *coherent* metric
    evidence that a proper rigid transform cannot explain.  In particular, a
    small number of outlying correspondences must not purchase a global warp:
    that is how an already correct fuselage gets pulled by a rotor.  We use the
    same adaptive correntropy view as occlusion-aware registration: the
    affine explanation has to improve the central residual mass *and* its
    robust high-residual tail.  A BIC is retained as an audit quantity, but is
    intentionally not the decision rule because it can favour affine models
    by explaining a few long-tail points while worsening the median fit.
    """
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if len(source) < 16:
        return {"active": False, "use_metric": False, "reason": "insufficient_pairs"}
    rigid = _proper_rigid_transform(source, target)
    if rigid is None:
        return {"active": False, "use_metric": False, "reason": "degenerate_rigid_fit"}
    rotation, translation = rigid
    rigid_error = np.linalg.norm(source @ rotation.T + translation - target, axis=1)
    centre = source.mean(axis=0)
    design = np.c_[source - centre, np.ones(len(source))]
    solution, *_ = np.linalg.lstsq(design, target - target.mean(axis=0), rcond=None)
    affine = solution[:3].T
    affine_prediction = (source - centre) @ affine.T + target.mean(axis=0)
    affine_error = np.linalg.norm(affine_prediction - target, axis=1)
    # Same robust residual scale for both models; trimming prevents isolated
    # partial outliers from purchasing an unnecessary global deformation.
    cutoff = max(
        float(np.quantile(np.r_[rigid_error, affine_error], .90)),
        3.0 * float(partial_spacing),
    )
    def bic(error: np.ndarray, dof: int) -> float:
        mse = float(np.mean(np.minimum(np.square(error), cutoff * cutoff)))
        return float(len(error) * np.log(max(mse, 1e-15)) + int(dof) * np.log(len(error)))
    rigid_bic, affine_bic = bic(rigid_error, 6), bic(affine_error, 12)

    # Adaptive correntropy makes the evidence comparable across sparse and
    # dense partial scans.  The bandwidth is derived only from observed
    # residuals and point spacing, never from category or coordinate axes.
    bandwidth = max(
        float(np.median(np.r_[rigid_error, affine_error])),
        2.0 * float(partial_spacing),
        1e-12,
    )

    def correntropy_loss(error: np.ndarray) -> float:
        normalized = np.minimum(np.asarray(error, dtype=np.float64) / bandwidth, 4.0)
        return float(np.mean(1.0 - np.exp(-0.5 * normalized * normalized)))

    rigid_median, affine_median = float(np.median(rigid_error)), float(np.median(affine_error))
    rigid_q75, affine_q75 = float(np.quantile(rigid_error, .75)), float(np.quantile(affine_error, .75))
    rigid_corr, affine_corr = correntropy_loss(rigid_error), correntropy_loss(affine_error)
    median_gain = float(1.0 - affine_median / max(rigid_median, 1e-12))
    q75_gain = float(1.0 - affine_q75 / max(rigid_q75, 1e-12))
    correntropy_gain = float(1.0 - affine_corr / max(rigid_corr, 1e-12))

    # A global metric field is not a free fitting capacity.  All three
    # dimensionless robust witnesses must agree that it explains substantial
    # residual mass.  These fixed fractions apply in normalized residual
    # space and are shared by every identity/dataset.
    use_metric = bool(
        median_gain >= .05
        and q75_gain >= .02
        and correntropy_gain >= .01
    )
    return {
        "active": True,
        "method": "adaptive_correntropy_rigid_vs_affine_transport_selection",
        "use_metric": use_metric,
        "decision_rule": "median_gain>=0.05_and_q75_gain>=0.02_and_correntropy_gain>=0.01",
        "rigid_bic": rigid_bic,
        "affine_bic": affine_bic,
        "bic_margin_affine_minus_rigid": float(affine_bic - rigid_bic),
        "rigid_median": rigid_median,
        "affine_median": affine_median,
        "rigid_q75": rigid_q75,
        "affine_q75": affine_q75,
        "affine_relative_median_gain": median_gain,
        "affine_relative_q75_gain": q75_gain,
        "rigid_correntropy_loss": rigid_corr,
        "affine_correntropy_loss": affine_corr,
        "affine_relative_correntropy_gain": correntropy_gain,
        "correntropy_bandwidth": bandwidth,
        "trim_cutoff": cutoff,
    }


def _connected_motion_support(
    current: np.ndarray,
    partial: np.ndarray,
    graph: sparse.csr_matrix,
    seed_ids: np.ndarray,
    rotation: np.ndarray,
    translation: np.ndarray,
    stable_mask: np.ndarray,
    *,
    partial_spacing: float,
    attachment_rings: int,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Recover a data-supported full SE(3) unit without a semantic part mask.

    A point joins a unit only if the *same* proper transform makes it closer to
    an observed sample.  The graph merely keeps the accepted support connected
    to consensus anchors; it never invents an axis, segment, or fixed-radius
    collar.  Keeping the transform binary on this support is intentional: a
    weighted pointwise blend is precisely what turns a rigid rotor into a bent
    curve.
    """
    seed_ids = np.unique(np.asarray(seed_ids, dtype=np.int64))
    seed_ids = seed_ids[(seed_ids >= 0) & (seed_ids < len(current))]
    if len(seed_ids) < 12:
        empty = np.zeros(len(current), dtype=np.float64)
        return empty.astype(bool), empty, {"active": False, "reason": "few_model_seeds"}

    tree = cKDTree(partial)
    transformed = current @ np.asarray(rotation, dtype=np.float64).T + np.asarray(translation, dtype=np.float64)
    before = tree.query(current, k=1, workers=-1)[0]
    after = tree.query(transformed, k=1, workers=-1)[0]
    gain = before - after
    positive_seed_gain = gain[seed_ids][gain[seed_ids] > 0.]
    if len(positive_seed_gain) < max(8, len(seed_ids) // 4):
        empty = np.zeros(len(current), dtype=np.float64)
        return empty.astype(bool), empty, {
            "active": False, "reason": "transform_does_not_improve_seed_support",
            "positive_seed_count": int(len(positive_seed_gain)),
        }
    gain_floor = max(.12 * float(np.median(positive_seed_gain)), .15 * float(partial_spacing))
    transformed_limit = max(
        2.5 * float(np.median(after[seed_ids])),
        3.0 * float(partial_spacing),
    )
    stable_mask = np.asarray(stable_mask, dtype=bool)
    allowed = (gain >= gain_floor) & (after <= transformed_limit) & ~stable_mask
    # Consensus inliers are trusted even when a nearest-neighbour query is
    # locally ambiguous.  Stable observations remain hard exclusions.
    allowed[seed_ids] = ~stable_mask[seed_ids]
    allowed_ids = np.flatnonzero(allowed)
    if len(allowed_ids) < 12:
        empty = np.zeros(len(current), dtype=np.float64)
        return empty.astype(bool), empty, {"active": False, "reason": "few_motion_supported_points"}

    subgraph = graph[allowed_ids][:, allowed_ids]
    component_count, labels = sparse.csgraph.connected_components(subgraph, directed=False)
    lookup = np.full(len(current), -1, dtype=np.int64)
    lookup[allowed_ids] = np.arange(len(allowed_ids), dtype=np.int64)
    valid_seeds = seed_ids[lookup[seed_ids] >= 0]
    if len(valid_seeds) < 8:
        empty = np.zeros(len(current), dtype=np.float64)
        return empty.astype(bool), empty, {"active": False, "reason": "no_seed_in_supported_component"}
    seed_labels, seed_counts = np.unique(labels[lookup[valid_seeds]], return_counts=True)
    # A residual model may have observations on several physically separate
    # units (e.g. repeated blades).  Retain only components that independently
    # carry enough model evidence; otherwise a few isolated pixels would make
    # a direct rigid update tear the carrier graph.
    component_minimum = max(8, int(np.ceil(.06 * len(valid_seeds))))
    seed_labels = seed_labels[seed_counts >= component_minimum]
    if len(seed_labels) == 0:
        empty = np.zeros(len(current), dtype=np.float64)
        return empty.astype(bool), empty, {
            "active": False, "reason": "no_component_has_coherent_seed_mass",
            "component_seed_minimum": int(component_minimum),
        }
    support = np.zeros(len(current), dtype=bool)
    support[allowed_ids[np.isin(labels, seed_labels)]] = True
    if int(support.sum()) < 12:
        empty = np.zeros(len(current), dtype=np.float64)
        return empty.astype(bool), empty, {"active": False, "reason": "empty_connected_support"}

    # The rigid core is binary.  Only a small graph band around an observed
    # attachment receives a continuous SE(3) transition.  That band is a
    # boundary condition, not a pointwise residual field: all visible body of
    # a structural unit receives the same rotation and translation.
    weight = support.astype(np.float64)
    frontier = support.copy()
    for step in range(1, max(0, int(attachment_rings)) + 1):
        reached = np.asarray(graph @ frontier.astype(np.float64)).reshape(-1) > 0.
        reached &= weight <= 0.
        reached &= ~stable_mask
        if not np.any(reached):
            break
        weight[reached] = float((int(attachment_rings) + 1 - step) / (int(attachment_rings) + 1))
        frontier = reached
    return support, weight, {
        "active": True,
        "seed_count": int(len(seed_ids)),
        "positive_seed_count": int(len(positive_seed_gain)),
        "gain_floor": float(gain_floor),
        "transformed_distance_limit": float(transformed_limit),
        "support_points": int(support.sum()),
        "support_fraction": float(support.mean()),
        "components": int(component_count),
        "component_seed_minimum": int(component_minimum),
        "retained_components": int(len(seed_labels)),
        "attachment_rings": int(attachment_rings),
        "attachment_transition_points": int(np.count_nonzero((weight > 0.) & ~support)),
        "seed_gain_median": float(np.median(positive_seed_gain)),
    }


def _apply_coherent_motion_models(
    current: np.ndarray,
    partial: np.ndarray,
    anchor_prior_ids: np.ndarray,
    anchor_targets: np.ndarray,
    runtime_models: list[dict[str, np.ndarray]],
    stable_mask: np.ndarray,
    validation_graph: sparse.csr_matrix,
    *,
    partial_spacing: float,
) -> tuple[np.ndarray, dict, np.ndarray]:
    """Apply only locally verifiable proper motions after metric deformation."""
    inactive = {
        "active": False,
        "method": "residual_consensus_whole_support_se3",
        "models": [],
    }
    if not runtime_models:
        return current.copy(), {**inactive, "reason": "no_rigid_consensus"}, np.zeros(len(current), dtype=bool)

    result = current.copy()
    moved = np.zeros(len(current), dtype=bool)
    records: list[dict] = []
    # Larger coherent support is tried first.  Overlap is resolved by the
    # already accepted support, never by a category-specific priority.
    ordered = sorted(runtime_models, key=lambda item: len(item["anchor_ids"]), reverse=True)
    for model in ordered:
        anchor_ids = np.asarray(model["anchor_ids"], dtype=np.int64)
        if len(anchor_ids) < 12:
            continue
        seed_ids = np.asarray(anchor_prior_ids[anchor_ids], dtype=np.int64)
        rotation = np.asarray(model["rotation"], dtype=np.float64)
        translation = np.asarray(model["translation"], dtype=np.float64)
        # The smallest attachment continuation that satisfies the same
        # no-GT integrity checks wins.  Its width is adapted to the observed
        # transform discontinuity, never to an object category or a hand
        # selected component.
        choices: list[dict] = []
        accepted_choice: tuple[np.ndarray, np.ndarray, dict] | None = None
        for attachment_rings in (2, 4, 6, 8, 12, 16):
            support, weight, support_info = _connected_motion_support(
                result, partial, validation_graph, seed_ids, rotation, translation, stable_mask | moved,
                partial_spacing=partial_spacing, attachment_rings=attachment_rings,
            )
            if not support_info.get("active", False):
                choices.append({"accepted": False, **support_info})
                continue
            trial = result.copy()
            transformed = trial @ rotation.T + translation
            trial += weight[:, None] * (transformed - trial)
            before = np.linalg.norm(result[anchor_prior_ids] - anchor_targets, axis=1)
            after = np.linalg.norm(trial[anchor_prior_ids] - anchor_targets, axis=1)
            seed_before = np.linalg.norm(result[seed_ids] - anchor_targets[anchor_ids], axis=1)
            seed_after = np.linalg.norm(trial[seed_ids] - anchor_targets[anchor_ids], axis=1)
            affected_anchor = weight[anchor_prior_ids] > 1e-8
            local_before = before[affected_anchor]
            local_after = after[affected_anchor]
            strain = edge_strain(result, trial, validation_graph)
            coverage, coverage_views = _orthographic_coverage(result, trial, resolution=160)
            accepted = bool(
                np.median(seed_after) < np.median(seed_before)
                # A local proper motion is judged on the anchors it can
                # actually affect.  Requiring the *global* median to fall
                # makes a small, correct rotor/limb motion hostage to
                # unrelated observations that the trial leaves unchanged.
                and len(local_after) >= 12
                and np.median(local_after) < np.median(local_before)
                and strain["edge_stretch_p01"] >= .45
                and strain["edge_stretch_p99"] <= 2.6
                and strain["edge_stretch_p999"] <= 4.0
                and coverage >= .90
            )
            angle = float(np.degrees(np.arccos(np.clip((np.trace(rotation) - 1.) * .5, -1., 1.))))
            record = {
                "accepted": accepted,
                **support_info,
                "rotation_degrees": angle,
                "translation_norm": float(np.linalg.norm(translation)),
                "seed_median_before": float(np.median(seed_before)),
                "seed_median_after": float(np.median(seed_after)),
                "affected_anchor_count": int(len(local_after)),
                "affected_anchor_median_before": float(np.median(local_before)) if len(local_before) else float("inf"),
                "affected_anchor_median_after": float(np.median(local_after)) if len(local_after) else float("inf"),
                "all_anchor_median_before": float(np.median(before)),
                "all_anchor_median_after": float(np.median(after)),
                "coverage": float(coverage), "coverage_views": coverage_views, **strain,
            }
            choices.append(record)
            if accepted:
                accepted_choice = (trial, support, record)
                break
        if accepted_choice is None:
            records.append({"accepted": False, "attachment_choices": choices})
            continue
        trial, support, record = accepted_choice
        records.append(record)
        result = trial
        moved |= support
    return result, {
        "active": bool(np.any(moved)),
        "method": "residual_consensus_whole_support_se3",
        "models": records,
        "moved_points": int(moved.sum()),
        "moved_fraction": float(moved.mean()),
    }, moved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--camera", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--nodes", type=int, default=2048)
    parser.add_argument("--modes", type=int, default=32)
    parser.add_argument("--regularization", type=float, default=.035)
    parser.add_argument("--stable-weight", type=float, default=6.0)
    parser.add_argument("--maximum-displacement-ratio", type=float, default=.30)
    # A low-frequency extent correction can legitimately alter a prior's
    # fixed-frame silhouette.  Its gate therefore protects graph integrity,
    # stable observations and carrier coverage, rather than forcing the old
    # silhouette to remain almost unchanged.
    parser.add_argument("--minimum-edge-compression", type=float, default=.40)
    parser.add_argument("--maximum-edge-stretch", type=float, default=3.0)
    parser.add_argument("--minimum-occupancy-retention", type=float, default=.80)
    parser.add_argument("--rigid-rounds", type=int, default=3)
    args = parser.parse_args()

    prior, partial = load_points(args.prior), load_points(args.partial)
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    camera = SavedCameraProjector.from_partial(
        partial, args.camera, padding=.15,
        image_shape=(int(args.resolution), int(args.resolution)), device=args.device,
    )
    views = load_manifest_projectors(args.manifest, resolution=int(args.resolution))
    evidence_config = ObservationAnchoredFusionConfig(
        num_views=4, pixel_radius=1.0, cross_view_pixel_radius=2.0,
        cross_view_depth_ratio=.075, anchor_residual_ratio=.075,
    )
    # Camera-1 OT is deliberately the structural authority: unlike a narrow
    # local pixel match, its unbalanced, feature-aware coupling can preserve
    # a reliable long-range residual arrow when a complete prior has the wrong
    # extent.  The four manifest views remain an independent residual audit.
    transport = partial_optimal_transport(
        prior, partial, camera, config=PosteriorAdapterConfig(), device=args.device,
        view_projectors=(camera,),
    )
    positive, four_view_evidence = positive_multiview_pairs(
        partial, prior, views, config=evidence_config, diagonal=diagonal,
    )
    four_view_anchors, four_view_assignment = collision_free_anchor_pairs(
        positive, partial, prior, max_residual=.075 * diagonal,
    )
    # A sparse scan can leave Camera-1 with too few long-range candidates.
    # This is an observability fallback, not an identity-specific route: use
    # the already-valid four-view physical correspondences in that case.  The
    # same confidence, scale and stable-support rules follow below.
    if len(transport.prior_ids) >= 96:
        partial_ids, prior_ids = transport.partial_ids, transport.prior_ids
        target = partial[partial_ids]
        residual = np.linalg.norm(target - prior[prior_ids], axis=1)
        stable_full = transport.stable_prior_mask.copy()
        transport_source = "camera1_structure_ot"
    else:
        if len(four_view_anchors) < 96:
            raise RuntimeError("insufficient Camera-1 and four-view transport pairs")
        partial_ids, prior_ids = four_view_anchors[:, 0], four_view_anchors[:, 1]
        target = partial[partial_ids]
        residual = np.linalg.norm(target - prior[prior_ids], axis=1)
        stable_full = np.zeros(len(prior), dtype=bool)
        stable_full[prior_ids[residual <= np.quantile(residual, .22)]] = True
        transport_source = "four_view_local_fallback"
    stable_ids = np.flatnonzero(stable_full).astype(np.int64)

    node_ids = _fps(prior, int(args.nodes))
    nodes = prior[node_ids]
    node_graph, node_metric, node_edges = local_surface_graph(nodes, neighbours=18, edge_ratio=2.45)
    node_graph, _, attachment_edges = _augment_attachment_edges(node_graph, node_metric, nodes, edge_ratio=3.2)
    partial_spacing = _median_spacing(partial)
    metric_selection = _metric_model_selection(
        prior[prior_ids], target, partial_spacing=float(partial_spacing),
    )
    if metric_selection.get("use_metric", False):
        node_displacement, modal_info = _node_displacements(
            nodes, node_graph, prior, prior_ids, target, stable_ids,
            modes=int(args.modes), regularization=float(args.regularization), stable_weight=float(args.stable_weight),
        )
        displacement = _interpolate(nodes, node_displacement, prior)
        length = np.linalg.norm(displacement, axis=1, keepdims=True)
        maximum = float(args.maximum_displacement_ratio) * diagonal
        displacement *= np.minimum(1., maximum / np.maximum(length, 1e-12))
    else:
        node_displacement = np.zeros((len(nodes), 3), dtype=np.float64)
        displacement = np.zeros_like(prior)
        modal_info = {
            "active": False,
            "reason": "rigid_transport_model_preferred",
            "basis_modes": 0,
            "observed_nodes": 0,
            "stable_nodes": 0,
        }
    # Stable observations constrain nearby graph controls with high stiffness.
    # Do not pin every sampled stable surfel after interpolation: those
    # isolated point clamps introduce artificial high-frequency strain exactly
    # at a continuous extent boundary.  Their motion is audited below instead.

    validation_graph, _, validation_edges = local_surface_graph(prior, neighbours=10, edge_ratio=1.85)
    before = np.linalg.norm(prior[prior_ids] - target, axis=1)
    candidate = prior.copy()
    selected = None
    line_search = []
    if metric_selection.get("use_metric", False):
        for alpha in (1.0, .85, .70, .55, .40, .25):
            trial = prior + float(alpha) * displacement
            after = np.linalg.norm(trial[prior_ids] - target, axis=1)
            strain = edge_strain(prior, trial, validation_graph)
            coverage, per_view = _orthographic_coverage(prior, trial, resolution=160)
            improvement = 1. - float(np.median(after)) / max(float(np.median(before)), 1e-12)
            stable_motion = np.linalg.norm(trial[stable_full] - prior[stable_full], axis=1)
            record = {
                "alpha": float(alpha), "median_before": float(np.median(before)),
                "median_after": float(np.median(after)), "improvement": float(improvement),
                "coverage": float(coverage), "coverage_views": per_view, **strain,
                "stable_motion_p95": float(np.quantile(stable_motion, .95)) if len(stable_motion) else 0.,
                "stable_motion_max": float(stable_motion.max(initial=0.)),
            }
            line_search.append(record)
            if (
                improvement > .002
                and strain["edge_stretch_p01"] >= float(args.minimum_edge_compression)
                and strain["edge_stretch_p999"] <= float(args.maximum_edge_stretch)
                and coverage >= float(args.minimum_occupancy_retention)
                # Stable support is a *relative* high-stiffness condition, not an
                # absolute pin.  On sparse scans, a few sampling intervals are
                # below measurement precision and must not suppress an otherwise
                # coherent low-frequency correction.
                and record["stable_motion_p95"] <= max(
                    .30 * float(np.median(before)), 5.0 * float(partial_spacing),
                )
            ):
                candidate, selected = trial, record
                break
    if selected is None:
        candidate = prior.copy()
        selected = {
            "accepted": False,
            "reason": (
                "rigid_transport_model_preferred"
                if not metric_selection.get("use_metric", False)
                else "no_metric_safe_modal_update"
            ),
        }
    else:
        selected = {"accepted": True, **selected}

    # Stage 2 intentionally re-observes the *metric-updated* carrier.  These
    # four-view pairs are unsuitable for the long-range Camera-1 transport
    # above, but are exactly the right evidence to decide whether a remaining
    # coherent residual should move as one proper rigid unit.
    stage1 = candidate.copy()
    partial_spacing = _median_spacing(partial)
    rigid_mask = np.zeros(len(prior), dtype=bool)
    final = stage1.copy()
    rigid_round_records: list[dict] = []
    four_view_evidence_after: dict = {}
    assignment_after: dict = {}
    anchors_after = np.empty((0, 2), dtype=np.int64)
    # Re-estimate the correspondence/motion hypotheses after every accepted
    # structural update.  A correct first rotor/limb motion changes which
    # residuals are explainable elsewhere; reusing its stale model would make
    # the next update under- or over-rotate a different structure.
    for round_index in range(max(1, int(args.rigid_rounds))):
        positive_after, four_view_evidence_after = positive_multiview_pairs(
            partial, final, views, config=evidence_config, diagonal=diagonal,
        )
        # A residual motion is only eligible when it is corroborated by at
        # least two saved cameras. One-view matches remain coverage evidence
        # but are too ambiguous to define a structural motion support.
        positive_after_consistent = positive_after[positive_after[:, 4] >= 2.]
        anchors_after, assignment_after = collision_free_anchor_pairs(
            positive_after_consistent, partial, final, max_residual=.075 * diagonal,
        )
        round_record: dict = {
            "round": int(round_index),
            "anchor_count": int(len(anchors_after)),
            "assignment": assignment_after,
            "evidence": four_view_evidence_after,
        }
        if len(anchors_after) < 32:
            round_record["active"] = False
            round_record["reason"] = "insufficient_post_metric_anchors"
            rigid_round_records.append(round_record)
            break
        residual_after = np.linalg.norm(
            partial[anchors_after[:, 0]] - final[anchors_after[:, 1]], axis=1,
        )
        robust_scale = max(float(np.median(residual_after)), float(partial_spacing), 1e-12)
        anchor_weights = np.clip(residual_after / robust_scale, .25, 2.5)
        _, _, consensus_info, _, runtime_models = _residual_rigid_consensus_targets(
            final[anchors_after[:, 1]],
            partial[anchors_after[:, 0]],
            anchor_weights,
            partial_spacing=float(partial_spacing),
            diagonal=diagonal,
            hard_quantile=.85,
            trials=4096,
            maximum_models=4,
            minimum_improvement=.20,
            weight_multiplier=2.5,
        )
        proposal, motion_info, round_mask = _apply_coherent_motion_models(
            final,
            partial,
            anchors_after[:, 1],
            partial[anchors_after[:, 0]],
            runtime_models,
            stable_full,
            validation_graph,
            partial_spacing=float(partial_spacing),
        )
        round_record.update({
            "active": bool(motion_info.get("active", False)),
            "consensus": consensus_info,
            "whole_support_motion": motion_info,
        })
        rigid_round_records.append(round_record)
        if not motion_info.get("active", False):
            break
        final = proposal
        rigid_mask |= round_mask
    rigid_info: dict = {
        "active": bool(np.any(rigid_mask)),
        "method": "iterative_four_view_coherent_motion",
        "rounds": rigid_round_records,
        "post_metric_anchor_count": int(len(anchors_after)),
    }

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    write_points(output / "stage1_metric_prior_100k.ply", stage1)
    write_points(output / "residual_motion_posterior_100k.ply", final)
    # Retain the old filename as a stable convenience alias for the final
    # carrier.  This avoids silently changing downstream inspection scripts.
    write_points(output / "residual_modal_prior_100k.ply", final)
    write_compare(output / "partial_gray_stage1_metric_red.ply", partial, stage1)
    write_compare(output / "partial_gray_residual_motion_red.ply", partial, final)
    write_compare(output / "partial_gray_residual_modal_red.ply", partial, final)
    write_compare(output / "partial_gray_before_red.ply", partial, prior)
    save_virtual_overlay_board(output / "before_virtual_views.png", partial, prior, frame_points=prior)
    save_virtual_overlay_board(output / "after_stage1_virtual_views.png", partial, stage1, frame_points=prior)
    save_virtual_overlay_board(output / "after_virtual_views.png", partial, final, frame_points=prior)
    np.savez_compressed(
        output / "residual_modal_field.npz", means=final.astype(np.float32), stage1=stage1.astype(np.float32),
        node_ids=node_ids, node_displacement=node_displacement.astype(np.float32),
        displacement=displacement.astype(np.float32), stable=stable_full,
        residual_support=prior_ids, rigid_support=rigid_mask,
    )
    info = {
        "method": "camera1_metric_transport_plus_four_view_coherent_motion_posterior",
        "strict_zero_shot": True,
        "ground_truth_cd_emd_used": False,
        "category_or_part_rules_used": False,
        "inputs": {"prior": str(args.prior.resolve()), "partial": str(args.partial.resolve())},
        "transport_source": transport_source,
        "camera1_transport": transport.diagnostics,
        "four_view_evidence": four_view_evidence,
        "four_view_assignment": four_view_assignment,
        "post_metric_four_view_evidence": four_view_evidence_after,
        "post_metric_four_view_assignment": assignment_after,
        "post_metric_minimum_cross_view_support": 2,
        "supports": {"anchors": int(len(prior_ids)), "stable": int(stable_full.sum()), "residual": int(len(prior_ids))},
        "graph": {"nodes": int(len(nodes)), "surface_edges": int(node_edges), "attachment_edges": int(attachment_edges), "validation_edges": int(validation_edges)},
        "modal": modal_info,
        "metric_model_selection": metric_selection,
        "affine_residual_diagnostic": _affine_residual_diagnostic(prior[prior_ids], target),
        "line_search": line_search, "selected": selected,
        "metric_deformation_gate": {
            "minimum_edge_compression": float(args.minimum_edge_compression),
            "maximum_edge_stretch": float(args.maximum_edge_stretch),
            "minimum_occupancy_retention": float(args.minimum_occupancy_retention),
        },
        "coherent_motion": rigid_info,
        "carrier_slots_before": int(len(prior)), "carrier_slots_after": int(len(final)),
        "carrier_slots_preserved": bool(len(prior) == len(final)),
        "stable_motion_max": float(np.linalg.norm(final[stable_full] - prior[stable_full], axis=1).max(initial=0.)),
    }
    (output / "residual_modal_info.json").write_text(json.dumps(jsonable(info), indent=2) + "\n")
    print(json.dumps(jsonable({"output_dir": output.resolve(), **info}), indent=2))


if __name__ == "__main__":
    main()
