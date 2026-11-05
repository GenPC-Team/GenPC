"""Partial-supported local rigid handles, with geodesic attachment transitions.

This proposal only moves existing carrier slots. Residual clusters identify
where a local motion is supported; they are not semantic part segmentation.
The rigid core preserves all pairwise distances, and the transition follows
the rest surface graph rather than a Euclidean ball across nearby surfaces.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from src.deformation_graph import edge_strain, local_surface_graph


@dataclass(frozen=True)
class LocalRigidConfig:
    residual_floor: float = .01
    maximum_translation: float = .12
    maximum_rotation_degrees: float = 20.
    minimum_support: int = 8
    maximum_region_fraction: float = .20
    maximum_candidates: int = 6
    transition_ratio: float = .04
    minimum_local_gain: float = .10


def fit_rigid(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Proper SE(3), with translation-only fallback for rank-deficient support."""
    source, target = np.asarray(source), np.asarray(target)
    a, b = source.mean(axis=0), target.mean(axis=0)
    u, values, vt = np.linalg.svd((source-a).T @ (target-b))
    if values[1] < max(values[0], 1e-12) * 1e-5:
        return np.eye(3), np.median(target-source, axis=0)
    correction = np.eye(3)
    correction[-1, -1] = np.sign(np.linalg.det(vt.T @ u.T))
    rotation = vt.T @ correction @ u.T
    return rotation, b - a @ rotation.T


def geodesic_rigid_warp(points, metric, core, rotation, translation, width):
    """Apply an exact rigid core and smoothly taper its SE(3) to identity.

    Fractional rotations avoid linear-blend shrinkage. Disconnected surfaces
    have infinite graph distance and therefore remain byte-for-byte fixed.
    """
    points = np.asarray(points, dtype=np.float64)
    core = np.asarray(core, dtype=np.int64)
    distance = dijkstra(metric, directed=False, indices=core,
                        min_only=True, limit=float(width))
    weight = np.clip(1.-distance / float(width), 0., 1.)
    weight = weight*weight*(3.-2.*weight)
    active = np.flatnonzero(weight > 0.)
    centre = points[core].mean(axis=0)
    shift = centre @ rotation.T + translation - centre
    fractional = Rotation.from_rotvec(
        weight[active, None]*Rotation.from_matrix(rotation).as_rotvec(),
    )
    result = points.copy()
    result[active] = (fractional.apply(points[active]-centre) + centre
                      + weight[active, None]*shift)
    return result, weight


def local_rigid_candidates(carrier, partial, *, config=None):
    """Return bounded local candidates and auditable no-GT screening records."""
    config = config or LocalRigidConfig()
    carrier, partial = (np.asarray(p, dtype=np.float64) for p in (carrier, partial))
    if (carrier.ndim != 2 or partial.ndim != 2 or carrier.shape[1] != 3
            or partial.shape[1] != 3 or min(len(carrier), len(partial)) < 8
            or not np.isfinite(carrier).all() or not np.isfinite(partial).all()):
        raise ValueError("finite nontrivial Nx3 point clouds are required")
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-12)
    tree = cKDTree(carrier)
    distances, nearest = tree.query(partial, workers=-1)
    spacing = float(np.median(cKDTree(partial).query(partial, k=2)[0][:, 1]))
    residual_floor = config.residual_floor*diagonal
    positive_ids = np.flatnonzero(distances > residual_floor)
    report = {"method": "geodesic_local_rigid_handles", "ground_truth_used": False,
              "config": asdict(config), "residual_points": len(positive_ids),
              "partial_spacing": spacing, "diagonal": diagonal, "regions": []}
    if len(positive_ids) < config.minimum_support:
        report["reason"] = "insufficient_residual_support"
        return [], report
    target = partial[positive_ids]
    residual = target-carrier[nearest[positive_ids]]
    pairs = cKDTree(target).query_pairs(max(3.*spacing, .025*diagonal), output_type="ndarray")
    if len(pairs):
        left, right = pairs.T
        length = np.linalg.norm(residual, axis=1)
        cosine = np.sum(residual[left]*residual[right], axis=1) / np.maximum(
            length[left]*length[right], 1e-12)
        keep = ((cosine > .8) & (np.linalg.norm(residual[left]-residual[right], axis=1)
                < np.maximum(.5*np.maximum(length[left], length[right]), residual_floor)))
        pairs = pairs[keep]
    rows, cols = pairs.T if len(pairs) else (np.array([], int), np.array([], int))
    graph = sparse.coo_matrix((np.ones(2*len(rows)),
                              (np.r_[rows,cols], np.r_[cols,rows])),
                             shape=(len(target),len(target))).tocsr()
    n, labels = connected_components(graph, directed=False)
    groups = [positive_ids[labels == i] for i in range(n)
              if config.minimum_support <= np.sum(labels == i) <= .25*len(partial)]
    groups.sort(key=lambda ids: -float(np.sum(distances[ids])))
    surface, metric, _ = local_surface_graph(carrier, neighbours=12, edge_ratio=1.85)
    _, components = connected_components(surface, directed=False)
    component_sizes = np.bincount(components)
    candidates = []
    for group in groups[:config.maximum_candidates]:
        # One observed sample per source slot prevents a tip attracting many
        # targets and masquerading as a well-supported rigid correspondence.
        order = group[np.argsort(distances[group])]
        _, unique = np.unique(nearest[order], return_index=True)
        ids = order[unique]
        if len(ids) < config.minimum_support:
            continue
        source_ids = nearest[ids]
        # Nearest surface points do not establish material correspondences:
        # on a long rod, a longitudinal shift leaves most surface samples
        # overlapping. Fitting rotations to those pairs can invent a large
        # tilt. Coherent residuals therefore support translation directly;
        # rotational handles require stronger correspondences in future.
        rotation = np.eye(3)
        translation = np.median(partial[ids]-carrier[source_ids], axis=0)
        angle = float(np.rad2deg(Rotation.from_matrix(rotation).magnitude()))
        centre = carrier[source_ids].mean(axis=0)
        shift = float(np.linalg.norm(centre@rotation.T+translation-centre)) / diagonal
        record = {"partial_ids": ids.tolist(), "source_ids": source_ids.tolist(),
                  "rotation_degrees": angle, "translation_ratio": shift}
        report["regions"].append(record)
        if angle > config.maximum_rotation_degrees or shift > config.maximum_translation:
            record["rejected"] = "motion_exceeds_local_trust_region"
            continue
        dominant = int(np.argmax(np.bincount(components[source_ids])))
        if np.mean(components[source_ids] == dominant) < .8:
            record["rejected"] = "ambiguous_cross_component_correspondence"
            continue
        # A small disconnected surface is moved whole. On a connected object,
        # extend the observed support by a bounded intrinsic surface distance.
        if component_sizes[dominant] <= config.maximum_region_fraction*len(carrier):
            core = np.flatnonzero(components == dominant)
        else:
            extent = np.linalg.norm(np.ptp(carrier[source_ids], axis=0))
            radius = min(.06*diagonal, max(2.*spacing, .25*extent))
            geodesic = dijkstra(metric, directed=False, indices=source_ids,
                                min_only=True, limit=radius)
            core = np.flatnonzero(geodesic <= radius)
        record["core_points"] = int(len(core))
        if len(core) > config.maximum_region_fraction*len(carrier):
            record["rejected"] = "motion_is_not_local"
            continue
        # Existing overlap is not a material anchor: tangential motion can
        # leave a surface equally well explained. Check its actual fit after
        # the proposal instead of rejecting all overlapping rigid cores.
        record["line_search"] = []
        for alpha in (1., .5, .25, .125, .0625):
            proposal, weight = geodesic_rigid_warp(
                carrier, metric, core, rotation, alpha*translation,
                width=config.transition_ratio*diagonal,
            )
            after = cKDTree(proposal).query(partial, workers=-1)[0]
            local_gain = 1.-float(np.mean(after[ids]))/max(float(np.mean(distances[ids])), 1e-12)
            stable = (weight[nearest] > 0.) & (distances <= .5*residual_floor)
            stable_loss = (float(np.quantile(after[stable]-distances[stable], .9))/diagonal
                           if np.any(stable) else 0.)
            affected_edges = surface.multiply((weight > 0.)[:, None]).maximum(
                surface.multiply((weight > 0.)[None, :]))
            local_strain = edge_strain(carrier, proposal, affected_edges)
            trial = {"alpha": alpha, "local_gain": local_gain,
                     "affected_points": int(np.sum(weight>0)),
                     "local_strain": local_strain,
                     "before_p90": float(np.quantile(distances,.9)/diagonal),
                     "after_p90": float(np.quantile(after,.9)/diagonal),
                     "mean_observation_gain": float(np.mean(distances-after)/diagonal),
                     "stable_observation_loss_p90": stable_loss}
            if local_gain < config.minimum_local_gain:
                trial["rejected"] = "insufficient_local_observation_gain"
            elif stable_loss > .002:
                trial["rejected"] = "stable_observation_regressed"
            elif np.mean(after) > np.mean(distances)*1.01 or np.quantile(after,.9) > np.quantile(distances,.9)*1.01:
                trial["rejected"] = "global_observation_regressed"
            elif local_strain["edge_stretch_p01"] < .75 or local_strain["edge_stretch_p99"] > 1.33:
                trial["rejected"] = "attachment_strain"
            record["line_search"].append(trial)
            if "rejected" not in trial:
                record.update(trial)
                record["rotation"] = rotation.tolist()
                record["translation"] = (alpha*translation).tolist()
                record["eligible"] = True
                candidates.append((proposal, record, weight))
                break
        if not record.get("eligible"):
            record["rejected"] = "no_safe_step"
    report["eligible_candidates"] = len(candidates)
    return candidates, report
