"""Generic invariants for complete-prior posterior adaptation."""

from __future__ import annotations

import numpy as np

from src.carrier_protection import (
    _continue_positive_residual_motion,
    _project_positive_components_to_similarity,
    _project_residual_coherent_raw_field,
    _project_small_topology_breaks,
    _smooth_positive_motion,
    project_reference_carrier_protection,
)
from src.partial_transport import partial_optimal_transport
from src.posterior_adapter import PosteriorAdapter, PosteriorAdapterConfig
from src.posterior_deformation import (
    _augment_attachment_edges,
    _embedded_arap_posterior,
)
from src.deformation_graph import local_surface_graph
from src.strain_aware_densification import StrainDensificationConfig, densify_stretched_surface
from scipy.sparse import csgraph


class OrthographicProjector:
    image_shape = (192, 192)

    def __init__(self, points: np.ndarray):
        low, high = points[:, :2].min(0), points[:, :2].max(0)
        self.low = low
        self.extent = np.maximum(high - low, 1e-6)

    def project(self, points: np.ndarray):
        points = np.asarray(points)
        uv = (points[:, :2] - self.low) / self.extent * 160. + 16.
        return uv, points[:, 2] - points[:, 2].min() + 1.


def _connected_shape() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x, y = np.meshgrid(np.linspace(0., 1., 40), np.linspace(-.22, .22, 18), indexing="ij")
    z = .04 * np.sin(np.pi * x) * np.cos(np.pi * y / .44)
    body = np.c_[x.reshape(-1), y.reshape(-1), z.reshape(-1)]
    t = np.linspace(0., 1., 12)
    appendage = np.c_[.80 + .08 * t, -.18 * np.ones_like(t), -.12 - .45 * t]
    appendage = np.repeat(appendage, 6, axis=0)
    jitter = np.tile(np.c_[np.zeros(6), np.linspace(-.025, .025, 6), np.zeros(6)], (12, 1))
    prior = np.concatenate((body, appendage + jitter), axis=0)
    partial = prior.copy()
    moved = np.arange(len(body), len(prior))
    ramp = np.linspace(.08, .25, len(moved))
    partial[moved, 0] += ramp
    partial[moved, 1] -= .12
    partial[moved, 2] -= .08
    return prior, partial, moved


def _test_config() -> PosteriorAdapterConfig:
    return PosteriorAdapterConfig(
        partial_samples=1_024, prior_samples=1_536, normal_neighbours=12,
        transport_iterations=25, minimum_transport_pairs=24,
        maximum_3d_ratio=.40, maximum_screen_ratio=.40, maximum_depth_ratio=.40,
        stable_spacing_multiplier=2., coarse_neighbours=12, coarse_edge_ratio=2.8,
        coarse_iterations=3, fine_neighbours=8, fine_edge_ratio=2.2, fine_iterations=3,
        attachment_edge_ratio=4., minimum_edge_compression=.25,
        maximum_edge_stretch=4., minimum_hidden_coverage=.80, coverage_resolution=64,
    )


def test_partial_transport_can_leave_an_unrelated_observation_unmatched():
    prior, partial, _ = _connected_shape()
    outliers = np.array([[4., 4., 4.], [4.1, 4., 4.]], dtype=np.float64)
    observed = np.concatenate((partial, outliers), axis=0)
    projector = OrthographicProjector(observed)
    result = partial_optimal_transport(prior, observed, projector, config=_test_config(), device="cpu")
    assert not np.isin(np.arange(len(partial), len(observed)), result.partial_ids).any()
    assert result.diagnostics["unmatched_partial_fraction"] > 0.


def test_partial_transport_records_every_visibility_valid_view():
    prior, partial, _ = _connected_shape()
    projector = OrthographicProjector(partial)
    result = partial_optimal_transport(
        prior, partial, projector, config=_test_config(), device="cpu",
        view_projectors=(projector, projector),
    )
    assert result.diagnostics["view_count"] == 2
    assert len(result.diagnostics["view_evidence"]) == 2
    assert result.diagnostics["method"].startswith("multiview_")


def test_embedded_posterior_preserves_slots_and_continuously_moves_supported_structure():
    prior, partial, moved_ids = _connected_shape()
    stable = np.zeros(len(prior), dtype=bool)
    stable[np.arange(len(prior) - len(moved_ids))[prior[:-len(moved_ids), 0] < .65]] = True
    posterior, info, moved = _embedded_arap_posterior(
        prior, moved_ids, partial[moved_ids], np.ones(len(moved_ids)), stable,
        node_fraction=.12, minimum_nodes=96, maximum_nodes=512, skinning_neighbours=4,
        neighbours=10, edge_ratio=3.0, attachment_edge_ratio=4.0,
        data_weight=4.0, screening=.001, iterations=4,
        maximum_displacement=.5, minimum_improvement=.01,
        minimum_edge_compression=.2, maximum_edge_stretch=4.0,
        minimum_hidden_coverage=.8, coverage_resolution=64,
    )
    assert info["active"]
    assert len(posterior) == len(prior)
    assert moved.any()
    assert np.allclose(posterior[stable], prior[stable])
    before = np.median(np.linalg.norm(prior[moved_ids] - partial[moved_ids], axis=1))
    after = np.median(np.linalg.norm(posterior[moved_ids] - partial[moved_ids], axis=1))
    assert after < before
    neighbour_step = np.linalg.norm(np.diff(posterior[moved_ids], axis=0), axis=1)
    assert np.quantile(neighbour_step, .99) < .12


def test_embedded_posterior_can_preserve_positive_target_amplitude_against_stable_anchors():
    prior, partial, moved_ids = _connected_shape()
    stable = np.zeros(len(prior), dtype=bool)
    stable[:len(prior) - len(moved_ids)] = True
    posterior, info, _ = _embedded_arap_posterior(
        prior, moved_ids, partial[moved_ids], np.ones(len(moved_ids)), stable,
        node_fraction=.12, minimum_nodes=96, maximum_nodes=512, skinning_neighbours=4,
        neighbours=10, edge_ratio=3.0, attachment_edge_ratio=4.0,
        data_weight=4.0, screening=.001, iterations=4,
        maximum_displacement=.5, minimum_improvement=.01,
        minimum_edge_compression=.2, maximum_edge_stretch=4.0,
        minimum_hidden_coverage=.8, coverage_resolution=64,
        preserve_target_amplitude=True,
    )
    assert info["active"]
    assert info["preserve_target_amplitude"]
    before = np.median(np.linalg.norm(prior[moved_ids] - partial[moved_ids], axis=1))
    after = np.median(np.linalg.norm(posterior[moved_ids] - partial[moved_ids], axis=1))
    assert after < .25 * before


def test_embedded_posterior_can_hard_constrain_verified_residual_targets():
    prior, partial, moved_ids = _connected_shape()
    stable = np.zeros(len(prior), dtype=bool)
    stable[prior[:, 0] < .55] = True
    posterior, info, _ = _embedded_arap_posterior(
        prior, moved_ids, partial[moved_ids], np.ones(len(moved_ids)), stable,
        node_fraction=.12, minimum_nodes=96, maximum_nodes=512, skinning_neighbours=4,
        neighbours=10, edge_ratio=3.0, attachment_edge_ratio=4.0,
        data_weight=4.0, screening=.001, iterations=4,
        maximum_displacement=.5, minimum_improvement=.01,
        minimum_edge_compression=.2, maximum_edge_stretch=4.0,
        minimum_hidden_coverage=.8, coverage_resolution=64,
        preserve_target_amplitude=True, hard_target_constraints=True,
    )
    assert info["active"]
    assert info["hard_target_constraints"]
    assert np.allclose(posterior[moved_ids], partial[moved_ids])
    assert np.allclose(posterior[stable], prior[stable])


def test_topology_projection_reconnects_a_new_small_fragment_without_moving_stable_points():
    x = np.linspace(0., 1., 180)
    prior = np.c_[x, .01 * np.sin(8. * x), np.zeros_like(x)]
    candidate = prior.copy()
    candidate[-3:] += np.array([0., .8, 0.])
    stable = np.zeros(len(prior), dtype=bool)
    stable[:20] = True
    repaired, info = _project_small_topology_breaks(
        prior, candidate, stable, neighbours=8, edge_ratio=3.0,
        component_threshold=16, maximum_passes=3,
    )
    assert info["active"]
    assert np.allclose(repaired[stable], prior[stable])
    assert np.linalg.norm(repaired[-1] - repaired[-4]) < np.linalg.norm(candidate[-1] - candidate[-4])


def test_reference_carrier_protection_damps_a_collapsing_iterative_update():
    x, y = np.meshgrid(np.linspace(0., 1., 48), np.linspace(-.2, .2, 24), indexing="ij")
    reference = np.c_[x.reshape(-1), y.reshape(-1), np.zeros(x.size)]
    candidate = reference.copy()
    candidate[:, :2] *= .08
    protected, info = project_reference_carrier_protection(
        reference, candidate, neighbours=10, edge_ratio=2.2,
        minimum_hidden_coverage=.90, maximum_edge_stretch=4., coverage_resolution=64,
    )
    assert info["accepted"]
    assert info["active"]
    assert info["alpha"] < 1.
    assert not np.allclose(protected, candidate)


def test_reference_carrier_protection_preserves_full_update_on_positive_evidence():
    x, y = np.meshgrid(np.linspace(0., 1., 48), np.linspace(-.2, .2, 24), indexing="ij")
    reference = np.c_[x.reshape(-1), y.reshape(-1), np.zeros(x.size)]
    candidate = reference.copy()
    candidate[:, :2] *= .60
    support = reference[:, 0] > .96
    protected, info = project_reference_carrier_protection(
        reference, candidate, neighbours=10, edge_ratio=2.2,
        minimum_hidden_coverage=.90, maximum_edge_stretch=4., coverage_resolution=64,
        positive_evidence_mask=support,
        deformation_config=_test_config(),
    )
    assert info["accepted"]
    assert info["positive_evidence_points"] == int(support.sum())
    assert info["support_projection"]["active"]
    assert np.median(np.linalg.norm(protected[support] - candidate[support], axis=1)) < np.median(
        np.linalg.norm(reference[support] - candidate[support], axis=1)
    )


def test_reference_protection_selects_prominent_local_motion_from_positive_evidence():
    x, y = np.meshgrid(np.linspace(0., 1., 48), np.linspace(-.2, .2, 24), indexing="ij")
    reference = np.c_[x.reshape(-1), y.reshape(-1), np.zeros(x.size)]
    candidate = reference.copy()
    evidence = reference[:, 0] > .90
    moved = reference[:, 0] > .96
    candidate[moved, 0] += .35
    _, info = project_reference_carrier_protection(
        reference, candidate, neighbours=10, edge_ratio=2.2,
        minimum_hidden_coverage=.80, maximum_edge_stretch=4., coverage_resolution=64,
        positive_evidence_mask=evidence, deformation_config=_test_config(),
        support_local_motion_selection=True,
    )
    selection = info["support_selection"]
    assert selection["active"]
    assert 0 < selection["selected_evidence_points"] < int(evidence.sum())


def test_reference_protection_repairs_tiny_new_fragment_before_damping_motion():
    x, y = np.meshgrid(np.linspace(0., 1., 48), np.linspace(-.2, .2, 24), indexing="ij")
    reference = np.c_[x.reshape(-1), y.reshape(-1), np.zeros(x.size)]
    candidate = reference.copy()
    # A compact observed region moves coherently, while a few samples at its
    # boundary become a non-significant isolated fragment.  Protection should
    # repair the tiny split rather than globally suppress the valid motion.
    support = reference[:, 0] > .90
    candidate[support, 0] += .16
    candidate[-3:, 1] += 2.
    protected, info = project_reference_carrier_protection(
        reference, candidate, neighbours=10, edge_ratio=2.2,
        minimum_hidden_coverage=.80, maximum_edge_stretch=4., coverage_resolution=64,
        positive_evidence_mask=support,
    )
    assert info["accepted"]
    assert info["line_search"][0]["topology_repair"]["corrected_points"] > 0
    assert np.linalg.norm(protected[support] - reference[support], axis=1).mean() > .01


def test_reference_protection_can_accept_a_local_increment_without_relaxing_global_integrity():
    x, y = np.meshgrid(np.linspace(0., 1., 48), np.linspace(-.2, .2, 24), indexing="ij")
    reference = np.c_[x.reshape(-1), y.reshape(-1), np.zeros(x.size)]
    current = reference.copy()
    current[reference[:, 0] > .90, 0] += .02
    candidate = current.copy()
    support = reference[:, 0] > .90
    candidate[support, 0] += .02
    protected, info = project_reference_carrier_protection(
        reference, candidate, update_reference=current,
        neighbours=10, edge_ratio=2.2,
        minimum_hidden_coverage=.80, maximum_edge_stretch=4., coverage_resolution=64,
        positive_evidence_mask=support,
    )
    assert info["accepted"]
    assert info["incremental_update"]
    assert np.median(protected[support, 0] - reference[support, 0]) > .03


def test_positive_residual_continuation_keeps_targets_and_fixed_far_carrier():
    x, y = np.meshgrid(np.linspace(0., 1., 48), np.linspace(-.2, .2, 24), indexing="ij")
    reference = np.c_[x.reshape(-1), y.reshape(-1), np.zeros(x.size)]
    candidate = reference.copy()
    support = reference[:, 0] > .96
    candidate[support, 0] += .35
    graph, _, _ = local_surface_graph(reference, neighbours=10, edge_ratio=2.2)
    continued, info = _continue_positive_residual_motion(
        reference, candidate, graph, support, hops=4,
    )
    assert info["active"]
    assert np.allclose(continued[support], candidate[support])
    far = reference[:, 0] < .50
    assert np.allclose(continued[far], reference[far])
    assert np.any(np.linalg.norm(continued - reference, axis=1) > 1e-8)


def test_positive_motion_smoothing_reduces_local_target_jitter_without_touching_outside():
    x = np.linspace(0., 1., 180)
    reference = np.c_[x, np.zeros_like(x), np.zeros_like(x)]
    candidate = reference.copy()
    support = x > .65
    candidate[support, 1] = .2
    candidate[150, 1] = -.4
    graph, _, _ = local_surface_graph(reference, neighbours=10, edge_ratio=3.0)
    smoothed, info = _smooth_positive_motion(reference, candidate, graph, support, steps=3)
    assert info["active"]
    assert info["edge_motion"]["after_p99"] < info["edge_motion"]["before_p99"]
    assert np.allclose(smoothed[~support], reference[~support])


def test_positive_component_similarity_removes_jitter_from_a_coherent_local_motion():
    x = np.linspace(0., 1., 240)
    reference = np.c_[x, .02 * np.sin(6. * x), np.zeros_like(x)]
    support = x > .70
    candidate = reference.copy()
    candidate[support] += np.array([.12, -.06, .03])
    candidate[210, 1] += .08
    graph, _, _ = local_surface_graph(reference, neighbours=10, edge_ratio=3.0)
    projected, info, driver = _project_positive_components_to_similarity(
        reference, candidate, graph, support, core_hops=1,
    )
    assert info["active"]
    raw = np.linalg.norm((candidate - reference)[support] - np.median((candidate - reference)[support], axis=0), axis=1)
    smooth = np.linalg.norm((projected - reference)[support] - np.median((projected - reference)[support], axis=0), axis=1)
    assert np.quantile(smooth, .99) < np.quantile(raw, .99)
    assert int(driver.sum()) >= int(support.sum())


def test_positive_component_similarity_gain_extrapolates_one_coherent_motion():
    x = np.linspace(0., 1., 240)
    reference = np.c_[x, .02 * np.sin(6. * x), np.zeros_like(x)]
    support = x > .70
    candidate = reference.copy()
    candidate[support] += np.array([.10, -.04, .02])
    graph, _, _ = local_surface_graph(reference, neighbours=10, edge_ratio=3.0)
    base, base_info, _ = _project_positive_components_to_similarity(
        reference, candidate, graph, support, core_hops=0, gain=1.0,
    )
    amplified, amplified_info, _ = _project_positive_components_to_similarity(
        reference, candidate, graph, support, core_hops=0, gain=1.5,
    )
    base_motion = np.median(np.linalg.norm(base[support] - reference[support], axis=1))
    amplified_motion = np.median(np.linalg.norm(amplified[support] - reference[support], axis=1))
    assert base_info["active"] and amplified_info["active"]
    assert amplified_motion > 1.35 * base_motion
    assert np.allclose(amplified[~support], candidate[~support])


def test_residual_coherent_raw_field_selects_locally_supported_motion():
    prior, _, moved_ids = _connected_shape()
    candidate = prior.copy()
    candidate[moved_ids] += np.array([.18, -.08, .05])
    support = np.zeros(len(prior), dtype=bool)
    support[moved_ids] = True
    graph, _, _ = local_surface_graph(prior, neighbours=10, edge_ratio=3.0)
    projected, info = _project_residual_coherent_raw_field(
        prior, candidate, graph, support,
    )
    assert info["active"]
    assert info["selected_points"] >= len(moved_ids)
    assert np.median(np.linalg.norm(projected[moved_ids] - prior[moved_ids], axis=1)) > .10
    assert np.median(np.linalg.norm(projected[:len(prior) - len(moved_ids)] - prior[:len(prior) - len(moved_ids)], axis=1)) < .05


def test_near_contact_components_receive_rotation_carrying_attachment_bundle():
    # Each plate has more than 32 closer in-component neighbours, so the old
    # fixed-k cross-component search could not see their nearby contact.
    x, y = np.meshgrid(np.linspace(0., .09, 12), np.linspace(0., .09, 12), indexing="ij")
    left = np.c_[x.reshape(-1), y.reshape(-1), np.zeros(x.size)]
    right = left + np.array([.115, 0., 0.])
    points = np.concatenate((left, right), axis=0)
    graph, metric, _ = local_surface_graph(points, neighbours=10, edge_ratio=1.8)
    before, _ = csgraph.connected_components(graph, directed=False)
    augmented, _, attachment_edges = _augment_attachment_edges(
        graph, metric, points, edge_ratio=4.0,
    )
    after, _ = csgraph.connected_components(augmented, directed=False)
    assert before == 2
    assert after == 1
    assert attachment_edges >= 3


def test_strain_densification_preserves_carrier_and_fills_stretched_edges():
    x, y = np.meshgrid(np.linspace(0., 1., 32), np.linspace(0., 1., 16), indexing="ij")
    reference = np.c_[x.reshape(-1), y.reshape(-1), np.zeros(x.size)]
    deformed = reference.copy()
    deformed[reference[:, 0] > .62, 0] += .75 * (reference[reference[:, 0] > .62, 0] - .62)
    dense, report = densify_stretched_surface(
        reference, deformed,
        config=StrainDensificationConfig(
            strain_quantile=.75, minimum_stretch=1.2,
            maximum_segment_stretch=1.15, maximum_new_point_ratio=.20,
        ),
    )
    assert report["new_points"] > 0
    assert len(dense) > len(deformed)
    assert np.allclose(dense[:len(deformed)], deformed)
    assert np.all(dense[len(deformed):, 0] >= deformed[:, 0].min())
    assert np.all(dense[len(deformed):, 0] <= deformed[:, 0].max())
