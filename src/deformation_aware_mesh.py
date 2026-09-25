"""Transfer a point-carrier deformation to its complete source mesh."""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.spatial import cKDTree
import trimesh

from src.multiview_diagnostics import apply_transform, estimate_ordered_similarity


def _row_normalized_mesh_adjacency(mesh: trimesh.Trimesh) -> sparse.csr_matrix:
    edges = np.asarray(mesh.edges_unique, dtype=np.int64)
    if not len(edges):
        return sparse.eye(len(mesh.vertices), format="csr")
    rows = np.r_[edges[:, 0], edges[:, 1]]
    cols = np.r_[edges[:, 1], edges[:, 0]]
    values = np.ones(len(rows), dtype=np.float64)
    adjacency = sparse.coo_matrix(
        (values, (rows, cols)), shape=(len(mesh.vertices), len(mesh.vertices)),
    ).tocsr()
    degree = np.asarray(adjacency.sum(axis=1)).reshape(-1)
    return sparse.diags(1.0 / np.maximum(degree, 1.0)) @ adjacency


def transfer_carrier_deformation_to_mesh(
    mesh: trimesh.Trimesh,
    source_carrier: np.ndarray,
    registered_carrier: np.ndarray,
    deformed_carrier: np.ndarray,
    *,
    interpolation_neighbours: int = 8,
    smoothing_steps: int = 4,
    smoothing_weight: float = 0.25,
) -> tuple[trimesh.Trimesh, dict]:
    """Warp a complete mesh with a smooth field inferred from matched carriers.

    The ordered source/registered carriers recover the global Sim(3). Local
    displacements are interpolated to mesh vertices and mildly regularized on
    the mesh adjacency while remaining anchored to the observed displacement
    field. No partial points, class labels, axes, or ground truth are used.
    """
    source = np.asarray(source_carrier, dtype=np.float64)
    registered = np.asarray(registered_carrier, dtype=np.float64)
    deformed = np.asarray(deformed_carrier, dtype=np.float64)
    if source.shape != registered.shape or registered.shape != deformed.shape:
        raise ValueError("source, registered, and deformed carriers must correspond")
    if source.ndim != 2 or source.shape[1] != 3 or len(source) < 3:
        raise ValueError("carriers must be non-empty (N, 3) arrays")
    if interpolation_neighbours < 1 or smoothing_steps < 0:
        raise ValueError("invalid interpolation or smoothing controls")
    if not 0.0 <= smoothing_weight < 1.0:
        raise ValueError("smoothing_weight must lie in [0, 1)")

    transform, fit_rmse = estimate_ordered_similarity(source, registered)
    diagonal = max(float(np.linalg.norm(np.ptp(registered, axis=0))), 1e-12)
    if fit_rmse > 1e-5 * diagonal:
        raise ValueError(f"ordered carrier Sim(3) is inconsistent: relative RMSE={fit_rmse / diagonal:.3g}")
    result = mesh.copy()
    registered_vertices = apply_transform(np.asarray(result.vertices, dtype=np.float64), transform)

    k = min(int(interpolation_neighbours), len(registered))
    distances, indices = cKDTree(registered).query(registered_vertices, k=k, workers=-1)
    if k == 1:
        distances, indices = distances[:, None], indices[:, None]
    scale = np.maximum(distances[:, -1:], np.quantile(distances[:, -1], .01) * .25 + 1e-12)
    weights = np.exp(-np.square(distances / scale))
    weights /= np.maximum(weights.sum(axis=1, keepdims=True), 1e-12)
    carrier_displacement = deformed - registered
    raw_displacement = np.sum(weights[..., None] * carrier_displacement[indices], axis=1)

    displacement = raw_displacement.copy()
    if smoothing_steps:
        adjacency = _row_normalized_mesh_adjacency(result)
        for _ in range(int(smoothing_steps)):
            neighbour_mean = adjacency @ displacement
            displacement = (
                (1.0 - float(smoothing_weight)) * raw_displacement
                + float(smoothing_weight) * neighbour_mean
            )
    result.vertices = registered_vertices + displacement
    return result, {
        "source_to_registered_fit_rmse": float(fit_rmse),
        "source_to_registered_fit_relative": float(fit_rmse / diagonal),
        "mesh_vertices": int(len(result.vertices)),
        "mesh_faces": int(len(result.faces)),
        "interpolation_neighbours": int(k),
        "smoothing_steps": int(smoothing_steps),
        "smoothing_weight": float(smoothing_weight),
        "displacement_median": float(np.median(np.linalg.norm(displacement, axis=1))),
        "displacement_p95": float(np.quantile(np.linalg.norm(displacement, axis=1), .95)),
        "displacement_max": float(np.max(np.linalg.norm(displacement, axis=1))),
    }


def sample_expansion_compensation(
    registered_mesh: trimesh.Trimesh,
    deformed_mesh: trimesh.Trimesh,
    *,
    count: int,
    seed: int = 6145,
    expansion_quantile: float = 0.85,
    minimum_expansion: float = 1.50,
) -> tuple[np.ndarray, dict]:
    """Sample additional points only from surface faces expanded by deformation."""
    if count < 0 or not 0.0 < expansion_quantile < 1.0 or minimum_expansion <= 1.0:
        raise ValueError("invalid expansion-compensation controls")
    if not np.array_equal(registered_mesh.faces, deformed_mesh.faces):
        raise ValueError("registered and deformed meshes must share topology")
    faces = np.asarray(deformed_mesh.faces, dtype=np.int64)
    before = np.asarray(registered_mesh.vertices, dtype=np.float64)[faces]
    after = np.asarray(deformed_mesh.vertices, dtype=np.float64)[faces]
    before_area = 0.5 * np.linalg.norm(np.cross(before[:, 1] - before[:, 0], before[:, 2] - before[:, 0]), axis=1)
    after_area = 0.5 * np.linalg.norm(np.cross(after[:, 1] - after[:, 0], after[:, 2] - after[:, 0]), axis=1)
    expansion = after_area / np.maximum(before_area, 1e-12)
    threshold = max(float(minimum_expansion), float(np.quantile(expansion, expansion_quantile)))
    # The quantile often coincides with a broad plateau (for example, all
    # faces of one stretched side).  Keep that plateau instead of requiring a
    # strict excess over the threshold, and weight retained faces by their
    # total area gain.
    valid = np.isfinite(expansion) & (expansion >= threshold) & (expansion > 1.0)
    excess = np.maximum(expansion - 1.0, 0.0) * after_area
    if count == 0 or not np.any(valid):
        return np.empty((0, 3), dtype=np.float64), {
            "new_points": 0, "selected_faces": 0, "expansion_threshold": threshold,
        }
    probability = excess.copy()
    probability[~valid] = 0.0
    probability /= probability.sum()
    rng = np.random.default_rng(int(seed))
    face_ids = rng.choice(len(faces), size=int(count), replace=True, p=probability)
    triangle = after[face_ids]
    uv = rng.random((int(count), 2))
    root = np.sqrt(uv[:, :1])
    barycentric = np.concatenate((1.0 - root, root * (1.0 - uv[:, 1:]), root * uv[:, 1:]), axis=1)
    points = np.sum(barycentric[..., None] * triangle, axis=1)
    return points, {
        "new_points": int(len(points)),
        "selected_faces": int(np.count_nonzero(valid)),
        "expansion_threshold": float(threshold),
        "selected_expansion_median": float(np.median(expansion[valid])),
        "selected_expansion_p99": float(np.quantile(expansion[valid], .99)),
    }
