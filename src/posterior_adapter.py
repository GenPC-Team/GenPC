"""Public orchestration facade for observation-conditioned posterior adaptation.

Algorithmic responsibilities live in partial_transport, posterior_deformation,
and carrier_protection.  Historical imports are re-exported here for compatibility.
"""

from __future__ import annotations

from dataclasses import asdict
import math
from collections.abc import Sequence

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.spatial import cKDTree

from src.bidirectional_cycle_registration import visible_score
from src.deformation_graph import edge_strain, local_surface_graph
from src.observation_anchored_fusion import (
    ObservationAnchoredFusionConfig,
    collision_free_anchor_pairs,
    positive_multiview_pairs,
)

from src.posterior_types import PosteriorAdapterConfig, TransportResult
from src.partial_transport import (
    _intrinsic_graph_signature,
    _local_surface_features,
    _median_spacing,
    _sample_ids,
    _unbalanced_log_transport,
    _visible_prior_ids,
    partial_optimal_transport,
)
from src.posterior_deformation import (
    _augment_attachment_edges,
    _coherent_targets,
    _embedded_arap_posterior,
    _orthographic_coverage,
    _soft_full_surface_arap,
    _solve_preconditioned,
    _weighted_median,
)
from src.carrier_protection import (
    _compact_visible_score,
    _continue_positive_residual_motion,
    _project_positive_components_to_similarity,
    _project_residual_coherent_raw_field,
    _project_slender_regions_rigid,
    _project_small_topology_breaks,
    _smooth_positive_motion,
    project_reference_carrier_protection,
)

__all__ = [
    "PosteriorAdapter",
    "PosteriorAdapterConfig",
    "TransportResult",
    "partial_optimal_transport",
    "project_reference_carrier_protection",
]


class PosteriorAdapter:
    """One category-agnostic coarse-to-fine complete-prior update."""

    def __init__(self, config: PosteriorAdapterConfig | None = None, *, device: str = "cuda"):
        self.config = config or PosteriorAdapterConfig()
        self.config.validate()
        self.device = str(device)

    def run(
        self,
        prior: np.ndarray,
        partial: np.ndarray,
        projector,
        *,
        view_projectors: Sequence | None = None,
        transport_projectors: Sequence | None = None,
    ) -> tuple[np.ndarray, dict, dict[str, np.ndarray]]:
        prior = np.asarray(prior, dtype=np.float64)
        partial = np.asarray(partial, dtype=np.float64)
        initial = prior.copy()
        diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
        stage_records: list[dict] = []
        transports: list[TransportResult] = []
        displacements: list[np.ndarray] = []
        inherited_stable = np.zeros(len(prior), dtype=bool)
        residual_support_union = np.zeros(len(prior), dtype=bool)
        stage_specs = (
            ("coarse", self.config.coarse_neighbours, self.config.coarse_edge_ratio,
             self.config.coarse_data_weight, self.config.coarse_screening,
             self.config.coarse_iterations, self.config.coarse_displacement_ratio,
             self.config.coarse_node_fraction),
            ("fine", self.config.fine_neighbours, self.config.fine_edge_ratio,
             self.config.fine_data_weight, self.config.fine_screening,
             self.config.fine_iterations, self.config.fine_displacement_ratio,
             self.config.fine_node_fraction),
        )
        current = prior.copy()
        transport_views = transport_projectors if transport_projectors is not None else view_projectors
        for name, neighbours, edge_ratio, data_weight, screening, iterations, displacement_ratio, node_fraction in stage_specs:
            transport = partial_optimal_transport(
                current, partial, projector, config=self.config, device=self.device,
                view_projectors=transport_views,
            )
            transports.append(transport)
            residual_support_union |= transport.residual_prior_mask
            stable = inherited_stable | transport.stable_prior_mask
            residual_pair = np.isin(transport.prior_ids, np.flatnonzero(transport.residual_prior_mask))
            target_ids = transport.prior_ids[residual_pair]
            targets = partial[transport.partial_ids[residual_pair]]
            weights = transport.weights[residual_pair]
            if len(target_ids) < int(self.config.minimum_transport_pairs):
                stage_records.append({
                    "stage": name, "active": False, "reason": "insufficient_residual_transport_pairs",
                    "transport": transport.diagnostics,
                })
                displacements.append(np.zeros_like(current))
                if not bool(transport.diagnostics.get("localized_residual_evidence", False)):
                    break
                continue
            updated, solve, moved = _embedded_arap_posterior(
                current, target_ids, targets, weights, stable,
                node_fraction=float(node_fraction),
                minimum_nodes=int(self.config.minimum_graph_nodes),
                maximum_nodes=int(self.config.maximum_graph_nodes),
                skinning_neighbours=int(self.config.skinning_neighbours),
                neighbours=int(neighbours), edge_ratio=float(edge_ratio),
                attachment_edge_ratio=float(self.config.attachment_edge_ratio),
                data_weight=float(data_weight), screening=float(screening), iterations=int(iterations),
                bending_regularization=float(self.config.bending_regularization),
                maximum_displacement=float(displacement_ratio) * diagonal,
                minimum_improvement=float(self.config.minimum_observed_improvement),
                minimum_edge_compression=float(self.config.minimum_edge_compression),
                maximum_edge_stretch=float(self.config.maximum_edge_stretch),
                enforce_edge_strain_limits=bool(self.config.enforce_edge_strain_limits),
                minimum_hidden_coverage=float(self.config.minimum_hidden_coverage),
                coverage_resolution=int(self.config.coverage_resolution),
            )
            stage_records.append({"stage": name, "transport": transport.diagnostics, "solver": solve})
            displacements.append(updated - current)
            if solve.get("active"):
                current = updated
                inherited_stable = stable
        while len(displacements) < 2:
            displacements.append(np.zeros_like(current))
        component_threshold = max(32, int(math.ceil(.001 * len(initial))))
        current, topology_projection = _project_small_topology_breaks(
            initial, current, transports[0].stable_prior_mask,
            neighbours=int(self.config.fine_neighbours),
            edge_ratio=float(self.config.fine_edge_ratio),
            component_threshold=int(component_threshold),
        )
        assimilation_displacement = np.zeros_like(current)
        assimilation_anchor_mask = np.zeros(len(current), dtype=bool)
        assimilation_info: dict = {
            "active": False,
            "reason": "disabled",
            "method": "integrated_multiview_observation_assimilation",
        }
        if bool(self.config.integrated_observation_fusion):
            if view_projectors is None or not 2 <= len(view_projectors) <= 6:
                raise ValueError(
                    "agentic observation assimilation requires two to six view projectors"
                )
            fusion_config = ObservationAnchoredFusionConfig(
                num_views=len(view_projectors),
                pixel_radius=float(self.config.assimilation_pixel_radius),
                cross_view_pixel_radius=float(
                    self.config.assimilation_cross_view_pixel_radius
                ),
                cross_view_depth_ratio=float(self.config.assimilation_anchor_residual_ratio),
                anchor_residual_ratio=float(self.config.assimilation_anchor_residual_ratio),
            )
            positive_pairs, pair_info = positive_multiview_pairs(
                partial,
                current,
                list(view_projectors),
                config=fusion_config,
                diagonal=diagonal,
            )
            positive_pairs = positive_pairs[
                positive_pairs[:, 4]
                >= int(self.config.assimilation_minimum_view_support)
            ]
            anchors, assignment_info = collision_free_anchor_pairs(
                positive_pairs,
                partial,
                current,
                max_residual=float(self.config.assimilation_anchor_residual_ratio) * diagonal,
            )
            if len(anchors) > int(self.config.assimilation_samples):
                retained = _sample_ids(
                    partial[anchors[:, 0]], int(self.config.assimilation_samples),
                )
                anchors = anchors[retained]
            if len(anchors) >= int(self.config.minimum_transport_pairs):
                partial_ids, prior_ids = anchors[:, 0], anchors[:, 1]
                residual = np.linalg.norm(partial[partial_ids] - current[prior_ids], axis=1)
                stable_mask = np.zeros(len(current), dtype=bool)
                stable_limit = None
                if bool(self.config.assimilation_separate_stable_anchors):
                    stable_limit = max(
                        3.0 * _median_spacing(partial),
                        float(np.quantile(
                            residual, float(self.config.assimilation_stable_quantile)
                        )),
                    )
                    stable_anchor = residual <= stable_limit
                    stable_mask[prior_ids[stable_anchor]] = True
                    if np.any(stable_mask):
                        stable_distance = cKDTree(current[stable_mask]).query(
                            current, k=1, workers=-1,
                        )[0]
                        stable_mask |= stable_distance <= max(
                            2.0 * _median_spacing(current), _median_spacing(partial)
                        )
                    residual_anchor = residual >= 1.15 * stable_limit
                    partial_ids = partial_ids[residual_anchor]
                    prior_ids = prior_ids[residual_anchor]
                    residual = residual[residual_anchor]
                residual_scale = max(float(np.quantile(residual, .50)), _median_spacing(partial))
                weights = np.exp(-.5 * np.square(residual / max(3.0 * residual_scale, 1e-12)))
                weights = np.clip(weights, .20, 1.0)
                if len(prior_ids) < int(self.config.minimum_transport_pairs):
                    solve_info = {
                        "active": False,
                        "reason": "insufficient_residual_observation_anchors",
                    }
                    assimilated = current.copy()
                    assimilated_mask = np.zeros(len(current), dtype=bool)
                else:
                    assimilated, solve_info, assimilated_mask = _embedded_arap_posterior(
                        current,
                        prior_ids,
                        partial[partial_ids],
                        weights,
                        stable_mask,
                        node_fraction=float(self.config.fine_node_fraction),
                        minimum_nodes=int(self.config.minimum_graph_nodes),
                        maximum_nodes=int(self.config.maximum_graph_nodes),
                        skinning_neighbours=int(self.config.skinning_neighbours),
                        neighbours=int(self.config.fine_neighbours),
                        edge_ratio=float(self.config.fine_edge_ratio),
                        attachment_edge_ratio=float(self.config.attachment_edge_ratio),
                        data_weight=float(self.config.assimilation_data_weight),
                        screening=float(self.config.assimilation_screening),
                        bending_regularization=float(self.config.bending_regularization),
                        iterations=int(self.config.assimilation_iterations),
                        maximum_displacement=(
                            float(self.config.assimilation_displacement_ratio) * diagonal
                        ),
                        minimum_improvement=max(
                            .25 * float(self.config.minimum_observed_improvement), .0025,
                        ),
                        minimum_edge_compression=float(self.config.minimum_edge_compression),
                        maximum_edge_stretch=float(self.config.maximum_edge_stretch),
                        enforce_edge_strain_limits=bool(self.config.enforce_edge_strain_limits),
                        minimum_hidden_coverage=float(self.config.minimum_hidden_coverage),
                        coverage_resolution=int(self.config.coverage_resolution),
                        coherent_component_targets=bool(
                            self.config.assimilation_coherent_residual_targets
                        ),
                        preserve_target_amplitude=bool(
                            self.config.assimilation_separate_stable_anchors
                        ),
                        hard_target_constraints=bool(
                            self.config.assimilation_hard_residual_targets
                        ),
                    )
                if solve_info.get("active"):
                    before_assimilation = current
                    current = assimilated
                    assimilation_displacement = current - before_assimilation
                    assimilation_anchor_mask[prior_ids] = True
                    current, assimilation_topology = _project_small_topology_breaks(
                        before_assimilation,
                        current,
                        stable_mask,
                        neighbours=int(self.config.fine_neighbours),
                        edge_ratio=float(self.config.fine_edge_ratio),
                        component_threshold=int(component_threshold),
                    )
                    assimilation_displacement = current - before_assimilation
                else:
                    assimilation_topology = {"active": False, "reason": "solver_rejected"}
                assimilation_info = {
                    "active": bool(solve_info.get("active")),
                    "method": "integrated_four_view_observation_assimilation",
                    "positive_evidence": pair_info,
                    "assignment": assignment_info,
                    "retained_anchors": int(len(anchors)),
                    "residual_anchors": int(len(prior_ids)),
                    "stable_gaussians": int(stable_mask.sum()),
                    "stable_limit": stable_limit,
                    "solver": solve_info,
                    "topology_projection": assimilation_topology,
                }
            else:
                assimilation_info = {
                    "active": False,
                    "reason": "insufficient_observation_anchors",
                    "method": "integrated_four_view_observation_assimilation",
                    "positive_evidence": pair_info,
                    "assignment": assignment_info,
                    "retained_anchors": int(len(anchors)),
                }
        slender_rigidity_mask = np.zeros(len(current), dtype=bool)
        slender_rigidity_info: dict = {
            "active": False,
            "reason": "disabled",
            "method": "covariance_detected_slender_region_se3_projection",
        }
        if bool(self.config.slender_rigidity_projection):
            before_rigidity = current
            current, slender_rigidity_info, slender_rigidity_mask = _project_slender_regions_rigid(
                initial,
                current,
                neighbours=int(self.config.slender_neighbours),
                linearity_quantile=float(self.config.slender_linearity_quantile),
                minimum_fraction=float(self.config.slender_minimum_fraction),
                minimum_aspect_ratio=float(self.config.slender_minimum_aspect_ratio),
                dilation_steps=int(self.config.slender_dilation_steps),
                graph_neighbours=int(self.config.fine_neighbours),
                graph_edge_ratio=float(self.config.fine_edge_ratio),
            )
            current, rigidity_topology = _project_small_topology_breaks(
                before_rigidity,
                current,
                np.zeros(len(current), dtype=bool),
                neighbours=int(self.config.fine_neighbours),
                edge_ratio=float(self.config.fine_edge_ratio),
                component_threshold=int(component_threshold),
            )
            slender_rigidity_info["topology_projection"] = rigidity_topology
        initial_visible = visible_score(partial, initial, projector, diagonal)
        posterior_visible = visible_score(partial, current, projector, diagonal)
        # Keep global visible evidence as an audit signal only.  The posterior
        # solver already enforces its structural constraints internally; this
        # diagnostic must not revert a successfully solved deformation.
        posterior_diagnostics = {
            "selection_gate_used": False,
            "initial": _compact_visible_score(initial_visible),
            "candidate": _compact_visible_score(posterior_visible),
            "objective_delta": float(posterior_visible["objective"] - initial_visible["objective"]),
            "ground_truth_cd_emd_used": False,
        }
        final_coverage, final_coverage_views = _orthographic_coverage(
            initial, current, resolution=int(self.config.coverage_resolution),
        )
        final_graph, _, _ = local_surface_graph(
            initial, neighbours=int(self.config.fine_neighbours), edge_ratio=float(self.config.fine_edge_ratio),
        )
        posterior_graph, _, _ = local_surface_graph(
            current, neighbours=int(self.config.fine_neighbours), edge_ratio=float(self.config.fine_edge_ratio),
        )
        final_strain = edge_strain(initial, current, final_graph)
        input_components, input_labels = csgraph.connected_components(final_graph, directed=False)
        output_components, output_labels = csgraph.connected_components(posterior_graph, directed=False)
        input_sizes = np.bincount(input_labels, minlength=input_components)
        output_sizes = np.bincount(output_labels, minlength=output_components)
        edge_rows, edge_cols = sparse.triu(final_graph, k=1).nonzero()
        tracked_edge_ratio = np.linalg.norm(current[edge_rows] - current[edge_cols], axis=1) / np.maximum(
            np.linalg.norm(initial[edge_rows] - initial[edge_cols], axis=1), 1e-12,
        )
        final_transport = transports[-1]
        # ``supported_stable`` is deliberately the support detected before
        # any deformation.  It is the auditable no-motion set.  Later stages
        # may discover additional now-explained points, recorded separately,
        # but must not retroactively describe a moved point as initially
        # stable.
        initial_stable = transports[0].stable_prior_mask
        stable_motion = np.linalg.norm(current[initial_stable] - initial[initial_stable], axis=1)
        integrity = {
            "input_connected_components": int(input_components),
            "output_connected_components": int(output_components),
            "new_connected_components": int(max(0, output_components - input_components)),
            "component_significance_size": int(component_threshold),
            "input_significant_components": int(np.sum(input_sizes >= component_threshold)),
            "output_significant_components": int(np.sum(output_sizes >= component_threshold)),
            "input_component_sizes": np.sort(input_sizes)[::-1][:16].tolist(),
            "output_component_sizes": np.sort(output_sizes)[::-1][:16].tolist(),
            "tracked_original_edges": int(len(edge_rows)),
            "tracked_edge_replacement_fraction": float(np.mean(
                tracked_edge_ratio > float(self.config.maximum_edge_stretch),
            )) if len(tracked_edge_ratio) else 0.,
            "stable_motion_p50": float(np.quantile(stable_motion, .50)) if len(stable_motion) else 0.,
            "stable_motion_p95": float(np.quantile(stable_motion, .95)) if len(stable_motion) else 0.,
            "stable_motion_max": float(stable_motion.max(initial=0.)),
        }
        integrity["passed"] = bool(
            output_components <= input_components
            and integrity["output_significant_components"] <= integrity["input_significant_components"]
            and final_coverage >= float(self.config.minimum_hidden_coverage)
            and len(current) == len(initial)
        )
        masks = {
            "supported_stable": initial_stable,
            "supported_stable_final": inherited_stable,
            "supported_residual": final_transport.residual_prior_mask,
            "supported_residual_any_stage": residual_support_union,
            "unsupported": final_transport.unsupported_prior_mask,
            "moved": np.linalg.norm(current - initial, axis=1) > 1e-8,
            "coarse_displacement": displacements[0],
            "fine_displacement": displacements[1],
            "assimilation_displacement": assimilation_displacement,
            "assimilation_anchor": assimilation_anchor_mask,
            "slender_rigidity": slender_rigidity_mask,
            "transport_partial_ids": final_transport.partial_ids,
            "transport_prior_ids": final_transport.prior_ids,
            "transport_weights": final_transport.weights,
            "transport_costs": final_transport.costs,
        }
        info = {
            "active": bool(np.any(masks["moved"])),
            "method": "structure_aware_partial_ot_complete_gaussian_posterior",
            "strict_zero_shot": True,
            "ground_truth_cd_emd_used": False,
            "category_or_part_rules_used": False,
            "carrier_slots_before": int(len(initial)),
            "carrier_slots_after": int(len(current)),
            "carrier_slots_preserved": bool(len(initial) == len(current)),
            "config": asdict(self.config),
            "stages": stage_records,
            "supported_stable": int(masks["supported_stable"].sum()),
            "supported_stable_final": int(masks["supported_stable_final"].sum()),
            "supported_residual": int(masks["supported_residual"].sum()),
            "unsupported": int(masks["unsupported"].sum()),
            "moved": int(masks["moved"].sum()),
            "hidden_coverage_ratio": final_coverage,
            "hidden_coverage_per_view": final_coverage_views,
            "integrity": integrity,
            "topology_projection": topology_projection,
            "observation_assimilation": assimilation_info,
            "slender_rigidity_projection": slender_rigidity_info,
            "posterior_diagnostics": posterior_diagnostics,
            **final_strain,
        }
        return current, info, masks
