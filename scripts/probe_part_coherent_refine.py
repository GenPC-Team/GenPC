#!/usr/bin/env python3
"""Ablate a category-free, partial-supported coherent deformation proposal.

The existing Partial OT and PosteriorAdapter provide correspondences and the
raw proposal.  Existing reference-carrier protection projects coherent moving
support through a finite graph band.  This script never reads GT or changes
the frozen GPT-refine result; it only writes candidates for comparison.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, fields, replace
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.carrier_protection import project_reference_carrier_protection
from src.multiview_partial_evidence import load_manifest_projectors
from src.pointcloud_io import jsonable, load_points, write_compare, write_points
from src.posterior_adapter import PosteriorAdapter, PosteriorAdapterConfig
from src.posterior_agent import observe, select_active_views
from src.posterior_deformation import _orthographic_coverage
from src.saved_camera import SavedCameraProjector


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, required=True,
                        help="Original registered complete carrier")
    parser.add_argument("--current", type=Path, required=True,
                        help="Frozen GPT-refine output to improve")
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--camera", type=Path, required=True)
    parser.add_argument("--multiview-manifest", type=Path, required=True)
    parser.add_argument("--config-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    reference, current, partial = (load_points(path) for path in
                                   (args.prior, args.current, args.partial))
    if reference.shape != current.shape or len(current) != 100_000:
        raise ValueError("the ordered reference and current carrier must each have 100k slots")
    values = json.loads(args.config_json.read_text(encoding="utf-8"))
    known = {field.name for field in fields(PosteriorAdapterConfig)}
    if set(values) - known:
        raise ValueError("unknown posterior configuration field")
    base = PosteriorAdapterConfig(**values)
    # Same generic coherent-target hypothesis for every category.  The
    # hypothesis is an ablation, not a silently promoted mainline setting.
    config = replace(base, assimilation_separate_stable_anchors=True,
                     assimilation_coherent_residual_targets=True,
                     assimilation_hard_residual_targets=True)
    camera = SavedCameraProjector.from_partial(
        partial, args.camera, padding=.15, image_shape=(512, 512), device=args.device,
    )
    saved_views = load_manifest_projectors(args.multiview_manifest, resolution=512)
    manifest = json.loads(args.multiview_manifest.read_text(encoding="utf-8"))
    active_views, view_audit = select_active_views(partial, current, manifest)
    raw, solver_info, masks = PosteriorAdapter(config, device=args.device).run(
        current, partial, camera, view_projectors=active_views,
        transport_projectors=(camera,),
    )
    support = masks["supported_residual_any_stage"] | masks["assimilation_anchor"]
    current_coverage, _ = _orthographic_coverage(
        reference, current, resolution=int(config.coverage_resolution),
    )
    coverage_floor = max(.85, min(.92, current_coverage - .005))
    protected, protection_info = project_reference_carrier_protection(
        reference, raw,
        neighbours=int(config.fine_neighbours),
        edge_ratio=float(config.fine_edge_ratio),
        minimum_hidden_coverage=coverage_floor,
        maximum_edge_stretch=float(config.maximum_edge_stretch),
        minimum_edge_compression=float(config.minimum_edge_compression),
        coverage_resolution=int(config.coverage_resolution),
        positive_evidence_mask=support,
        fallback_carrier=current,
        update_reference=current,
        support_local_motion_selection=True,
        support_continuation_hops=3,
        support_componentwise_similarity=True,
        support_component_similarity_core_hops=2,
        support_component_connectivity_hops=3,
    )
    baseline_observation, caches = observe(partial, current, saved_views)
    raw_observation, _ = observe(partial, raw, saved_views, caches=caches)
    protected_observation, _ = observe(partial, protected, saved_views, caches=caches)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    write_points(output / "coherent_raw_100k.ply", raw)
    write_points(output / "coherent_protected_100k.ply", protected)
    write_compare(output / "partial_gray_coherent_protected_red.ply", partial, protected)
    report = {
        "method": "partial_supported_coherent_target_ablation",
        "ground_truth_used": False,
        "category_or_part_rules_used": False,
        "inputs": {key: str(getattr(args, key).resolve()) for key in
                   ("prior", "current", "partial", "camera", "multiview_manifest", "config_json")},
        "view_selection": view_audit,
        "support_points": int(support.sum()),
        "coverage_floor": coverage_floor,
        "raw_motion_p90": float(np.quantile(np.linalg.norm(raw-current, axis=1), .90)),
        "protected_motion_p90": float(np.quantile(np.linalg.norm(protected-current, axis=1), .90)),
        "solver_integrity": solver_info["integrity"],
        "protection": protection_info,
        "observations": {"baseline": asdict(baseline_observation),
                         "raw": asdict(raw_observation),
                         "protected": asdict(protected_observation)},
    }
    (output / "probe_report.json").write_text(
        json.dumps(jsonable(report), indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(jsonable({"output": output.resolve(), "support_points": int(support.sum()),
                               "protection_accepted": protection_info.get("accepted"),
                               "p90": {name: state.partial_to_carrier_p90 for name, state in
                                       (("baseline", baseline_observation), ("raw", raw_observation),
                                        ("protected", protected_observation))}}), indent=2))


if __name__ == "__main__":
    main()
