#!/usr/bin/env python3
"""Run a saved depth image through two controlled Qwen completion prompts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qwen_image_edit import QwenImageEdit, build_completion_prompt


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def geometry_prompt(label: str) -> str:
    return (
        "生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述："
        f"完整自然的{label}，保持图1可见区域的轮廓、姿态、朝向和前后深度关系，"
        "合理补全未观测区域，纯白背景"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--transformer", type=Path, default=Path("models/nunchaku-qwen-image-edit/nunchaku_qwen_image_2511_balance_int4.safetensors"))
    parser.add_argument("--pipeline", type=Path, default=Path("models/Qwen-Image-Edit-2511"))
    parser.add_argument("--seed", type=int, default=6145)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--modes", choices=("baseline", "geometry"), nargs="+", default=("baseline", "geometry"))
    args = parser.parse_args()

    depth = args.depth.resolve(strict=True)
    transformer = args.transformer.resolve(strict=True)
    pipeline_path = args.pipeline.resolve(strict=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    input_image = Image.open(depth).convert("RGB")
    prompts = {
        "baseline": build_completion_prompt(args.label),
        "geometry": geometry_prompt(args.label),
    }
    editor = QwenImageEdit(
        device="cuda", transformer_path=transformer, pipeline_path=pipeline_path,
        step=args.steps, generation_size=1024, true_cfg_scale=4.0,
        negative_prompt=" ", cpu_offload=True,
    )
    try:
        for mode in args.modes:
            case_dir = output / mode
            case_dir.mkdir(parents=True, exist_ok=True)
            prompt = prompts[mode]
            (case_dir / "qwen_prompt.txt").write_text(prompt + "\n", encoding="utf-8")
            result = editor.generate_with_prompt(input_image, prompt, size=args.size, seed=args.seed)
            result_path = case_dir / "semantic.png"
            result.save(result_path)
            if editor.last_stage1_image is not None:
                editor.last_stage1_image.save(case_dir / "semantic_native.png")
            record = {
                "input_depth": str(depth), "input_depth_sha256": sha256(depth),
                "input_size": input_image.size, "label": args.label,
                "prompt": prompt, "negative_prompt": " ", "mode": mode,
                "transformer": str(transformer), "pipeline": str(pipeline_path),
                "seed": args.seed, "steps": args.steps, "true_cfg_scale": 4.0,
                "requested_output_size": args.size, "native_output_size": editor.last_stage1_image.size,
                "resampling": "PIL LANCZOS when native image differs from requested output size",
                "output": str(result_path), "output_sha256": sha256(result_path),
                "ground_truth_used": False,
            }
            (case_dir / "generation.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps({"mode": mode, "output": str(result_path)}, ensure_ascii=False), flush=True)
    finally:
        editor.close()


if __name__ == "__main__":
    main()
