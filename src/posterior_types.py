"""Typed, dataset-independent contracts for posterior adaptation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PosteriorAdapterConfig:
    """Dataset-independent controls for the posterior solver."""

    partial_samples: int = 3_072
    prior_samples: int = 6_144
    normal_neighbours: int = 24
    transport_iterations: int = 60
    transport_relaxation: float = .72
    transport_temperature_floor: float = .012
    maximum_3d_ratio: float = .34
    maximum_screen_ratio: float = .28
    maximum_depth_ratio: float = .34
    structural_rescue_candidates: int = 48
    structural_rescue_screen_fraction: float = .55
    structural_rescue_depth_fraction: float = .70
    intrinsic_landmarks: int = 8
    intrinsic_graph_neighbours: int = 12
    minimum_transport_pairs: int = 96
    stable_spacing_multiplier: float = 3.0
    stable_residual_quantile: float = .22
    residual_quantile: float = .42
    require_localized_residual_evidence: bool = True
    coarse_node_fraction: float = .020
    fine_node_fraction: float = .055
    minimum_graph_nodes: int = 192
    maximum_graph_nodes: int = 6_144
    skinning_neighbours: int = 4
    low_frequency_modes: int = 24
    low_frequency_regularization: float = .035
    low_frequency_stable_weight: float = 6.0
    coarse_neighbours: int = 18
    coarse_edge_ratio: float = 2.45
    coarse_data_weight: float = 2.5
    coarse_screening: float = .0008
    coarse_iterations: int = 5
    coarse_displacement_ratio: float = .28
    fine_neighbours: int = 10
    fine_edge_ratio: float = 1.85
    fine_data_weight: float = 4.0
    fine_screening: float = .003
    fine_iterations: int = 5
    fine_displacement_ratio: float = .12
    bending_regularization: float = 0.0
    attachment_edge_ratio: float = 3.2
    minimum_observed_improvement: float = .025
    minimum_edge_compression: float = .55
    # This is a dimensionless rest-edge ratio.  The connectivity gate below
    # remains the hard topology constraint; this robust tail bound prevents a
    # vanishing number of sampling edges from stopping a coherent update.
    maximum_edge_stretch: float = 2.80
    minimum_hidden_coverage: float = .95
    coverage_resolution: int = 160
    integrated_observation_fusion: bool = False
    assimilation_samples: int = 6_144
    assimilation_pixel_radius: float = 1.0
    assimilation_cross_view_pixel_radius: float = 2.0
    assimilation_minimum_view_support: int = 1
    assimilation_separate_stable_anchors: bool = False
    assimilation_stable_quantile: float = .25
    assimilation_hard_residual_targets: bool = False
    assimilation_coherent_residual_targets: bool = False
    assimilation_data_weight: float = 2.0
    assimilation_screening: float = .004
    assimilation_iterations: int = 3
    assimilation_displacement_ratio: float = .050
    assimilation_anchor_residual_ratio: float = .075
    slender_rigidity_projection: bool = False
    slender_neighbours: int = 128
    slender_linearity_quantile: float = .95
    slender_minimum_fraction: float = .003
    slender_minimum_aspect_ratio: float = 6.0
    slender_dilation_steps: int = 2

    def validate(self) -> None:
        if min(self.partial_samples, self.prior_samples) < 32:
            raise ValueError("transport sample counts must be at least 32")
        if self.normal_neighbours < 6 or self.transport_iterations < 1:
            raise ValueError("normal and transport iteration counts are invalid")
        if self.structural_rescue_candidates < 1 or self.intrinsic_landmarks < 2:
            raise ValueError("structural transport controls are invalid")
        if self.intrinsic_graph_neighbours < 3 or self.low_frequency_modes < 0:
            raise ValueError("intrinsic graph and modal controls are invalid")
        ratios = (
            self.maximum_3d_ratio, self.maximum_screen_ratio,
            self.maximum_depth_ratio, self.stable_spacing_multiplier,
            self.coarse_edge_ratio, self.fine_edge_ratio,
            self.attachment_edge_ratio, self.coarse_displacement_ratio,
            self.fine_displacement_ratio, self.structural_rescue_screen_fraction,
            self.structural_rescue_depth_fraction, self.low_frequency_regularization,
            self.low_frequency_stable_weight,
        )
        if min(ratios) <= 0.:
            raise ValueError("metric and graph ratios must be positive")
        unit = (
            self.transport_relaxation, self.stable_residual_quantile, self.residual_quantile,
            self.minimum_observed_improvement, self.minimum_edge_compression,
            self.minimum_hidden_coverage,
        )
        if any(not 0. < value < 1. for value in unit):
            raise ValueError("quantiles, relaxation, and acceptance ratios must lie in (0, 1)")
        if self.stable_residual_quantile >= self.residual_quantile:
            raise ValueError("stable_residual_quantile must precede residual_quantile")
        if self.maximum_edge_stretch <= 1. or self.coverage_resolution < 32:
            raise ValueError("invalid topology or coverage controls")
        if not 0. < self.coarse_node_fraction < self.fine_node_fraction < 1.:
            raise ValueError("deformation graph fractions must be ordered in (0, 1)")
        if self.minimum_graph_nodes < 32 or self.maximum_graph_nodes < self.minimum_graph_nodes:
            raise ValueError("invalid deformation graph node bounds")
        if self.skinning_neighbours < 1:
            raise ValueError("skinning_neighbours must be positive")
        if self.assimilation_samples < 32 or self.assimilation_iterations < 1:
            raise ValueError("observation assimilation controls are invalid")
        if self.assimilation_minimum_view_support not in (1, 2, 3, 4):
            raise ValueError("assimilation_minimum_view_support must lie in [1, 4]")
        if not 0. < self.assimilation_stable_quantile < 1.:
            raise ValueError("assimilation_stable_quantile must lie in (0, 1)")
        if min(
            self.assimilation_pixel_radius,
            self.assimilation_cross_view_pixel_radius,
            self.assimilation_data_weight,
            self.assimilation_screening,
            self.assimilation_displacement_ratio,
            self.assimilation_anchor_residual_ratio,
        ) <= 0.:
            raise ValueError("observation assimilation weights must be positive")
        if self.slender_neighbours < 16 or self.slender_dilation_steps < 0:
            raise ValueError("slender-structure neighbourhood controls are invalid")
        if not 0.5 < self.slender_linearity_quantile < 1.:
            raise ValueError("slender_linearity_quantile must lie in (0.5, 1)")
        if not 0. < self.slender_minimum_fraction < .25:
            raise ValueError("slender_minimum_fraction must lie in (0, 0.25)")
        if self.slender_minimum_aspect_ratio <= 1.:
            raise ValueError("slender_minimum_aspect_ratio must exceed one")
        if self.bending_regularization < 0.:
            raise ValueError("bending_regularization must be non-negative")


@dataclass(frozen=True)
class TransportResult:
    partial_ids: np.ndarray
    prior_ids: np.ndarray
    weights: np.ndarray
    costs: np.ndarray
    residuals: np.ndarray
    stable_prior_mask: np.ndarray
    residual_prior_mask: np.ndarray
    unsupported_prior_mask: np.ndarray
    diagnostics: dict
