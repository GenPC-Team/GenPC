"""Fuse a physical partial scan into a deformed complete carrier.

The fusion is an observation decoder rather than another deformation stage.
Camera-consistent correspondences from the four mainline views replace an
equal number of complete-carrier slots. Thus measured samples occupy observed
surface locations while unmatched slots retain the complete posterior.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from src.partial_transport import _median_spacing
from src.posterior_deformation import _embedded_arap_posterior
from src.visible_pixel_sim3_refinement import visible_pixel_pairs


@dataclass(frozen=True)
class ObservationAnchoredFusionConfig:
    """Shared category- and sample-independent fusion parameters."""

    num_views: int = 4
    pixel_radius: float = 1.0
    cross_view_pixel_radius: float = 2.0
    cross_view_depth_ratio: float = 0.075
    anchor_residual_ratio: float = 0.075
    max_pairs_per_view: int = 100_000


@dataclass(frozen=True)
class ContinuousObservationFusionConfig:
    """Shared controls for structure-preserving measurement assimilation.

    The thresholds are dimensionless or normalized by measured point spacing.
    They are intentionally category- and dataset-independent.
    """

    num_views: int = 4
    pixel_radius: float = 1.0
    cross_view_pixel_radius: float = 2.0
    cross_view_depth_ratio: float = 0.03
    maximum_residual_ratio: float = 0.03
    minimum_view_support: int = 2
    residual_quantile: float = 0.90
    partial_spacing_multiplier: float = 6.0
    carrier_influence_multiplier: float = 12.0
    partial_influence_multiplier: float = 4.0
    max_pairs_per_view: int = 100_000
    node_fraction: float = 0.04
    minimum_nodes: int = 192
    maximum_nodes: int = 6_144
    neighbours: int = 10
    edge_ratio: float = 1.85
    attachment_edge_ratio: float = 3.2
    data_weight: float = 4.0
    screening: float = 0.004
    iterations: int = 3
    minimum_improvement: float = 0.01
    minimum_edge_compression: float = 0.70
    maximum_edge_stretch: float = 1.80
    minimum_hidden_coverage: float = 0.98
    coverage_resolution: int = 160


def _adaptive_residual_limit(
    residual: np.ndarray,
    *,
    diagonal: float,
    partial_spacing: float,
    config: ContinuousObservationFusionConfig,
) -> float:
    """Choose a density-aware metric gate without sample-specific units."""
    values = np.asarray(residual, dtype=np.float64)
    values = values[np.isfinite(values)]
    hard_limit = float(config.maximum_residual_ratio) * float(diagonal)
    if not len(values):
        return hard_limit
    density_limit = float(config.partial_spacing_multiplier) * float(partial_spacing)
    distribution_limit = float(np.quantile(values, float(config.residual_quantile)))
    return min(hard_limit, max(density_limit, distribution_limit))


def positive_multiview_pairs(
    partial: np.ndarray,
    carrier: np.ndarray,
    projectors: list,
    *,
    config: ObservationAnchoredFusionConfig,
    diagonal: float,
) -> tuple[np.ndarray, dict]:
    """Build visible pair candidates and count their cross-view support."""
    if len(projectors) != int(config.num_views):
        raise ValueError(
            f"fusion requires exactly {config.num_views} projectors; "
            f"received {len(projectors)}"
        )
    tables: list[np.ndarray] = []
    records: list[dict] = []
    projected: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for index, projector in enumerate(projectors):
        pairs, info = visible_pixel_pairs(
            partial,
            carrier,
            projector,
            max_pixel_distance=float(config.pixel_radius),
            max_pairs=int(config.max_pairs_per_view),
            continue_with_nearest=True,
        )
        tables.append(pairs[:, :4])
        partial_uv, partial_depth = projector.project(partial)
        carrier_uv, carrier_depth = projector.project(carrier)
        projected.append((partial_uv, partial_depth, carrier_uv, carrier_depth))
        records.append({"view_index": int(index), **info})

    raw = np.concatenate(tables, axis=0)
    partial_ids = raw[:, 0].astype(np.int64)
    carrier_ids = raw[:, 1].astype(np.int64)
    # One deterministic row per physical pair, retaining its best 2-D fit.
    order = np.lexsort((raw[:, 3], carrier_ids, partial_ids))
    raw = raw[order]
    keys = raw[:, :2].astype(np.int64)
    unique = np.ones(len(raw), dtype=bool)
    unique[1:] = np.any(keys[1:] != keys[:-1], axis=1)
    candidates = raw[unique]
    partial_ids = candidates[:, 0].astype(np.int64)
    carrier_ids = candidates[:, 1].astype(np.int64)

    support = np.zeros(len(candidates), dtype=np.int64)
    depth_limit = float(config.cross_view_depth_ratio) * float(diagonal)
    for projector, values in zip(projectors, projected):
        partial_uv, partial_depth, carrier_uv, carrier_depth = values
        p_uv, q_uv = partial_uv[partial_ids], carrier_uv[carrier_ids]
        p_depth, q_depth = partial_depth[partial_ids], carrier_depth[carrier_ids]
        height, width = projector.image_shape
        valid = (
            np.isfinite(p_uv).all(axis=1)
            & np.isfinite(q_uv).all(axis=1)
            & np.isfinite(p_depth)
            & np.isfinite(q_depth)
            & (p_depth > 0.0)
            & (q_depth > 0.0)
            & (p_uv[:, 0] >= 0.0)
            & (p_uv[:, 0] < width)
            & (p_uv[:, 1] >= 0.0)
            & (p_uv[:, 1] < height)
            & (q_uv[:, 0] >= 0.0)
            & (q_uv[:, 0] < width)
            & (q_uv[:, 1] >= 0.0)
            & (q_uv[:, 1] < height)
        )
        valid &= np.linalg.norm(p_uv - q_uv, axis=1) <= float(
            config.cross_view_pixel_radius
        )
        valid &= np.abs(p_depth - q_depth) <= depth_limit
        support += valid.astype(np.int64)

    # First four columns preserve the indexed-pair contract; column five is
    # the number of agreeing cameras used by the collision-free decoder.
    result = np.column_stack((candidates[:, :4], support)).astype(np.float64)
    return result, {
        "views": records,
        "raw_visible_pairs": int(len(raw)),
        "unique_physical_pairs": int(len(result)),
        "support_histogram": {
            str(level): int(np.count_nonzero(support == level))
            for level in range(0, int(config.num_views) + 1)
        },
        "cross_view_pixel_radius": float(config.cross_view_pixel_radius),
        "cross_view_depth_limit": float(depth_limit),
    }


def collision_free_anchor_pairs(
    pixel_pairs: np.ndarray,
    partial: np.ndarray,
    carrier: np.ndarray,
    *,
    max_residual: float,
) -> tuple[np.ndarray, dict]:
    """Reduce visible correspondences to a deterministic one-to-one assignment."""
    pairs = np.asarray(pixel_pairs, dtype=np.float64)
    partial = np.asarray(partial, dtype=np.float64)
    carrier = np.asarray(carrier, dtype=np.float64)
    if pairs.ndim != 2 or pairs.shape[1] < 4:
        raise ValueError("pixel_pairs must be shaped (N, >=4)")
    if max_residual <= 0.0:
        raise ValueError("max_residual must be positive")
    if len(pairs) == 0:
        return np.empty((0, 2), dtype=np.int64), {
            "pixel_pairs": 0,
            "within_metric_limit": 0,
            "collision_free_pairs": 0,
            "max_residual": float(max_residual),
        }

    partial_ids = pairs[:, 0].astype(np.int64)
    carrier_ids = pairs[:, 1].astype(np.int64)
    valid = (
        (partial_ids >= 0)
        & (partial_ids < len(partial))
        & (carrier_ids >= 0)
        & (carrier_ids < len(carrier))
    )
    partial_ids = partial_ids[valid]
    carrier_ids = carrier_ids[valid]
    pixel_distance = pairs[valid, 3]
    support = pairs[valid, 4] if pairs.shape[1] >= 5 else np.ones(valid.sum())
    residual = np.linalg.norm(partial[partial_ids] - carrier[carrier_ids], axis=1)
    keep = np.isfinite(residual) & (residual <= float(max_residual)) & (support >= 1)
    partial_ids = partial_ids[keep]
    carrier_ids = carrier_ids[keep]
    pixel_distance = pixel_distance[keep]
    support = support[keep]
    residual = residual[keep]

    # More cross-view support wins; geometry and pixel residuals break ties.
    order = np.lexsort((carrier_ids, partial_ids, pixel_distance, residual, -support))
    used_partial: set[int] = set()
    used_carrier: set[int] = set()
    rows: list[tuple[int, int]] = []
    selected_support: list[int] = []
    for row in order:
        partial_id = int(partial_ids[row])
        carrier_id = int(carrier_ids[row])
        if partial_id in used_partial or carrier_id in used_carrier:
            continue
        used_partial.add(partial_id)
        used_carrier.add(carrier_id)
        rows.append((partial_id, carrier_id))
        selected_support.append(int(support[row]))
    selected = np.asarray(rows, dtype=np.int64).reshape(-1, 2)
    return selected, {
        "pixel_pairs": int(len(pairs)),
        "within_metric_limit": int(keep.sum()),
        "collision_free_pairs": int(len(selected)),
        "max_residual": float(max_residual),
        "residual_median": float(np.median(residual)) if len(residual) else float("inf"),
        "residual_p90": float(np.quantile(residual, 0.90)) if len(residual) else float("inf"),
        "selected_support_mean": (
            float(np.mean(selected_support)) if selected_support else 0.0
        ),
    }


def fuse_observation_anchors(
    carrier: np.ndarray,
    partial: np.ndarray,
    view_projectors: list,
    *,
    config: ObservationAnchoredFusionConfig | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Write reliable four-view observations into complete-carrier slots."""
    config = config or ObservationAnchoredFusionConfig()
    carrier = np.asarray(carrier, dtype=np.float64)
    partial = np.asarray(partial, dtype=np.float64)
    if carrier.ndim != 2 or partial.ndim != 2 or carrier.shape[1] != 3 or partial.shape[1] != 3:
        raise ValueError("carrier and partial must be shaped (N, 3)")
    if len(carrier) < 3 or len(partial) < 3:
        raise ValueError("carrier and partial must contain at least three points")

    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-8)
    pairs, multiview_info = positive_multiview_pairs(
        partial,
        carrier,
        list(view_projectors),
        config=config,
        diagonal=diagonal,
    )
    selected, assignment = collision_free_anchor_pairs(
        pairs,
        partial,
        carrier,
        max_residual=float(config.anchor_residual_ratio) * diagonal,
    )
    fused = carrier.copy()
    if len(selected):
        fused[selected[:, 1]] = partial[selected[:, 0]]
    changed = np.zeros(len(carrier), dtype=bool)
    if len(selected):
        changed[selected[:, 1]] = True
    info = {
        "method": "four_view_observation_anchored_carrier_fusion",
        "ground_truth_used": False,
        "point_concatenation_used": False,
        "second_deformation_used": False,
        "carrier_slots_before": int(len(carrier)),
        "carrier_slots_after": int(len(fused)),
        "all_carrier_slots_preserved": bool(len(fused) == len(carrier)),
        "fused_anchor_fraction": float(changed.mean()),
        "multiview_positive_evidence": multiview_info,
        "assignment": assignment,
        "parameters": {
            "num_views": int(config.num_views),
            "pixel_radius": float(config.pixel_radius),
            "cross_view_pixel_radius": float(config.cross_view_pixel_radius),
            "cross_view_depth_ratio": float(config.cross_view_depth_ratio),
            "anchor_residual_ratio": float(config.anchor_residual_ratio),
        },
    }
    return fused, selected, pairs, info


def fuse_continuous_observation_field(
    carrier: np.ndarray,
    partial: np.ndarray,
    view_projectors: list,
    *,
    config: ContinuousObservationFusionConfig | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Assimilate reliable measurements through a finite continuous field.

    Cross-view agreement first removes ambiguous image correspondences.  The
    surviving residual vectors drive the existing embedded-ARAP carrier, while
    samples outside a density-normalized observation band are fixed boundary
    conditions.  The solver's line search protects coverage, connectivity and
    local edge strain, so fusion cannot erase unsupported complete geometry.
    """
    config = config or ContinuousObservationFusionConfig()
    carrier = np.asarray(carrier, dtype=np.float64)
    partial = np.asarray(partial, dtype=np.float64)
    if carrier.ndim != 2 or partial.ndim != 2 or carrier.shape[1] != 3 or partial.shape[1] != 3:
        raise ValueError("carrier and partial must be shaped (N, 3)")
    if len(carrier) < 32 or len(partial) < 32:
        raise ValueError("continuous fusion requires at least 32 points per cloud")
    if len(view_projectors) != int(config.num_views):
        raise ValueError(
            f"fusion requires exactly {config.num_views} projectors; "
            f"received {len(view_projectors)}"
        )
    if config.minimum_view_support < 1 or config.minimum_view_support > config.num_views:
        raise ValueError("minimum_view_support must lie in [1, num_views]")

    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-8)
    partial_spacing = _median_spacing(partial)
    carrier_spacing = _median_spacing(carrier)
    pair_config = ObservationAnchoredFusionConfig(
        num_views=int(config.num_views),
        pixel_radius=float(config.pixel_radius),
        cross_view_pixel_radius=float(config.cross_view_pixel_radius),
        cross_view_depth_ratio=float(config.cross_view_depth_ratio),
        anchor_residual_ratio=float(config.maximum_residual_ratio),
        max_pairs_per_view=int(config.max_pairs_per_view),
    )
    pairs, multiview_info = positive_multiview_pairs(
        partial, carrier, list(view_projectors),
        config=pair_config, diagonal=diagonal,
    )
    supported = pairs[pairs[:, 4] >= int(config.minimum_view_support)]
    if len(supported):
        partial_ids = supported[:, 0].astype(np.int64)
        carrier_ids = supported[:, 1].astype(np.int64)
        residual = np.linalg.norm(partial[partial_ids] - carrier[carrier_ids], axis=1)
    else:
        residual = np.empty(0, dtype=np.float64)
    residual_limit = _adaptive_residual_limit(
        residual,
        diagonal=diagonal,
        partial_spacing=partial_spacing,
        config=config,
    )
    anchors, assignment = collision_free_anchor_pairs(
        supported, partial, carrier, max_residual=residual_limit,
    )
    minimum_anchors = max(32, int(config.minimum_nodes) // 2)
    if len(anchors) < minimum_anchors:
        info = {
            "method": "continuous_multiview_observation_fusion",
            "active": False,
            "reason": "insufficient_cross_view_observation_anchors",
            "ground_truth_used": False,
            "point_concatenation_used": False,
            "carrier_slots_before": int(len(carrier)),
            "carrier_slots_after": int(len(carrier)),
            "all_carrier_slots_preserved": True,
            "multiview_positive_evidence": multiview_info,
            "assignment": assignment,
            "supported_pairs": int(len(supported)),
            "residual_limit": float(residual_limit),
        }
        return carrier.copy(), anchors, pairs, info

    partial_ids = anchors[:, 0]
    carrier_ids = anchors[:, 1]
    influence_radius = max(
        float(config.carrier_influence_multiplier) * carrier_spacing,
        float(config.partial_influence_multiplier) * partial_spacing,
    )
    anchor_distance = cKDTree(carrier[carrier_ids]).query(
        carrier, k=1, workers=-1,
    )[0]
    stable_mask = anchor_distance > influence_radius
    stable_mask[carrier_ids] = False

    support_lookup = {
        (int(row[0]), int(row[1])): float(row[4])
        for row in supported
    }
    target_weights = np.asarray([
        support_lookup[(int(partial_id), int(carrier_id))] / float(config.num_views)
        for partial_id, carrier_id in anchors
    ], dtype=np.float64)
    fused, solve, moved = _embedded_arap_posterior(
        carrier,
        carrier_ids,
        partial[partial_ids],
        target_weights,
        stable_mask,
        node_fraction=float(config.node_fraction),
        minimum_nodes=int(config.minimum_nodes),
        maximum_nodes=int(config.maximum_nodes),
        skinning_neighbours=4,
        neighbours=int(config.neighbours),
        edge_ratio=float(config.edge_ratio),
        attachment_edge_ratio=float(config.attachment_edge_ratio),
        data_weight=float(config.data_weight),
        screening=float(config.screening),
        iterations=int(config.iterations),
        maximum_displacement=float(residual_limit),
        minimum_improvement=float(config.minimum_improvement),
        minimum_edge_compression=float(config.minimum_edge_compression),
        maximum_edge_stretch=float(config.maximum_edge_stretch),
        minimum_hidden_coverage=float(config.minimum_hidden_coverage),
        coverage_resolution=int(config.coverage_resolution),
        coherent_component_targets=False,
        preserve_target_amplitude=True,
        hard_target_constraints=False,
    )
    if not solve.get("active"):
        fused = carrier.copy()
        moved = np.zeros(len(carrier), dtype=bool)
    info = {
        "method": "continuous_multiview_observation_fusion",
        "active": bool(solve.get("active")),
        "reason": solve.get("reason", "accepted"),
        "ground_truth_used": False,
        "point_concatenation_used": False,
        "carrier_slots_before": int(len(carrier)),
        "carrier_slots_after": int(len(fused)),
        "all_carrier_slots_preserved": bool(len(fused) == len(carrier)),
        "multiview_positive_evidence": multiview_info,
        "assignment": assignment,
        "supported_pairs": int(len(supported)),
        "observation_anchors": int(len(anchors)),
        "stable_carrier_slots": int(stable_mask.sum()),
        "moved_carrier_slots": int(moved.sum()),
        "partial_spacing": float(partial_spacing),
        "carrier_spacing": float(carrier_spacing),
        "residual_limit": float(residual_limit),
        "influence_radius": float(influence_radius),
        "solver": solve,
        "parameters": {
            key: value for key, value in vars(config).items()
        },
    }
    return fused, anchors, pairs, info
