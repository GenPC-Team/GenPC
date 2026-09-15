"""No-GT routing between dense-prior and sparse-observation registration.

Extremely sparse LiDAR provides reliable occupied samples but does not define
free space.  This scorer therefore uses one-sided visible evidence and adds an
ordered-carrier distortion term so that fitting the observations cannot win by
damaging the complete generative prior.  It contains no category or sample
rules and is used only by the opt-in sparse-LiDAR pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.spatial import cKDTree

from src.bidirectional_cycle_registration import visible_score
from src.ray_consistent_registration import apply_transform
from src.robust_similarity import weighted_umeyama


@dataclass(frozen=True)
class SparsePriorRouterConfig:
    surface_mean_weight: float = .65
    surface_tail_weight: float = .35
    surface_tail_quantile: float = .90
    prior_distortion_weight: float = 1.0
    distortion_quantile: float = .90
    pixel_radius: float = 5.0

    def validate(self) -> None:
        weights = (
            self.surface_mean_weight,
            self.surface_tail_weight,
            self.prior_distortion_weight,
        )
        if any(value < 0. for value in weights) or sum(weights[:2]) <= 0.:
            raise ValueError("router weights are invalid")
        if not .5 <= self.surface_tail_quantile < 1.:
            raise ValueError("surface_tail_quantile is invalid")
        if not .5 <= self.distortion_quantile < 1. or self.pixel_radius <= 0.:
            raise ValueError("router quantile or pixel radius is invalid")


def _ordered_prior_distortion(raw_prior: np.ndarray, candidate: np.ndarray, quantile: float) -> dict:
    raw_prior = np.asarray(raw_prior, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if raw_prior.shape != candidate.shape:
        raise ValueError("candidate must preserve the ordered prior carrier")
    transform = weighted_umeyama(raw_prior, candidate, np.ones(len(raw_prior)))
    residual = np.linalg.norm(apply_transform(raw_prior, transform) - candidate, axis=1)
    diagonal = max(float(np.linalg.norm(np.ptp(candidate, axis=0))), 1e-8)
    return {
        "median": float(np.median(residual) / diagonal),
        "quantile": float(np.quantile(residual, float(quantile)) / diagonal),
        "normalization_diagonal": diagonal,
        "best_ordered_sim3": transform,
    }


def score_sparse_prior_candidate(
    partial: np.ndarray,
    raw_prior: np.ndarray,
    candidate: np.ndarray,
    projector,
    *,
    config: SparsePriorRouterConfig | None = None,
) -> dict:
    """Score a complete candidate using positive observations and prior shape."""
    config = config or SparsePriorRouterConfig()
    config.validate()
    partial = np.asarray(partial, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-8)
    visible = visible_score(
        partial,
        candidate,
        projector,
        diagonal,
        pixel_radius=float(config.pixel_radius),
    )
    visible_3d = float(visible["geometric"]["objective"])
    projection = visible["projection"]
    # Every LiDAR return is positive occupied-surface evidence, including
    # samples that are sparse or unstable under a raster z-buffer.  Evaluate
    # all observations one-sidedly; do not penalise prior regions without a
    # return, since those pixels are unknown rather than empty.
    surface_distance = cKDTree(candidate).query(partial, k=1, workers=-1)[0] / diagonal
    surface_mean = float(np.mean(surface_distance))
    surface_tail = float(np.quantile(surface_distance, float(config.surface_tail_quantile)))
    observation = float(
        float(config.surface_mean_weight) * surface_mean
        + float(config.surface_tail_weight) * surface_tail
    )
    distortion = _ordered_prior_distortion(
        raw_prior,
        candidate,
        float(config.distortion_quantile),
    )
    objective = observation + float(config.prior_distortion_weight) * distortion["quantile"]
    return {
        "objective": float(objective),
        "observation_objective": observation,
        "one_sided_surface_mean": surface_mean,
        "one_sided_surface_tail": surface_tail,
        "visible_3d": visible_3d,
        "visible_pair_count": int(len(visible["geometric"]["partial_ids"])),
        "coverage": float(projection["coverage"]),
        "visible_depth_normalized": float(projection["visible_depth_normalized"]),
        "prior_distortion": distortion,
        "config": asdict(config),
    }


def select_sparse_prior_candidate(
    partial: np.ndarray,
    raw_prior: np.ndarray,
    candidates: dict[str, np.ndarray],
    projector,
    *,
    config: SparsePriorRouterConfig | None = None,
) -> tuple[str, np.ndarray, dict]:
    """Return the lowest no-GT posterior candidate and full audit record."""
    if not candidates:
        raise ValueError("at least one candidate is required")
    scores = {
        name: score_sparse_prior_candidate(
            partial, raw_prior, candidate, projector, config=config,
        )
        for name, candidate in candidates.items()
    }
    selected = min(scores, key=lambda name: float(scores[name]["objective"]))
    return selected, np.asarray(candidates[selected], dtype=np.float64).copy(), {
        "method": "one_sided_sparse_observation_prior_protection_router",
        "ground_truth_used": False,
        "category_rules_used": False,
        "selected": selected,
        "scores": scores,
    }
