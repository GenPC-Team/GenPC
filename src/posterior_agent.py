"""No-GT observe/decide/verify controller for the frozen posterior solver.

The controller selects views, bounded update profiles and a refinement route.
Partial OT and continuous geometry are solved by existing deterministic modules.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from src.bidirectional_cycle_registration import prepare_visible_target, projection_metrics
from src.multiview_diagnostics import (
    _visible_point_ids, look_at_pose, rotate_about_axis,
)
from src.multiview_partial_evidence import PoseProjector


@dataclass(frozen=True)
class Observation:
    coverage: tuple[float, ...]
    depth: tuple[float, ...]
    partial_to_carrier_p90: float
    partial_to_carrier_p99: float
    partial_to_carrier_median: float

    @property
    def mean_coverage(self) -> float:
        return float(np.mean(self.coverage))


@dataclass(frozen=True)
class Decision:
    action: str
    profile: str
    reason: str
    transport: str = "CAMERA1"


def observe(partial: np.ndarray, carrier: np.ndarray, projectors, caches=None):
    """Score physical partial evidence in the four saved cameras and in 3-D."""
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    if caches is None:
        caches = tuple(prepare_visible_target(partial, camera) for camera in projectors)
    view_scores = [
        projection_metrics(partial, carrier, camera, diagonal, target_cache=cache)
        for camera, cache in zip(projectors, caches, strict=True)
    ]
    distance = cKDTree(carrier).query(partial, k=1, workers=-1)[0] / diagonal
    return Observation(
        coverage=tuple(float(score["coverage"]) for score in view_scores),
        depth=tuple(float(score["visible_depth_normalized"]) for score in view_scores),
        partial_to_carrier_p90=float(np.quantile(distance, .90)),
        partial_to_carrier_p99=float(np.quantile(distance, .99)),
        partial_to_carrier_median=float(np.median(distance)),
    ), caches


def decide_next(current: Observation, previous: Observation | None, *,
                round_index: int, maximum_rounds: int) -> Decision:
    """Choose one bounded action from current evidence, without GT or labels."""
    if round_index >= maximum_rounds:
        return Decision("ACCEPT", "NONE", "round_budget_reached")
    if previous is not None:
        # A large p99/p90 gap indicates a genuinely *localized* residual tail.
        # Otherwise the mismatch is still broad and needs the full transport.
        if (round_index >= 2 and current.partial_to_carrier_p90 < .01
                and current.partial_to_carrier_p99 > .012
                and current.partial_to_carrier_p99 / max(current.partial_to_carrier_p90, 1e-9) > 5.0):
            return Decision("REFINE_OBSERVED", "OBSERVATION_FIELD", "unexplained_residual_tail", "ALL_ACTIVE_VIEWS")
        gain = current.mean_coverage - previous.mean_coverage
        residual_gain = (previous.partial_to_carrier_p90 - current.partial_to_carrier_p90) / max(
            previous.partial_to_carrier_p90, 1e-9,
        )
        if gain < .002 and residual_gain < .01:
            return Decision("ACCEPT", "NONE", "positive_evidence_plateau")
        if current.partial_to_carrier_p90 > .035 and gain > .002:
            return Decision("UPDATE_POSTERIOR", "EXPANSIVE", "coherent_unexplained_observation")
    if (current.partial_to_carrier_p90 > .025
            and max(current.coverage) - min(current.coverage) > .12):
        return Decision(
            "UPDATE_POSTERIOR", "BALANCED", "camera_evidence_ambiguous",
            "ALL_ACTIVE_VIEWS",
        )
    return Decision("UPDATE_POSTERIOR", "BALANCED", "residual_observation_remains")


def verify_update(before: Observation, after: Observation, estimate: dict, *,
                  reference_coverage: float = 1.0,
                  minimum_reference_coverage: float = .95) -> Decision:
    """Reject any step that damages a view or the 100k carrier's integrity."""
    integrity = estimate.get("integrity", {})
    if not bool(integrity.get("passed", False)):
        return Decision("ROLLBACK", "CONSERVATIVE", "carrier_integrity_failed")
    if reference_coverage < minimum_reference_coverage:
        return Decision("ROLLBACK", "CONSERVATIVE", "reference_prior_coverage_regressed")
    if any(new < old - .02 for old, new in zip(before.coverage, after.coverage, strict=True)):
        return Decision("ROLLBACK", "CONSERVATIVE", "view_coverage_regressed")
    if after.mean_coverage < before.mean_coverage - .005:
        return Decision("ROLLBACK", "CONSERVATIVE", "aggregate_coverage_regressed")
    coverage_gain = after.mean_coverage - before.mean_coverage
    distance_gain = before.partial_to_carrier_p90 - after.partial_to_carrier_p90
    if coverage_gain < .002 and distance_gain < .005 * before.partial_to_carrier_p90:
        return Decision("ROLLBACK", "CONSERVATIVE", "no_observed_improvement")
    return Decision("ACCEPT_UPDATE", "NONE", "positive_evidence_improved")


def select_active_views(partial: np.ndarray, carrier: np.ndarray, manifest: dict, *,
                        maximum_views: int = 6, resolution: int = 512,
                        minimum_new_evidence_fraction: float = .02):
    """Greedily cover observed partial residuals with two to six orbit views.

    The saved yaw-zero observation is retained. Additional candidates come
    from the same camera orbit and are chosen using only newly visible
    physical partial samples, weighted by unexplained 3-D residual.
    """
    if not 2 <= maximum_views <= 6:
        raise ValueError("maximum_views must be between two and six")
    centre = np.asarray(manifest["centre"], dtype=np.float64)
    front = np.asarray(manifest["front_direction"], dtype=np.float64)
    up = np.asarray(manifest["up_direction"], dtype=np.float64)
    fov = float(manifest["field_of_view_degrees"])
    radius = float(manifest["radius"])
    distance = radius / max(np.sin(np.deg2rad(fov) * .5), 1e-3) * 1.12
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    nearest = cKDTree(carrier).query(partial, k=1, workers=-1)[0]
    weight = 1.0 + np.clip(nearest / (.03 * diagonal), 0.0, 2.0)
    total_weight = float(weight.sum())
    candidate_ids = {}
    candidate_views = {}
    for yaw in range(0, 360, 15):
        direction = rotate_about_axis(front, up, float(yaw))
        pose = look_at_pose(centre + direction * distance, centre, up)
        ids = _visible_point_ids(partial, pose, fov, 256)
        candidate_ids[yaw] = ids
        candidate_views[yaw] = PoseProjector(pose, fov, resolution)

    selected = [0]
    covered = np.zeros(len(partial), dtype=bool)
    covered[candidate_ids[0]] = True
    audit = [{"yaw_degrees": 0, "new_visible_points": int(len(candidate_ids[0])),
              "new_weighted_evidence_fraction": float(weight[candidate_ids[0]].sum() / total_weight)}]
    while len(selected) < maximum_views:
        eligible = [yaw for yaw in candidate_ids if yaw not in selected
                    and all(min(abs(yaw - past), 360 - abs(yaw - past)) >= 45
                            for past in selected)]
        if not eligible:
            break
        chosen = max(eligible, key=lambda yaw: (
            float(weight[candidate_ids[yaw][~covered[candidate_ids[yaw]]]].sum()),
            -yaw,
        ))
        new_ids = candidate_ids[chosen][~covered[candidate_ids[chosen]]]
        gain = float(weight[new_ids].sum() / total_weight)
        if len(selected) >= 2 and gain < minimum_new_evidence_fraction:
            break
        selected.append(chosen)
        covered[new_ids] = True
        audit.append({"yaw_degrees": chosen, "new_visible_points": int(len(new_ids)),
                      "new_weighted_evidence_fraction": gain})
    return [candidate_views[yaw] for yaw in selected], {
        "method": "incremental_visible_residual_coverage",
        "selected": audit,
        "covered_partial_fraction": float(covered.mean()),
        "view_count": len(selected),
    }
