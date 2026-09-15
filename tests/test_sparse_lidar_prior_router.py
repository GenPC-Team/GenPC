import numpy as np

from src.sparse_lidar_prior_router import select_sparse_prior_candidate


class _Projector:
    image_shape = (128, 128)
    center_xy = np.array((64., 64.))
    scale_xy = 128.

    def project(self, points):
        points = np.asarray(points)
        depth = points[:, 2]
        return np.c_[64. + 32. * points[:, 0] / depth, 64. + 32. * points[:, 1] / depth], depth


def test_sparse_router_prefers_observation_fit_without_destroying_ordered_prior():
    y, x = np.mgrid[-8:9, -8:9]
    raw = np.c_[x.ravel() / 20., y.ravel() / 20., np.ones(x.size)]
    partial = raw[::2].copy()
    good = 1.3 * raw + np.array([.05, 0., .2])
    partial = good[::2]
    damaged = good.copy()
    damaged[::3, 0] += .25
    name, selected, info = select_sparse_prior_candidate(
        partial,
        raw,
        {"good": good, "damaged": damaged},
        _Projector(),
    )
    assert name == "good"
    assert np.array_equal(selected, good)
    assert info["ground_truth_used"] is False
