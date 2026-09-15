import numpy as np

from src.ray_consistent_registration import apply_transform
from src.sparse_ray_registration import (
    SparseRayRegistrationConfig,
    camera_anchored_indexed_similarity,
    moge_to_saved_raster_convention,
    sparse_partial_to_moge_refine,
    sparse_ray_surface_refine,
)


def _surface():
    y, x = np.mgrid[-8:9, -12:13]
    points = np.c_[x.ravel() / 12., y.ravel() / 12., 1. + .04 * np.sin(x.ravel() / 3.)]
    pixels = np.c_[x.ravel() * 8. + 128., y.ravel() * 8. + 128.]
    return points, pixels


def test_sparse_ray_surface_refine_recovers_residual_sim3_with_pixel_jitter():
    moge, pixels = _surface()
    selected = np.arange(0, len(moge), 7)
    partial = moge[selected].copy()
    partial[:, 0] = 1.04 * partial[:, 0] + .035
    partial[:, 1] = 1.04 * partial[:, 1] - .018
    partial[:, 2] = 1.04 * partial[:, 2] + .025
    mapped = pixels[selected] + np.c_[4. * np.sin(selected), 3. * np.cos(selected)]
    initial = np.eye(4)
    config = SparseRayRegistrationConfig(
        minimum_pairs=24,
        radius_fractions=(.06, .03),
        trim_quantiles=(.80, .72),
        maximum_rotation_deg=4.,
        scale_bounds=(.92, 1.08),
        maximum_translation_ratio=.10,
    )
    transform, info = sparse_ray_surface_refine(
        moge, partial, mapped, np.ones(len(partial), dtype=bool), pixels, initial,
        target_mask_bbox_diagonal=240., config=config,
    )
    before = np.linalg.norm(moge[selected] - partial, axis=1).mean()
    after = np.linalg.norm(apply_transform(moge[selected], transform) - partial, axis=1).mean()
    assert info["accepted_levels"] >= 1
    assert after < .55 * before


def test_sparse_ray_surface_refine_balances_dense_regions_and_rejects_outliers():
    moge, pixels = _surface()
    selected = np.r_[np.arange(0, 150), np.arange(300, len(moge), 13)]
    partial = moge[selected] + np.array([.025, -.015, .02])
    partial[-8:] += 4.0
    mapped = pixels[selected]
    transform, info = sparse_ray_surface_refine(
        moge, partial, mapped, np.ones(len(partial), dtype=bool), pixels, np.eye(4),
        target_mask_bbox_diagonal=240.,
        config=SparseRayRegistrationConfig(
            minimum_pairs=24, radius_fractions=(.04, .02),
            trim_quantiles=(.72, .68), maximum_translation_ratio=.08,
        ),
    )
    clean = np.arange(len(selected) - 8)
    before = np.linalg.norm(moge[selected[clean]] - partial[clean], axis=1).mean()
    after = np.linalg.norm(apply_transform(moge[selected[clean]], transform) - partial[clean], axis=1).mean()
    assert info["accepted_levels"] >= 1
    assert after < before


def test_sparse_partial_queries_fit_dense_moge_then_return_inverse_map():
    moge, pixels = _surface()
    selected = np.arange(0, len(moge), 6)
    partial = moge[selected] + np.array([.045, -.025, .03])
    mapped = pixels[selected] + np.c_[2.5 * np.sin(selected), 2. * np.cos(selected)]
    transform, info = sparse_partial_to_moge_refine(
        moge, partial, mapped, np.ones(len(partial), dtype=bool), pixels, np.eye(4),
        target_mask_bbox_diagonal=240.,
        config=SparseRayRegistrationConfig(
            minimum_pairs=24, radius_fractions=(.05, .025),
            trim_quantiles=(.80, .72), maximum_translation_ratio=.10,
        ),
    )
    before = np.linalg.norm(moge[selected] - partial, axis=1).mean()
    after = np.linalg.norm(apply_transform(moge[selected], transform) - partial, axis=1).mean()
    assert info["accepted_levels"] >= 1
    assert after < .6 * before


def test_saved_raster_convention_accounts_for_historical_vertical_flip():
    historical, historical_info = moge_to_saved_raster_convention(
        flip_saved_uv_y=True,
    )
    standard, standard_info = moge_to_saved_raster_convention(
        flip_saved_uv_y=False,
    )
    assert np.array_equal(np.diag(historical)[:3], np.array([1., 1., -1.]))
    assert np.array_equal(np.diag(standard)[:3], np.array([1., -1., -1.]))
    assert historical_info["determinant"] == -1.
    assert standard_info["determinant"] == 1.


def test_camera_anchored_fit_keeps_rotation_and_recovers_scale_translation():
    source, pixels = _surface()
    convention, _ = moge_to_saved_raster_convention(flip_saved_uv_y=True)
    converted = apply_transform(source, convention)
    angle = np.deg2rad(31.)
    axes = np.array([
        [np.cos(angle), 0., np.sin(angle)],
        [0., 1., 0.],
        [-np.sin(angle), 0., np.cos(angle)],
    ])
    expected_rotation = axes.T
    target = 1.7 * (converted @ expected_rotation.T) + np.array([.3, -.2, .5])
    matches = np.c_[
        np.arange(len(source)), np.arange(len(source)), np.arange(len(source)),
        np.zeros(len(source)),
    ]
    transform, info = camera_anchored_indexed_similarity(
        converted, target, matches, axes,
        diagonal=float(np.linalg.norm(np.ptp(target, axis=0))),
    )
    assert np.allclose(transform[:3, :3], 1.7 * expected_rotation, atol=1e-8)
    assert np.allclose(transform[:3, 3], np.array([.3, -.2, .5]), atol=1e-8)
    assert info["residual_p90_normalized"] < 1e-8
