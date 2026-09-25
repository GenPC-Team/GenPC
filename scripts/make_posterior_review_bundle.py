#!/usr/bin/env python3
"""Create a compact, human-readable view of posterior experiment outputs.

The bundle contains relative symlinks, so it adds negligible storage and never
modifies or deletes the complete audit artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


REVIEW_FILES = (
    ("posterior_prior_100k.ply", "01_final_posterior.ply"),
    ("partial_gray_registered_red.ply", "02_before_registered_partial_overlay.ply"),
    ("partial_gray_posterior_red.ply", "03_after_posterior_partial_overlay.ply"),
    ("posterior_saved_view_projection.png", "04_camera1_projection.png"),
    ("posterior_virtual_views.png", "05_multiview_projection.png"),
    ("posterior_info.json", "06_run_info.json"),
)

RESIDUAL_PROXIMAL_REVIEW_FILES = (
    ("prior_projection/posterior_expert_distilled_100k.ply", "01_final_posterior.ply"),
    ("prior_projection/partial_gray_registered_prior_red.ply", "02_before_registered_partial_overlay.ply"),
    ("prior_projection/partial_gray_posterior_expert_distilled_red.ply", "03_after_posterior_partial_overlay.ply"),
    ("prior_projection/posterior_saved_view_projection.png", "04_camera1_projection.png"),
    ("prior_projection/posterior_expert_distilled_views.png", "05_multiview_projection.png"),
    ("prior_projection/expert_distillation_report.json", "06_run_info.json"),
)


def _relative_link(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.exists():
        destination.unlink()
    destination.symlink_to(os.path.relpath(source.resolve(), destination.parent.resolve()))


def _preferred_roots(values: list[str]) -> dict[str, Path]:
    roots = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"preferred result must use SAMPLE=PATH syntax: {value}")
        sample, path = value.split("=", 1)
        roots[str(sample)] = Path(path).expanduser().resolve()
    return roots


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--datasets", nargs="+", default=("redwood", "custom"))
    parser.add_argument(
        "--preferred", action="append", default=[], metavar="SAMPLE=PATH",
        help=(
            "Use a validated residual-proximal result for one sample while keeping "
            "the same compact review contract. May be repeated."
        ),
    )
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    preferred = _preferred_roots(args.preferred)
    records = []
    for dataset in args.datasets:
        dataset_root = source_root / dataset
        if not dataset_root.is_dir():
            raise FileNotFoundError(dataset_root)
        for sample_root in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
            if not (sample_root / REVIEW_FILES[0][0]).is_file():
                continue
            selected_root = preferred.get(sample_root.name, sample_root)
            review_files = (
                RESIDUAL_PROXIMAL_REVIEW_FILES
                if selected_root != sample_root else REVIEW_FILES
            )
            if not (selected_root / review_files[0][0]).is_file():
                raise FileNotFoundError(
                    f"preferred result for {sample_root.name} has no final posterior: "
                    f"{selected_root / review_files[0][0]}"
                )
            review_root = output_root / dataset / sample_root.name
            expected_names = {review_name for _, review_name in review_files}
            if review_root.is_dir():
                for existing in review_root.iterdir():
                    if existing.is_symlink() and existing.name not in expected_names:
                        existing.unlink()
            linked = []
            for source_name, review_name in review_files:
                source = selected_root / source_name
                if source.is_file():
                    destination = review_root / review_name
                    _relative_link(source, destination)
                    linked.append(review_name)
            records.append({
                "dataset": dataset,
                "sample_id": sample_root.name,
                "source": str(selected_root),
                "preferred_override": bool(selected_root != sample_root),
                "review": str(review_root),
                "files": linked,
            })
    readme = """# Posterior 精简查看入口

这里仅保留人工检查需要的文件，并使用相对软链接指向完整实验，因此不会重复占用点云空间。

每个样本按下面的顺序查看：

1. `01_final_posterior.ply` — 最终完整 100k 形变点云；
2. `02_before_registered_partial_overlay.ply` — 灰色 partial 与红色配准 prior；
3. `03_after_posterior_partial_overlay.ply` — 灰色 partial 与红色形变 posterior；
4. `04_camera1_projection.png` — 物理 Camera-1 下的覆盖情况；
5. `05_multiview_projection.png` — 辅助多视角覆盖情况；
6. `06_run_info.json` — 参数和数值审计，通常不需要打开。

coarse carrier、support mask、OT pair 和完整形变场属于 debug 产物，故意不放在这里。
"""
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "README.md").write_text(readme, encoding="utf-8")
    (output_root / "index.json").write_text(
        json.dumps({"source_root": str(source_root), "samples": records}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output_root": str(output_root), "samples": len(records)}, indent=2))


if __name__ == "__main__":
    main()
