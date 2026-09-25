#!/usr/bin/env python3
"""Distil only observation-supported local gains from an aggressive posterior.

The aggressive carrier acts as a proposal, never as the final shape.  A point
is eligible only when the proposal materially improves its distance to the
partial observation and the protected carrier still has a high residual.
The selected motion is projected through the same category-free structural
guard used by the posterior solver, leaving the complete carrier intact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.deformation_graph import local_surface_graph
from src.pointcloud_io import load_points, write_compare, write_points
from src.carrier_protection import project_reference_carrier_protection
from src.partial_transport import _median_spacing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--protected", type=Path, required=True)
    parser.add_argument("--aggressive", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--residual-quantile", type=float, default=.55)
    parser.add_argument("--improvement-quantile", type=float, default=.55)
    parser.add_argument(
        "--selection-mode", choices=("forward", "reverse", "bidirectional"),
        default="forward",
    )
    parser.add_argument("--reverse-improvement-quantile", type=float, default=.90)
    parser.add_argument("--reverse-distance-quantile", type=float, default=.60)
    parser.add_argument("--reverse-dilation-hops", type=int, default=1)
    parser.add_argument("--minimum-improvement-spacing", type=float, default=1.0)
    parser.add_argument("--neighbours", type=int, default=10)
    parser.add_argument("--edge-ratio", type=float, default=1.85)
    parser.add_argument("--continuation-hops", type=int, default=3)
    parser.add_argument("--component-core-hops", type=int, default=6)
    parser.add_argument("--maximum-edge-stretch", type=float, default=25.0)
    parser.add_argument("--minimum-hidden-coverage", type=float, default=.92)
    args = parser.parse_args()

    reference = load_points(args.reference)
    protected = load_points(args.protected)
    aggressive = load_points(args.aggressive)
    partial = load_points(args.partial)
    if reference.shape != protected.shape or protected.shape != aggressive.shape:
        raise ValueError("ordered reference, protected, and aggressive carriers must correspond")
    if not 0. < args.residual_quantile < 1. or not 0. < args.improvement_quantile < 1.:
        raise ValueError("quantiles must lie in (0, 1)")
    if not 0. < args.reverse_improvement_quantile < 1. or not 0. < args.reverse_distance_quantile < 1.:
        raise ValueError("reverse quantiles must lie in (0, 1)")
    if int(args.reverse_dilation_hops) < 0:
        raise ValueError("reverse dilation hops must be non-negative")

    tree = cKDTree(partial)
    protected_distance = tree.query(protected, k=1, workers=-1)[0]
    aggressive_distance = tree.query(aggressive, k=1, workers=-1)[0]
    improvement = protected_distance - aggressive_distance
    positive = improvement[improvement > 0.]
    spacing = _median_spacing(protected)
    improvement_threshold = max(
        float(args.minimum_improvement_spacing) * float(spacing),
        float(np.quantile(positive, args.improvement_quantile)) if len(positive) else np.inf,
    )
    residual_threshold = float(np.quantile(protected_distance, args.residual_quantile))
    forward_support = (
        (improvement >= improvement_threshold)
        & (protected_distance >= residual_threshold)
    )

    graph, _, _ = local_surface_graph(
        protected, neighbours=int(args.neighbours), edge_ratio=float(args.edge_ratio),
    )
    protected_partial_distance = cKDTree(protected).query(partial, k=1, workers=-1)[0]
    aggressive_partial_distance, aggressive_partial_ids = cKDTree(aggressive).query(
        partial, k=1, workers=-1,
    )
    reverse_improvement = protected_partial_distance - aggressive_partial_distance
    reverse_threshold = float(np.quantile(reverse_improvement, args.reverse_improvement_quantile))
    reverse_distance_threshold = float(np.quantile(aggressive_partial_distance, args.reverse_distance_quantile))
    reverse_partial = (
        (reverse_improvement >= reverse_threshold)
        & (aggressive_partial_distance <= reverse_distance_threshold)
    )
    reverse_support = np.zeros(len(protected), dtype=bool)
    reverse_support[np.unique(aggressive_partial_ids[reverse_partial])] = True
    frontier = reverse_support.copy()
    for _ in range(int(args.reverse_dilation_hops)):
        reached = np.asarray(graph @ frontier.astype(np.float64)).reshape(-1) > 0.
        reached &= ~reverse_support
        if not np.any(reached):
            break
        reverse_support |= reached
        frontier = reached
    # A reverse proposal must not overwrite carrier points that the protected
    # solution already explains.  This is the category-free analogue of
    # freezing an aligned limb or surface: only the same robust residual
    # threshold used by the forward selector determines stability.
    reverse_support &= protected_distance >= residual_threshold
    if args.selection_mode == "forward":
        support = forward_support
    elif args.selection_mode == "reverse":
        support = reverse_support
    else:
        support = forward_support | reverse_support

    # Remove isolated nearest-neighbour wins.  A retained target must belong
    # to a rest-graph connected patch large enough to define structural
    # motion; the threshold scales only with carrier cardinality.
    minimum_component = max(32, int(np.ceil(.0005 * len(protected))))
    ids = np.flatnonzero(support)
    if len(ids):
        from scipy.sparse import csgraph

        count, labels = csgraph.connected_components(graph[ids][:, ids], directed=False)
        sizes = np.bincount(labels, minlength=count)
        keep = sizes[labels] >= minimum_component
        filtered = np.zeros_like(support)
        filtered[ids[keep]] = True
        support = filtered

    proposal = protected.copy()
    proposal[support] = aggressive[support]
    result, protection = project_reference_carrier_protection(
        reference,
        proposal,
        neighbours=int(args.neighbours),
        edge_ratio=float(args.edge_ratio),
        minimum_hidden_coverage=float(args.minimum_hidden_coverage),
        maximum_edge_stretch=float(args.maximum_edge_stretch),
        coverage_resolution=192,
        positive_evidence_mask=support,
        fallback_carrier=protected,
        update_reference=protected,
        support_continuation_hops=int(args.continuation_hops),
        support_componentwise_similarity=True,
        support_component_similarity_core_hops=int(args.component_core_hops),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_points(args.output_dir / "posterior_distilled_100k.ply", result)
    write_compare(args.output_dir / "partial_gray_posterior_distilled_red.ply", partial, result)
    write_points(args.output_dir / "distilled_support_points.ply", protected[support])
    write_compare(
        args.output_dir / "protected_gray_distilled_support_red.ply",
        protected, protected[support],
    )
    np.save(args.output_dir / "distilled_support_mask.npy", support)
    report = {
        "method": "observation_supported_aggressive_local_target_distillation",
        "ground_truth_used": False,
        "category_or_part_rules_used": False,
        "spacing": float(spacing),
        "residual_threshold": residual_threshold,
        "improvement_threshold": improvement_threshold,
        "selection_mode": args.selection_mode,
        "forward_selected_points": int(forward_support.sum()),
        "reverse_improvement_threshold": reverse_threshold,
        "reverse_distance_threshold": reverse_distance_threshold,
        "reverse_partial_points": int(reverse_partial.sum()),
        "reverse_selected_points_before_component_filter": int(reverse_support.sum()),
        "reverse_dilation_hops": int(args.reverse_dilation_hops),
        "selected_points": int(support.sum()),
        "minimum_component_points": int(minimum_component),
        "protected_residual_median_selected": (
            float(np.median(protected_distance[support])) if np.any(support) else None
        ),
        "aggressive_residual_median_selected": (
            float(np.median(aggressive_distance[support])) if np.any(support) else None
        ),
        "protection": protection,
    }
    (args.output_dir / "distillation_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
