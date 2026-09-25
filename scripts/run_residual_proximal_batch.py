#!/usr/bin/env python3
"""Run one residual-proximal posterior configuration over saved cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
INPUT_KEYS = ("prior", "partial", "camera", "semantic", "multiview_manifest")


def _load_cases(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("samples", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("case manifest must be a list or contain a 'samples' list")
    cases: list[dict[str, object]] = []
    for record in records:
        sample = str(record["sample_id"])
        paths = {key: Path(record[key]).expanduser().resolve() for key in INPUT_KEYS}
        missing = [str(value) for value in paths.values() if not value.is_file()]
        if missing:
            raise FileNotFoundError(f"{sample}: missing inputs: {missing}")
        cases.append({"sample_id": sample, "paths": paths})
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--proposal-config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--proposal-rounds", type=int, default=6)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    manifest_path = args.case_manifest.resolve()
    profile_path = args.proposal_config.resolve()
    output_root = args.output_root.resolve()
    if not profile_path.is_file():
        parser.error(f"proposal profile does not exist: {profile_path}")
    output_root.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    for case in _load_cases(manifest_path):
        sample = str(case["sample_id"])
        paths = case["paths"]
        assert isinstance(paths, dict)
        output = output_root / sample
        report = output / "residual_proximal_report.json"
        if args.resume and report.is_file():
            print(f"[reused] {sample}", flush=True)
            records.append({"sample_id": sample, "status": "reused", "output": str(output)})
            continue

        output.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(ROOT / "scripts" / "run_residual_proximal_prior_adaptation.py"),
            "--prior", str(paths["prior"]),
            "--partial", str(paths["partial"]),
            "--camera", str(paths["camera"]),
            "--semantic", str(paths["semantic"]),
            "--multiview-manifest", str(paths["multiview_manifest"]),
            "--proposal-config", str(profile_path),
            "--output-dir", str(output),
            "--proposal-rounds", str(int(args.proposal_rounds)),
            "--device", str(args.device),
        ]
        started = time.time()
        log = output / "stage.log"
        print(f"[run] {sample}", flush=True)
        with log.open("w", encoding="utf-8") as handle:
            result = subprocess.run(
                command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, text=True,
            )
        status = "completed" if result.returncode == 0 and report.is_file() else "failed"
        record = {
            "sample_id": sample,
            "status": status,
            "elapsed_seconds": time.time() - started,
            "output": str(output),
            "inputs": {key: str(value) for key, value in paths.items()},
        }
        records.append(record)
        print(f"[{status}] {sample} ({record['elapsed_seconds']:.1f}s)", flush=True)
        if status == "failed":
            break

    batch = {
        "method": "residual_guided_proximal_prior_adaptation",
        "strict_zero_shot": True,
        "ground_truth_used": False,
        "category_or_part_rules_used": False,
        "case_manifest": str(manifest_path),
        "proposal_config": str(profile_path),
        "proposal_rounds": int(args.proposal_rounds),
        "execution": "sequential_single_gpu",
        "samples": records,
    }
    (output_root / "batch_manifest.json").write_text(
        json.dumps(batch, indent=2) + "\n", encoding="utf-8",
    )
    failures = [record for record in records if record["status"] == "failed"]
    if failures:
        raise SystemExit(f"batch stopped after failure: {failures[0]['sample_id']}")


if __name__ == "__main__":
    main()
