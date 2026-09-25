"""Complete-carrier embedded deformation and topology primitives."""

from __future__ import annotations

import math

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.sparse import linalg as sparse_linalg
from scipy.spatial import cKDTree

from src.deformation_graph import edge_strain, local_surface_graph

from src.partial_transport import _median_spacing, _sample_ids


def _augment_attachment_edges(graph: sparse.csr_matrix, metric: sparse.csr_matrix,
                              points: np.ndarray, *, edge_ratio: float) -> tuple[sparse.csr_matrix, sparse.csr_matrix, int]:
    """Join near-contact components with small, rotation-carrying edge bundles.

    Surface sampling can leave a visually attached thin part disconnected from
    the deformation graph.  A single bridge only transfers translation and
    behaves like a hinge; a short bundle of nearby bridges also transfers the
    local rigid rotation.  Candidate bridges are determined solely by rest
    geometry and local point spacing.
    """
    component_count, labels = csgraph.connected_components(graph, directed=False)
    if component_count <= 1:
        return graph, metric, 0
    points = np.asarray(points, dtype=np.float64)
    query_k = min(32, len(points))
    distances, neighbours = cKDTree(points).query(points, k=query_k, workers=-1)
    local_scale = np.median(distances[:, 1:min(query_k, 9)], axis=1)
    candidates_by_components: dict[tuple[int, int], dict[tuple[int, int], float]] = {}

    def add_candidate(distance: float, source: int, target: int) -> None:
        if source == target:
            return
        source, target = sorted((int(source), int(target)))
        left, right = sorted((int(labels[source]), int(labels[target])))
        if left == right:
            return
        group = candidates_by_components.setdefault((left, right), {})
        pair = (source, target)
        group[pair] = min(float(distance), group.get(pair, np.inf))

    for column in range(1, query_k):
        other = neighbours[:, column]
        cross = labels != labels[other]
        allowed = distances[:, column] <= float(edge_ratio) * np.sqrt(
            np.maximum(local_scale * local_scale[other], 1e-18)
        )
        for source in np.flatnonzero(cross & allowed):
            target = int(other[source])
            add_candidate(float(distances[source, column]), int(source), target)

    # Dense components may have more than ``query_k`` same-component
    # neighbours, hiding a nearby attachment from the global k-NN query.  Find
    # the exact nearest boundary pairs for geometrically plausible component
    # pairs.  This is cheap because generated object priors normally contain
    # only a handful of components and we query the smaller one against the
    # larger one.
    component_ids = [np.flatnonzero(labels == label) for label in range(component_count)]
    component_scale = np.asarray([
        np.median(local_scale[ids][local_scale[ids] > 0.])
        if np.any(local_scale[ids] > 0.) else np.inf
        for ids in component_ids
    ], dtype=np.float64)
    lower = np.asarray([points[ids].min(axis=0) for ids in component_ids])
    upper = np.asarray([points[ids].max(axis=0) for ids in component_ids])
    for left in range(component_count):
        for right in range(left + 1, component_count):
            pair_scale = math.sqrt(max(component_scale[left] * component_scale[right], 1e-18))
            threshold = float(edge_ratio) * pair_scale
            bbox_gap = np.maximum(np.maximum(lower[left] - upper[right], lower[right] - upper[left]), 0.)
            if float(np.linalg.norm(bbox_gap)) > threshold:
                continue
            left_ids, right_ids = component_ids[left], component_ids[right]
            if len(left_ids) <= len(right_ids):
                query_ids, reference_ids = left_ids, right_ids
            else:
                query_ids, reference_ids = right_ids, left_ids
            pair_distance, pair_neighbour = cKDTree(points[reference_ids]).query(
                points[query_ids], k=1, workers=-1,
            )
            pair_target = reference_ids[np.asarray(pair_neighbour, dtype=np.int64)]
            pair_limit = float(edge_ratio) * np.sqrt(np.maximum(
                local_scale[query_ids] * local_scale[pair_target], 1e-18,
            ))
            valid = np.flatnonzero(np.asarray(pair_distance) <= pair_limit)
            if len(valid) == 0:
                continue
            # More than three nearby rest-space constraints makes the bridge
            # rotation-carrying instead of hinge-like.  Keep a few extras for
            # sparse or nearly collinear thin structures.
            order = valid[np.argsort(np.asarray(pair_distance)[valid])[:32]]
            for item in order:
                add_candidate(
                    float(pair_distance[item]), int(query_ids[item]), int(pair_target[item]),
                )

    component_candidates: list[tuple[float, int, int]] = []
    for (left, right), group in candidates_by_components.items():
        if group:
            component_candidates.append((min(group.values()), left, right))
    component_candidates.sort()
    parent = np.arange(component_count, dtype=np.int64)

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = int(parent[value])
        return value

    accepted_component_pairs: list[tuple[int, int]] = []
    for _, source_component, target_component in component_candidates:
        left, right = find(source_component), find(target_component)
        if left == right:
            continue
        parent[right] = left
        accepted_component_pairs.append(tuple(sorted((source_component, target_component))))

    accepted: list[tuple[float, int, int]] = []
    for component_pair in accepted_component_pairs:
        ranked = sorted(
            (distance, source, target)
            for (source, target), distance in candidates_by_components[component_pair].items()
        )
        used_source: set[int] = set()
        used_target: set[int] = set()
        bundle: list[tuple[float, int, int]] = []
        for distance, source, target in ranked:
            # Prefer spatially distinct endpoints so the attachment carries a
            # local rotation.  If the contact has fewer unique samples, the
            # nearest bridge below still preserves connectivity.
            if source in used_source or target in used_target:
                continue
            bundle.append((distance, source, target))
            used_source.add(source)
            used_target.add(target)
            if len(bundle) == 6:
                break
        if not bundle and ranked:
            bundle.append(ranked[0])
        accepted.extend(bundle)
    if not accepted:
        return graph, metric, 0
    source = np.asarray([row[1] for row in accepted], dtype=np.int64)
    target = np.asarray([row[2] for row in accepted], dtype=np.int64)
    distance = np.asarray([row[0] for row in accepted], dtype=np.float64)
    scale = np.sqrt(np.maximum(local_scale[source] * local_scale[target], 1e-18))
    weight = .25 * np.exp(-np.square(distance / np.maximum(scale, 1e-12)))
    attachment_graph = sparse.coo_matrix(
        (np.r_[weight, weight], (np.r_[source, target], np.r_[target, source])), shape=graph.shape,
    ).tocsr()
    attachment_metric = sparse.coo_matrix(
        (np.r_[distance, distance], (np.r_[source, target], np.r_[target, source])), shape=metric.shape,
    ).tocsr()
    return (graph + attachment_graph).tocsr(), (metric + attachment_metric).tocsr(), int(len(accepted))


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    values, weights = np.asarray(values), np.asarray(weights)
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order[np.searchsorted(cumulative, .5 * cumulative[-1], side="left")]])


def _coherent_targets(source: np.ndarray, target: np.ndarray, *, diagonal: float) -> tuple[np.ndarray, dict]:
    """Replace pointwise residuals by robust local component motion.

    Partial transport establishes *where* positive support exists.  A coarse
    deformation should not turn each transported sample into an independent
    pin, because that creates spikes and tears.  Connected observations with
    compatible displacement instead vote for one robust motion, irrespective
    of class or semantic part.
    """
    source, target = np.asarray(source), np.asarray(target)
    if len(source) < 8:
        return target.copy(), {"components": 0, "regularized_targets": 0}
    spacing = _median_spacing(target)
    radius = max(4.0 * spacing, .015 * float(diagonal))
    edges = cKDTree(target).query_pairs(radius, output_type="ndarray")
    if len(edges):
        graph = sparse.coo_matrix(
            (np.ones(2 * len(edges)), (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
            shape=(len(target), len(target)),
        ).tocsr()
        count, labels = csgraph.connected_components(graph, directed=False)
    else:
        count, labels = len(target), np.arange(len(target), dtype=np.int64)
    residual = target - source
    result = target.copy()
    records: list[dict] = []
    minimum = max(8, int(math.ceil(.01 * len(target))))
    regularized = 0
    for component in range(count):
        member = np.flatnonzero(labels == component)
        if len(member) < minimum:
            continue
        median = np.median(residual[member], axis=0)
        magnitude = float(np.linalg.norm(median))
        if magnitude <= 1e-12:
            continue
        coherence = float(np.mean((residual[member] @ median) / np.maximum(
            np.linalg.norm(residual[member], axis=1) * magnitude, 1e-12,
        )))
        if coherence < .20:
            continue
        result[member] = source[member] + median
        regularized += len(member)
        records.append({
            "points": int(len(member)), "median_residual": median.tolist(),
            "median_residual_norm": magnitude, "directional_coherence": coherence,
        })
    return result, {
        "component_radius": radius, "minimum_component_points": minimum,
        "components": int(len(records)), "regularized_targets": int(regularized),
        "component_records": records,
    }


def _solve_preconditioned(matrix: sparse.csr_matrix, rhs: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Jacobi-preconditioned CG for the full 100k-carrier system."""
    inverse_diagonal = 1. / np.maximum(np.asarray(matrix.diagonal()).reshape(-1), 1e-12)
    preconditioner = sparse.diags(inverse_diagonal, format="csr")
    result = np.zeros_like(rhs, dtype=np.float64)
    status: list[int] = []
    for axis in range(rhs.shape[1]):
        try:
            value, code = sparse_linalg.cg(
                matrix, rhs[:, axis], M=preconditioner, rtol=2e-6, atol=0., maxiter=900,
            )
        except TypeError:
            value, code = sparse_linalg.cg(
                matrix, rhs[:, axis], M=preconditioner, tol=2e-6, maxiter=900,
            )
        result[:, axis] = value
        status.append(int(code))
    return result, status


def _orthographic_coverage(reference: np.ndarray, candidate: np.ndarray, *, resolution: int) -> tuple[float, list[float]]:
    """Measure fixed-frame support retention in six signed PCA views."""
    reference, candidate = np.asarray(reference), np.asarray(candidate)
    centre = reference.mean(axis=0, keepdims=True)
    _, _, basis = np.linalg.svd(reference - centre, full_matrices=False)
    ref_coordinates = (reference - centre) @ basis.T
    candidate_coordinates = (candidate - centre) @ basis.T
    combined = np.concatenate((ref_coordinates, candidate_coordinates), axis=0)
    ratios: list[float] = []
    for depth_axis in range(3):
        planar = [axis for axis in range(3) if axis != depth_axis]
        lower, upper = np.quantile(combined[:, planar], [.005, .995], axis=0)
        extent = np.maximum(upper - lower, 1e-9)
        occupied: list[int] = []
        for coordinates in (ref_coordinates, candidate_coordinates):
            uv = np.floor((coordinates[:, planar] - lower) / extent * (int(resolution) - 1)).astype(np.int64)
            valid = ((uv >= 0) & (uv < int(resolution))).all(axis=1)
            key = uv[valid, 0] * int(resolution) + uv[valid, 1]
            occupied.append(int(len(np.unique(key))))
        ratios.append(float(occupied[1] / max(occupied[0], 1)))
    return float(min(ratios, default=1.)), ratios


def _soft_full_surface_arap(
    prior: np.ndarray,
    target_ids: np.ndarray,
    targets: np.ndarray,
    target_weights: np.ndarray,
    stable_mask: np.ndarray,
    *,
    neighbours: int,
    edge_ratio: float,
    attachment_edge_ratio: float,
    data_weight: float,
    screening: float,
    iterations: int,
    maximum_displacement: float,
    minimum_improvement: float,
    minimum_edge_compression: float,
    maximum_edge_stretch: float,
    minimum_hidden_coverage: float,
    coverage_resolution: int,
    coherent_component_targets: bool,
    bending_regularization: float = 0.0,
    hard_target_constraints: bool = False,
) -> tuple[np.ndarray, dict, np.ndarray]:
    """Fit soft observations while ARAP propagates motion over complete support."""
    prior = np.asarray(prior, dtype=np.float64)
    target_ids = np.asarray(target_ids, dtype=np.int64)
    targets = np.asarray(targets, dtype=np.float64)
    target_weights = np.asarray(target_weights, dtype=np.float64)
    stable_mask = np.asarray(stable_mask, dtype=bool)
    graph, metric, original_edges = local_surface_graph(prior, neighbours=int(neighbours), edge_ratio=float(edge_ratio))
    graph, metric, attachment_edges = _augment_attachment_edges(
        graph, metric, prior, edge_ratio=float(attachment_edge_ratio),
    )
    if graph.nnz == 0 or len(target_ids) == 0:
        return prior.copy(), {"active": False, "reason": "empty_graph_or_targets"}, np.zeros(len(prior), dtype=bool)
    target_ids_unique, inverse = np.unique(target_ids, return_inverse=True)
    target_sum = np.zeros((len(target_ids_unique), 3), dtype=np.float64)
    weight_sum = np.zeros(len(target_ids_unique), dtype=np.float64)
    np.add.at(target_sum, inverse, targets * target_weights[:, None])
    np.add.at(weight_sum, inverse, target_weights)
    targets_unique = target_sum / np.maximum(weight_sum[:, None], 1e-12)
    weights_unique = weight_sum / max(float(np.median(weight_sum[weight_sum > 0.])), 1e-12)
    keep = ~stable_mask[target_ids_unique]
    target_ids_unique, targets_unique, weights_unique = (
        target_ids_unique[keep], targets_unique[keep], weights_unique[keep]
    )
    if len(target_ids_unique) == 0:
        return prior.copy(), {"active": False, "reason": "all_transport_targets_are_stable"}, np.zeros(len(prior), dtype=bool)
    coherence_info = {"components": 0, "regularized_targets": 0}
    if bool(coherent_component_targets):
        diagonal = max(float(np.linalg.norm(np.ptp(np.concatenate((prior, targets_unique), axis=0), axis=0))), 1e-9)
        targets_unique, coherence_info = _coherent_targets(
            prior[target_ids_unique], targets_unique, diagonal=diagonal,
        )
    initial_residual = np.linalg.norm(prior[target_ids_unique] - targets_unique, axis=1)
    degree = np.asarray(graph.sum(axis=1)).reshape(-1)
    laplacian = sparse.diags(degree, format="csr") - graph
    # Standard posterior updates keep transported samples soft.  The optional
    # hard mode is reserved for verified residual evidence in the
    # reference-carrier projection, so a small supported structure is not
    # diluted by the much larger unobserved carrier.
    fixed_mask = stable_mask.copy()
    if bool(hard_target_constraints):
        fixed_mask[target_ids_unique] = True
    fixed_ids = np.flatnonzero(fixed_mask)
    unknown = np.flatnonzero(~fixed_mask)
    fixed_positions = prior.copy()
    if bool(hard_target_constraints):
        fixed_positions[target_ids_unique] = targets_unique
    lookup = np.full(len(prior), -1, dtype=np.int64)
    lookup[unknown] = np.arange(len(unknown), dtype=np.int64)
    local_targets = lookup[target_ids_unique]
    soft_target = local_targets >= 0
    data_diagonal = np.zeros(len(unknown), dtype=np.float64)
    effective_data_weight = float(data_weight) * max(float(np.median(degree[degree > 0.])), 1e-6)
    if np.any(soft_target):
        np.add.at(
            data_diagonal, local_targets[soft_target],
            effective_data_weight * weights_unique[soft_target],
        )
    system = laplacian[unknown][:, unknown].tocsr() + sparse.diags(
        np.full(len(unknown), float(screening)) + data_diagonal, format="csr",
    )
    bending_system = None
    bending_laplacian_unknown = None
    bending_fixed_term = None
    bending_rest_coordinates = None
    bending_factor = 0.0
    if float(bending_regularization) > 0.:
        # Preserve differential coordinates in each point's *co-rotating*
        # frame.  A world-frame biharmonic term prevents bending but also
        # incorrectly locks an unsupported thin structure to its old
        # orientation.  Rotating the rest differential coordinates with the
        # ARAP frame keeps the anti-bending effect while allowing a connected
        # structure to inherit rigid motion from observed neighbours.
        laplacian_unknown = laplacian[:, unknown].tocsr()
        bending_system = (laplacian_unknown.T @ laplacian_unknown).tocsr()
        median_degree = max(float(np.median(degree[degree > 0.])), 1e-6)
        bending_factor = float(bending_regularization) / median_degree
        bending_system *= bending_factor
        system = (system + bending_system).tocsr()
        bending_laplacian_unknown = laplacian_unknown
        bending_rest_coordinates = laplacian @ prior
        bending_fixed_term = (
            laplacian[:, fixed_ids] @ fixed_positions[fixed_ids]
            if len(fixed_ids) else np.zeros_like(prior)
        )
    rows, cols = sparse.triu(graph, k=1).nonzero()
    edge_weight = np.asarray(graph[rows, cols]).reshape(-1)
    rest_edge = prior[rows] - prior[cols]
    deformed = prior.copy()
    rotations = np.broadcast_to(np.eye(3), (len(prior), 3, 3)).copy()
    cg_status: list[int] = [0, 0, 0]
    for _ in range(int(iterations)):
        deformed_edge = deformed[rows] - deformed[cols]
        covariance = np.zeros((len(prior), 3, 3), dtype=np.float64)
        contribution = edge_weight[:, None, None] * np.einsum("ni,nj->nij", deformed_edge, rest_edge)
        np.add.at(covariance, rows, contribution)
        np.add.at(covariance, cols, contribution)
        active = np.flatnonzero(~fixed_mask)
        left, _, right = np.linalg.svd(covariance[active], full_matrices=False)
        local_rotation = left @ right
        reflected = np.linalg.det(local_rotation) < 0.
        if np.any(reflected):
            left[reflected, :, -1] *= -1.
            local_rotation = left @ right
        rotations[active] = local_rotation
        desired = np.einsum("nij,nj->ni", .5 * (rotations[rows] + rotations[cols]), rest_edge)
        rhs = np.zeros((len(prior), 3), dtype=np.float64)
        np.add.at(rhs, rows, edge_weight[:, None] * desired)
        np.add.at(rhs, cols, -edge_weight[:, None] * desired)
        rhs_unknown = rhs[unknown] + float(screening) * prior[unknown]
        if bending_system is not None:
            rotated_rest_coordinates = np.einsum(
                "nij,nj->ni", rotations, bending_rest_coordinates,
            )
            bending_target = rotated_rest_coordinates - bending_fixed_term
            rhs_unknown += bending_factor * (
                bending_laplacian_unknown.T @ bending_target
            )
        if np.any(soft_target):
            np.add.at(
                rhs_unknown, local_targets[soft_target],
                (effective_data_weight * weights_unique[soft_target])[:, None]
                * targets_unique[soft_target],
            )
        if len(fixed_ids):
            rhs_unknown -= laplacian[unknown][:, fixed_ids] @ fixed_positions[fixed_ids]
        solution, cg_status = _solve_preconditioned(system, rhs_unknown)
        displacement = solution - prior[unknown]
        length = np.linalg.norm(displacement, axis=1, keepdims=True)
        displacement *= np.minimum(1., float(maximum_displacement) / np.maximum(length, 1e-12))
        deformed[unknown] = prior[unknown] + displacement
        deformed[fixed_ids] = fixed_positions[fixed_ids]

    accepted = None
    best_improvement = -np.inf
    last: dict | None = None
    trace: list[dict] = []
    for alpha in (1., .85, .70, .55, .40, .25, .15):
        candidate = prior + float(alpha) * (deformed - prior)
        candidate[stable_mask] = prior[stable_mask]
        if bool(hard_target_constraints):
            candidate[target_ids_unique] = targets_unique
        after = np.linalg.norm(candidate[target_ids_unique] - targets_unique, axis=1)
        before_median = _weighted_median(initial_residual, weights_unique)
        after_median = _weighted_median(after, weights_unique)
        improvement = 1. - after_median / max(before_median, 1e-12)
        strain = edge_strain(prior, candidate, graph)
        coverage, per_view = _orthographic_coverage(prior, candidate, resolution=int(coverage_resolution))
        effective_graph = graph.copy().tolil()
        edge_ratio_now = np.linalg.norm(candidate[rows] - candidate[cols], axis=1) / np.maximum(
            np.linalg.norm(prior[rows] - prior[cols], axis=1), 1e-12,
        )
        broken = edge_ratio_now > float(maximum_edge_stretch)
        if np.any(broken):
            effective_graph[rows[broken], cols[broken]] = 0.; effective_graph[cols[broken], rows[broken]] = 0.
        candidate_components, candidate_labels = csgraph.connected_components(effective_graph.tocsr(), directed=False)
        original_components, original_labels = csgraph.connected_components(graph, directed=False)
        significant_size = max(32, int(math.ceil(.001 * len(prior))))
        candidate_sizes = np.bincount(candidate_labels, minlength=candidate_components)
        original_sizes = np.bincount(original_labels, minlength=original_components)
        candidate_significant = int(np.sum(candidate_sizes >= significant_size))
        original_significant = int(np.sum(original_sizes >= significant_size))
        candidate_small_mass = int(candidate_sizes[candidate_sizes < significant_size].sum())
        last = {
            "alpha": float(alpha), "observed_residual_before": before_median,
            "observed_residual_after": after_median, "observed_improvement": float(improvement),
            "hidden_coverage_ratio": coverage, "hidden_coverage_per_view": per_view,
            "original_graph_components": int(original_components),
            "candidate_graph_components": int(candidate_components), **strain,
            "significant_component_size": int(significant_size),
            "original_significant_components": original_significant,
            "candidate_significant_components": candidate_significant,
            "candidate_small_component_mass": candidate_small_mass,
        }
        trace.append(last)
        best_improvement = max(best_improvement, float(improvement))
        if (
            improvement >= float(minimum_improvement)
            and strain["edge_stretch_p01"] >= float(minimum_edge_compression)
            and strain["edge_stretch_p999"] <= float(maximum_edge_stretch)
            and coverage >= float(minimum_hidden_coverage)
            and candidate_significant <= original_significant
        ):
            accepted = candidate, last
            break
    if accepted is None:
        return prior.copy(), {
            "active": False, "reason": "no_pareto_valid_structural_update",
            "best_observed_improvement": float(best_improvement), "last_trial": last,
            "surface_graph_edges": int(original_edges), "attachment_edges": int(attachment_edges),
            "coherent_targets": coherence_info,
            "line_search": trace,
        }, np.zeros(len(prior), dtype=bool)
    candidate, accepted_info = accepted
    moved = np.linalg.norm(candidate - prior, axis=1) > 1e-8
    return candidate, {
        "active": True, "field": "soft_full_surface_arap_posterior",
        "surface_graph_edges": int(original_edges), "attachment_edges": int(attachment_edges),
        "coherent_targets": coherence_info,
        "hard_target_constraints": bool(hard_target_constraints),
        "line_search": trace,
        "target_gaussians": int(len(target_ids_unique)), "stable_gaussians": int(stable_mask.sum()),
        "moved_gaussians": int(moved.sum()), "moved_fraction": float(moved.mean()),
        "maximum_displacement": float(np.linalg.norm(candidate - prior, axis=1).max(initial=0.)),
        "mean_displacement": float(np.linalg.norm(candidate - prior, axis=1).mean()),
        "cg_status": cg_status, **accepted_info,
    }, moved


def _embedded_arap_posterior(
    prior: np.ndarray,
    target_ids: np.ndarray,
    targets: np.ndarray,
    target_weights: np.ndarray,
    stable_mask: np.ndarray,
    *,
    node_fraction: float,
    minimum_nodes: int,
    maximum_nodes: int,
    skinning_neighbours: int,
    neighbours: int,
    edge_ratio: float,
    attachment_edge_ratio: float,
    data_weight: float,
    screening: float,
    iterations: int,
    maximum_displacement: float,
    minimum_improvement: float,
    minimum_edge_compression: float,
    maximum_edge_stretch: float,
    minimum_hidden_coverage: float,
    coverage_resolution: int,
    bending_regularization: float = 0.0,
    coherent_component_targets: bool = True,
    preserve_target_amplitude: bool = False,
    hard_target_constraints: bool = False,
    node_minimum_edge_compression: float | None = None,
) -> tuple[np.ndarray, dict, np.ndarray]:
    """Deform the full carrier with a sparse, rotation-aware ARAP graph.

    Every transported carrier is retained as a graph node.  Additional nodes
    are sampled uniformly from the complete prior and drive all 100k surfels
    through smooth embedded-deformation skinning.  Consequently an observed
    residual moves its attached structure continuously, while stable evidence
    provides fixed boundary conditions and unsupported regions retain their
    relative geometry.
    """
    prior = np.asarray(prior, dtype=np.float64)
    target_ids = np.asarray(target_ids, dtype=np.int64)
    targets = np.asarray(targets, dtype=np.float64)
    target_weights = np.asarray(target_weights, dtype=np.float64)
    stable_mask = np.asarray(stable_mask, dtype=bool)
    if len(target_ids) == 0:
        return prior.copy(), {"active": False, "reason": "empty_transport_targets"}, np.zeros(len(prior), dtype=bool)

    unique_target_ids, inverse = np.unique(target_ids, return_inverse=True)
    target_sum = np.zeros((len(unique_target_ids), 3), dtype=np.float64)
    weight_sum = np.zeros(len(unique_target_ids), dtype=np.float64)
    np.add.at(target_sum, inverse, targets * target_weights[:, None])
    np.add.at(weight_sum, inverse, target_weights)
    unique_targets = target_sum / np.maximum(weight_sum[:, None], 1e-12)
    unique_weights = weight_sum / max(float(np.median(weight_sum[weight_sum > 0.])), 1e-12)
    keep = ~stable_mask[unique_target_ids]
    unique_target_ids = unique_target_ids[keep]
    unique_targets = unique_targets[keep]
    unique_weights = unique_weights[keep]
    if len(unique_target_ids) == 0:
        return prior.copy(), {"active": False, "reason": "all_transport_targets_are_stable"}, np.zeros(len(prior), dtype=bool)

    diagonal = max(float(np.linalg.norm(np.ptp(np.concatenate((prior, unique_targets), axis=0), axis=0))), 1e-9)
    coherence_info = {"components": 0, "regularized_targets": 0}
    if bool(coherent_component_targets):
        unique_targets, coherence_info = _coherent_targets(
            prior[unique_target_ids], unique_targets, diagonal=diagonal,
        )

    requested_nodes = int(np.clip(
        math.ceil(float(node_fraction) * len(prior)), int(minimum_nodes), int(maximum_nodes),
    ))
    sampled_node_ids = _sample_ids(prior, requested_nodes)
    node_ids = np.unique(np.r_[sampled_node_ids, unique_target_ids]).astype(np.int64)
    nodes = prior[node_ids]
    node_lookup = np.full(len(prior), -1, dtype=np.int64)
    node_lookup[node_ids] = np.arange(len(node_ids), dtype=np.int64)
    target_nodes = node_lookup[unique_target_ids]
    stable_nodes = stable_mask[node_ids].copy()
    if np.any(stable_mask):
        # Stable observations constrain their nearest graph controls.  They
        # are high-rigidity boundary conditions rather than pointwise clamps,
        # which avoids cracks between individually frozen samples and a
        # smoothly moving unsupported surface.
        nearest_stable_nodes = cKDTree(nodes).query(prior[stable_mask], k=1, workers=-1)[1]
        stable_nodes[np.asarray(nearest_stable_nodes, dtype=np.int64)] = True
    stable_nodes[target_nodes] = False

    node_targets = nodes[target_nodes] + (unique_targets - prior[unique_target_ids])
    deformed_nodes, node_info, _ = _soft_full_surface_arap(
        nodes, target_nodes, node_targets, unique_weights, stable_nodes,
        neighbours=int(neighbours), edge_ratio=float(edge_ratio),
        attachment_edge_ratio=float(attachment_edge_ratio),
        data_weight=float(data_weight), screening=float(screening), iterations=int(iterations),
        bending_regularization=float(bending_regularization),
        maximum_displacement=float(maximum_displacement),
        minimum_improvement=max(.5 * float(minimum_improvement), 1e-4),
        minimum_edge_compression=(
            max(.5 * float(minimum_edge_compression), .20)
            if node_minimum_edge_compression is None
            else float(node_minimum_edge_compression)
        ),
        maximum_edge_stretch=1.5 * float(maximum_edge_stretch),
        minimum_hidden_coverage=min(float(minimum_hidden_coverage), .85),
        coverage_resolution=max(48, int(coverage_resolution) // 2),
        coherent_component_targets=False,
        hard_target_constraints=bool(hard_target_constraints),
    )
    if not node_info.get("active"):
        return prior.copy(), {
            "active": False, "reason": "deformation_graph_rejected",
            "graph_nodes": int(len(nodes)), "node_solver": node_info,
            "coherent_targets": coherence_info,
        }, np.zeros(len(prior), dtype=bool)

    node_graph, _, node_edges = local_surface_graph(
        nodes, neighbours=int(neighbours), edge_ratio=float(edge_ratio),
    )
    node_graph, _, attachment_edges = _augment_attachment_edges(
        node_graph, node_graph.copy(), nodes, edge_ratio=float(attachment_edge_ratio),
    )
    rows, cols = sparse.triu(node_graph, k=1).nonzero()
    rotations = np.broadcast_to(np.eye(3), (len(nodes), 3, 3)).copy()
    if len(rows):
        weights = np.asarray(node_graph[rows, cols]).reshape(-1)
        rest = nodes[rows] - nodes[cols]
        changed = deformed_nodes[rows] - deformed_nodes[cols]
        covariance = np.zeros((len(nodes), 3, 3), dtype=np.float64)
        contribution = weights[:, None, None] * np.einsum("ni,nj->nij", changed, rest)
        np.add.at(covariance, rows, contribution)
        np.add.at(covariance, cols, contribution)
        active_nodes = np.flatnonzero(np.asarray(node_graph.sum(axis=1)).reshape(-1) > 0.)
        left, _, right = np.linalg.svd(covariance[active_nodes], full_matrices=False)
        local_rotation = left @ right
        reflected = np.linalg.det(local_rotation) < 0.
        if np.any(reflected):
            left[reflected, :, -1] *= -1.
            local_rotation = left @ right
        rotations[active_nodes] = local_rotation

    skin_k = min(max(1, int(skinning_neighbours)), len(nodes))
    skin_distance, skin_ids = cKDTree(nodes).query(prior, k=skin_k, workers=-1)
    if skin_k == 1:
        skin_distance = np.asarray(skin_distance)[:, None]
        skin_ids = np.asarray(skin_ids)[:, None]
    node_spacing = _median_spacing(nodes)
    radius = np.maximum(np.asarray(skin_distance)[:, -1], .5 * node_spacing)
    skin_weight = np.exp(-.5 * np.square(skin_distance / np.maximum(radius[:, None], 1e-12)))
    skin_weight /= np.maximum(skin_weight.sum(axis=1, keepdims=True), 1e-12)
    warped = np.zeros_like(prior)
    for column in range(skin_k):
        local = skin_ids[:, column]
        offset = prior - nodes[local]
        transformed = np.einsum("nij,nj->ni", rotations[local], offset) + deformed_nodes[local]
        warped += skin_weight[:, column, None] * transformed
    if bool(hard_target_constraints):
        # Skinning blends multiple graph controls.  Restore only the verified
        # residual surfels so the hard node constraints remain observable;
        # neighbouring carrier samples keep the smooth embedded field.
        warped[unique_target_ids] = unique_targets
    if np.any(stable_mask):
        stable_distance = cKDTree(prior[stable_mask]).query(prior, k=1, workers=-1)[0]
        transition = max(2.0 * _median_spacing(prior), _median_spacing(prior[stable_mask]))
        release = 1. - np.exp(-.5 * np.square(stable_distance / max(transition, 1e-12)))
        if bool(preserve_target_amplitude):
            # Targets are positive observation evidence.  They must retain
            # their requested displacement; only the transition into the
            # protected complete prior is attenuated.
            release[unique_target_ids] = 1.0
        warped = prior + release[:, None] * (warped - prior)
    carrier_graph, _, carrier_edges = local_surface_graph(
        prior, neighbours=int(neighbours), edge_ratio=float(edge_ratio),
    )
    carrier_graph, _, carrier_attachment_edges = _augment_attachment_edges(
        carrier_graph, carrier_graph.copy(), prior, edge_ratio=float(attachment_edge_ratio),
    )
    carrier_rows, carrier_cols = sparse.triu(carrier_graph, k=1).nonzero()
    initial_residual = np.linalg.norm(prior[unique_target_ids] - unique_targets, axis=1)
    original_components, original_labels = csgraph.connected_components(carrier_graph, directed=False)
    significant_size = max(32, int(math.ceil(.001 * len(prior))))
    original_sizes = np.bincount(original_labels, minlength=original_components)
    original_significant = int(np.sum(original_sizes >= significant_size))
    trace: list[dict] = []
    accepted: tuple[np.ndarray, dict] | None = None
    for alpha in (1., .85, .70, .55, .40, .25, .15):
        candidate = prior + float(alpha) * (warped - prior)
        after = np.linalg.norm(candidate[unique_target_ids] - unique_targets, axis=1)
        before_median = _weighted_median(initial_residual, unique_weights)
        after_median = _weighted_median(after, unique_weights)
        improvement = 1. - after_median / max(before_median, 1e-12)
        strain = edge_strain(prior, candidate, carrier_graph)
        coverage, per_view = _orthographic_coverage(prior, candidate, resolution=int(coverage_resolution))
        edge_ratio_now = np.linalg.norm(candidate[carrier_rows] - candidate[carrier_cols], axis=1) / np.maximum(
            np.linalg.norm(prior[carrier_rows] - prior[carrier_cols], axis=1), 1e-12,
        )
        effective_graph = carrier_graph.copy().tolil()
        broken = edge_ratio_now > float(maximum_edge_stretch)
        if np.any(broken):
            effective_graph[carrier_rows[broken], carrier_cols[broken]] = 0.
            effective_graph[carrier_cols[broken], carrier_rows[broken]] = 0.
        candidate_components, candidate_labels = csgraph.connected_components(
            effective_graph.tocsr(), directed=False,
        )
        candidate_sizes = np.bincount(candidate_labels, minlength=candidate_components)
        candidate_significant = int(np.sum(candidate_sizes >= significant_size))
        candidate_small_mass = int(candidate_sizes[candidate_sizes < significant_size].sum())
        record = {
            "alpha": float(alpha), "observed_residual_before": before_median,
            "observed_residual_after": after_median, "observed_improvement": float(improvement),
            "hidden_coverage_ratio": coverage, "hidden_coverage_per_view": per_view,
            "original_graph_components": int(original_components),
            "candidate_graph_components": int(candidate_components),
            "significant_component_size": int(significant_size),
            "original_significant_components": original_significant,
            "candidate_significant_components": candidate_significant,
            "candidate_small_component_mass": candidate_small_mass,
            "robust_edge_quantile": .99,
            **strain,
        }
        trace.append(record)
        if (
            improvement >= float(minimum_improvement)
            and strain["edge_stretch_p01"] >= float(minimum_edge_compression)
            and strain["edge_stretch_p99"] <= float(maximum_edge_stretch)
            and coverage >= float(minimum_hidden_coverage)
            and candidate_significant <= original_significant
        ):
            accepted = candidate, record
            break
    if accepted is None:
        return prior.copy(), {
            "active": False, "reason": "no_pareto_valid_embedded_update",
            "graph_nodes": int(len(nodes)), "node_graph_edges": int(node_edges),
            "attachment_edges": int(attachment_edges), "carrier_graph_edges": int(carrier_edges),
            "carrier_attachment_edges": int(carrier_attachment_edges),
            "coherent_targets": coherence_info, "node_solver": node_info,
            "line_search": trace,
        }, np.zeros(len(prior), dtype=bool)
    candidate, accepted_info = accepted
    moved = np.linalg.norm(candidate - prior, axis=1) > 1e-8
    return candidate, {
        "active": True, "field": "hierarchical_embedded_arap_posterior",
        "graph_nodes": int(len(nodes)), "node_graph_edges": int(node_edges),
        "attachment_edges": int(attachment_edges), "carrier_graph_edges": int(carrier_edges),
        "carrier_attachment_edges": int(carrier_attachment_edges),
        "target_gaussians": int(len(unique_target_ids)), "stable_gaussians": int(stable_mask.sum()),
        "moved_gaussians": int(moved.sum()), "moved_fraction": float(moved.mean()),
        "maximum_displacement": float(np.linalg.norm(candidate - prior, axis=1).max(initial=0.)),
        "mean_displacement": float(np.linalg.norm(candidate - prior, axis=1).mean()),
        "coherent_targets": coherence_info, "node_solver": node_info,
        "preserve_target_amplitude": bool(preserve_target_amplitude),
        "hard_target_constraints": bool(hard_target_constraints),
        "node_minimum_edge_compression": (
            None if node_minimum_edge_compression is None
            else float(node_minimum_edge_compression)
        ),
        "line_search": trace, **accepted_info,
    }, moved
