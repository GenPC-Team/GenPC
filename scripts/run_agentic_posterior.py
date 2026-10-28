#!/usr/bin/env python3
"""Experimental no-GT observe/decide/act loop around existing solvers."""

from __future__ import annotations

import argparse
from dataclasses import asdict, fields, replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multiview_partial_evidence import load_manifest_projectors
from src.observation_anchored_fusion import (
    ContinuousObservationFusionConfig, fuse_continuous_observation_field,
)
from src.pointcloud_io import jsonable, load_points, write_compare, write_points
from src.posterior_adapter import PosteriorAdapter, PosteriorAdapterConfig
from src.posterior_agent import decide_next, observe, select_active_views, verify_update
from src.posterior_deformation import _orthographic_coverage
from src.saved_camera import SavedCameraProjector, draw_projection_overlay


PROFILE_STRENGTH = {"CONSERVATIVE": .75, "BALANCED": 1.0, "EXPANSIVE": 1.25}


def _config(path: Path) -> PosteriorAdapterConfig:
    values = json.loads(path.read_text(encoding="utf-8"))
    known = {item.name for item in fields(PosteriorAdapterConfig)}
    if not isinstance(values, dict) or set(values) - known:
        raise ValueError("invalid posterior configuration")
    return PosteriorAdapterConfig(**values)


def _profile(base: PosteriorAdapterConfig, name: str) -> PosteriorAdapterConfig:
    strength = PROFILE_STRENGTH[name]
    return replace(
        base,
        assimilation_data_weight=base.assimilation_data_weight * strength,
        assimilation_displacement_ratio=base.assimilation_displacement_ratio * strength,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--camera", type=Path, required=True)
    parser.add_argument("--semantic", type=Path, required=True)
    parser.add_argument("--multiview-manifest", type=Path, required=True)
    parser.add_argument("--config-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--maximum-rounds", type=int, default=3)
    parser.add_argument("--view-policy", choices=("adaptive", "fixed4"), default="adaptive")
    parser.add_argument("--maximum-active-views", type=int, default=6)
    parser.add_argument(
        "--minimum-reference-coverage", type=float, default=.85,
        help="Cumulative reference-prior coverage floor; each solver step retains its stricter local guard.",
    )
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    if not 1 <= args.maximum_rounds <= 6:
        raise ValueError("maximum rounds must be between 1 and 6")
    if not 2 <= args.maximum_active_views <= 6:
        raise ValueError("maximum active views must be between 2 and 6")
    if not 0.0 < args.minimum_reference_coverage <= 1.0:
        raise ValueError("minimum reference coverage must lie in (0, 1]")

    initial, partial = load_points(args.prior), load_points(args.partial)
    if len(initial) != 100_000:
        raise ValueError("the agent requires the complete ordered 100k carrier")
    camera = SavedCameraProjector.from_partial(
        partial, args.camera, padding=.15, image_shape=(512, 512), device=args.device,
    )
    audit_views = load_manifest_projectors(args.multiview_manifest, resolution=512)
    if len(audit_views) != 4:
        raise ValueError("four saved diagnostic cameras are required")
    manifest = json.loads(args.multiview_manifest.read_text(encoding="utf-8"))
    base = _config(args.config_json)
    if not base.integrated_observation_fusion:
        raise ValueError("the mainline four-view posterior configuration is required")

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    current = initial.copy()
    evidence, caches = observe(partial, current, audit_views)
    initial_evidence = evidence
    previous = None
    trace: list[dict] = []
    write_compare(output / "before_registered_partial_gray_prior_red.ply", partial, current)

    for round_index in range(args.maximum_rounds):
        decision = decide_next(
            evidence, previous, round_index=round_index,
            maximum_rounds=args.maximum_rounds,
        )
        if decision.action not in {"UPDATE_POSTERIOR", "REFINE_OBSERVED"}:
            trace.append({"round": round_index, "decision": asdict(decision)})
            break
        if args.view_policy == "adaptive":
            active_views, view_audit = select_active_views(
                partial, current, manifest, maximum_views=args.maximum_active_views,
            )
        else:
            active_views = audit_views
            view_audit = {"method": "fixed_saved_four_views", "view_count": len(active_views)}
        candidate_records = []
        accepted = False
        candidates = [(decision.profile, decision.transport)]
        if decision.action == "REFINE_OBSERVED":
            candidates.append(("BALANCED", "CAMERA1"))
        elif (decision.profile, decision.transport) != ("CONSERVATIVE", "CAMERA1"):
            candidates.append(("CONSERVATIVE", "CAMERA1"))
        if decision.action == "UPDATE_POSTERIOR":
            candidates.append(("OBSERVATION_FIELD", "ALL_ACTIVE_VIEWS"))
        for name, transport in candidates:
            if name == "OBSERVATION_FIELD":
                proposal, _, _, field_info = fuse_continuous_observation_field(
                    current, partial, active_views,
                    config=ContinuousObservationFusionConfig(num_views=len(active_views)),
                )
                estimate = {"integrity": {"passed": bool(field_info.get("active", False))}}
            else:
                config = _profile(base, name)
                proposal, estimate, _ = PosteriorAdapter(config, device=args.device).run(
                    current, partial, camera,
                    view_projectors=active_views,
                    transport_projectors=(active_views if transport == "ALL_ACTIVE_VIEWS" else (camera,)),
                )
            observed, _ = observe(partial, proposal, audit_views, caches=caches)
            reference_coverage, reference_per_view = _orthographic_coverage(
                initial, proposal, resolution=int(base.coverage_resolution),
            )
            verdict = verify_update(
                evidence, observed, estimate,
                reference_coverage=reference_coverage,
                minimum_reference_coverage=args.minimum_reference_coverage,
            )
            candidate_records.append({
                "profile": name,
                "transport": transport,
                "verdict": asdict(verdict),
                "observation": asdict(observed),
                "integrity": estimate.get("integrity", {}),
                "reference_coverage": reference_coverage,
                "reference_coverage_per_view": reference_per_view,
                "field_info": field_info if name == "OBSERVATION_FIELD" else None,
                "hidden_coverage_ratio": estimate.get("hidden_coverage_ratio"),
            })
            if verdict.action == "ACCEPT_UPDATE":
                previous, current, evidence = evidence, proposal, observed
                accepted = True
                write_points(output / f"accepted_round_{round_index + 1:02d}_100k.ply", current)
                break
        trace.append({
            "round": round_index + 1,
            "decision": asdict(decision),
            "active_views": view_audit,
            "candidates": candidate_records,
            "accepted": accepted,
        })
        if not accepted:
            trace.append({
                "round": round_index + 1,
                "decision": {"action": "ACCEPT", "profile": "NONE", "reason": "all_candidates_rejected"},
            })
            break

    final_path = output / "agent_selected_posterior_100k.ply"
    write_points(final_path, current)
    write_compare(output / "after_partial_gray_posterior_red.ply", partial, current)
    draw_projection_overlay(
        output / "after_camera1_overlay.png", args.semantic, partial, current, camera,
    )
    audit = {
        "method": "bounded_observe_decide_act_posterior_experiment",
        "policy": "deterministic_no_gt_v1",
        "view_policy": args.view_policy,
        "maximum_active_views": args.maximum_active_views,
        "minimum_reference_coverage": args.minimum_reference_coverage,
        "ground_truth_used": False,
        "category_or_part_rules_used": False,
        "inputs": {key: str(getattr(args, key).resolve()) for key in (
            "prior", "partial", "camera", "semantic", "multiview_manifest", "config_json"
        )},
        "initial_observation": asdict(initial_evidence),
        "final_observation": asdict(evidence),
        "trace": trace,
        "final": str(final_path.resolve()),
        "carrier_slots": len(current),
    }
    (output / "agent_trace.json").write_text(
        json.dumps(jsonable(audit), indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(jsonable({
        "final": final_path.resolve(),
        "accepted_rounds": sum(bool(row.get("accepted")) for row in trace),
        "coverage_before": initial_evidence.mean_coverage,
        "coverage_after": evidence.mean_coverage,
        "partial_to_carrier_p90_before": initial_evidence.partial_to_carrier_p90,
        "partial_to_carrier_p90_after": evidence.partial_to_carrier_p90,
    }), indent=2), flush=True)


if __name__ == "__main__":
    main()
