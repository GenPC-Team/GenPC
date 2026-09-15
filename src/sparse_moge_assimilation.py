"""Dense visible-surface assimilation for sparse-LiDAR completion.

Sparse LiDAR determines the metric object frame but is too incomplete to be a
stable local surface target.  Native MoGe, inferred from the accepted semantic
image in Pixal's own camera, supplies that dense visible target.  This module
writes only reliable native-MoGe observations into visible Pixal carrier slots;
all unmatched and hidden Pixal slots remain untouched.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from src.pixal_moge_analytic_registration import (
    pixal_moge_render_score,
    visible_ray_depth_scale_step,
)
from src.ray_consistent_registration import apply_transform
from src.visible_pixel_sim3_refinement import visible_pixel_pairs


@dataclass(frozen=True)
class CameraRayGaugeConfig:
    """Camera-origin scale calibration for monocular metric-depth ambiguity.

    Scaling all camera-frame coordinates about the optical centre leaves the
    perspective projection unchanged.  It is therefore the one global degree
    of freedom that dense monocular geometry can estimate robustly before an
    extremely sparse LiDAR scan supplies the final world-frame placement.
    """

    scale_bounds: tuple[float, float] = (.25, 4.0)
    line_search_fractions: tuple[float, ...] = (1.0, .75, .50, .25, 0.0)
    maximum_projection_drop: float = .002
    maximum_trimmed_ratio_spread: float = 1.25
    minimum_relative_depth_improvement: float = .05

    def validate(self) -> None:
        if not 0. < self.scale_bounds[0] <= 1. <= self.scale_bounds[1]:
            raise ValueError("scale_bounds must contain one and remain positive")
        if not self.line_search_fractions or any(
            not 0. <= value <= 1. for value in self.line_search_fractions
        ):
            raise ValueError("line_search_fractions must lie in [0, 1]")
        if not 0. <= self.maximum_projection_drop < .1:
            raise ValueError("maximum_projection_drop is invalid")
        if not 1. < self.maximum_trimmed_ratio_spread <= 2.:
            raise ValueError("maximum_trimmed_ratio_spread is invalid")
        if not 0. <= self.minimum_relative_depth_improvement < 1.:
            raise ValueError("minimum_relative_depth_improvement is invalid")


def calibrate_camera_ray_depth_gauge(
    prior_native_moge: np.ndarray,
    native_moge: np.ndarray,
    projector,
    *,
    config: CameraRayGaugeConfig | None = None,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Resolve the prior/MoGe depth gauge without changing image alignment.

    The input must already be in the native MoGe camera frame.  Candidate
    scales are estimated from same-pixel visible depths and evaluated using
    silhouette, depth, and boundary evidence only; no sparse scan or GT is
    involved.  The returned transform acts on native-camera coordinates.
    """
    config = config or CameraRayGaugeConfig()
    config.validate()
    carrier = np.asarray(prior_native_moge, dtype=np.float64)
    observation = np.asarray(native_moge, dtype=np.float64)
    identity = np.eye(4, dtype=np.float64)
    before = pixal_moge_render_score(observation, carrier, projector)
    raw_step, estimate = visible_ray_depth_scale_step(
        observation,
        carrier,
        projector,
        max_depth_ratio=max(
            1.0 - float(config.scale_bounds[0]),
            float(config.scale_bounds[1]) - 1.0,
        ),
    )
    if not bool(estimate.get("accepted", False)):
        return carrier.copy(), identity, {
            "active": False,
            "reason": estimate.get("reason", "depth_scale_estimation_failed"),
            "config": asdict(config),
            "estimate": estimate,
            "before": before,
        }
    ratio_low, ratio_high = map(float, estimate["trimmed_ratio_range"])
    ratio_spread = ratio_high / max(ratio_low, 1e-8)
    if ratio_spread > float(config.maximum_trimmed_ratio_spread):
        return carrier.copy(), identity, {
            "active": False,
            "reason": "inconsistent_same_pixel_depth_ratio",
            "config": asdict(config),
            "estimate": estimate,
            "trimmed_ratio_spread": float(ratio_spread),
            "before": before,
        }

    raw_scale = float(np.clip(
        estimate["raw_median_target_over_prior_z"],
        float(config.scale_bounds[0]),
        float(config.scale_bounds[1]),
    ))
    candidates: list[tuple[dict, float, np.ndarray, np.ndarray]] = []
    for fraction in config.line_search_fractions:
        scale = 1.0 + float(fraction) * (raw_scale - 1.0)
        step = np.eye(4, dtype=np.float64)
        step[:3, :3] *= scale
        moved = apply_transform(carrier, step)
        score = pixal_moge_render_score(observation, moved, projector)
        projection_preserved = (
            score["iou"] >= before["iou"] - float(config.maximum_projection_drop)
            and score["coverage"] >= before["coverage"] - float(config.maximum_projection_drop)
        )
        if projection_preserved:
            candidates.append((score, float(fraction), step, moved))
    if not candidates:
        return carrier.copy(), identity, {
            "active": False,
            "reason": "no_projection_preserving_scale_candidate",
            "config": asdict(config),
            "estimate": estimate,
            "before": before,
        }
    score, fraction, step, moved = min(
        candidates,
        key=lambda item: (float(item[0]["objective"]), float(item[0]["log_depth_median"])),
    )
    before_depth = float(before["log_depth_median"])
    after_depth = float(score["log_depth_median"])
    relative_improvement = (before_depth - after_depth) / max(before_depth, 1e-8)
    accepted = bool(
        after_depth < before_depth
        and relative_improvement >= float(config.minimum_relative_depth_improvement)
        and float(score["objective"]) <= float(before["objective"]) + 1e-8
    )
    if not accepted:
        moved, step, score, fraction = carrier.copy(), identity, before, 0.0
    return moved, step, {
        "active": accepted,
        "method": "camera_origin_native_moge_depth_gauge_calibration",
        "config": asdict(config),
        "estimate": estimate,
        "trimmed_ratio_spread": float(ratio_spread),
        "selected_fraction": float(fraction),
        "selected_scale": float(step[0, 0]),
        "relative_depth_improvement": float(relative_improvement),
        "before": before,
        "after": score,
        "candidates": [
            {
                "fraction": candidate_fraction,
                "scale": float(candidate_step[0, 0]),
                "score": candidate_score,
            }
            for candidate_score, candidate_fraction, candidate_step, _ in candidates
        ],
    }


@dataclass(frozen=True)
class SparseMoGeAssimilationConfig:
    pixel_radius: float = 1.5
    residual_quantile: float = .85
    maximum_residual_ratio: float = .05
    blend: float = 1.0
    maximum_pairs: int = 100_000
    minimum_pairs: int = 96

    def validate(self) -> None:
        if self.pixel_radius < 0. or not .5 < self.residual_quantile < 1.:
            raise ValueError("invalid pixel radius or residual quantile")
        if not 0. < self.maximum_residual_ratio < .5 or not 0. < self.blend <= 1.:
            raise ValueError("invalid residual ratio or blend")
        if self.maximum_pairs < self.minimum_pairs or self.minimum_pairs < 6:
            raise ValueError("invalid pair budget")


def assimilate_native_moge_surface(
    prior_native_moge: np.ndarray,
    native_moge: np.ndarray,
    projector,
    *,
    config: SparseMoGeAssimilationConfig | None = None,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Replace reliable visible carrier slots while preserving complete support."""
    config = config or SparseMoGeAssimilationConfig()
    config.validate()
    carrier = np.asarray(prior_native_moge, dtype=np.float64)
    observation = np.asarray(native_moge, dtype=np.float64)
    pairs, pair_info = visible_pixel_pairs(
        observation,
        carrier,
        projector,
        max_pixel_distance=float(config.pixel_radius),
        max_pairs=int(config.maximum_pairs),
        continue_with_nearest=False,
    )
    observation_ids = pairs[:, 0].astype(np.int64)
    carrier_ids = pairs[:, 1].astype(np.int64)
    residual = np.linalg.norm(observation[observation_ids] - carrier[carrier_ids], axis=1)
    diagonal = max(float(np.linalg.norm(np.ptp(observation, axis=0))), 1e-8)
    threshold = min(
        float(np.quantile(residual, float(config.residual_quantile))),
        float(config.maximum_residual_ratio) * diagonal,
    )
    keep = residual <= max(threshold, .0025 * diagonal)
    observation_ids, carrier_ids, residual = (
        observation_ids[keep], carrier_ids[keep], residual[keep]
    )
    if len(carrier_ids) < int(config.minimum_pairs):
        return carrier.copy(), np.empty((0, 2), dtype=np.int64), {
            "active": False,
            "reason": "insufficient_reliable_native_moge_pairs",
            "config": asdict(config),
            "pairing": pair_info,
            "candidate_pairs": int(len(pairs)),
            "retained_pairs": int(len(carrier_ids)),
            "residual_threshold": float(threshold),
        }
    # ``visible_pixel_pairs`` already gives one claimant per carrier slot.
    result = carrier.copy()
    alpha = float(config.blend)
    result[carrier_ids] = (
        (1. - alpha) * carrier[carrier_ids] + alpha * observation[observation_ids]
    )
    changed = np.zeros(len(carrier), dtype=bool)
    changed[carrier_ids] = True
    return result, np.c_[observation_ids, carrier_ids], {
        "active": True,
        "method": "native_moge_visible_surface_carrier_assimilation",
        "config": asdict(config),
        "pairing": pair_info,
        "candidate_pairs": int(len(pairs)),
        "retained_pairs": int(len(carrier_ids)),
        "retained_fraction": float(len(carrier_ids) / max(len(carrier), 1)),
        "residual_threshold": float(threshold),
        "residual_median": float(np.median(residual)),
        "residual_p90": float(np.quantile(residual, .90)),
        "carrier_slots_before": int(len(carrier)),
        "carrier_slots_after": int(len(result)),
        "all_carrier_slots_preserved": bool(len(result) == len(carrier)),
        "hidden_and_unmatched_slots_preserved": int((~changed).sum()),
    }
