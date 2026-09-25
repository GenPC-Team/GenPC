import numpy as np

from src.observation_anchored_fusion import (
    ContinuousObservationFusionConfig,
    _adaptive_residual_limit,
    collision_free_anchor_pairs,
)


def test_collision_free_fusion_replaces_each_carrier_slot_at_most_once():
    carrier = np.array(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)))
    partial = np.array(((0.1, 0.0, 0.0), (0.2, 0.0, 0.0), (2.1, 0.0, 0.0)))
    pairs = np.array(((0, 0, 0, 0.0), (1, 0, 0, 0.1), (2, 2, 2, 0.0)))
    selected, info = collision_free_anchor_pairs(
        pairs, partial, carrier, max_residual=0.3,
    )
    assert np.array_equal(selected, np.array(((0, 0), (2, 2))))
    assert info["collision_free_pairs"] == 2


def test_collision_free_fusion_rejects_large_geometric_residuals():
    carrier = np.array(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)))
    partial = np.array(((5.0, 0.0, 0.0),))
    pairs = np.array(((0, 0, 0, 0.0),))
    selected, info = collision_free_anchor_pairs(
        pairs, partial, carrier, max_residual=0.3,
    )
    assert selected.shape == (0, 2)
    assert info["within_metric_limit"] == 0


def test_continuous_fusion_residual_gate_is_density_aware_and_bounded():
    config = ContinuousObservationFusionConfig(
        maximum_residual_ratio=0.03,
        partial_spacing_multiplier=6.0,
        residual_quantile=0.90,
    )
    residual = np.array((0.001, 0.002, 0.003, 0.020))
    limit = _adaptive_residual_limit(
        residual, diagonal=1.0, partial_spacing=0.001, config=config,
    )
    assert np.isclose(limit, np.quantile(residual, 0.90))
    sparse_limit = _adaptive_residual_limit(
        residual, diagonal=1.0, partial_spacing=0.010, config=config,
    )
    assert np.isclose(sparse_limit, 0.03)
