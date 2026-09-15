import numpy as np

from src.moge_camera import MoGeProjector
from src.sparse_moge_assimilation import (
    assimilate_native_moge_surface,
    calibrate_camera_ray_depth_gauge,
)


class _Projector:
    image_shape = (128, 128)

    def project(self, points):
        points = np.asarray(points)
        return np.c_[64. + 24. * points[:, 0], 64. + 24. * points[:, 1]], points[:, 2]


def test_native_moge_assimilation_preserves_slots_and_updates_visible_surface():
    y, x = np.mgrid[-6:7, -6:7]
    observation = np.c_[x.ravel() / 10., y.ravel() / 10., 1. + .02 * x.ravel()]
    carrier_visible = observation + np.array([0., 0., .02])
    hidden = observation.copy()
    hidden[:, 2] = 2.0
    carrier = np.concatenate((carrier_visible, hidden), axis=0)
    result, pairs, info = assimilate_native_moge_surface(
        carrier, observation, _Projector(),
    )
    assert info["active"] is True
    assert len(result) == len(carrier)
    assert len(pairs) >= 96
    assert np.linalg.norm(result[pairs[:, 1]] - observation[pairs[:, 0]], axis=1).max() < 1e-10
    assert np.array_equal(result[len(carrier_visible):], hidden)


def test_camera_ray_gauge_recovers_depth_scale_and_preserves_projection():
    y, x = np.mgrid[-8:9, -8:9]
    prior = np.c_[x.ravel() / 20., y.ravel() / 20., np.ones(x.size)]
    target = 1.55 * prior
    projector = MoGeProjector(
        np.array([[1., 0., .5], [0., 1., .5], [0., 0., 1.]]), (128, 128),
    )
    before_uv, _ = projector.project(prior)
    result, step, info = calibrate_camera_ray_depth_gauge(prior, target, projector)
    after_uv, _ = projector.project(result)
    assert info["active"] is True
    assert np.isclose(step[0, 0], 1.55, atol=.03)
    assert np.allclose(before_uv, after_uv)
    assert info["after"]["log_depth_median"] < .02
