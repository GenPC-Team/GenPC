import numpy as np

from scripts.audit_prior_depth_order import compare_depth_order


def test_ordinal_depth_audit_detects_reversal_without_metric_scale():
    x = np.linspace(35, 220, 96, dtype=np.float64)
    observed = np.tile(x, (96, 1))
    mask = np.ones_like(observed, dtype=bool)
    matched = compare_depth_order(observed, 10.0 - observed / 30.0, mask)
    reversed_view = compare_depth_order(observed, 2.0 + observed / 30.0, mask)
    assert matched["reliable"] and reversed_view["reliable"]
    assert matched["spearman_depth_order"] > .99
    assert reversed_view["spearman_depth_order"] < -.99
    assert matched["pairwise_order_accuracy"] > .99
    assert reversed_view["pairwise_order_accuracy"] < .01
