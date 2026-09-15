"""MoGe-anchored residual registration for extremely sparse observations.

The standard two-camera bridge assumes that a transferred Camera-1 pixel and
the nearest native-MoGe pixel describe the same physical surface sample.  That
assumption is unnecessarily brittle for sparse LiDAR: a completion image may
move a contour by a few pixels while preserving the correct object and camera.

This module keeps the analytic Pixal--MoGe relation fixed and refines only the
native-MoGe-to-observation Sim(3).  Correspondences are selected from a small
pixel neighbourhood, scored in the current 3-D frame, spatially balanced over
the image, and robustly re-estimated from coarse to fine.  It is an opt-in
sparse-input adapter; no object-mainline default calls it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.spatial import cKDTree

from src.bidirectional_cycle_registration import interpolate_sim3, invert_proper_sim3
from src.indexed_pixel_sim3 import unique_pixel_matches
from src.ray_consistent_registration import apply_transform, bounded_delta_sim3
from src.robust_similarity import validate_proper_sim3, weighted_umeyama


def moge_to_saved_raster_convention(*, flip_saved_uv_y: bool) -> tuple[np.ndarray, dict]:
    """Convert MoGe/OpenCV camera coordinates to the saved Kaolin raster frame.

    MoGe uses image coordinates with ``+z`` forward.  Kaolin's view frame uses
    ``-z`` forward.  A standard top-left raster also reverses camera ``y``;
    the historical depth painter reverses the raster once more.  The latter is
    represented by ``flip_saved_uv_y=True`` in the two-camera bridge.

    This is a fixed coordinate-convention conversion, not an estimated object
    reflection.  Keeping it separate lets every subsequently estimated motion
    remain a proper Sim(3).
    """
    step = np.eye(4, dtype=np.float64)
    step[1, 1] = 1.0 if bool(flip_saved_uv_y) else -1.0
    step[2, 2] = -1.0
    return step, {
        "method": "moge_opencv_to_saved_kaolin_raster_convention",
        "flip_saved_uv_y": bool(flip_saved_uv_y),
        "axis_signs": np.diag(step)[:3].tolist(),
        "determinant": float(np.linalg.det(step[:3, :3])),
        "estimated_from_geometry": False,
    }


def camera_anchored_indexed_similarity(
    convention_moge: np.ndarray,
    partial: np.ndarray,
    matches: np.ndarray,
    world_to_camera_axes: np.ndarray,
    *,
    diagonal: float,
    trim_quantile: float = .72,
    iterations: int = 6,
) -> tuple[np.ndarray, dict]:
    """Fit positive scale and translation while fixing the saved camera axes.

    Pixel-indexed pairs already determine the observation orientation.  A
    free three-dimensional rotation can turn monocular depth error into a
    spurious object rotation, especially for sparse LiDAR.  This fit therefore
    maps convention-corrected MoGe through the analytic camera-to-world basis
    and robustly estimates only one positive scale and a translation.
    """
    source = np.asarray(convention_moge, dtype=np.float64)
    target = np.asarray(partial, dtype=np.float64)
    pairs = unique_pixel_matches(matches)
    target_ids = pairs[:, 0].astype(np.int64)
    source_ids = pairs[:, 1].astype(np.int64)
    axes = np.asarray(world_to_camera_axes, dtype=np.float64)
    if axes.shape != (3, 3) or not np.allclose(
        axes @ axes.T, np.eye(3), atol=1e-5, rtol=1e-4,
    ):
        raise ValueError("world_to_camera_axes must be orthonormal")
    if len(pairs) < 6:
        raise ValueError("camera-anchored fit requires at least six indexed pairs")
    rotation = axes.T
    oriented = source[source_ids] @ rotation.T
    observed = target[target_ids]
    confidence = np.exp(-np.clip(pairs[:, 3], 0.0, None) / 2.0)
    keep = np.ones(len(pairs), dtype=bool)
    scale, translation = 1.0, np.zeros(3, dtype=np.float64)
    residual = np.full(len(pairs), np.inf, dtype=np.float64)
    for _ in range(max(int(iterations), 1)):
        weights = confidence * keep
        if int(keep.sum()) < 6 or float(weights.sum()) <= 1e-12:
            break
        source_mean = np.sum(oriented * weights[:, None], axis=0) / weights.sum()
        target_mean = np.sum(observed * weights[:, None], axis=0) / weights.sum()
        source_centered = oriented - source_mean
        target_centered = observed - target_mean
        denominator = float(np.sum(weights * np.sum(source_centered ** 2, axis=1)))
        numerator = float(np.sum(weights * np.sum(source_centered * target_centered, axis=1)))
        scale = max(numerator / max(denominator, 1e-12), 1e-8)
        translation = target_mean - scale * source_mean
        residual = np.linalg.norm(scale * oriented + translation - observed, axis=1)
        active = residual[keep]
        median = float(np.median(active))
        mad = float(np.median(np.abs(active - median)))
        robust_limit = median + 2.5 * max(1.4826 * mad, 1e-8)
        quantile_limit = float(np.quantile(active, float(trim_quantile)))
        keep = residual <= min(robust_limit, quantile_limit)
    if int(keep.sum()) < 6:
        raise RuntimeError("camera-anchored fit rejected too many indexed pairs")
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = scale * rotation
    transform[:3, 3] = translation
    validate_proper_sim3(transform)
    return transform, {
        "method": "camera_anchored_positive_scale_translation_indexed_fit",
        "unique_pixel_pairs": int(len(pairs)),
        "inliers": int(keep.sum()),
        "inlier_ratio": float(keep.mean()),
        "trim_quantile": float(trim_quantile),
        "scale": float(scale),
        "residual_median": float(np.median(residual[keep])),
        "residual_p90": float(np.quantile(residual[keep], .90)),
        "residual_median_normalized": float(np.median(residual[keep]) / max(diagonal, 1e-8)),
        "residual_p90_normalized": float(
            np.quantile(residual[keep], .90) / max(diagonal, 1e-8)
        ),
        "world_to_camera_axes": axes,
    }


@dataclass(frozen=True)
class SparseRayRegistrationConfig:
    """Category-independent settings normalized by image/object resolution."""

    candidate_count: int = 24
    radius_fractions: tuple[float, ...] = (.045, .028, .017, .010)
    trim_quantiles: tuple[float, ...] = (.78, .74, .70, .68)
    pixel_cost_weight: float = .08
    grid_size: int = 8
    minimum_pairs: int = 48
    maximum_rotation_deg: float = 3.0
    scale_bounds: tuple[float, float] = (.94, 1.06)
    maximum_translation_ratio: float = .06
    line_search_fractions: tuple[float, ...] = (1.0, .75, .50, .25)
    minimum_relative_improvement: float = 1e-4

    def validate(self) -> None:
        if self.candidate_count < 2 or self.minimum_pairs < 6:
            raise ValueError("candidate_count and minimum_pairs are too small")
        if len(self.radius_fractions) != len(self.trim_quantiles):
            raise ValueError("radius and trim schedules must have equal length")
        if not self.radius_fractions or any(value <= 0. for value in self.radius_fractions):
            raise ValueError("radius fractions must be positive")
        if any(not .5 < value < 1. for value in self.trim_quantiles):
            raise ValueError("trim quantiles must lie in (0.5, 1)")
        if not 0. < self.scale_bounds[0] <= 1. <= self.scale_bounds[1]:
            raise ValueError("scale bounds must contain one")


def _candidate_table(
    mapped_partial_pixels: np.ndarray,
    valid_partial: np.ndarray,
    moge_pixels: np.ndarray,
    *,
    candidate_count: int,
    radius: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return partial ids, candidate MoGe ids and normalized pixel distances."""
    mapped = np.asarray(mapped_partial_pixels, dtype=np.float64)
    valid = np.asarray(valid_partial, dtype=bool)
    target = np.asarray(moge_pixels, dtype=np.float64)
    source_ids = np.flatnonzero(valid & np.isfinite(mapped).all(axis=1))
    if not len(source_ids) or not len(target):
        return source_ids, np.empty((0, 0), dtype=np.int64), np.empty((0, 0))
    count = min(int(candidate_count), len(target))
    distance, candidate = cKDTree(target).query(mapped[source_ids], k=count)
    if count == 1:
        distance, candidate = distance[:, None], candidate[:, None]
    keep = np.isfinite(distance) & (distance <= float(radius))
    candidate = np.where(keep, candidate, -1)
    normalized = np.where(keep, distance / max(float(radius), 1e-8), np.inf)
    useful = np.any(keep, axis=1)
    return source_ids[useful], candidate[useful], normalized[useful]


def _balanced_weights(pixel_xy: np.ndarray, residual: np.ndarray, *, grid_size: int) -> np.ndarray:
    """Balance sparse scan density while retaining a smooth robust residual weight."""
    pixel_xy = np.asarray(pixel_xy, dtype=np.float64)
    residual = np.asarray(residual, dtype=np.float64)
    low, high = np.quantile(pixel_xy, [.01, .99], axis=0)
    extent = np.maximum(high - low, 1.)
    cell = np.floor((pixel_xy - low) / extent * int(grid_size)).astype(np.int64)
    cell = np.clip(cell, 0, int(grid_size) - 1)
    linear = cell[:, 1] * int(grid_size) + cell[:, 0]
    count = np.bincount(linear, minlength=int(grid_size) ** 2)
    spatial = 1. / np.sqrt(np.maximum(count[linear], 1))
    median = float(np.median(residual))
    mad = float(np.median(np.abs(residual - median)))
    scale = max(1.4826 * mad, .10 * median, 1e-8)
    robust = 1. / (1. + np.square(residual / (median + 2.5 * scale)))
    weights = spatial * robust
    return weights / max(float(np.median(weights)), 1e-8)


def _ray_surface_pairs(
    moge: np.ndarray,
    partial: np.ndarray,
    mapped_partial_pixels: np.ndarray,
    partial_ids: np.ndarray,
    candidate_ids: np.ndarray,
    candidate_pixel_distance: np.ndarray,
    transform: np.ndarray,
    *,
    diagonal: float,
    pixel_cost_weight: float,
    trim_quantile: float,
    grid_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Select one collision-free, camera-local surface candidate per observation."""
    transformed = apply_transform(moge, transform)
    valid_candidate = candidate_ids >= 0
    safe_ids = np.maximum(candidate_ids, 0)
    delta = transformed[safe_ids] - partial[partial_ids, None, :]
    distance = np.linalg.norm(delta, axis=2) / max(float(diagonal), 1e-8)
    score = distance + float(pixel_cost_weight) * np.square(candidate_pixel_distance)
    score[~valid_candidate] = np.inf
    rank = np.argmin(score, axis=1)
    row = np.arange(len(partial_ids))
    chosen_moge = candidate_ids[row, rank]
    chosen_score = score[row, rank]
    chosen_distance = distance[row, rank] * float(diagonal)
    finite = (chosen_moge >= 0) & np.isfinite(chosen_score) & np.isfinite(chosen_distance)
    if int(finite.sum()) < 6:
        return (np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64),
                np.empty(0), {"pairs": 0, "reason": "too_few_finite_candidates"})
    limit = min(
        float(np.quantile(chosen_distance[finite], float(trim_quantile))),
        .25 * float(diagonal),
    )
    keep = finite & (chosen_distance <= max(limit, .005 * float(diagonal)))
    p_ids, m_ids = partial_ids[keep], chosen_moge[keep]
    residual, fit_score = chosen_distance[keep], chosen_score[keep]
    # A generated surface point has unit capacity.  Sorting by current fit
    # avoids allowing a dense LiDAR strip to claim the same carrier repeatedly.
    order = np.lexsort((p_ids, fit_score, m_ids))
    p_ids, m_ids, residual = p_ids[order], m_ids[order], residual[order]
    unique = np.r_[True, m_ids[1:] != m_ids[:-1]]
    p_ids, m_ids, residual = p_ids[unique], m_ids[unique], residual[unique]
    weights = _balanced_weights(mapped_partial_pixels[p_ids], residual, grid_size=int(grid_size))
    return p_ids, m_ids, weights, {
        "pairs": int(len(p_ids)),
        "candidate_rows": int(len(partial_ids)),
        "trim_limit": float(limit),
        "residual_median": float(np.median(residual)) if len(residual) else None,
        "residual_p90": float(np.quantile(residual, .90)) if len(residual) else None,
        "occupied_grid_cells": int(len(np.unique(
            np.floor(mapped_partial_pixels[p_ids] / max(np.ptp(mapped_partial_pixels[p_ids], axis=0).max(), 1.)
                     * int(grid_size)).astype(np.int64), axis=0
        ))) if len(p_ids) else 0,
    }


def _centred_bounded_step(
    source: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
    centre: np.ndarray,
    *,
    maximum_rotation_deg: float,
    scale_bounds: tuple[float, float],
    maximum_translation: float,
) -> np.ndarray:
    raw = weighted_umeyama(source - centre, target - centre, weights)
    bounded = bounded_delta_sim3(
        raw,
        max_rotation_deg=float(maximum_rotation_deg),
        scale_bounds=scale_bounds,
        max_translation=float(maximum_translation),
    )
    step = np.eye(4, dtype=np.float64)
    step[:3, :3] = bounded[:3, :3]
    step[:3, 3] = centre + bounded[:3, 3] - bounded[:3, :3] @ centre
    return step


def sparse_ray_surface_refine(
    moge: np.ndarray,
    partial: np.ndarray,
    mapped_partial_pixels: np.ndarray,
    valid_partial: np.ndarray,
    moge_pixels: np.ndarray,
    initial_moge_to_partial: np.ndarray,
    *,
    target_mask_bbox_diagonal: float,
    config: SparseRayRegistrationConfig | None = None,
) -> tuple[np.ndarray, dict]:
    """Refine a two-camera bridge without exposing the mainline to sparse noise."""
    config = config or SparseRayRegistrationConfig()
    config.validate()
    moge = np.asarray(moge, dtype=np.float64)
    partial = np.asarray(partial, dtype=np.float64)
    mapped = np.asarray(mapped_partial_pixels, dtype=np.float64)
    valid = np.asarray(valid_partial, dtype=bool)
    current = np.asarray(initial_moge_to_partial, dtype=np.float64).copy()
    validate_proper_sim3(current)
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-8)
    centre = np.median(partial, axis=0)
    trace: list[dict] = []
    last_pairs: tuple[np.ndarray, np.ndarray] = (
        np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64),
    )
    for level, (radius_fraction, trim_quantile) in enumerate(zip(
        config.radius_fractions, config.trim_quantiles,
    )):
        radius = max(float(radius_fraction) * float(target_mask_bbox_diagonal), 2.0)
        p_candidates, candidate_ids, pixel_distance = _candidate_table(
            mapped, valid, moge_pixels,
            candidate_count=int(config.candidate_count), radius=radius,
        )
        p_ids, m_ids, weights, before = _ray_surface_pairs(
            moge, partial, mapped, p_candidates, candidate_ids, pixel_distance, current,
            diagonal=diagonal, pixel_cost_weight=float(config.pixel_cost_weight),
            trim_quantile=float(trim_quantile), grid_size=int(config.grid_size),
        )
        record = {
            "level": int(level), "radius_pixels": float(radius),
            "radius_fraction": float(radius_fraction),
            "trim_quantile": float(trim_quantile), "before": before,
        }
        if len(p_ids) < int(config.minimum_pairs):
            record.update({"accepted": False, "reason": "insufficient_balanced_pairs"})
            trace.append(record)
            continue
        moved_moge = apply_transform(moge[m_ids], current)
        raw_step = _centred_bounded_step(
            moved_moge, partial[p_ids], weights, centre,
            maximum_rotation_deg=float(config.maximum_rotation_deg),
            scale_bounds=config.scale_bounds,
            maximum_translation=float(config.maximum_translation_ratio) * diagonal,
        )
        best = None
        before_value = float(before["residual_median"] + .35 * before["residual_p90"])
        for fraction in config.line_search_fractions:
            step = interpolate_sim3(raw_step, float(fraction))
            candidate_transform = step @ current
            after_p, after_m, _, after = _ray_surface_pairs(
                moge, partial, mapped, p_candidates, candidate_ids, pixel_distance,
                candidate_transform, diagonal=diagonal,
                pixel_cost_weight=float(config.pixel_cost_weight),
                trim_quantile=float(trim_quantile), grid_size=int(config.grid_size),
            )
            if len(after_p) < int(config.minimum_pairs):
                continue
            value = float(after["residual_median"] + .35 * after["residual_p90"])
            candidate = (value, float(fraction), candidate_transform, after_p, after_m, after)
            if best is None or value < best[0]:
                best = candidate
        if best is None or best[0] >= before_value * (1. - float(config.minimum_relative_improvement)):
            record.update({"accepted": False, "reason": "no_robust_improvement",
                           "objective_before": before_value,
                           "objective_after": None if best is None else best[0]})
        else:
            value, fraction, current, after_p, after_m, after = best
            last_pairs = after_p, after_m
            record.update({"accepted": True, "fraction": fraction,
                           "objective_before": before_value, "objective_after": value,
                           "after": after})
        trace.append(record)
    validate_proper_sim3(current)
    accepted = [record for record in trace if record.get("accepted")]
    return current, {
        "method": "moge_anchored_sparse_ray_surface_sim3",
        "config": asdict(config),
        "partial_diagonal": float(diagonal),
        "trace": trace,
        "accepted_levels": int(len(accepted)),
        "final_pairs": int(len(last_pairs[0])),
        "final_partial_ids": last_pairs[0],
        "final_moge_ids": last_pairs[1],
        "initial_moge_to_partial": initial_moge_to_partial,
        "moge_to_partial": current,
    }


def _partial_to_moge_pairs(
    moge: np.ndarray,
    partial: np.ndarray,
    mapped_partial_pixels: np.ndarray,
    partial_ids: np.ndarray,
    candidate_ids: np.ndarray,
    candidate_pixel_distance: np.ndarray,
    partial_to_moge: np.ndarray,
    *,
    native_diagonal: float,
    pixel_cost_weight: float,
    trim_quantile: float,
    grid_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Match each sparse observation to the dense native-MoGe surface."""
    query = apply_transform(partial[partial_ids], partial_to_moge)
    valid_candidate = candidate_ids >= 0
    safe_ids = np.maximum(candidate_ids, 0)
    distance = np.linalg.norm(moge[safe_ids] - query[:, None, :], axis=2)
    normalized = distance / max(float(native_diagonal), 1e-8)
    score = normalized + float(pixel_cost_weight) * np.square(candidate_pixel_distance)
    score[~valid_candidate] = np.inf
    rank = np.argmin(score, axis=1)
    row = np.arange(len(partial_ids))
    chosen_moge = candidate_ids[row, rank]
    chosen_score = score[row, rank]
    chosen_distance = distance[row, rank]
    finite = (chosen_moge >= 0) & np.isfinite(chosen_score) & np.isfinite(chosen_distance)
    if int(finite.sum()) < 6:
        return (np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64),
                np.empty(0), {"pairs": 0, "reason": "too_few_finite_candidates"})
    limit = min(
        float(np.quantile(chosen_distance[finite], float(trim_quantile))),
        .25 * float(native_diagonal),
    )
    keep = finite & (chosen_distance <= max(limit, .005 * float(native_diagonal)))
    p_ids, m_ids = partial_ids[keep], chosen_moge[keep]
    residual, fit_score = chosen_distance[keep], chosen_score[keep]
    # The sparse observations are the queries.  Retain one claim per dense
    # surface slot while preserving the best currently supported observation.
    order = np.lexsort((p_ids, fit_score, m_ids))
    p_ids, m_ids, residual = p_ids[order], m_ids[order], residual[order]
    unique = np.r_[True, m_ids[1:] != m_ids[:-1]]
    p_ids, m_ids, residual = p_ids[unique], m_ids[unique], residual[unique]
    weights = _balanced_weights(mapped_partial_pixels[p_ids], residual, grid_size=int(grid_size))
    return p_ids, m_ids, weights, {
        "pairs": int(len(p_ids)),
        "candidate_rows": int(len(partial_ids)),
        "trim_limit": float(limit),
        "residual_median": float(np.median(residual)) if len(residual) else None,
        "residual_p90": float(np.quantile(residual, .90)) if len(residual) else None,
    }


def sparse_partial_to_moge_refine(
    moge: np.ndarray,
    partial: np.ndarray,
    mapped_partial_pixels: np.ndarray,
    valid_partial: np.ndarray,
    moge_pixels: np.ndarray,
    initial_moge_to_partial: np.ndarray,
    *,
    target_mask_bbox_diagonal: float,
    config: SparseRayRegistrationConfig | None = None,
) -> tuple[np.ndarray, dict]:
    """Fit sparse partial queries to dense MoGe, then return the inverse map.

    This direction is deliberately asymmetric.  Missing LiDAR samples do not
    ask the complete surface to move; every measured query instead selects a
    nearby point on the dense semantic surface.  Only a globally supported
    proper Sim(3) is estimated, so the complete Pixal carrier remains intact.
    """
    config = config or SparseRayRegistrationConfig()
    config.validate()
    moge = np.asarray(moge, dtype=np.float64)
    partial = np.asarray(partial, dtype=np.float64)
    mapped = np.asarray(mapped_partial_pixels, dtype=np.float64)
    valid = np.asarray(valid_partial, dtype=bool)
    current = invert_proper_sim3(np.asarray(initial_moge_to_partial, dtype=np.float64))
    native_diagonal = max(float(np.linalg.norm(np.ptp(moge, axis=0))), 1e-8)
    trace: list[dict] = []
    last_pairs = (np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64))
    for level, (radius_fraction, trim_quantile) in enumerate(zip(
        config.radius_fractions, config.trim_quantiles,
    )):
        radius = max(float(radius_fraction) * float(target_mask_bbox_diagonal), 2.0)
        p_candidates, candidate_ids, pixel_distance = _candidate_table(
            mapped, valid, moge_pixels,
            candidate_count=int(config.candidate_count), radius=radius,
        )
        p_ids, m_ids, weights, before = _partial_to_moge_pairs(
            moge, partial, mapped, p_candidates, candidate_ids, pixel_distance, current,
            native_diagonal=native_diagonal,
            pixel_cost_weight=float(config.pixel_cost_weight),
            trim_quantile=float(trim_quantile), grid_size=int(config.grid_size),
        )
        record = {
            "level": int(level), "radius_pixels": float(radius),
            "radius_fraction": float(radius_fraction),
            "trim_quantile": float(trim_quantile), "before": before,
        }
        if len(p_ids) < int(config.minimum_pairs):
            record.update({"accepted": False, "reason": "insufficient_balanced_pairs"})
            trace.append(record)
            continue
        source = apply_transform(partial[p_ids], current)
        centre = np.median(source, axis=0)
        raw_step = _centred_bounded_step(
            source, moge[m_ids], weights, centre,
            maximum_rotation_deg=float(config.maximum_rotation_deg),
            scale_bounds=config.scale_bounds,
            maximum_translation=float(config.maximum_translation_ratio) * native_diagonal,
        )
        before_value = float(before["residual_median"] + .35 * before["residual_p90"])
        best = None
        for fraction in config.line_search_fractions:
            step = interpolate_sim3(raw_step, float(fraction))
            candidate_transform = step @ current
            after_p, after_m, _, after = _partial_to_moge_pairs(
                moge, partial, mapped, p_candidates, candidate_ids, pixel_distance,
                candidate_transform, native_diagonal=native_diagonal,
                pixel_cost_weight=float(config.pixel_cost_weight),
                trim_quantile=float(trim_quantile), grid_size=int(config.grid_size),
            )
            if len(after_p) < int(config.minimum_pairs):
                continue
            value = float(after["residual_median"] + .35 * after["residual_p90"])
            candidate = (value, float(fraction), candidate_transform, after_p, after_m, after)
            if best is None or value < best[0]:
                best = candidate
        if best is None or best[0] >= before_value * (1. - float(config.minimum_relative_improvement)):
            record.update({"accepted": False, "reason": "no_robust_improvement",
                           "objective_before": before_value,
                           "objective_after": None if best is None else best[0]})
        else:
            value, fraction, current, after_p, after_m, after = best
            last_pairs = after_p, after_m
            record.update({"accepted": True, "fraction": fraction,
                           "objective_before": before_value, "objective_after": value,
                           "after": after})
        trace.append(record)
    refined = invert_proper_sim3(current)
    validate_proper_sim3(refined)
    accepted = [record for record in trace if record.get("accepted")]
    return refined, {
        "method": "sparse_partial_query_to_dense_moge_surface_sim3",
        "config": asdict(config),
        "native_moge_diagonal": float(native_diagonal),
        "trace": trace,
        "accepted_levels": int(len(accepted)),
        "final_pairs": int(len(last_pairs[0])),
        "final_partial_ids": last_pairs[0],
        "final_moge_ids": last_pairs[1],
        "initial_moge_to_partial": initial_moge_to_partial,
        "moge_to_partial": refined,
    }
