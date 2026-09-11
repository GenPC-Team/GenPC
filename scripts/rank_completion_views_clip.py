#!/usr/bin/env python3
"""Experimental: rank geometry-pruned partial views by frozen CLIP.

The selector is category-conditional but category-agnostic: the same render,
prompt-ensemble, camera lattice and score are used for every object.  CLIP only
chooses a discrete candidate/roll; it never predicts camera parameters.

This opt-in probe is not imported by or configured as the default mainline.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw
import torch
from transformers import CLIPModel, CLIPProcessor

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.gpt_select_scansalon_view import (
    camera_parameters,
    project,
    render_depth,
    select_completion_aware_view,
)
from src.mainline_data import load_partial
from src.zbuffer import zbuffer_depth_with_indices


_CLIP_CACHE: dict[tuple[str, str], tuple[CLIPModel, CLIPProcessor]] = {}


def _load_clip(model_name: str, device: str) -> tuple[CLIPModel, CLIPProcessor]:
    """Load one frozen CLIP instance per process for efficient dataset batches."""
    key = (str(model_name), str(device))
    if key not in _CLIP_CACHE:
        processor = CLIPProcessor.from_pretrained(model_name)
        model = CLIPModel.from_pretrained(model_name, torch_dtype=torch.float16).to(device).eval()
        _CLIP_CACHE[key] = (model, processor)
    return _CLIP_CACHE[key]


def _rolled_parameters(parameters: dict, roll_degrees: float) -> dict:
    result = dict(parameters)
    forward = np.asarray(parameters["target"]) - np.asarray(parameters["eye"])
    forward /= max(float(np.linalg.norm(forward)), 1e-12)
    up = np.asarray(parameters["up"], dtype=np.float64)
    right = np.cross(forward, up)
    right /= max(float(np.linalg.norm(right)), 1e-12)
    radians = math.radians(float(roll_degrees))
    result["up"] = math.cos(radians) * up + math.sin(radians) * right
    result["roll_degrees"] = float(roll_degrees)
    return result


def _render_modalities(points: np.ndarray, parameters: dict, resolution: int) -> list[Image.Image]:
    _, uv, depth, _, _ = project(points, parameters, resolution)
    rendered, mask, _ = zbuffer_depth_with_indices(
        uv * float(resolution - 1), depth, (resolution, resolution), splat_radius=2,
    )
    if not mask.any():
        blank = Image.new("RGB", (resolution, resolution), "white")
        return [blank, blank.copy(), blank.copy()]
    values = rendered[mask]
    near, far = np.quantile(values, (.01, .99))
    unit = np.zeros_like(rendered, dtype=np.float32)
    unit[mask] = np.clip((rendered[mask] - near) / max(float(far - near), 1e-8), 0., 1.)

    shaded = np.full((resolution, resolution, 3), 255, dtype=np.uint8)
    shade = np.rint(35. + 190. * (1. - unit[mask])).astype(np.uint8)
    shaded[mask] = np.stack((shade, shade, shade), axis=1)

    coloured = np.full_like(shaded, 255)
    turbo = cv2.applyColorMap(np.rint(unit * 255.).astype(np.uint8), cv2.COLORMAP_TURBO)
    turbo = cv2.cvtColor(turbo, cv2.COLOR_BGR2RGB)
    coloured[mask] = turbo[mask]

    silhouette = np.full_like(shaded, 255)
    silhouette[mask] = 20
    return [Image.fromarray(shaded), Image.fromarray(coloured), Image.fromarray(silhouette)]


def export_selected_view(
    points: np.ndarray,
    colours: np.ndarray,
    output: Path,
    selection: dict,
    *,
    resolution: int,
    output_roll_offset_degrees: float = 180.0,
) -> dict:
    """Export one selected view with the image-coordinate upright correction.

    CLIP ranks the physical viewing direction and an in-plane roll.  The sparse
    depth raster used by the completion model has the opposite image-axis
    convention, so the final Camera-1 export applies one fixed 180-degree roll.
    Re-rendering (instead of rotating only the PNG) keeps the camera, UVs,
    depths, mask and raster mutually consistent.
    """
    selected_roll = float(selection["roll_degrees"])
    applied_roll = (selected_roll + float(output_roll_offset_degrees)) % 360.0
    parameters = _rolled_parameters(camera_parameters(
        points,
        float(selection["azimuth_degrees"]),
        float(selection["elevation_degrees"]),
        49.1,
    ), applied_roll)
    camera, _, _, _, _ = project(points, parameters, int(resolution))
    raw, depth_image, _, _, inpaint_mask, uv, point_depth, centre, scale = render_depth(
        points, colours, parameters, int(resolution),
    )
    Image.fromarray(raw).save(output / "raw_depth.png")
    Image.fromarray(depth_image).save(output / "depth.png")
    Image.fromarray(inpaint_mask).save(output / "mask.png")
    np.save(output / "point_uv.npy", uv.astype(np.float32))
    np.save(output / "camera_point_depth.npy", point_depth.astype(np.float32))
    np.save(output / "viewpoint.npy", np.asarray(parameters["eye"], dtype=np.float32))
    np.save(output / "target.npy", np.asarray(parameters["target"], dtype=np.float32))
    torch.save(camera, output / "camera.pth")
    return {
        "azimuth_degrees": float(selection["azimuth_degrees"]),
        "elevation_degrees": float(selection["elevation_degrees"]),
        "selected_roll_degrees": selected_roll,
        "output_roll_offset_degrees": float(output_roll_offset_degrees),
        "roll_degrees": applied_roll,
        "parameters": {
            key: value.tolist() if isinstance(value, np.ndarray) else value
            for key, value in parameters.items()
        },
        "projection_normalisation": {
            "xy_center_camera": centre.tolist(),
            "xy_scale_camera": float(scale),
        },
    }


def _prompt_ensemble(category: str) -> tuple[list[str], list[str]]:
    subject = category.strip()
    positive = [
        f"a clear and recognizable 3D point cloud view of {subject}",
        f"an informative view of {subject} with its overall structure easy to understand",
        f"a naturally oriented and visually interpretable {subject}",
        f"a canonical three-quarter view of {subject} with distinctive structures visually separated",
        f"a low-foreshortening view of {subject} showing its characteristic overall shape",
    ]
    negative = [
        f"an ambiguous heavily overlapping view of {subject}",
        "an unrecognizable partial point cloud",
        "an end-on degenerate view of an object",
        "a strongly foreshortened view with important structures overlapping",
        "an upside-down or unnaturally oriented object view",
    ]
    return positive, negative


def _score_batches(model, processor, images: list[Image.Image], positive: list[str],
                   negative: list[str], device: str, batch_size: int) -> np.ndarray:
    texts = positive + negative
    text_inputs = processor(text=texts, return_tensors="pt", padding=True).to(device)
    with torch.inference_mode():
        text_features = model.get_text_features(**text_inputs)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)
    scores = []
    for start in range(0, len(images), batch_size):
        inputs = processor(images=images[start:start + batch_size], return_tensors="pt").to(device)
        with torch.inference_mode():
            image_features = model.get_image_features(**inputs)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            similarity = image_features @ text_features.T
            margin = similarity[:, :len(positive)].mean(dim=1) - similarity[:, len(positive):].mean(dim=1)
        scores.append(margin.float().cpu().numpy())
    return np.concatenate(scores)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="openai/clip-vit-large-patch14-336")
    parser.add_argument("--geometry-top-k", type=int, default=36)
    parser.add_argument("--render-resolution", type=int, default=336)
    parser.add_argument("--output-resolution", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--output-roll-offset-degrees", type=float, default=180.0)
    args = parser.parse_args(argv)

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    points, colours = load_partial(args.partial.resolve())
    _, geometry_ranking = select_completion_aware_view(points, resolution=160)
    candidates = geometry_ranking[:max(1, int(args.geometry_top_k))]
    rolls = (0., 90., 180., 270.)
    records, images = [], []
    for candidate in candidates:
        base = camera_parameters(
            points, candidate["azimuth_degrees"], candidate["elevation_degrees"], 49.1,
        )
        for roll in rolls:
            parameters = _rolled_parameters(base, roll)
            modalities = _render_modalities(points, parameters, int(args.render_resolution))
            start = len(images)
            images.extend(modalities)
            records.append({
                "azimuth_degrees": candidate["azimuth_degrees"],
                "elevation_degrees": candidate["elevation_degrees"],
                "roll_degrees": roll,
                "geometry_rank": candidate["rank"],
                "geometry_score": candidate["completion_view_score"],
                "image_indices": list(range(start, start + len(modalities))),
                "parameters": parameters,
            })

    model, processor = _load_clip(args.model, args.device)
    positive, negative = _prompt_ensemble(args.category)
    modality_scores = _score_batches(
        model, processor, images, positive, negative, args.device, int(args.batch_size),
    )
    clip_values = np.asarray([
        float(np.mean(modality_scores[record["image_indices"]])) for record in records
    ])
    clip_min, clip_max = float(clip_values.min()), float(clip_values.max())
    for record, clip_score in zip(records, clip_values):
        clip_rank = (float(clip_score) - clip_min) / max(clip_max - clip_min, 1e-12)
        record["clip_margin"] = float(clip_score)
        record["clip_rank_normalised"] = clip_rank
        record["combined_score"] = .72 * clip_rank + .28 * float(record["geometry_score"])
        record.pop("image_indices")
        record["parameters"] = {
            key: value.tolist() if isinstance(value, np.ndarray) else value
            for key, value in record["parameters"].items()
        }
    records.sort(key=lambda item: item["combined_score"], reverse=True)
    for rank, record in enumerate(records, 1):
        record["rank"] = rank

    best = records[0]
    output_view = export_selected_view(
        points,
        colours,
        output,
        best,
        resolution=int(args.output_resolution),
        output_roll_offset_degrees=float(args.output_roll_offset_degrees),
    )

    top = records[:12]
    cell = 224
    sheet = Image.new("RGB", (4 * cell, 3 * cell), "white")
    for index, record in enumerate(top):
        params = _rolled_parameters(camera_parameters(
            points, record["azimuth_degrees"], record["elevation_degrees"], 49.1,
        ), record["roll_degrees"])
        panel = _render_modalities(points, params, cell)[0]
        draw = ImageDraw.Draw(panel)
        draw.rectangle((0, 0, cell, 22), fill="black")
        draw.text((4, 4), f"#{index+1} az{record['azimuth_degrees']:.0f} el{record['elevation_degrees']:.0f} r{record['roll_degrees']:.0f}", fill="white")
        sheet.paste(panel, ((index % 4) * cell, (index // 4) * cell))
    sheet.save(output / "clip_top12.png")

    manifest = {
        "method": "geometry_pruned_clip_explainability_with_roll",
        "ground_truth_used": False,
        "partial": str(args.partial.resolve()),
        "category": args.category,
        "model": args.model,
        "positive_prompts": positive,
        "negative_prompts": negative,
        "best": best,
        "output_view": output_view,
        "projection_normalisation": output_view["projection_normalisation"],
        "ranking": records,
    }
    (output / "clip_view_ranking.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "best": best, "top12": str(output / 'clip_top12.png')}, indent=2))


if __name__ == "__main__":
    main()
