"""Densify a deformed complete carrier where its rest-surface graph stretches.

Every original point is retained. New points are interpolated only on edges
that belonged to the complete prior before deformation, repairing sampling
holes without inserting partial-observation points or moving the geometry.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import sparse

from src.deformation_graph import local_surface_graph


@dataclass(frozen=True)
class StrainDensificationConfig:
    """Dimensionless controls for carrier-preserving surface densification."""

    neighbours: int = 10
    edge_ratio: float = 1.85
    strain_quantile: float = 0.92
    minimum_stretch: float = 1.80
    maximum_segment_stretch: float = 1.35
    maximum_splits_per_edge: int = 4
    maximum_new_point_ratio: float = 0.25

    def validate(self) -> None:
        if self.neighbours < 3 or self.edge_ratio <= 0.0:
            raise ValueError("invalid rest-surface graph controls")
        if not 0.0 < self.strain_quantile < 1.0:
            raise ValueError("strain_quantile must lie in (0, 1)")
        if self.minimum_stretch <= 1.0 or self.maximum_segment_stretch <= 1.0:
            raise ValueError("stretch controls must exceed one")
        if self.maximum_splits_per_edge < 1 or self.maximum_new_point_ratio <= 0.0:
            raise ValueError("densification budget is invalid")


def _undirected_edges(graph: sparse.csr_matrix) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = sparse.triu(graph, k=1).nonzero()
    return rows.astype(np.int64), cols.astype(np.int64)


def densify_stretched_surface(
    reference: np.ndarray,
    deformed: np.ndarray,
    *,
    config: StrainDensificationConfig = StrainDensificationConfig(),
) -> tuple[np.ndarray, dict]:
    """Add samples to strongly stretched rest-surface edges.

    ``reference`` and ``deformed`` retain point correspondence. The returned
    cloud starts with every deformed point unchanged; appended samples are
    convex combinations of endpoint pairs in the prior's local surface graph.
    """
    config.validate()
    reference = np.asarray(reference, dtype=np.float64)
    deformed = np.asarray(deformed, dtype=np.float64)
    if reference.ndim != 2 or reference.shape[1] != 3 or reference.shape != deformed.shape:
        raise ValueError("reference and deformed must be matched (N, 3) arrays")
    if len(reference) < 4:
        return deformed.copy(), {"active": False, "reason": "too_few_points"}

    graph, _, graph_edge_count = local_surface_graph(
        reference, neighbours=int(config.neighbours), edge_ratio=float(config.edge_ratio),
    )
    rows, cols = _undirected_edges(graph)
    if not len(rows):
        return deformed.copy(), {"active": False, "reason": "empty_rest_graph"}
    rest_length = np.linalg.norm(reference[rows] - reference[cols], axis=1)
    current_length = np.linalg.norm(deformed[rows] - deformed[cols], axis=1)
    stretch = current_length / np.maximum(rest_length, 1e-12)
    threshold = max(float(config.minimum_stretch), float(np.quantile(stretch, config.strain_quantile)))
    selected = stretch >= threshold
    if not np.any(selected):
        return deformed.copy(), {
            "active": True, "graph_edges": int(graph_edge_count),
            "selected_edges": 0, "new_points": 0, "stretch_threshold": float(threshold),
        }

    selected_ids = np.flatnonzero(selected)
    requested = np.ceil(stretch[selected_ids] / float(config.maximum_segment_stretch)).astype(np.int64) - 1
    requested = np.clip(requested, 1, int(config.maximum_splits_per_edge))
    order = np.lexsort((selected_ids, -stretch[selected_ids]))
    budget = max(1, int(np.floor(float(config.maximum_new_point_ratio) * len(deformed))))
    inserted: list[np.ndarray] = []
    densified_edges = 0
    for position in order:
        edge_id = int(selected_ids[position])
        count = int(min(requested[position], budget - len(inserted)))
        if count <= 0:
            break
        weights = np.arange(1, count + 1, dtype=np.float64)[:, None] / float(count + 1)
        first, second = deformed[rows[edge_id]], deformed[cols[edge_id]]
        inserted.extend((1.0 - weights) * first + weights * second)
        densified_edges += 1
    new_points = np.asarray(inserted, dtype=np.float64).reshape(-1, 3)
    dense = deformed.copy() if not len(new_points) else np.concatenate((deformed, new_points), axis=0)
    return dense, {
        "active": True,
        "graph_edges": int(graph_edge_count),
        "selected_edges": int(np.count_nonzero(selected)),
        "densified_edges": int(densified_edges),
        "new_points": int(len(new_points)),
        "original_points": int(len(deformed)),
        "output_points": int(len(dense)),
        "stretch_threshold": float(threshold),
        "selected_stretch_median": float(np.median(stretch[selected])),
        "selected_stretch_p99": float(np.quantile(stretch[selected], 0.99)),
    }
