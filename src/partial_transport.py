"""Visibility- and structure-aware partial-to-prior transport."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.spatial import cKDTree
import torch

from fpsample import fps_sampling

from src.zbuffer import zbuffer_depth_with_indices

from src.posterior_types import PosteriorAdapterConfig, TransportResult


def _sample_ids(points: np.ndarray, count: int) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32)
    if len(points) <= int(count):
        return np.arange(len(points), dtype=np.int64)
    return np.asarray(fps_sampling(points, int(count), start_idx=0), dtype=np.int64)


def _local_surface_features(points: np.ndarray, sample_ids: np.ndarray, neighbours: int) -> tuple[np.ndarray, np.ndarray]:
    """Return unoriented normals and normalized covariance eigenvalues."""
    points = np.asarray(points, dtype=np.float64)
    sample_ids = np.asarray(sample_ids, dtype=np.int64)
    k = min(max(6, int(neighbours)), len(points))
    _, local_ids = cKDTree(points).query(points[sample_ids], k=k, workers=-1)
    local = points[np.asarray(local_ids)]
    centred = local - local.mean(axis=1, keepdims=True)
    covariance = np.einsum("nki,nkj->nij", centred, centred) / max(k - 1, 1)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.maximum(eigenvalues, 0.)
    descriptor = eigenvalues / np.maximum(eigenvalues.sum(axis=1, keepdims=True), 1e-12)
    normals = eigenvectors[:, :, 0]
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    return normals, descriptor


def _intrinsic_graph_signature(
    points: np.ndarray,
    sample_ids: np.ndarray,
    *,
    neighbours: int,
    landmarks: int,
) -> np.ndarray:
    """Return a scale- and landmark-order-invariant geodesic signature.

    The signature is evaluated only on the transport samples.  Sorted
    distances to farthest-point landmarks encode whether a sample lies on a
    compact sheet, a thin appendage, or near an attachment, without assuming
    a semantic part or a world axis.  Local radial quantiles complement the
    global graph coordinates when a partial scan truncates a geodesic path.
    """
    sampled = np.asarray(points, dtype=np.float64)[np.asarray(sample_ids, dtype=np.int64)]
    if len(sampled) < 3:
        return np.zeros((len(sampled), 4), dtype=np.float64)
    k = min(max(3, int(neighbours)), len(sampled))
    distance, neighbour_ids = cKDTree(sampled).query(sampled, k=k, workers=-1)
    if k == 1:
        distance = np.asarray(distance)[:, None]
        neighbour_ids = np.asarray(neighbour_ids)[:, None]
    spacing = max(float(np.median(distance[:, 1])), 1e-9)
    source = np.repeat(np.arange(len(sampled), dtype=np.int64), k - 1)
    target = np.asarray(neighbour_ids[:, 1:], dtype=np.int64).reshape(-1)
    weight = np.asarray(distance[:, 1:], dtype=np.float64).reshape(-1) / spacing
    graph = sparse.coo_matrix((weight, (source, target)), shape=(len(sampled), len(sampled))).tocsr()
    graph = graph.maximum(graph.T).tocsr()
    landmark_ids = _sample_ids(sampled, min(int(landmarks), len(sampled)))
    geodesic = np.asarray(csgraph.dijkstra(graph, directed=False, indices=landmark_ids), dtype=np.float64)
    finite = np.isfinite(geodesic)
    for row in range(len(geodesic)):
        row_finite = finite[row]
        fill = float(np.max(geodesic[row, row_finite])) if np.any(row_finite) else 1.
        geodesic[row, ~row_finite] = 1.25 * max(fill, 1.)
    normalization = max(float(np.quantile(geodesic, .90)), 1e-9)
    ordered_geodesic = np.sort(geodesic.T / normalization, axis=1)
    radial_columns = np.unique(np.clip(
        np.asarray([1, max(1, k // 3), max(1, 2 * k // 3), k - 1]), 1, k - 1,
    ))
    radial = distance[:, radial_columns] / np.maximum(distance[:, -1:], spacing)
    return np.concatenate((ordered_geodesic, radial), axis=1)


def _median_spacing(points: np.ndarray, *, maximum_samples: int = 8_192) -> float:
    ids = _sample_ids(points, min(int(maximum_samples), len(points)))
    distance, _ = cKDTree(points).query(np.asarray(points)[ids], k=min(2, len(points)), workers=-1)
    if np.ndim(distance) == 1:
        return max(float(np.median(distance)), 1e-9)
    return max(float(np.median(distance[:, 1])), 1e-9)


def _visible_prior_ids(prior: np.ndarray, projector) -> np.ndarray:
    uv, depth = projector.project(prior)
    _, mask, indices = zbuffer_depth_with_indices(uv, depth, projector.image_shape, splat_radius=1)
    ids = np.unique(indices[mask])
    ids = ids[ids >= 0]
    return ids.astype(np.int64, copy=False)


def _unbalanced_log_transport(cost: torch.Tensor, valid: torch.Tensor, *, iterations: int,
                              relaxation: float, temperature_floor: float) -> tuple[torch.Tensor, float]:
    """Entropic unbalanced transport on a dense, subsampled cost matrix."""
    finite_min = torch.where(valid, cost, torch.inf).amin(dim=1)
    usable = torch.isfinite(finite_min)
    if not bool(usable.any()):
        return torch.zeros_like(cost), float(temperature_floor)
    temperature = max(float(torch.quantile(finite_min[usable], .50).item()) * .55, float(temperature_floor))
    log_kernel = -cost / temperature
    log_kernel = torch.where(valid, log_kernel, torch.full_like(log_kernel, -1.0e4))
    n, m = cost.shape
    log_a = torch.full((n,), -math.log(max(n, 1)), dtype=cost.dtype, device=cost.device)
    log_b = torch.full((m,), -math.log(max(m, 1)), dtype=cost.dtype, device=cost.device)
    log_u = torch.zeros_like(log_a)
    log_v = torch.zeros_like(log_b)
    rho = float(relaxation)
    for _ in range(int(iterations)):
        log_u = rho * (log_a - torch.logsumexp(log_kernel + log_v[None, :], dim=1))
        log_v = rho * (log_b - torch.logsumexp(log_kernel + log_u[:, None], dim=0))
    log_plan = log_kernel + log_u[:, None] + log_v[None, :]
    plan = torch.exp(torch.clamp(log_plan, min=-80., max=20.))
    plan = torch.where(valid, plan, torch.zeros_like(plan))
    return plan, float(temperature)


def partial_optimal_transport(
    prior: np.ndarray,
    partial: np.ndarray,
    projector,
    *,
    config: PosteriorAdapterConfig,
    device: str = "cuda",
    view_projectors: Sequence | None = None,
) -> TransportResult:
    """Estimate capacity-aware, positive-only partial-to-prior evidence."""
    config.validate()
    prior = np.asarray(prior, dtype=np.float64)
    partial = np.asarray(partial, dtype=np.float64)
    if prior.ndim != 2 or partial.ndim != 2 or prior.shape[1:] != (3,) or partial.shape[1:] != (3,):
        raise ValueError("prior and partial must be shaped (N, 3)")
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    spacing = _median_spacing(partial)
    projectors = tuple(view_projectors or (projector,))
    if not projectors:
        raise ValueError("at least one view projector is required")
    visible_ids = np.unique(np.concatenate([
        _visible_prior_ids(prior, item) for item in projectors
    ])).astype(np.int64)
    if len(visible_ids) < int(config.minimum_transport_pairs):
        raise ValueError("too few camera-visible prior surfels for partial transport")
    partial_sample_ids = _sample_ids(partial, int(config.partial_samples))
    visible_sample_local = _sample_ids(prior[visible_ids], int(config.prior_samples))
    prior_sample_ids = visible_ids[visible_sample_local]

    partial_normal, partial_shape = _local_surface_features(
        partial, partial_sample_ids, int(config.normal_neighbours),
    )
    prior_normal, prior_shape = _local_surface_features(
        prior, prior_sample_ids, int(config.normal_neighbours),
    )
    actual_device = str(device)
    if actual_device.startswith("cuda") and not torch.cuda.is_available():
        actual_device = "cpu"
    dtype = torch.float32
    pp = torch.as_tensor(partial[partial_sample_ids] / diagonal, dtype=dtype, device=actual_device)
    qp = torch.as_tensor(prior[prior_sample_ids] / diagonal, dtype=dtype, device=actual_device)
    pn = torch.as_tensor(partial_normal, dtype=dtype, device=actual_device)
    qn = torch.as_tensor(prior_normal, dtype=dtype, device=actual_device)
    ps = torch.as_tensor(partial_shape, dtype=dtype, device=actual_device)
    qs = torch.as_tensor(prior_shape, dtype=dtype, device=actual_device)
    with torch.no_grad():
        distance_3d = torch.cdist(pp, qp)
        multiview_screen = torch.zeros_like(distance_3d)
        multiview_depth = torch.zeros_like(distance_3d)
        multiview_weight = torch.zeros_like(distance_3d)
        multiview_valid = torch.zeros_like(distance_3d, dtype=torch.bool)
        per_view_diagnostics = []
        for view_id, view_projector in enumerate(projectors):
            partial_uv_all, partial_depth_all = view_projector.project(partial)
            prior_uv_all, prior_depth_all = view_projector.project(prior)
            partial_uv = partial_uv_all[partial_sample_ids]
            prior_uv = prior_uv_all[prior_sample_ids]
            partial_depth = partial_depth_all[partial_sample_ids]
            prior_depth = prior_depth_all[prior_sample_ids]
            partial_visible_ids = _visible_prior_ids(partial, view_projector)
            prior_visible_ids = _visible_prior_ids(prior, view_projector)
            partial_visible = np.isin(partial_sample_ids, partial_visible_ids)
            prior_visible = np.isin(prior_sample_ids, prior_visible_ids)
            partial_visible &= (
                np.isfinite(partial_uv).all(axis=1)
                & np.isfinite(partial_depth) & (partial_depth > 1e-8)
            )
            prior_visible &= (
                np.isfinite(prior_uv).all(axis=1)
                & np.isfinite(prior_depth) & (prior_depth > 1e-8)
            )
            evidence = torch.as_tensor(
                partial_visible[:, None] & prior_visible[None, :],
                dtype=torch.bool, device=actual_device,
            )
            if not bool(evidence.any()):
                per_view_diagnostics.append({
                    "view": int(view_id), "partial_visible": int(partial_visible.sum()),
                    "prior_visible": int(prior_visible.sum()), "supported_pairs": 0,
                })
                continue
            visible_partial_uv = partial_uv[partial_visible]
            visible_partial_depth = partial_depth[partial_visible]
            uv_low, uv_high = np.quantile(visible_partial_uv, [.01, .99], axis=0)
            screen_extent = max(float(np.max(uv_high - uv_low)), 1.)
            depth_low, depth_high = np.quantile(visible_partial_depth, [.01, .99])
            depth_extent = max(float(depth_high - depth_low), spacing)
            partial_uv_tensor = torch.as_tensor(
                partial_uv / screen_extent, dtype=dtype, device=actual_device,
            )
            prior_uv_tensor = torch.as_tensor(
                prior_uv / screen_extent, dtype=dtype, device=actual_device,
            )
            partial_depth_tensor = torch.as_tensor(
                partial_depth / depth_extent, dtype=dtype, device=actual_device,
            )
            prior_depth_tensor = torch.as_tensor(
                prior_depth / depth_extent, dtype=dtype, device=actual_device,
            )
            distance_uv_view = torch.cdist(partial_uv_tensor, prior_uv_tensor)
            distance_depth_view = torch.abs(
                partial_depth_tensor[:, None] - prior_depth_tensor[None, :]
            )
            weight = evidence.to(dtype)
            multiview_screen += weight * distance_uv_view.square()
            multiview_depth += weight * distance_depth_view.square()
            multiview_weight += weight
            multiview_valid |= evidence & (
                (distance_uv_view <= float(config.maximum_screen_ratio))
                & (distance_depth_view <= float(config.maximum_depth_ratio))
            )
            per_view_diagnostics.append({
                "view": int(view_id), "partial_visible": int(partial_visible.sum()),
                "prior_visible": int(prior_visible.sum()),
                "supported_pairs": int(evidence.sum().item()),
            })
        has_view_support = multiview_weight > 0.
        multiview_screen /= torch.clamp(multiview_weight, min=1.)
        multiview_depth /= torch.clamp(multiview_weight, min=1.)
        normal_cost = 1. - torch.abs(pn @ qn.T)
        shape_cost = torch.cdist(ps, qs)
        cost = (
            .46 * distance_3d.square()
            + .23 * multiview_screen
            + .18 * multiview_depth
            + .08 * normal_cost
            + .05 * shape_cost
        )
        valid = (
            (distance_3d <= float(config.maximum_3d_ratio))
            & has_view_support
            & multiview_valid
            & (normal_cost <= .92)
        )
        plan, temperature = _unbalanced_log_transport(
            cost, valid, iterations=int(config.transport_iterations),
            relaxation=float(config.transport_relaxation),
            temperature_floor=float(config.transport_temperature_floor),
        )
        row_mass = plan.sum(dim=1)
        top_k = min(8, plan.shape[1])
        top_weight, top_prior_local = torch.topk(plan, k=top_k, dim=1, largest=True, sorted=True)
        top_cost = cost.gather(1, top_prior_local)
        top_valid = valid.gather(1, top_prior_local)
        top_concentration = top_weight / torch.clamp(row_mass[:, None], min=1e-12)
        arrays = [value.detach().cpu().numpy() for value in (
            row_mass, top_weight, top_prior_local, top_cost, top_valid, top_concentration,
        )]
    row_mass_np, top_weight_np, top_local_np, top_cost_np, top_valid_np, top_concentration_np = arrays
    valid_rows = top_valid_np[:, 0].astype(bool) & np.isfinite(top_cost_np[:, 0]) & (row_mass_np > 0.)
    if int(valid_rows.sum()) < int(config.minimum_transport_pairs):
        empty = np.zeros(len(prior), dtype=bool)
        return TransportResult(
            np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64),
            np.empty(0), np.empty(0), np.empty(0), empty.copy(), empty.copy(), ~empty,
            {"active": False, "reason": "insufficient_valid_transport_rows", "valid_rows": int(valid_rows.sum())},
        )
    best_local = top_local_np[:, 0].astype(np.int64)
    best_prior = prior_sample_ids[best_local]
    row_residual = np.linalg.norm(partial[partial_sample_ids] - prior[best_prior], axis=1)
    stable_limit = max(
        float(config.stable_spacing_multiplier) * spacing,
        float(np.quantile(row_residual[valid_rows], float(config.stable_residual_quantile))),
    )
    stable_limit = min(stable_limit, .035 * diagonal)
    residual_limit = max(
        stable_limit * 1.35,
        float(np.quantile(row_residual[valid_rows], float(config.residual_quantile))),
    )

    # High residual does not mean invalid: it is precisely the positive
    # evidence needed when a complete prior is locally too short.  Reject
    # only isolated/incoherent residuals, then allocate their top-k transport
    # choices with one carrier slot per observed sample.  Stable body points
    # cannot consume all target capacity before an extremity is considered.
    residual_rows = np.flatnonzero(valid_rows & (row_residual >= residual_limit))
    coherent_rows: list[int] = []
    if len(residual_rows):
        residual_points = partial[partial_sample_ids[residual_rows]]
        residual_spacing = _median_spacing(residual_points)
        component_radius = max(3.0 * residual_spacing, .012 * diagonal)
        pairs = cKDTree(residual_points).query_pairs(component_radius, output_type="ndarray")
        if len(pairs):
            component_graph = sparse.coo_matrix(
                (np.ones(2 * len(pairs)), (np.r_[pairs[:, 0], pairs[:, 1]], np.r_[pairs[:, 1], pairs[:, 0]])),
                shape=(len(residual_rows), len(residual_rows)),
            ).tocsr()
            component_count, labels = csgraph.connected_components(component_graph, directed=False)
        else:
            component_count, labels = len(residual_rows), np.arange(len(residual_rows), dtype=np.int64)
        minimum_component = max(8, int(math.ceil(.003 * len(partial_sample_ids))))
        for component in range(component_count):
            member = np.flatnonzero(labels == component)
            if len(member) < minimum_component:
                continue
            rows_local = residual_rows[member]
            vectors = partial[partial_sample_ids[rows_local]] - prior[best_prior[rows_local]]
            median_vector = np.median(vectors, axis=0)
            magnitude = float(np.linalg.norm(median_vector))
            if magnitude <= 1e-12:
                continue
            coherence = float(np.mean((vectors @ median_vector) / np.maximum(
                np.linalg.norm(vectors, axis=1) * magnitude, 1e-12,
            )))
            if coherence >= .20:
                coherent_rows.extend(rows_local.tolist())
    coherent_rows_np = np.asarray(coherent_rows, dtype=np.int64)
    coherent_fraction = float(len(coherent_rows_np) / max(int(valid_rows.sum()), 1))
    coherent_prior_fraction = float(
        len(np.unique(best_prior[coherent_rows_np])) / max(len(prior_sample_ids), 1)
    )
    # A posterior update is identifiable only when reliable residual support
    # is local relative to the already explained and uncertain quantile bands.
    # Broad coherent residuals indicate a global observation/prior mismatch;
    # allowing a local deformation graph to absorb them would overfit one view.
    localization_bound = float(config.residual_quantile - config.stable_residual_quantile)
    localized_residual_evidence = bool(
        len(coherent_rows_np) >= int(config.minimum_transport_pairs)
        and (
            not bool(config.require_localized_residual_evidence)
            or coherent_fraction <= localization_bound
        )
    )
    if not localized_residual_evidence:
        coherent_rows_np = np.empty(0, dtype=np.int64)
    edges: list[tuple[float, float, float, int, int, int]] = []
    for row in coherent_rows_np:
        for rank in range(top_local_np.shape[1]):
            if not bool(top_valid_np[row, rank]):
                continue
            local_prior = int(top_local_np[row, rank])
            edges.append((
                -float(row_residual[row]),
                float(top_cost_np[row, rank]),
                -float(top_concentration_np[row, rank]),
                int(row), local_prior, int(rank),
            ))
    edges.sort()
    used_rows: set[int] = set()
    used_prior: set[int] = set()
    assignments: list[tuple[int, int, int]] = []
    for _, _, _, row, local_prior, rank in edges:
        prior_id = int(prior_sample_ids[local_prior])
        if row in used_rows or prior_id in used_prior:
            continue
        used_rows.add(row); used_prior.add(prior_id)
        assignments.append((row, local_prior, rank))
    if assignments:
        selected_rows = np.asarray([row[0] for row in assignments], dtype=np.int64)
        selected_local = np.asarray([row[1] for row in assignments], dtype=np.int64)
        selected_rank = np.asarray([row[2] for row in assignments], dtype=np.int64)
        selected_partial = partial_sample_ids[selected_rows]
        selected_prior = prior_sample_ids[selected_local]
        selected_residual = np.linalg.norm(partial[selected_partial] - prior[selected_prior], axis=1)
        selected_weight = top_concentration_np[selected_rows, selected_rank]
        selected_cost = top_cost_np[selected_rows, selected_rank]
    else:
        selected_rows = np.empty(0, dtype=np.int64)
        selected_partial = np.empty(0, dtype=np.int64)
        selected_prior = np.empty(0, dtype=np.int64)
        selected_residual = np.empty(0, dtype=np.float64)
        selected_weight = np.empty(0, dtype=np.float64)
        selected_cost = np.empty(0, dtype=np.float64)

    stable_rows = valid_rows & (row_residual <= stable_limit)
    stable_mask = np.zeros(len(prior), dtype=bool)
    residual_mask = np.zeros(len(prior), dtype=bool)
    stable_mask[best_prior[stable_rows]] = True
    residual_mask[selected_prior] = True
    # Expand stable evidence only within local carrier sampling scale.  This
    # locks a measured surface patch, not a hand-authored semantic part.
    if stable_mask.any():
        nearest_stable, _ = cKDTree(prior[stable_mask]).query(prior, k=1, workers=-1)
        stable_mask |= nearest_stable <= max(2.0 * _median_spacing(prior), spacing)
    stable_mask &= ~residual_mask
    unsupported = ~(stable_mask | residual_mask)
    return TransportResult(
        partial_ids=selected_partial,
        prior_ids=selected_prior,
        weights=selected_weight,
        costs=selected_cost,
        residuals=selected_residual,
        stable_prior_mask=stable_mask,
        residual_prior_mask=residual_mask,
        unsupported_prior_mask=unsupported,
        diagnostics={
            "active": bool(residual_mask.any()),
            "method": "multiview_camera_structure_unbalanced_partial_transport",
            "device": actual_device,
            "view_count": int(len(projectors)),
            "view_evidence": per_view_diagnostics,
            "partial_diagonal": diagonal,
            "partial_spacing": spacing,
            "visible_prior": int(len(visible_ids)),
            "partial_samples": int(len(partial_sample_ids)),
            "prior_samples": int(len(prior_sample_ids)),
            "valid_transport_rows": int(valid_rows.sum()),
            "retained_capacity_pairs": int(len(selected_rows)),
            "stable_pairs": int(stable_rows.sum()),
            "coherent_residual_rows": int(len(coherent_rows_np)),
            "raw_coherent_residual_rows": int(len(coherent_rows)),
            "coherent_residual_fraction": coherent_fraction,
            "coherent_prior_support_fraction": coherent_prior_fraction,
            "localization_bound": localization_bound,
            "localized_residual_evidence": localized_residual_evidence,
            "residual_pairs": int(len(selected_rows)),
            "stable_prior": int(stable_mask.sum()),
            "residual_prior": int(residual_mask.sum()),
            "unsupported_prior": int(unsupported.sum()),
            "unmatched_partial_fraction": float(1. - (stable_rows.sum() + len(selected_rows)) / max(len(partial_sample_ids), 1)),
            "temperature": temperature,
            "stable_limit": stable_limit,
            "residual_limit": residual_limit,
            "residual_median": float(np.median(selected_residual)) if len(selected_residual) else None,
            "residual_p90": float(np.quantile(selected_residual, .90)) if len(selected_residual) else None,
        },
    )
