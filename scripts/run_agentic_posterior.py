#!/usr/bin/env python3
"""Experimental no-GT observe/decide/act loop around existing solvers."""

from __future__ import annotations

import argparse
from dataclasses import asdict, fields, replace
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

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
from src.gpt_refine_agent import (
    GPTRefineAgent, PLATEAU_PATIENCE, PROMPT_VERSION, next_plateau_streak,
    render_diagnostic_board, visible_partial_fraction,
)
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


def _structured_proposal(args, original, output: Path):
    """Reuse the existing aggressive-observation/complete-graph solver, no GT."""
    if args.semantic is None or args.structural_proposal_config is None:
        raise ValueError("structured proposal requires semantic and proposal config")
    command = [
        sys.executable, str(ROOT / "scripts" / "run_residual_proximal_prior_adaptation.py"),
        "--prior", str(args.prior), "--partial", str(args.partial),
        "--camera", str(args.camera), "--semantic", str(args.semantic),
        "--multiview-manifest", str(args.multiview_manifest),
        "--proposal-config", str(args.structural_proposal_config),
        "--output-dir", str(output), "--device", str(args.device),
    ]
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False)
    output.mkdir(parents=True, exist_ok=True)
    (output / "run.log").write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"structured proposal failed ({completed.returncode}); see {output / 'run.log'}")
    proposal_path = output / "prior_projection" / "posterior_expert_distilled_100k.ply"
    report_path = output / "prior_projection" / "expert_distillation_report.json"
    proposal = load_points(proposal_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if proposal.shape != original.shape or not np.isfinite(proposal).all():
        raise ValueError("structured proposal did not preserve finite 100k carrier")
    estimate = {"integrity": {"passed": bool(report.get("solve", {}).get("active"))},
                "structural_report": str(report_path.resolve())}
    return proposal, estimate, proposal_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--camera", type=Path, required=True)
    parser.add_argument("--semantic", type=Path,
                        help="Optional semantic image used only for the final Camera-1 overlay")
    parser.add_argument("--multiview-manifest", type=Path, required=True)
    parser.add_argument("--config-json", type=Path, required=True)
    parser.add_argument("--structural-proposal-config", type=Path,
                        help="Opt-in residual-proximal graph proposal; requires --semantic")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--maximum-rounds", type=int, default=3)
    parser.add_argument("--decision-backend", choices=("deterministic", "gpt"),
                        default="deterministic")
    parser.add_argument("--gpt-model", help="Required for --decision-backend gpt")
    parser.add_argument("--gpt-provider", choices=("codex", "api"), default="codex",
                        help="Codex uses the logged-in CLI; api uses OPENAI_API_KEY")
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
    if args.decision_backend == "gpt" and not args.gpt_model:
        raise ValueError("--gpt-model is required for the GPT decision backend")
    if args.structural_proposal_config is not None and (
        not args.structural_proposal_config.is_file() or args.semantic is None
    ):
        raise ValueError("--structural-proposal-config requires a file and --semantic")
    gpt_agent = (GPTRefineAgent(args.gpt_model, provider=args.gpt_provider)
                 if args.decision_backend == "gpt" else None)

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
    plateau_streak = 0
    stop_reason = "maximum_rounds"
    write_compare(output / "before_registered_partial_gray_prior_red.ply", partial, current)

    for round_index in range(args.maximum_rounds):
        board = None
        gpt_plan = None
        view_options = None
        adaptive_views = None
        adaptive_audit = None
        if gpt_agent is None:
            decision = decide_next(
                evidence, previous, round_index=round_index,
                maximum_rounds=args.maximum_rounds,
            )
        else:
            adaptive_views, adaptive_audit = select_active_views(
                partial, current, manifest, maximum_views=args.maximum_active_views,
            )
            view_options = {
                "SAVED_FOUR": {
                    "view_count": len(audit_views),
                    "unique_visible_partial_fraction": visible_partial_fraction(partial, audit_views),
                },
                "ADAPTIVE_ORBIT": {
                    "view_count": len(adaptive_views),
                    "unique_visible_partial_fraction": adaptive_audit["covered_partial_fraction"],
                    "yaw_degrees": [item["yaw_degrees"] for item in adaptive_audit["selected"]],
                },
            }
            board = render_diagnostic_board(
                partial, current, audit_views,
                output / f"round_{round_index + 1:02d}_before_board.png",
            )
            decision, gpt_plan = gpt_agent.plan(
                evidence, previous, round_index=round_index,
                maximum_rounds=args.maximum_rounds, board=board,
                recent_trace=trace, view_options=view_options,
                structural_available=args.structural_proposal_config is not None,
                plateau_streak=plateau_streak,
            )
        if decision.action not in {"UPDATE_POSTERIOR", "REFINE_OBSERVED", "STRUCTURED_DEFORMATION"}:
            trace.append({"round": round_index + 1, "decision": asdict(decision),
                          "gpt_plan": gpt_plan, "view_options": view_options})
            stop_reason = "gpt_accept" if gpt_agent is not None else decision.reason
            break
        view_policy = args.view_policy
        if gpt_plan is not None:
            view_policy = ("fixed4" if gpt_plan["decision"]["view_strategy"] == "SAVED_FOUR"
                           else "adaptive")
        if view_policy == "adaptive":
            if adaptive_views is None:
                active_views, view_audit = select_active_views(
                    partial, current, manifest, maximum_views=args.maximum_active_views,
                )
            else:
                active_views, view_audit = adaptive_views, adaptive_audit
        else:
            active_views = audit_views
            view_audit = {"method": "fixed_saved_four_views", "view_count": len(active_views)}
        view_audit["selected_by"] = "gpt" if gpt_plan is not None else "command_line"
        candidate_records = []
        accepted = False
        stop_requested = False
        candidates = [(("STRUCTURAL_EXPERT", "ORIGINAL_PRIOR")
                       if decision.action == "STRUCTURED_DEFORMATION" else
                       (("OBSERVATION_FIELD", "ALL_ACTIVE_VIEWS")
                        if decision.action == "REFINE_OBSERVED" else
                        (decision.profile, decision.transport)))]
        if decision.action == "REFINE_OBSERVED":
            candidates.append(("BALANCED", "CAMERA1"))
        elif decision.action == "STRUCTURED_DEFORMATION":
            # The strong complete-graph candidate may be wrong for an otherwise
            # well-registered object.  A rejected route must not waste the
            # remaining round budget or silently become an early stop.
            candidates.extend((("OBSERVATION_FIELD", "ALL_ACTIVE_VIEWS"),
                               ("BALANCED", "CAMERA1")))
        elif (decision.action == "UPDATE_POSTERIOR"
              and (decision.profile, decision.transport) != ("CONSERVATIVE", "CAMERA1")):
            candidates.append(("CONSERVATIVE", "CAMERA1"))
        if decision.action == "UPDATE_POSTERIOR":
            candidates.append(("OBSERVATION_FIELD", "ALL_ACTIVE_VIEWS"))
        for candidate_index, (name, transport) in enumerate(candidates):
            proposal_path = None
            field_info = None
            if name == "STRUCTURAL_EXPERT":
                try:
                    proposal, estimate, proposal_path = _structured_proposal(
                        args, initial, output / f"round_{round_index + 1:02d}_structured_expert",
                    )
                except (RuntimeError, ValueError, FileNotFoundError) as error:
                    candidate_records.append({
                        "profile": name,
                        "transport": transport,
                        "verdict": {"action": "ROLLBACK", "reason": "candidate_solver_failed"},
                        "error": f"{type(error).__name__}: {error}",
                        "proposal_cloud": None,
                    })
                    continue
            elif name == "OBSERVATION_FIELD":
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
            gpt_review = None
            proposal_board = None
            if gpt_agent is not None and verdict.action == "ACCEPT_UPDATE":
                proposal_board = render_diagnostic_board(
                    partial, proposal, audit_views,
                    output / f"round_{round_index + 1:02d}_{name.lower()}_{transport.lower()}_proposal_board.png",
                )
                gpt_review = gpt_agent.review(
                    evidence, observed, before_board=board, after_board=proposal_board,
                    profile=name, transport=transport,
                    integrity=estimate.get("integrity", {}),
                    remaining_candidates=len(candidates) - candidate_index - 1,
                    previous_candidate_results=[
                        {"profile": item["profile"], "transport": item["transport"],
                         "hard_verdict": item["verdict"]["reason"]}
                        for item in candidate_records
                    ],
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
                "gpt_review": gpt_review,
                "proposal_board": str(proposal_board) if proposal_board else None,
                "proposal_cloud": str(proposal_path) if proposal_path else None,
            })
            if gpt_review is not None and gpt_review["decision"]["action"] == "STOP_KEEP_CURRENT":
                stop_requested = True
                break
            if verdict.action == "ACCEPT_UPDATE" and (
                gpt_review is None or gpt_review["decision"]["action"] == "ACCEPT_UPDATE"
            ):
                previous, current, evidence = evidence, proposal, observed
                accepted = True
                write_points(output / f"accepted_round_{round_index + 1:02d}_100k.ply", current)
                break
        trace.append({
            "round": round_index + 1,
            "decision": asdict(decision),
            "gpt_plan": gpt_plan,
            "view_options": view_options,
            "active_views": view_audit,
            "candidates": candidate_records,
            "accepted": accepted,
            "stopped_by_gpt": stop_requested,
        })
        if stop_requested:
            stop_reason = "gpt_review_stop"
            break
        if not accepted:
            stop_reason = "all_candidates_rejected"
            trace.append({
                "round": round_index + 1,
                "decision": {"action": "ACCEPT", "profile": "NONE", "reason": "all_candidates_rejected"},
            })
            break
        plateau_streak = next_plateau_streak(previous, evidence, plateau_streak)
        trace[-1]["progress"] = {
            "coverage_gain": evidence.mean_coverage - previous.mean_coverage,
            "relative_p90_gain": (previous.partial_to_carrier_p90 - evidence.partial_to_carrier_p90)
                                 / max(previous.partial_to_carrier_p90, 1e-9),
            "relative_p99_gain": (previous.partial_to_carrier_p99 - evidence.partial_to_carrier_p99)
                                 / max(previous.partial_to_carrier_p99, 1e-9),
            "plateau_streak": plateau_streak,
        }
        if gpt_agent is not None and plateau_streak >= PLATEAU_PATIENCE:
            stop_reason = "observed_gain_plateau"
            break

    final_path = output / "agent_selected_posterior_100k.ply"
    write_points(final_path, current)
    write_compare(output / "after_partial_gray_posterior_red.ply", partial, current)
    if args.semantic is not None:
        draw_projection_overlay(
            output / "after_camera1_overlay.png", args.semantic, partial, current, camera,
        )
    audit = {
        "method": "bounded_observe_decide_act_posterior_experiment",
        "policy": f"gpt_vision_no_gt_{PROMPT_VERSION}" if gpt_agent else "deterministic_no_gt_v1",
        "gpt_model": args.gpt_model if gpt_agent else None,
        "gpt_provider": args.gpt_provider if gpt_agent else None,
        "view_policy": args.view_policy,
        "maximum_active_views": args.maximum_active_views,
        "minimum_reference_coverage": args.minimum_reference_coverage,
        "maximum_rounds": args.maximum_rounds,
        "stop_reason": stop_reason,
        "plateau_patience": PLATEAU_PATIENCE if gpt_agent is not None else None,
        "ground_truth_used": False,
        "category_or_part_rules_used": False,
        "inputs": {key: (str(value.resolve()) if value is not None else None)
                   for key in ("prior", "partial", "camera", "semantic",
                               "multiview_manifest", "config_json",
                               "structural_proposal_config")
                   for value in (getattr(args, key),)},
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
