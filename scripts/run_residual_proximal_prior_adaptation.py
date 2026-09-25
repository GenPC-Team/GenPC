#!/usr/bin/env python3
"""Run observation proposal and complete-prior projection as one TTO method.

The public inputs are only a registered complete prior, a partial observation,
and its saved cameras.  A high-gain local-fit carrier is generated internally
and immediately projected back onto the complete prior's structural support.
Ground truth, categories, and semantic part labels are never read.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--camera", type=Path, required=True)
    parser.add_argument("--semantic", type=Path, required=True)
    parser.add_argument("--multiview-manifest", type=Path, required=True)
    parser.add_argument("--proposal-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--proposal-rounds", type=int, default=6)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--trajectory-steps", type=int, default=17)
    parser.add_argument("--trajectory-tolerance-spacing", type=float, default=.20)
    parser.add_argument("--cohort-radius-spacing", type=float, default=5.0)
    parser.add_argument("--cohort-minimum-motion-spacing", type=float, default=.75)
    parser.add_argument("--minimum-hidden-coverage", type=float, default=.90)
    parser.add_argument("--low-frequency-structural-motion", action="store_true")
    args = parser.parse_args()

    output = args.output_dir.resolve()
    proposal_dir = output / "internal_observation_proposal"
    final_dir = output / "prior_projection"
    output.mkdir(parents=True, exist_ok=True)

    _run([
        sys.executable,
        str(ROOT / "scripts" / "iterative_posterior_tto.py"),
        "--prior", str(args.prior.resolve()),
        "--partial", str(args.partial.resolve()),
        "--camera", str(args.camera.resolve()),
        "--semantic", str(args.semantic.resolve()),
        "--multiview-manifest", str(args.multiview_manifest.resolve()),
        "--config-json", str(args.proposal_config.resolve()),
        "--output-dir", str(proposal_dir),
        "--outer-rounds", str(int(args.proposal_rounds)),
        "--device", str(args.device),
    ])
    proposal = proposal_dir / f"round_{int(args.proposal_rounds):02d}" / "posterior_prior_100k.ply"
    if not proposal.exists():
        raise FileNotFoundError(f"internal proposal was not generated: {proposal}")

    projection_command = [
        sys.executable,
        str(ROOT / "scripts" / "distill_visibility_gated_expert.py"),
        "--reference", str(args.prior.resolve()),
        "--expert", str(proposal),
        "--partial", str(args.partial.resolve()),
        "--multiview-manifest", str(args.multiview_manifest.resolve()),
        "--output-dir", str(final_dir),
        "--residual-quantile", "0.10",
        "--minimum-improvement-spacing", "0.25",
        "--teacher-visibility-dilation-spacing", "0.0",
        "--trajectory-steps", str(int(args.trajectory_steps)),
        "--trajectory-tolerance-spacing", str(float(args.trajectory_tolerance_spacing)),
        "--cohort-radius-spacing", str(float(args.cohort_radius_spacing)),
        "--cohort-minimum-motion-spacing", str(float(args.cohort_minimum_motion_spacing)),
        "--transition-spacing", "10.0",
        "--transition-motion", "1.25",
        "--transition-diagonal", "0.04",
        "--minimum-hidden-coverage", str(float(args.minimum_hidden_coverage)),
        "--minimum-edge-compression", "0.34",
        "--node-minimum-edge-compression", "0.20",
    ]
    if bool(args.low_frequency_structural_motion):
        projection_command.append("--low-frequency-structural-motion")
    _run(projection_command)

    record = {
        "method": "residual_guided_proximal_prior_adaptation",
        "strict_zero_shot": True,
        "ground_truth_used": False,
        "external_inputs": {
            "prior": str(args.prior.resolve()),
            "partial": str(args.partial.resolve()),
            "camera": str(args.camera.resolve()),
            "semantic": str(args.semantic.resolve()),
            "multiview_manifest": str(args.multiview_manifest.resolve()),
        },
        "internal_observation_proposal": str(proposal),
        "final_posterior": str(final_dir / "posterior_expert_distilled_100k.ply"),
        "proposal_rounds": int(args.proposal_rounds),
        "low_frequency_structural_motion": bool(args.low_frequency_structural_motion),
        "note": (
            "The aggressive carrier is an internal proposal state, not an "
            "external method input or released output contract."
        ),
    }
    (output / "residual_proximal_report.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
