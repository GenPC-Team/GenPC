import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from src.sparse_observation_registration import fit_sparse_bridge, camera_bridge_rotation
from src.ray_consistent_registration import apply_transform


def fixture(seed=7):
    rng = np.random.default_rng(seed)
    x = rng.uniform(-1, 1, (256, 3))
    uv = (x[:, :2] + 1) / 2
    matches = np.column_stack((np.arange(len(x)), np.arange(len(x)), np.arange(len(x)), np.zeros(len(x))))
    return x, uv, matches


def test_camera_retained_without_evidence_for_rotation():
    x, uv, matches = fixture()
    y = x * 2.3 + [4, -2, 7]
    transform, report = fit_sparse_bridge(x, y, matches, uv, np.eye(3))
    np.testing.assert_allclose(apply_transform(x, transform), y, atol=1e-6)
    assert report['rotation_fraction'] == 0
    assert not report['empty_space_penalty']


def test_real_rotation_is_released_with_spatial_evidence():
    x, uv, matches = fixture()
    r = Rotation.from_euler('xyz', [12, -22, 8], degrees=True).as_matrix()
    y = 1.8 * x @ r.T + [4, 2, -1]
    transform, report = fit_sparse_bridge(x, y, matches, uv, np.eye(3))
    np.testing.assert_allclose(apply_transform(x, transform), y, atol=1e-6)
    assert report['rotation_fraction'] == 1
    assert np.linalg.det(transform[:3, :3]) > 0


def test_robust_to_isolated_false_correspondences():
    x, uv, matches = fixture()
    y = x * 3 + [2, -3, 7]
    noisy = y.copy()
    noisy[::13] += [4, -7, 2]
    transform, _ = fit_sparse_bridge(x, noisy, matches, uv, np.eye(3))
    assert np.median(np.linalg.norm(apply_transform(x, transform) - y, axis=1)) < .01


def test_collinear_support_cannot_invent_rotation():
    t = np.linspace(-1, 1, 30)
    x = np.column_stack((t, t * 0, t * 0))
    uv = np.column_stack(((t + 1) / 2, t * 0 + .5))
    m = np.column_stack((np.arange(30), np.arange(30), np.arange(30), t * 0))
    transform, report = fit_sparse_bridge(x, 2 * x + [1, 2, 3], m, uv, np.eye(3))
    assert report['rotation_fraction'] == 0
    assert report['selection'].startswith('insufficient')
    np.testing.assert_allclose(apply_transform(x, transform), 2 * x + [1, 2, 3], atol=1e-6)


def test_scale_translation_equivariance():
    x, uv, matches = fixture()
    y = 1.2 * x + [2, -1, 0]
    a, _ = fit_sparse_bridge(x, y, matches, uv, np.eye(3))
    b, _ = fit_sparse_bridge(x, 100 * y + [50, 10, -7], matches, uv, np.eye(3))
    np.testing.assert_allclose(apply_transform(x, b), 100 * apply_transform(x, a) + [50, 10, -7], atol=1e-5)


def test_insufficient_points_fail_explicitly():
    x, uv, matches = fixture()
    with pytest.raises(ValueError, match='six'):
        fit_sparse_bridge(x, x, matches[:3], uv, np.eye(3))


def test_camera_coordinate_conventions():
    from types import SimpleNamespace
    r = Rotation.from_euler('xyz', [20, 30, 40], degrees=True).as_matrix()
    p = SimpleNamespace(pinhole_world_to_camera=None, camera=SimpleNamespace(R=r))
    np.testing.assert_allclose(camera_bridge_rotation(p), r.T @ np.diag([1, -1, -1]), atol=1e-8)
    t = np.eye(4); t[:3, :3] = r
    p.pinhole_world_to_camera = t
    np.testing.assert_allclose(camera_bridge_rotation(p), r.T, atol=1e-8)


def test_surface_polish_does_not_rotate_or_delete_carrier():
    from src.sparse_observation_registration import refine_sparse_scale_translation
    class Projector:
        image_shape = (512, 512)
        def project(self, points):
            return (points[:, :2] + 1) * 180 + 50, points[:, 2] + 5
    gx, gy = np.meshgrid(np.linspace(-1,1,32), np.linspace(-1,1,32))
    prior = np.column_stack((gx.ravel(), gy.ravel(), .1*np.sin(gx.ravel())))
    partial = prior[::2] + [0, 0, .15]
    uv = (partial[:, :2]+1)/2
    result, report = refine_sparse_scale_translation(partial, prior, uv, Projector())
    assert result.shape == prior.shape
    assert report['rotation_fixed']
    t = np.array(report['transform'])
    np.testing.assert_allclose(t[:3,:3], np.eye(3)*t[0,0], atol=1e-10)
    assert np.median(abs(result[:,2]-prior[:,2]-.15)) < .02


def test_guard_rejects_regression_and_accepts_distributed_gain():
    from src.sparse_observation_registration import select_sparse_candidate
    x, uv, _ = fixture()
    accepted, _ = select_sparse_candidate(x, x, x+[0,0,.2], uv)
    assert not accepted
    accepted, report = select_sparse_candidate(x, x+[0,0,.2], x, uv)
    assert accepted
    assert report['selected'] == 'sparse'


def test_guard_retains_identity_when_evidence_is_identical():
    from src.sparse_observation_registration import select_sparse_candidate
    x, uv, _ = fixture()
    accepted, _ = select_sparse_candidate(x, x, x.copy(), uv)
    assert not accepted
