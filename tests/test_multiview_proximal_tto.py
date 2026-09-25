from __future__ import annotations

import numpy as np

from src.multiview_proximal_tto import (
    MultiViewProximalTTOConfig,
    multiview_ordered_proposal_evidence,
)


class _IdentityProjector:
    image_shape = (64, 64)

    def project(self, points):
        points = np.asarray(points, dtype=np.float64)
        return points[:, :2], points[:, 2] + 1.0


def test_auxiliary_evidence_cannot_target_acquisition_hidden_carrier():
    partial = np.array([[10.0, 10.0, 0.0], [30.0, 30.0, 0.0]])
    current = np.array([[10.0, 10.0, 0.4], [26.0, 30.0, 0.4]])
    proposal = np.array([[10.0, 10.0, 0.0], [30.0, 30.0, 0.0]])
    eligible = np.array([True, False])
    config = MultiViewProximalTTOConfig(
        minimum_view_votes=1,
        proposal_pixel_radius=8.0,
        proposal_depth_ratio=1.0,
        stable_pixel_radius=0.0,
        stable_depth_ratio=0.0,
        minimum_normalized_improvement=0.01,
    )

    support, _, _, report = multiview_ordered_proposal_evidence(
        partial,
        current,
        proposal,
        [_IdentityProjector()],
        config=config,
        support_eligibility=eligible,
    )

    assert support.tolist() == [True, False]
    assert report["acquisition_visible_eligible_points"] == 1
