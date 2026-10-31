"""Reference-carrier protection and structure-preserving projections."""

from __future__ import annotations

import math

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from src.deformation_graph import edge_strain, local_surface_graph
from src.robust_similarity import weighted_umeyama

from src.posterior_types import PosteriorAdapterConfig
from src.partial_transport import _median_spacing, _sample_ids
from src.posterior_deformation import (
    _embedded_arap_posterior, _orthographic_coverage,
    _solve_preconditioned,
)


def _project_small_topology_breaks(
    initial: np.ndarray,
    candidate: np.ndarray,
    stable_mask: np.ndarray,
    *,
    neighbours: int,
    edge_ratio: float,
    component_threshold: int,
    maximum_passes: int = 3,
) -> tuple[np.ndarray, dict]:
    """Project accidental tiny fragments back onto their structural motion.

    A sparse Gaussian carrier can contain pre-existing isolated samples.  The
    relevant failure is therefore not the absolute component count, but a
    *new* small fragment split from a previously significant component.  Such
    points inherit the robust displacement of their neighbours in the rest
    graph.  This projection is category- and axis-free and leaves stable
    observations fixed.
    """
    initial = np.asarray(initial, dtype=np.float64)
    projected = np.asarray(candidate, dtype=np.float64).copy()
    stable_mask = np.asarray(stable_mask, dtype=bool)
    rest_graph, _, _ = local_surface_graph(
        initial, neighbours=int(neighbours), edge_ratio=float(edge_ratio),
    )
    input_components, input_labels = csgraph.connected_components(rest_graph, directed=False)
    input_sizes = np.bincount(input_labels, minlength=input_components)
    corrected: set[int] = set()
    trace: list[dict] = []
    for pass_id in range(max(1, int(maximum_passes))):
        output_graph, _, _ = local_surface_graph(
            projected, neighbours=int(neighbours), edge_ratio=float(edge_ratio),
        )
        output_components, output_labels = csgraph.connected_components(output_graph, directed=False)
        output_sizes = np.bincount(output_labels, minlength=output_components)
        bad_components: list[int] = []
        for label, size in enumerate(output_sizes):
            if int(size) >= int(component_threshold):
                continue
            members = np.flatnonzero(output_labels == label)
            if len(members) and np.any(input_sizes[input_labels[members]] >= int(component_threshold)):
                bad_components.append(int(label))
        bad_ids = np.flatnonzero(np.isin(output_labels, bad_components))
        bad_ids = bad_ids[~stable_mask[bad_ids]]
        trace.append({
            "pass": int(pass_id),
            "components_before": int(output_components),
            "new_small_fragment_points": int(len(bad_ids)),
        })
        if not len(bad_ids):
            break
        displacement = projected - initial
        replacement = projected[bad_ids].copy()
        for local, point_id in enumerate(bad_ids):
            start, stop = rest_graph.indptr[point_id], rest_graph.indptr[point_id + 1]
            adjacent = rest_graph.indices[start:stop]
            adjacent = adjacent[~np.isin(adjacent, bad_ids)]
            if not len(adjacent):
                same_component = np.flatnonzero(input_labels == input_labels[point_id])
                same_component = same_component[same_component != point_id]
                if len(same_component):
                    k = min(8, len(same_component))
                    nearest = cKDTree(initial[same_component]).query(initial[point_id], k=k)[1]
                    adjacent = same_component[np.atleast_1d(nearest)]
            if len(adjacent):
                replacement[local] = initial[point_id] + np.median(displacement[adjacent], axis=0)
        projected[bad_ids] = replacement
        corrected.update(int(value) for value in bad_ids)
    projected[stable_mask] = initial[stable_mask]
    return projected, {
        "active": bool(corrected),
        "corrected_points": int(len(corrected)),
        "passes": trace,
    }


def _continue_positive_residual_motion(
    reference: np.ndarray,
    candidate: np.ndarray,
    graph: sparse.csr_matrix,
    support: np.ndarray,
    *,
    hops: int,
) -> tuple[np.ndarray, dict]:
    """Diffuse positive residual motion through a finite rest-graph band.

    The raw posterior proposal can correctly identify a residual extremity,
    yet a soft ARAP projection attenuates its displacement because the full
    carrier contributes many more graph controls.  Here only the *positive*
    residual samples are Dirichlet constraints.  Their raw displacement is
    continued harmonically through a finite neighbourhood, while every point
    outside that band remains a zero-displacement boundary.  Consequently the
    construction is independent of semantic parts and world axes, preserves
    all carrier slots, and cannot drag the entire prior toward the partial.
    """
    reference = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    support = np.asarray(support, dtype=bool)
    if reference.shape != candidate.shape or support.shape != (len(reference),):
        raise ValueError("reference, candidate, and support shapes are inconsistent")
    if int(hops) < 1 or not np.any(support):
        return candidate.copy(), {"active": False, "reason": "empty_support_or_zero_hops"}

    influence = support.copy()
    frontier = support.copy()
    visited = influence.copy()
    for _ in range(int(hops)):
        reached = np.asarray(graph @ frontier.astype(np.float64)).reshape(-1) > 0.
        reached &= ~visited
        if not np.any(reached):
            break
        influence |= reached
        frontier = reached
        visited |= reached
    fixed = support | ~influence
    unknown = np.flatnonzero(~fixed)
    displacement = np.zeros_like(reference)
    displacement[support] = candidate[support] - reference[support]
    if len(unknown):
        degree = np.asarray(graph.sum(axis=1)).reshape(-1)
        laplacian = sparse.diags(degree, format="csr") - graph
        system = laplacian[unknown][:, unknown].tocsr() + sparse.eye(
            len(unknown), format="csr"
        ) * 1e-8
        rhs = -(laplacian[unknown][:, fixed] @ displacement[fixed])
        interpolated, cg_status = _solve_preconditioned(system, rhs)
        displacement[unknown] = interpolated
    else:
        cg_status = [0, 0, 0]
    output = reference + displacement
    return output, {
        "active": True,
        "field": "positive_residual_harmonic_continuation",
        "support_points": int(support.sum()),
        "continuation_points": int(influence.sum()),
        "fixed_boundary_points": int(fixed.sum()),
        "hops": int(hops),
        "cg_status": [int(value) for value in cg_status],
        "maximum_displacement": float(np.linalg.norm(displacement, axis=1).max(initial=0.)),
        "mean_displacement": float(np.linalg.norm(displacement, axis=1).mean()),
    }


def _smooth_positive_motion(
    reference: np.ndarray,
    candidate: np.ndarray,
    graph: sparse.csr_matrix,
    support: np.ndarray,
    *,
    steps: int,
) -> tuple[np.ndarray, dict]:
    """Denoise raw displacement only within positive structural evidence.

    Residual transport can give neighbouring surfels of one physical branch
    slightly inconsistent targets.  Propagating those point-wise offsets
    directly creates artificial edge strain and forces the complete-prior
    guard to suppress an otherwise valid large motion.  A few component-wise
    graph medians remove this correspondence noise without looking at
    categories, semantic parts, axes, or ground truth.  Samples outside the
    positive support are deliberately reset to the reference: they are later
    moved only by the finite harmonic continuation.
    """
    reference = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    support = np.asarray(support, dtype=bool)
    if reference.shape != candidate.shape or support.shape != (len(reference),):
        raise ValueError("reference, candidate, and support shapes are inconsistent")
    if int(steps) < 1 or not np.any(support):
        return candidate.copy(), {"active": False, "reason": "zero_steps_or_empty_support"}

    displacement = np.zeros_like(reference)
    displacement[support] = candidate[support] - reference[support]
    before = displacement.copy()
    for _ in range(int(steps)):
        updated = displacement.copy()
        for point_id in np.flatnonzero(support):
            start, stop = graph.indptr[point_id], graph.indptr[point_id + 1]
            adjacent = graph.indices[start:stop]
            adjacent = adjacent[support[adjacent]]
            if len(adjacent):
                updated[point_id] = np.median(
                    np.vstack((displacement[point_id], displacement[adjacent])), axis=0,
                )
        displacement[support] = updated[support]
    rows, cols = sparse.triu(graph, k=1).nonzero()
    edge_support = support[rows] & support[cols]
    if np.any(edge_support):
        before_jump = np.linalg.norm(before[rows[edge_support]] - before[cols[edge_support]], axis=1)
        after_jump = np.linalg.norm(displacement[rows[edge_support]] - displacement[cols[edge_support]], axis=1)
        edge_info = {
            "edge_count": int(edge_support.sum()),
            "before_p90": float(np.quantile(before_jump, .90)),
            "after_p90": float(np.quantile(after_jump, .90)),
            "before_p99": float(np.quantile(before_jump, .99)),
            "after_p99": float(np.quantile(after_jump, .99)),
        }
    else:
        edge_info = {
            "edge_count": 0, "before_p90": 0., "after_p90": 0.,
            "before_p99": 0., "after_p99": 0.,
        }
    return reference + displacement, {
        "active": True,
        "field": "positive_evidence_graph_median_motion",
        "support_points": int(support.sum()),
        "steps": int(steps),
        "edge_motion": edge_info,
        "maximum_displacement": float(np.linalg.norm(displacement, axis=1).max(initial=0.)),
    }


def _project_positive_components_to_similarity(
    reference: np.ndarray,
    candidate: np.ndarray,
    graph: sparse.csr_matrix,
    support: np.ndarray,
    *,
    core_hops: int = 0,
    gain: float = 1.0,
    connectivity_hops: int = 0,
) -> tuple[np.ndarray, dict, np.ndarray]:
    """Make coherent positive-evidence structures move as proper Sim(3)s.

    The residual field is sampled independently at carrier surfels, although
    a physical appendage, branch, wheel, or limb should usually move as a
    coherent local structure.  We therefore split *only positive structural
    evidence* by rest-graph connectivity and replace a well-explained local
    raw motion by its proper similarity fit.  This is not a part detector:
    components, their fit quality, and their scale are inferred solely from
    the carrier graph and the raw proposal.  Unsupported samples are left to
    the following harmonic continuation.
    """
    reference = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    support = np.asarray(support, dtype=bool)
    if reference.shape != candidate.shape or support.shape != (len(reference),):
        raise ValueError("reference, candidate, and support shapes are inconsistent")
    if float(gain) <= 0.:
        raise ValueError("gain must be positive")
    if int(connectivity_hops) < 0:
        raise ValueError("connectivity_hops must be non-negative")
    ids = np.flatnonzero(support)
    if len(ids) < 16:
        return candidate.copy(), {"active": False, "reason": "insufficient_positive_support"}, support.copy()
    # Sparse OT surfels on the same physical structure are rarely immediate
    # graph neighbours.  Geodesic dilation is used only to establish which
    # positive seeds belong to one region; the similarity is still fitted
    # exclusively on the original observed seeds.
    connected_region = support.copy()
    frontier = support.copy()
    for _ in range(int(connectivity_hops)):
        reached = np.asarray(graph @ frontier.astype(np.float64)).reshape(-1) > 0.
        reached &= ~connected_region
        if not np.any(reached):
            break
        connected_region |= reached
        frontier = reached
    connected_ids = np.flatnonzero(connected_region)
    induced = graph[connected_ids][:, connected_ids]
    component_count, labels = csgraph.connected_components(induced, directed=False)
    spacing = _median_spacing(reference)
    minimum = max(16, int(math.ceil(.00025 * len(reference))))
    output = candidate.copy()
    driver_support = support.copy()
    best_priority = np.full(len(reference), -np.inf, dtype=np.float64)
    records: list[dict] = []
    for component in range(component_count):
        member = connected_ids[labels == component]
        member = member[support[member]]
        if len(member) < minimum:
            continue
        source = reference[member]
        target = candidate[member]
        raw = np.linalg.norm(target - source, axis=1)
        raw_median = float(np.median(raw))
        if raw_median <= float(spacing):
            continue
        try:
            transform = weighted_umeyama(source, target, np.ones(len(member), dtype=np.float64))
        except (np.linalg.LinAlgError, ValueError):
            continue
        predicted = source @ transform[:3, :3].T + transform[:3, 3]
        residual = np.linalg.norm(predicted - target, axis=1)
        residual_median = float(np.median(residual))
        # A component contributes only when one similarity genuinely explains
        # its raw motion better than leaving independent point offsets.  The
        # tolerance is expressed relative to the observed motion and local
        # sampling scale, never in world coordinates.
        if residual_median > max(2.0 * float(spacing), .70 * raw_median):
            continue
        region = np.zeros(len(reference), dtype=bool)
        region[member] = True
        frontier = region.copy()
        for _ in range(int(core_hops)):
            reached = np.asarray(graph @ frontier.astype(np.float64)).reshape(-1) > 0.
            reached &= ~region
            if not np.any(reached):
                break
            region |= reached
            frontier = reached
        region_ids = np.flatnonzero(region)
        linear = transform[:3, :3]
        similarity_scale = float(np.cbrt(np.linalg.det(linear)))
        rotation = linear / max(similarity_scale, 1e-12)
        # Extrapolate one coherent component in Sim(3), rather than scaling
        # independent point displacements.  Rotation, isotropic scale, and
        # centroid translation therefore remain a single proper similarity;
        # the downstream finite continuation supplies the smooth attachment
        # band to the rest of the complete carrier.
        rotation_vector = Rotation.from_matrix(rotation).as_rotvec()
        gained_rotation = Rotation.from_rotvec(float(gain) * rotation_vector).as_matrix()
        gained_scale = float(similarity_scale ** float(gain))
        centre = source.mean(axis=0)
        target_centre = centre @ linear.T + transform[:3, 3]
        gained_centre = centre + float(gain) * (target_centre - centre)
        # Prefer the component whose raw motion is most tightly explained by
        # one similarity in any small overlap.  This preserves distinct local
        # motions without semantic segmentation.
        priority = raw_median / max(residual_median + float(spacing), 1e-12)
        replace = priority > best_priority[region_ids]
        selected = region_ids[replace]
        if len(selected):
            output[selected] = (
                (reference[selected] - centre) @ (gained_scale * gained_rotation).T
                + gained_centre
            )
            best_priority[selected] = priority
            driver_support[selected] = True
        records.append({
            "support_points": int(len(member)),
            "core_points": int(len(region_ids)),
            "raw_motion_median": raw_median,
            "fit_residual_median": residual_median,
            "fit_residual_ratio": float(residual_median / max(raw_median, 1e-12)),
            "similarity_scale": similarity_scale,
            "similarity_gain": float(gain),
            "gained_similarity_scale": gained_scale,
        })
    if not records:
        return candidate.copy(), {
            "active": False,
            "reason": "no_coherent_positive_component",
            "positive_support_points": int(len(ids)),
            "minimum_component_points": int(minimum),
        }, support.copy()
    return output, {
        "active": True,
        "field": "positive_component_proper_sim3_projection",
        "positive_support_points": int(len(ids)),
        "minimum_component_points": int(minimum),
        "components": int(len(records)),
        "component_records": records,
        "projected_points": int(np.isfinite(best_priority).sum()),
        "driver_support_points": int(driver_support.sum()),
        "core_hops": int(core_hops),
        "connectivity_hops": int(connectivity_hops),
        "similarity_gain": float(gain),
    }, driver_support


def _project_residual_coherent_raw_field(
    reference: np.ndarray,
    candidate: np.ndarray,
    graph: sparse.csr_matrix,
    support: np.ndarray,
    *,
    transition_hops: int = 3,
) -> tuple[np.ndarray, dict]:
    """Keep raw deformation only on structures supported by residual evidence.

    A raw posterior step can resolve a distant appendage but also displace a
    broad, weakly observed carrier.  We therefore segment the raw displacement
    field on the rest graph: a region is retained only when its displacement
    is locally continuous *and* it has a higher residual-evidence density than
    the carrier as a whole.  The selected raw field is then feathered through
    a finite rest-graph band.  All quantities are geometric and normalized by
    graph spacing or support density; no category, part, axis, or GT signal is
    involved.
    """
    reference = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    support = np.asarray(support, dtype=bool)
    if reference.shape != candidate.shape or support.shape != (len(reference),):
        raise ValueError("reference, candidate, and support shapes are inconsistent")
    if not np.any(support):
        return reference.copy(), {"active": False, "reason": "empty_support"}
    rows, cols = sparse.triu(graph, k=1).nonzero()
    if len(rows) == 0:
        return reference.copy(), {"active": False, "reason": "empty_graph"}
    displacement = candidate - reference
    edge_change = np.linalg.norm(displacement[rows] - displacement[cols], axis=1)
    rest_length = np.linalg.norm(reference[rows] - reference[cols], axis=1)
    incident = support[rows] | support[cols]
    if not np.any(incident):
        return reference.copy(), {"active": False, "reason": "support_without_graph_incidence"}
    local_threshold = max(
        float(np.quantile(edge_change[incident], .90)),
        1.5 * float(np.median(rest_length[rest_length > 0.])),
    )
    keep = edge_change <= local_threshold
    coherent_graph = sparse.coo_matrix(
        (np.ones(2 * int(keep.sum()), dtype=np.float64),
         (np.r_[rows[keep], cols[keep]], np.r_[cols[keep], rows[keep]])),
        shape=graph.shape,
    ).tocsr()
    component_count, labels = csgraph.connected_components(coherent_graph, directed=False)
    global_density = float(support.mean())
    selected = np.zeros(len(reference), dtype=bool)
    records: list[dict] = []
    for label in range(component_count):
        member = np.flatnonzero(labels == label)
        supported = int(support[member].sum())
        if supported == 0:
            continue
        density = float(supported / max(len(member), 1))
        # A component must be locally better supported than the complete
        # carrier.  This discards broad raw collapse while keeping appendages,
        # repeated limbs, and other compact residual structures.
        if density < max(1.5 * global_density, .005):
            continue
        if len(member) > int(.45 * len(reference)):
            continue
        selected[member] = True
        records.append({
            "points": int(len(member)), "support_points": supported,
            "support_density": density,
        })
    if not np.any(selected):
        return reference.copy(), {
            "active": False, "reason": "no_residual_dense_motion_component",
            "edge_change_threshold": local_threshold,
            "global_support_density": global_density,
        }
    selected_candidate = reference.copy()
    selected_candidate[selected] = candidate[selected]
    continued, continuation = _continue_positive_residual_motion(
        reference, selected_candidate, graph, selected,
        hops=int(transition_hops),
    )
    return continued, {
        "active": bool(continuation.get("active")),
        "field": "residual_coherent_raw_field",
        "edge_change_threshold": float(local_threshold),
        "global_support_density": global_density,
        "selected_points": int(selected.sum()),
        "selected_components": int(len(records)),
        "components": records,
        "continuation": continuation,
    }


def project_reference_carrier_protection(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    neighbours: int,
    edge_ratio: float,
    minimum_hidden_coverage: float,
    maximum_edge_stretch: float,
    coverage_resolution: int,
    minimum_edge_compression: float = .40,
    positive_evidence_mask: np.ndarray | None = None,
    fallback_carrier: np.ndarray | None = None,
    update_reference: np.ndarray | None = None,
    deformation_config: PosteriorAdapterConfig | None = None,
    support_data_weight_scale: float = 1.0,
    support_continuation_hops: int = 0,
    support_hard_target_constraints: bool = False,
    support_coherent_raw_field: bool = False,
    support_local_motion_selection: bool = False,
    support_motion_smoothing_steps: int = 0,
    support_componentwise_similarity: bool = False,
    support_component_similarity_core_hops: int = 0,
    support_component_similarity_gain: float = 1.0,
    support_component_connectivity_hops: int = 0,
) -> tuple[np.ndarray, dict]:
    """Keep an iterative update inside the complete-prior support envelope.

    A posterior update may be locally well supported while several successive
    outer rounds slowly draw the whole carrier into the observed scan.  This
    reference-space line search is deliberately agnostic to category, parts,
    axes, and target labels: it only compares the proposed full carrier with
    the registered full carrier.  The largest continuous update that preserves
    support coverage, graph connectivity, and robust rest-edge strain is kept.
    When positive multi-view evidence is supplied with a deformation config,
    the raw update is first projected through a second embedded ARAP field:
    evidence-supported carrier points retain their raw targets while the
    complement provides complete-prior anchors.  This preserves attachments
    before the global complete-carrier line search, rather than blending point
    displacements independently and introducing artificial cracks.
    """
    reference = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if reference.shape != candidate.shape:
        raise ValueError("reference and candidate carriers must have identical shapes")
    source = reference if update_reference is None else np.asarray(update_reference, dtype=np.float64)
    if source.shape != reference.shape:
        raise ValueError("update_reference must match the reference carrier shape")
    if fallback_carrier is not None and np.asarray(fallback_carrier).shape != reference.shape:
        raise ValueError("fallback_carrier must match reference carrier shape")
    if float(support_data_weight_scale) <= 0.:
        raise ValueError("support_data_weight_scale must be positive")
    if not 0. < float(minimum_edge_compression) <= 1.:
        raise ValueError("minimum_edge_compression must lie in (0, 1]")
    if int(support_continuation_hops) < 0:
        raise ValueError("support_continuation_hops must be non-negative")
    if int(support_motion_smoothing_steps) < 0:
        raise ValueError("support_motion_smoothing_steps must be non-negative")
    if int(support_component_similarity_core_hops) < 0:
        raise ValueError("support_component_similarity_core_hops must be non-negative")
    if int(support_component_connectivity_hops) < 0:
        raise ValueError("support_component_connectivity_hops must be non-negative")
    if float(support_component_similarity_gain) <= 0.:
        raise ValueError("support_component_similarity_gain must be positive")
    if not len(reference):
        return candidate.copy(), {"active": False, "reason": "empty_carrier"}

    # `source` is the carrier re-linearized in the current outer round.  The
    # complete `reference` remains the immutable integrity frame.  This makes
    # successive evidence-supported updates additive without allowing the
    # local update to redefine what counts as a complete object.
    graph, _, _ = local_surface_graph(
        source, neighbours=int(neighbours), edge_ratio=float(edge_ratio),
    )
    guard_graph = graph if update_reference is None else local_surface_graph(
        reference, neighbours=int(neighbours), edge_ratio=float(edge_ratio),
    )[0]
    input_components, input_labels = csgraph.connected_components(guard_graph, directed=False)
    input_sizes = np.bincount(input_labels, minlength=input_components)
    significant_size = max(32, int(math.ceil(.001 * len(reference))))
    input_significant = int(np.sum(input_sizes >= significant_size))
    support = np.zeros(len(reference), dtype=bool)
    if positive_evidence_mask is not None:
        provided = np.asarray(positive_evidence_mask, dtype=bool)
        if provided.shape != support.shape:
            raise ValueError("positive_evidence_mask must match carrier cardinality")
        support = provided
    support_selection: dict = {
        "active": False,
        "source_evidence_points": int(support.sum()),
    }
    if bool(support_local_motion_selection) and np.any(support):
        # Remove the raw proposal's global Sim(3) drift before ranking
        # positive observations by structural motion.  This keeps only
        # appendage/part-scale evidence as deformation targets; static body
        # anchors remain complete-prior boundary conditions.
        sample_ids = _sample_ids(source, min(len(source), 16_384))
        global_transform = weighted_umeyama(
            source[sample_ids], candidate[sample_ids],
            np.ones(len(sample_ids), dtype=np.float64),
        )
        global_candidate = source @ global_transform[:3, :3].T + global_transform[:3, 3]
        local_motion = np.linalg.norm(candidate - global_candidate, axis=1)
        threshold = float(np.quantile(local_motion[support], .70))
        selected = support & (local_motion >= threshold)
        minimum = max(32, int(math.ceil(.001 * len(reference))))
        if int(selected.sum()) >= minimum:
            support = selected
            support_selection = {
                "active": True,
                "method": "sim3_residual_quantile_positive_evidence",
                "source_evidence_points": int(provided.sum()),
                "selected_evidence_points": int(support.sum()),
                "local_motion_threshold": threshold,
                "global_scale": float(np.cbrt(np.linalg.det(global_transform[:3, :3]))),
            }
        else:
            support_selection.update({
                "reason": "insufficient_prominent_local_evidence",
                "selected_evidence_points": int(selected.sum()),
                "local_motion_threshold": threshold,
            })
    # Kept for the topology projection below even when an update has no
    # positive evidence (then every carrier point is a stable reference).
    influence = support.copy()
    support_projection: dict = {"active": False, "reason": "no_positive_evidence"}
    if np.any(support):
        frontier = support.copy()
        visited = influence.copy()
        for _ in range(2):
            reached = np.asarray(graph @ frontier.astype(np.float64)).reshape(-1) > 0.
            reached &= ~visited
            if not np.any(reached):
                break
            influence |= reached
            frontier = reached
            visited |= reached
        if bool(support_coherent_raw_field):
            projected, support_projection = _project_residual_coherent_raw_field(
                source, candidate, graph, support,
            )
            if support_projection.get("active"):
                candidate = projected
        elif int(support_continuation_hops) > 0:
            # Dirichlet continuation applies only the raw update supported by
            # residual transport, then diffuses it through a finite geodesic
            # band of the original carrier.  The full carrier remains present
            # and the outer line search below still enforces coverage and
            # topology.  Unlike a soft global ARAP data term, positive
            # residual anchors keep their observed displacement exactly.
            componentwise, component_projection, continuation_support = _project_positive_components_to_similarity(
                source, candidate, graph, support,
                core_hops=int(support_component_similarity_core_hops),
                gain=float(support_component_similarity_gain),
                connectivity_hops=int(support_component_connectivity_hops),
            ) if bool(support_componentwise_similarity) else (
                candidate, {"active": False, "reason": "disabled"}, support
            )
            smoothed, motion_smoothing = _smooth_positive_motion(
                source, componentwise, graph, continuation_support,
                steps=int(support_motion_smoothing_steps),
            )
            candidate, support_projection = _continue_positive_residual_motion(
                source, smoothed, graph, continuation_support,
                hops=int(support_continuation_hops),
            )
            support_projection["motion_smoothing"] = motion_smoothing
            support_projection["componentwise_similarity"] = component_projection
        elif deformation_config is not None:
            diagonal = max(float(np.linalg.norm(np.ptp(source, axis=0))), 1e-9)
            projected, support_projection, _ = _embedded_arap_posterior(
                source,
                np.flatnonzero(support),
                candidate[support],
                np.ones(int(support.sum()), dtype=np.float64),
                ~influence,
                node_fraction=float(deformation_config.fine_node_fraction),
                minimum_nodes=int(deformation_config.minimum_graph_nodes),
                maximum_nodes=int(deformation_config.maximum_graph_nodes),
                skinning_neighbours=int(deformation_config.skinning_neighbours),
                neighbours=int(deformation_config.fine_neighbours),
                edge_ratio=float(deformation_config.fine_edge_ratio),
                attachment_edge_ratio=float(deformation_config.attachment_edge_ratio),
                data_weight=(
                    float(deformation_config.assimilation_data_weight)
                    * float(support_data_weight_scale)
                ),
                screening=float(deformation_config.assimilation_screening),
                bending_regularization=float(deformation_config.bending_regularization),
                iterations=int(deformation_config.assimilation_iterations),
                maximum_displacement=(
                    float(deformation_config.coarse_displacement_ratio) * diagonal
                ),
                minimum_improvement=max(
                    .25 * float(deformation_config.minimum_observed_improvement), .0025,
                ),
                minimum_edge_compression=float(deformation_config.minimum_edge_compression),
                maximum_edge_stretch=float(deformation_config.maximum_edge_stretch),
                minimum_hidden_coverage=float(deformation_config.minimum_hidden_coverage),
                coverage_resolution=int(deformation_config.coverage_resolution),
                # A hard constraint is meaningful only for a locally
                # consistent residual component.  Coherently regularizing
                # its raw displacement removes conflicting pointwise targets
                # while retaining distinct motions of separate structures.
                coherent_component_targets=bool(support_hard_target_constraints),
                preserve_target_amplitude=True,
                hard_target_constraints=bool(support_hard_target_constraints),
            )
            if support_projection.get("active"):
                candidate = projected
            support_projection["data_weight_scale"] = float(support_data_weight_scale)
    trace: list[dict] = []
    for alpha in (1.0, .90, .80, .70, .60, .50, .40, .30, .20, .10, .05):
        proposal = source + float(alpha) * (candidate - source)
        # A spatially local, evidence-driven update can detach a handful of
        # sparse carrier samples at a branch boundary even though the only
        # significant component remains intact.  Rejecting the entire update
        # in that case unnecessarily attenuates the observed structural
        # motion.  Reattach only those new *non-significant* fragments in the
        # rest graph before evaluating the complete-prior constraints.  The
        # operation is category-, axis-, and target-label-free: fragments
        # inherit the robust displacement of their connected reference
        # neighbourhood while stable carrier points remain fixed.
        topology_repair: dict = {"active": False, "reason": "no_local_evidence"}
        if np.any(influence):
            proposal, topology_repair = _project_small_topology_breaks(
                source,
                proposal,
                ~influence,
                neighbours=int(neighbours),
                edge_ratio=float(edge_ratio),
                component_threshold=int(significant_size),
            )
        coverage, coverage_views = _orthographic_coverage(
            reference, proposal, resolution=int(coverage_resolution),
        )
        proposal_graph, _, _ = local_surface_graph(
            proposal, neighbours=int(neighbours), edge_ratio=float(edge_ratio),
        )
        components, labels = csgraph.connected_components(proposal_graph, directed=False)
        sizes = np.bincount(labels, minlength=components)
        significant = int(np.sum(sizes >= significant_size))
        strain = edge_strain(reference, proposal, guard_graph)
        record = {
            "alpha": float(alpha),
            "hidden_coverage_ratio": float(coverage),
            "hidden_coverage_per_view": coverage_views,
            "input_components": int(input_components),
            "output_components": int(components),
            "input_significant_components": int(input_significant),
            "output_significant_components": int(significant),
            "positive_evidence_points": int(support.sum()),
            "positive_evidence_halo_points": int(influence.sum()) if np.any(support) else 0,
            "topology_repair": topology_repair,
            **strain,
        }
        trace.append(record)
        if (
            coverage >= float(minimum_hidden_coverage)
            and significant <= input_significant
            and strain["edge_stretch_p01"] >= float(minimum_edge_compression)
            and strain["edge_stretch_p99"] <= float(maximum_edge_stretch)
        ):
            return proposal, {
                "active": bool(alpha < 1.0),
                "accepted": True,
                "method": "reference_complete_carrier_protection",
                "incremental_update": bool(update_reference is not None),
                "line_search": trace,
                "support_projection": support_projection,
                "support_selection": support_selection,
                **record,
            }
    retained = reference if fallback_carrier is None else np.asarray(fallback_carrier, dtype=np.float64)
    return retained.copy(), {
        "active": True,
        "accepted": False,
        "reason": "no_complete_carrier_safe_increment",
        "method": "reference_complete_carrier_protection",
        "fallback_retained": bool(fallback_carrier is not None),
        "line_search": trace,
        "support_projection": support_projection,
        "support_selection": support_selection,
    }


def _compact_visible_score(score: dict) -> dict:
    projection = score["projection"]
    geometric = score["geometric"]
    return {
        "objective": float(score["objective"]),
        "visible_3d": float(geometric["objective"]),
        "visible_pair_count": int(len(geometric["partial_ids"])),
        "silhouette_iou": float(projection["iou"]),
        "coverage": float(projection["coverage"]),
        "leakage": float(projection["leakage"]),
        "depth_error_normalized": float(projection["visible_depth_normalized"]),
    }


def _project_slender_regions_rigid(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    neighbours: int,
    linearity_quantile: float,
    minimum_fraction: float,
    minimum_aspect_ratio: float,
    dilation_steps: int,
    graph_neighbours: int,
    graph_edge_ratio: float,
) -> tuple[np.ndarray, dict, np.ndarray]:
    """Remove bending from automatically detected elongated structures.

    The detector uses only local covariance anisotropy and graph connectivity.
    Each sufficiently long region is projected onto the proper rigid motion
    that best explains its unconstrained deformation.  Graph dilation blends
    that correction into neighbouring carrier points, preserving attachments
    without any category, part label, or world-axis convention.
    """
    reference = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    count = len(reference)
    if count < max(32, int(neighbours)):
        return candidate.copy(), {"active": False, "reason": "insufficient_points"}, np.zeros(count, dtype=bool)

    tree = cKDTree(reference)
    query_k = min(int(neighbours), count)
    linearity = np.empty(count, dtype=np.float64)
    principal_direction = np.empty((count, 3), dtype=np.float64)
    chunk = 4_096
    for start in range(0, count, chunk):
        stop = min(start + chunk, count)
        _, local_ids = tree.query(reference[start:stop], k=query_k, workers=-1)
        local = reference[np.asarray(local_ids, dtype=np.int64)]
        local = local - local.mean(axis=1, keepdims=True)
        covariance = np.einsum("nki,nkj->nij", local, local) / max(query_k - 1, 1)
        values, vectors = np.linalg.eigh(covariance)
        linearity[start:stop] = (values[:, -1] - values[:, -2]) / np.maximum(values[:, -1], 1e-12)
        principal_direction[start:stop] = vectors[:, :, -1]

    threshold = float(np.quantile(linearity, float(linearity_quantile)))
    propagation_threshold = float(np.quantile(linearity, .65))
    high_linearity = np.flatnonzero(linearity >= threshold)
    minimum_points = max(64, int(math.ceil(float(minimum_fraction) * count)))
    if len(high_linearity) < minimum_points:
        return candidate.copy(), {
            "active": False, "reason": "insufficient_high_linearity_support",
            "linearity_threshold": threshold, "high_linearity_points": int(len(high_linearity)),
        }, np.zeros(count, dtype=bool)

    slender_points = reference[high_linearity]
    slender_tree = cKDTree(slender_points)
    cluster_k = min(8, len(slender_points))
    distances, indices = slender_tree.query(slender_points, k=cluster_k, workers=-1)
    if cluster_k == 1:
        return candidate.copy(), {"active": False, "reason": "singleton_linearity_support"}, np.zeros(count, dtype=bool)
    spacing = max(float(np.median(distances[:, 1])), 1e-12)
    rows = np.repeat(np.arange(len(slender_points), dtype=np.int64), cluster_k - 1)
    cols = np.asarray(indices[:, 1:], dtype=np.int64).reshape(-1)
    lengths = np.asarray(distances[:, 1:], dtype=np.float64).reshape(-1)
    keep = (rows < cols) & (lengths <= 3.0 * spacing)
    component_graph = sparse.coo_matrix(
        (np.ones(2 * int(keep.sum())), (
            np.r_[rows[keep], cols[keep]], np.r_[cols[keep], rows[keep]],
        )),
        shape=(len(slender_points), len(slender_points)),
    ).tocsr()
    component_count, labels = csgraph.connected_components(component_graph, directed=False)

    surface_graph, _, _ = local_surface_graph(
        reference, neighbours=int(graph_neighbours), edge_ratio=float(graph_edge_ratio),
    )
    best_correction = np.zeros_like(reference)
    best_weight = np.zeros(count, dtype=np.float64)
    best_priority = np.full(count, -np.inf, dtype=np.float64)
    rigid_mask = np.zeros(count, dtype=bool)
    records: list[dict] = []
    for component in range(component_count):
        member_local = np.flatnonzero(labels == component)
        if len(member_local) < minimum_points:
            continue
        member = high_linearity[member_local]
        source = reference[member]
        centre = source.mean(axis=0)
        _, _, basis = np.linalg.svd(source - centre, full_matrices=False)
        extent = np.ptp((source - centre) @ basis.T, axis=0)
        aspect = float(extent[0] / max(extent[1], 1e-12))
        if aspect < float(minimum_aspect_ratio):
            continue

        source_centre = source.mean(axis=0)
        target = candidate[member]
        target_centre = target.mean(axis=0)
        left, _, right = np.linalg.svd((source - source_centre).T @ (target - target_centre))
        rotation = right.T @ left.T
        if np.linalg.det(rotation) < 0.:
            right[-1] *= -1.
            rotation = right.T @ left.T

        # Recover the complete surface by propagating through points whose
        # local principal direction agrees with the detected structure.  This
        # reaches the blade/rod surface but stops at a differently oriented
        # body or hub, unlike a broad oriented bounding box.
        local_all = (reference - centre) @ basis.T
        local_member = local_all[member]
        lower, upper = local_member.min(axis=0), local_member.max(axis=0)
        member_extent = np.maximum(upper - lower, 1e-12)
        diagonal = max(float(np.linalg.norm(np.ptp(reference, axis=0))), 1e-12)
        longitudinal = (
            (local_all[:, 0] >= lower[0] - .08 * member_extent[0])
            & (local_all[:, 0] <= upper[0] + .08 * member_extent[0])
        )
        radial_limit = max(
            1.25 * float(np.quantile(np.linalg.norm(local_member[:, 1:], axis=1), .99)),
            .006 * diagonal,
        )
        direction_agreement = np.abs(principal_direction @ basis[0])
        allowed = (
            longitudinal
            & (np.linalg.norm(local_all[:, 1:], axis=1) <= radial_limit)
            & (linearity >= propagation_threshold)
            & (direction_agreement >= .72)
        )
        allowed[member] = True
        core = np.zeros(count, dtype=bool)
        frontier = np.zeros(count, dtype=bool)
        core[member] = True
        frontier[member] = True
        for _ in range(32):
            reached = np.asarray(surface_graph @ frontier.astype(np.float64)).reshape(-1) > 0.
            reached &= allowed & ~core
            if not np.any(reached):
                break
            core |= reached
            frontier = reached

        weight = np.zeros(count, dtype=np.float64)
        frontier = core.copy()
        weight[core] = 1.0
        visited = frontier.copy()
        for step in range(int(dilation_steps)):
            reached = np.asarray(surface_graph @ frontier.astype(np.float64)).reshape(-1) > 0.
            reached &= ~visited
            if not np.any(reached):
                break
            weight[reached] = max(weight[reached].max(initial=0.), (dilation_steps - step) / (dilation_steps + 1.0))
            visited |= reached
            frontier = reached
        region = np.flatnonzero(weight > 0.)
        rigid = (reference[region] - source_centre) @ rotation.T + target_centre
        correction = rigid - candidate[region]
        nearest_seed = cKDTree(source).query(reference[region], k=1, workers=-1)[0]
        seed_spacing = max(_median_spacing(source), 1e-12)
        priority = weight[region] / (.25 + nearest_seed / seed_spacing)
        replace = priority > best_priority[region]
        selected = region[replace]
        best_priority[selected] = priority[replace]
        best_weight[selected] = weight[selected]
        best_correction[selected] = correction[replace]
        rigid_mask[region] = True
        records.append({
            "seed_points": int(len(member)), "rigid_core_points": int(core.sum()),
            "projected_points": int(len(region)),
            "aspect_ratio": aspect, "principal_extent": extent.tolist(),
            "mean_correction": float(np.linalg.norm(correction, axis=1).mean()),
            "maximum_correction": float(np.linalg.norm(correction, axis=1).max(initial=0.)),
        })

    if not records:
        return candidate.copy(), {
            "active": False, "reason": "no_elongated_component",
            "linearity_threshold": threshold, "high_linearity_points": int(len(high_linearity)),
        }, rigid_mask
    output = candidate.copy()
    active = best_weight > 0.
    output[active] += best_weight[active, None] * best_correction[active]
    return output, {
        "active": True,
        "method": "covariance_detected_slender_region_se3_projection",
        "linearity_threshold": threshold,
        "high_linearity_points": int(len(high_linearity)),
        "projected_components": int(len(records)),
        "projected_points": int(active.sum()),
        "components": records,
    }, active
