"""Opt-in sparse camera bridge: positive indexed evidence, no empty-space loss.

Camera orientation is the parsimonious model. Spatial held-out observations
must support extra rotation freedom. Neither category names nor GT are inputs.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from src.indexed_pixel_sim3 import unique_pixel_matches
from src.robust_similarity import weighted_umeyama
from src.saved_camera import world_to_camera_axes


VERSION = 'sparse_observation_v1'


def camera_bridge_rotation(projector):
    """MoGe uses OpenCV (+x right,+y down,+z forward); Kaolin uses OpenGL."""
    if projector.pinhole_world_to_camera is not None:
        rotation = projector.pinhole_world_to_camera[:3, :3].T
    else:
        rotation = world_to_camera_axes(projector.camera).T @ np.diag([1., -1., -1.])
    # Camera serialization is float32; project to SO(3), not a reflection.
    u, _, vt = np.linalg.svd(rotation)
    result = u @ vt
    if np.linalg.det(result) < 0:
        raise ValueError('saved camera orientation is a reflection')
    return result


def _fixed_rotation_fit(x, y, weight, rotation):
    weight = weight / weight.sum()
    cx, cy = weight @ x, weight @ y
    a, b = (x - cx) @ rotation.T, y - cy
    denominator = np.sum(weight * np.sum(a * a, axis=1))
    if denominator < 1e-16:
        raise ValueError('degenerate source extent')
    scale = np.sum(weight * np.sum(a * b, axis=1)) / denominator
    if not np.isfinite(scale) or scale <= 1e-10:
        raise ValueError('observations do not support a positive camera-aligned scale')
    transform = np.eye(4)
    transform[:3, :3] = scale * rotation
    transform[:3, 3] = cy - scale * rotation @ cx
    return transform


def _residual(x, y, transform):
    return np.linalg.norm(x @ transform[:3, :3].T + transform[:3, 3] - y, axis=1)


def _fit(x, y, weights, camera_rotation, freedom):
    weights = weights / weights.sum()
    robust = weights.copy()
    transform = _fixed_rotation_fit(x, y, robust, camera_rotation)
    for _ in range(12):
        if freedom:
            free = weighted_umeyama(x, y, robust.copy())
            scale = np.cbrt(np.linalg.det(free[:3, :3]))
            if not np.isfinite(scale) or scale <= 0:
                raise ValueError('invalid proper similarity')
            delta = Rotation.from_matrix((free[:3, :3] / scale) @ camera_rotation.T)
            rotation = Rotation.from_rotvec(freedom * delta.as_rotvec()).as_matrix() @ camera_rotation
        else:
            rotation = camera_rotation
        candidate = _fixed_rotation_fit(x, y, robust, rotation)
        distance = _residual(x, y, candidate)
        # Cauchy IRLS, data-estimated scale; no dataset-specific metric threshold.
        sigma = max(float(np.median(distance)), 1e-7)
        robust = weights / (1. + (distance / sigma) ** 2)
        if np.max(np.abs(candidate - transform)) < 1e-9:
            transform = candidate
            break
        transform = candidate
    return transform


def fit_sparse_bridge(source, target, matches, point_uv, camera_rotation):
    """Fit native MoGe -> partial, keeping physical point indices unchanged.

    A 4x4 observed-image partition balances scanning density. Four deterministic
    spatial folds compare camera-only and progressively released rotations.
    The one-standard-error rule favours fewer rotation degrees of freedom.
    Insufficient spatial support retains the camera orientation explicitly.
    """
    source, target = np.asarray(source, float), np.asarray(target, float)
    uv = np.asarray(point_uv, float)
    if uv.shape != (len(target), 2):
        raise ValueError('point_uv must have one 2D entry per partial point')
    pairs = unique_pixel_matches(matches)
    ti, si = pairs[:, 0].astype(int), pairs[:, 1].astype(int)
    if len(pairs) < 6 or np.any(ti < 0) or np.any(ti >= len(target)) or np.any(si < 0) or np.any(si >= len(source)):
        raise ValueError('at least six valid unique pixel correspondences are required')
    x, y, pixel = source[si], target[ti], uv[ti]
    valid = np.isfinite(x).all(1) & np.isfinite(y).all(1) & np.isfinite(pixel).all(1) & np.isfinite(pairs[:, 3])
    x, y, pixel, pairs = x[valid], y[valid], pixel[valid], pairs[valid]
    if len(x) < 6:
        raise ValueError('too few finite indexed observations')
    r0 = np.asarray(camera_rotation, float)
    if r0.shape != (3, 3) or not np.allclose(r0.T @ r0, np.eye(3), atol=1e-5) or np.linalg.det(r0) < 0:
        raise ValueError('camera_rotation must be proper orthonormal')
    # Normalize both domains for stable fitting at arbitrary scene units.
    cx, cy = np.median(x, axis=0), np.median(y, axis=0)
    sx = max(float(np.linalg.norm(np.ptp(x, axis=0))), 1e-12)
    sy = max(float(np.linalg.norm(np.ptp(y, axis=0))), 1e-12)
    xn, yn = (x - cx) / sx, (y - cy) / sy
    span = np.maximum(np.ptp(pixel, axis=0), 1e-12)
    grid = np.minimum(((pixel - pixel.min(0)) / span * 4).astype(int), 3)
    cells = grid[:, 0] + 4 * grid[:, 1]
    occupied, counts = np.unique(cells, return_counts=True)
    count_map = dict(zip(occupied, counts))
    confidence = np.exp(-np.maximum(pairs[:, 3], 0.) / 2.)
    def weights_for(mask):
        # Equal mass per occupied cell even if pixel-match confidence differs.
        w = confidence[mask].copy()
        for cell in np.unique(cells[mask]):
            chosen = cells[mask] == cell
            w[chosen] /= max(w[chosen].sum(), 1e-30)
        return w / w.sum()
    folds = (grid[:, 0] + 2 * grid[:, 1]) % 4
    singular = np.linalg.svd(xn - xn.mean(0), compute_uv=False)
    identifiable = bool(len(occupied) >= 8 and singular[1] > 1e-4 * singular[0])
    candidates = []
    freedoms = (0., .25, .5, 1.) if identifiable else (0.,)
    for freedom in freedoms:
        losses = []
        if identifiable:
            for fold in range(4):
                train, test = folds != fold, folds == fold
                if train.sum() < 6 or test.sum() < 2:
                    losses = []
                    break
                try:
                    transform = _fit(xn[train], yn[train], weights_for(train), r0, freedom)
                    residual = _residual(xn[test], yn[test], transform)
                    # Spatial cell median suppresses isolated returns; folds are
                    # held out as spatial groups, never duplicate dense points.
                    losses.append(float(np.mean([np.median(residual[cells[test] == c]) for c in np.unique(cells[test])])))
                except (ValueError, np.linalg.LinAlgError):
                    losses = []
                    break
        candidates.append({'rotation_fraction': freedom, 'fold_errors': losses,
                           'mean': float(np.mean(losses)) if losses else None,
                           'standard_error': float(np.std(losses, ddof=1) / np.sqrt(len(losses))) if len(losses) > 1 else None})
    eligible = [c for c in candidates if len(c['fold_errors']) == 4]
    if eligible:
        best = min(eligible, key=lambda c: c['mean'])
        chosen = min((c for c in eligible if c['mean'] <= best['mean'] + best['standard_error']), key=lambda c: c['rotation_fraction'])
        reason = 'spatial_holdout_one_standard_error'
    else:
        chosen = candidates[0]
        reason = 'insufficient_spatial_support_camera_orientation_retained'
    all_mask = np.ones(len(x), dtype=bool)
    transform = _fit(xn, yn, weights_for(all_mask), r0, chosen['rotation_fraction'])
    transform[:3, :3] *= sy / sx
    transform[:3, 3] = cy + sy * transform[:3, 3] - transform[:3, :3] @ cx
    residual = _residual(x, y, transform)
    scale = float(np.cbrt(np.linalg.det(transform[:3, :3])))
    return transform, {
        'method': VERSION, 'ground_truth_used': False, 'unique_pixel_pairs': len(x),
        'occupied_image_cells': len(occupied), 'cell_counts': {str(k): int(v) for k, v in count_map.items()},
        'source_singular_values_normalized': singular.tolist(), 'selection': reason,
        'rotation_fraction': chosen['rotation_fraction'], 'candidates': candidates,
        'camera_rotation': r0.tolist(), 'scale': scale,
        'camera_rotation_delta_degrees': float(np.degrees(Rotation.from_matrix(transform[:3, :3] / scale @ r0.T).magnitude())),
        'median_indexed_residual': float(np.median(residual)),
        'p90_indexed_residual': float(np.quantile(residual, .9)),
        'empty_space_penalty': False, 'densified_points_used': False,
    }


def refine_sparse_scale_translation(partial, registered, point_uv, projector):
    """Positive visible-surface fit after the bridge, with rotation fixed.

    A spatial holdout chooses among the initial placement and ICP iterates.
    Only scale/translation can change, so this step cannot reintroduce tilt.
    Unobserved complete surfaces never appear as negative measurements.
    """
    from scipy.spatial import cKDTree
    from src.ray_consistent_registration import zbuffer_indices, apply_transform

    partial, registered = np.asarray(partial, float), np.asarray(registered, float)
    uv = np.asarray(point_uv, float)
    if uv.shape != (len(partial), 2) or not np.isfinite(partial).all() or not np.isfinite(uv).all():
        raise ValueError('finite partial points and aligned UV required')
    low, span = uv.min(0), np.maximum(np.ptp(uv, axis=0), 1e-12)
    grid = np.minimum(((uv - low) / span * 4).astype(int), 3)
    cells = grid[:, 0] + 4 * grid[:, 1]
    holdout = (grid[:, 0] + 2 * grid[:, 1]) % 4 == 0
    if holdout.sum() < 6 or (~holdout).sum() < 6 or len(np.unique(cells[holdout])) < 2:
        return registered.copy(), {'applied': False, 'reason': 'insufficient_spatial_holdout'}
    sample_ids = np.linspace(0, len(registered)-1, min(len(registered), 32000), dtype=int)
    source = registered[sample_ids]
    scale_unit = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-12)
    center = np.median(partial, axis=0)
    x, y = (source-center)/scale_unit, (partial-center)/scale_unit
    train = ~holdout
    weights = np.ones(train.sum())
    for cell in np.unique(cells[train]):
        chosen = cells[train] == cell
        weights[chosen] /= chosen.sum()
    def correspond(transform):
        moved = apply_transform(x, transform)
        pixels, depth = projector.project(moved*scale_unit + center)
        _, mask, indices = zbuffer_indices(pixels, depth, projector.image_shape)
        visible = np.unique(indices[mask])
        if len(visible) < 6:
            raise ValueError('fewer than six visible carrier samples')
        distance, ids = cKDTree(moved[visible]).query(y, workers=1)
        return distance, visible[ids]
    def heldout_loss(distance):
        errors = np.array([np.median(distance[cells == cell]) for cell in np.unique(cells[holdout])])
        return float(errors.mean()), float(errors.std(ddof=1)/np.sqrt(len(errors)))
    transform = np.eye(4)
    distance, ids = correspond(transform)
    loss, error = heldout_loss(distance)
    candidates = [(transform.copy(), loss, error)]
    for _ in range(12):
        try:
            candidate = _fit(x[ids[train]], y[train], weights, np.eye(3), 0.)
            distance, new_ids = correspond(candidate)
            loss, error = heldout_loss(distance)
        except (ValueError, np.linalg.LinAlgError):
            break
        candidates.append((candidate.copy(), loss, error))
        if np.max(np.abs(candidate-transform)) < 1e-7:
            break
        transform, ids = candidate, new_ids
    best = min(candidates, key=lambda c: c[1])
    # Earliest iterate within validation uncertainty avoids needless movement.
    selected = next(i for i, c in enumerate(candidates) if c[1] <= best[1] + best[2])
    transform = candidates[selected][0].copy()
    transform[:3, 3] = center + scale_unit*transform[:3, 3] - transform[:3, :3]@center
    return apply_transform(registered, transform), {
        'applied': selected > 0, 'selected_iteration': selected,
        'selection': 'spatial_holdout_one_standard_error_earliest_iterate',
        'rotation_fixed': True, 'empty_space_penalty': False,
        'validation': [{'iteration':i,'mean':c[1],'standard_error':c[2]} for i,c in enumerate(candidates)],
        'transform': transform.tolist(),
    }


def select_sparse_candidate(partial, baseline, candidate, point_uv):
    """Conservative observed-only comparison against the unchanged main route.

    A candidate must improve spatially balanced support beyond cell uncertainty,
    while not regressing either mean or p95 distance over actual observations.
    These are geometry witnesses, not a claim of semantic or hidden accuracy.
    """
    from scipy.spatial import cKDTree
    partial, baseline, candidate = map(lambda x: np.asarray(x, float), (partial, baseline, candidate))
    if baseline.shape != candidate.shape or not all(np.isfinite(x).all() for x in (partial, baseline, candidate)):
        raise ValueError('finite candidates with identical carrier counts required')
    uv = np.asarray(point_uv, float)
    if uv.shape != (len(partial), 2) or not np.isfinite(uv).all():
        raise ValueError('finite aligned point UV required')
    grid = np.minimum(((uv-uv.min(0))/np.maximum(np.ptp(uv,axis=0),1e-12)*4).astype(int),3)
    cells = grid[:,0]+4*grid[:,1]
    scale = max(float(np.linalg.norm(np.ptp(partial, axis=0))),1e-12)
    old = cKDTree(baseline).query(partial, workers=1)[0]/scale
    new = cKDTree(candidate).query(partial, workers=1)[0]/scale
    gains = np.array([np.median(old[cells==c])-np.median(new[cells==c]) for c in np.unique(cells)])
    error = float(gains.std(ddof=1)/np.sqrt(len(gains))) if len(gains)>1 else float('inf')
    accepted = bool(gains.mean()>error and new.mean()<old.mean() and np.quantile(new,.95)<=np.quantile(old,.95))
    return accepted, {
        'selected': 'sparse' if accepted else 'mainline', 'ground_truth_used':False,
        'spatial_mean_gain':float(gains.mean()),
        'spatial_gain_standard_error':error if np.isfinite(error) else None,
        'baseline':{'mean_percent':float(old.mean()*100),'p95_percent':float(np.quantile(old,.95)*100)},
        'candidate':{'mean_percent':float(new.mean()*100),'p95_percent':float(np.quantile(new,.95)*100)},
        'reason':'positive_spatial_gain_beyond_uncertainty_and_mean_p95_nonregression' if accepted else 'insufficient_consistent_observed_gain_keep_mainline',
        'limitation':'Does not certify semantic correspondence or unseen geometry.'}
