#!/usr/bin/env python3
"""Create publication figures for residual-calibrated posterior deformation.

The figures use only the registered prior, partial observation, accepted
posterior, saved cameras, and solver support sets.  They do not use ground
truth.  Rasterization is deterministic and camera-consistent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multiview_partial_evidence import load_manifest_projectors
from src.multiview_proximal_tto import _median_spacing
from src.pointcloud_io import load_points
from src.zbuffer import zbuffer_depth_with_indices


BACKGROUND = np.asarray([0.018, 0.021, 0.027])
PRIOR = np.asarray([0.88, 0.25, 0.20])
PARTIAL = np.asarray([0.16, 0.78, 0.98])
POSTERIOR = np.asarray([0.90, 0.92, 0.95])
FIXED = np.asarray([0.23, 0.26, 0.31])
CORE = np.asarray([0.10, 0.78, 0.92])
COHORT = np.asarray([0.96, 0.45, 0.18])
TRANSITION = np.asarray([0.69, 0.39, 0.91])


def _style() -> None:
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Nimbus Roman", "Times New Roman", "Times", "DejaVu Serif"],
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "figure.facecolor": BACKGROUND,
        "axes.facecolor": BACKGROUND,
        "savefig.facecolor": BACKGROUND,
        "text.color": "white",
        "axes.labelcolor": "white",
        "xtick.color": "white",
        "ytick.color": "white",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def _visible(points: np.ndarray, projector, *, splat_radius: int = 1):
    uv, depth = projector.project(points)
    _, mask, indices = zbuffer_depth_with_indices(
        uv, depth, projector.image_shape, splat_radius=splat_radius,
    )
    return uv, depth, mask, indices


def _solid_layer(points: np.ndarray, projector, color: np.ndarray, *, radius: int = 1):
    _, _, mask, indices = _visible(points, projector, splat_radius=radius)
    image = np.broadcast_to(BACKGROUND, (*mask.shape, 3)).copy()
    image[mask] = color
    return image, mask, indices


def _blend_layers(base_image, base_mask, top_image, top_mask, *, top_alpha=.88):
    image = base_image.copy()
    image[top_mask] = top_image[top_mask]
    overlap = base_mask & top_mask
    image[overlap] = (
        (1.0 - top_alpha) * base_image[overlap]
        + top_alpha * top_image[overlap]
    )
    return image


def _partial_silhouette(partial: np.ndarray, projector) -> tuple[np.ndarray, np.ndarray]:
    """Return a coherent display-only silhouette and its thin boundary."""
    _, mask, _ = _solid_layer(partial, projector, PARTIAL, radius=2)
    silhouette = ndimage.binary_closing(mask, iterations=2)
    silhouette = ndimage.binary_fill_holes(silhouette)
    boundary = ndimage.binary_dilation(silhouette, iterations=1) ^ ndimage.binary_erosion(
        silhouette, iterations=1,
    )
    return silhouette, boundary


def _overlay(prior: np.ndarray, partial: np.ndarray, projector, *, prior_color: np.ndarray):
    prior_image, prior_mask, _ = _solid_layer(prior, projector, prior_color, radius=1)
    partial_mask, boundary = _partial_silhouette(partial, projector)
    image = prior_image.copy()
    image[boundary] = PARTIAL
    return image, partial_mask


def _field_image(
    points: np.ndarray,
    values: np.ndarray,
    projector,
    *,
    cmap,
    vmin: float,
    vmax: float,
    partial: np.ndarray | None = None,
):
    _, _, mask, indices = _visible(points, projector, splat_radius=1)
    image = np.broadcast_to(BACKGROUND, (*mask.shape, 3)).copy()
    norm = mpl.colors.Normalize(vmin=vmin, vmax=max(vmax, vmin + 1e-9), clip=True)
    image[mask] = cmap(norm(values[indices[mask]]))[:, :3]
    if partial is not None:
        _, outline = _partial_silhouette(partial, projector)
        image[outline] = PARTIAL
    return image


def _camera_residual(
    prior: np.ndarray,
    partial: np.ndarray,
    projector,
) -> np.ndarray:
    prior_uv, prior_depth, prior_mask, prior_indices = _visible(prior, projector)
    partial_uv, partial_depth, partial_mask, partial_indices = _visible(partial, projector)
    prior_ids = np.unique(prior_indices[prior_mask])
    partial_ids = np.unique(partial_indices[partial_mask])
    residual = np.full(len(prior), np.nan, dtype=np.float64)
    if not len(prior_ids) or not len(partial_ids):
        return residual
    resolution = float(projector.image_shape[0])
    valid_depth = partial_depth[partial_ids]
    depth_scale = max(float(np.quantile(valid_depth, .95) - np.quantile(valid_depth, .05)), 1e-9)
    feature_partial = np.column_stack((
        partial_uv[partial_ids] / resolution,
        partial_depth[partial_ids, None] / depth_scale,
    ))
    feature_prior = np.column_stack((
        prior_uv[prior_ids] / resolution,
        prior_depth[prior_ids, None] / depth_scale,
    ))
    residual[prior_ids] = cKDTree(feature_partial).query(
        feature_prior, k=1, workers=-1,
    )[0]
    return residual


def _map_saved_points(reference: np.ndarray, saved: np.ndarray, *, tolerance: float) -> np.ndarray:
    mask = np.zeros(len(reference), dtype=bool)
    if not len(saved):
        return mask
    distance, ids = cKDTree(reference).query(saved, k=1, workers=-1)
    mask[ids[distance <= tolerance]] = True
    return mask


def _save(fig, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=360, bbox_inches="tight", pad_inches=.04)
    fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight", pad_inches=.04)
    plt.close(fig)


def _clean_axis(axis, title: str | None = None) -> None:
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)
    if title:
        axis.set_title(title, pad=5, fontweight="normal")


def _plot_before_after(reference, posterior, partial, projectors, names, output):
    for projector, name in zip(projectors, names):
        before, _ = _overlay(reference, partial, projector, prior_color=PRIOR)
        after, _ = _overlay(posterior, partial, projector, prior_color=POSTERIOR)
        for label, image, color, title in (
            ("before", before, PRIOR, "Registered complete prior"),
            ("after", after, POSTERIOR, "Adapted complete posterior"),
        ):
            fig, axis = plt.subplots(figsize=(5.2, 5.0))
            axis.imshow(image)
            _clean_axis(axis, f"{title} — {name.replace('_', ' ').title()} view")
            handles = [
                Line2D([0], [0], marker="o", color="none", markerfacecolor=color,
                       markersize=6, label=title),
                Line2D([0], [0], marker="o", color="none", markerfacecolor=PARTIAL,
                       markersize=6, label="Observed partial"),
            ]
            fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False,
                       bbox_to_anchor=(.5, .01), labelcolor="white")
            fig.subplots_adjust(bottom=.09)
            _save(fig, output / f"{label}_{name}.png")


def _plot_residual_evidence(reference, partial, projectors, names, output):
    residuals = [_camera_residual(reference, partial, projector) for projector in projectors]
    finite = np.concatenate([value[np.isfinite(value)] for value in residuals])
    vmax = float(np.quantile(finite, .95)) if len(finite) else 1.0
    cmap = mpl.colormaps["magma"]
    for projector, name, residual in zip(projectors, names, residuals):
        fig, axis = plt.subplots(figsize=(5.2, 5.0))
        fill = np.nan_to_num(residual, nan=vmax)
        axis.imshow(_field_image(
            reference, fill, projector, cmap=cmap, vmin=0., vmax=vmax, partial=partial,
        ))
        _clean_axis(axis, f"Observation residual — {name.replace('_', ' ').title()} view")
        scalar = mpl.cm.ScalarMappable(norm=mpl.colors.Normalize(0., vmax), cmap=cmap)
        colorbar = fig.colorbar(scalar, ax=axis, fraction=.046, pad=.025)
        colorbar.set_label("Normalized pixel-depth residual")
        colorbar.ax.tick_params(colors="white")
        colorbar.outline.set_edgecolor((1, 1, 1, .25))
        _save(fig, output / f"residual_{name}.png")


def _plot_support_states(
    reference, partial, projectors, names, core, cohort, transition, output,
):
    state = np.zeros(len(reference), dtype=np.int64)
    state[transition] = 1
    state[cohort] = 2
    state[core] = 3
    colors = np.vstack([FIXED, TRANSITION, COHORT, CORE])
    for index, (projector, name) in enumerate(zip(projectors, names)):
        fig, axis = plt.subplots(figsize=(5.2, 5.0))
        _, _, mask, indices = _visible(reference, projector)
        image = np.broadcast_to(BACKGROUND, (*mask.shape, 3)).copy()
        image[mask] = colors[state[indices[mask]]]
        _, outline = _partial_silhouette(partial, projector)
        image[outline] = PARTIAL
        axis.imshow(image)
        _clean_axis(axis, f"Posterior support state — {name.replace('_', ' ').title()} view")
        handles = [
            Line2D([0], [0], marker="o", color="none", markerfacecolor=CORE,
                   markersize=6, label="Observed target"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor=COHORT,
                   markersize=6, label="Structural cohort"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor=TRANSITION,
                   markersize=6, label="ARAP transition"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor=FIXED,
                   markersize=6, label="Protected prior"),
            Line2D([0], [0], color=PARTIAL, lw=2, label="Partial silhouette"),
        ]
        fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False,
                   bbox_to_anchor=(.5, .00), labelcolor="white")
        fig.subplots_adjust(bottom=.15)
        _save(fig, output / f"support_{name}.png")


def _plot_deformation_magnitude(reference, posterior, partial, projectors, names, spacing, output):
    displacement = np.linalg.norm(posterior - reference, axis=1) / spacing
    vmax = float(np.quantile(displacement[displacement > 0], .98))
    cmap = mpl.colormaps["turbo"]
    for projector, name in zip(projectors, names):
        fig, axis = plt.subplots(figsize=(5.2, 5.0))
        axis.imshow(_field_image(
            posterior, displacement, projector, cmap=cmap, vmin=0., vmax=vmax,
            partial=partial,
        ))
        _clean_axis(axis, f"Posterior displacement — {name.replace('_', ' ').title()} view")
        scalar = mpl.cm.ScalarMappable(norm=mpl.colors.Normalize(0., vmax), cmap=cmap)
        colorbar = fig.colorbar(scalar, ax=axis, fraction=.046, pad=.025)
        colorbar.set_label("Displacement / median spacing")
        colorbar.ax.tick_params(colors="white")
        colorbar.outline.set_edgecolor((1, 1, 1, .25))
        _save(fig, output / f"displacement_{name}.png")


def _plot_deformation_demand(
    reference, posterior, partial, projectors, names, spacing, output,
):
    """Map the accepted posterior update back onto the undeformed prior."""
    displacement = np.linalg.norm(posterior - reference, axis=1) / spacing
    positive = displacement[displacement > 0]
    vmax = float(np.quantile(positive, .98)) if len(positive) else 1.0
    norm = mpl.colors.Normalize(0., vmax, clip=True)
    cmap = mpl.colormaps["turbo"]
    for projector, name in zip(projectors, names):
        fig, axis = plt.subplots(figsize=(5.2, 5.0))
        axis.imshow(_field_image(
            reference, displacement, projector, cmap=cmap, vmin=0., vmax=vmax,
            partial=partial,
        ))
        _clean_axis(axis, f"Deformation demand — {name.replace('_', ' ').title()} view")
        scalar = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
        colorbar = fig.colorbar(scalar, ax=axis, fraction=.046, pad=.025)
        colorbar.set_label("Required displacement / median spacing")
        colorbar.ax.tick_params(colors="white")
        colorbar.outline.set_edgecolor((1, 1, 1, .25))
        _save(fig, output / f"deformation_demand_{name}.png")


def _select_vector_samples(
    reference, posterior, projector, magnitude, *, cell: int = 18,
    minimum_magnitude: float = .5,
):
    """Choose one visible, high-motion carrier per image cell."""
    uv0, depth0, visible_mask, visible_indices = _visible(
        reference, projector, splat_radius=1,
    )
    uv1, depth1 = projector.project(posterior)
    visible_ids = np.unique(visible_indices[visible_mask])
    valid = np.zeros(len(reference), dtype=bool)
    valid[visible_ids] = True
    valid &= (
        (depth0 > 0) & (depth1 > 0)
        & (uv1[:, 0] >= 0) & (uv1[:, 0] < projector.image_shape[1])
        & (uv1[:, 1] >= 0) & (uv1[:, 1] < projector.image_shape[0])
    )
    valid_ids = np.flatnonzero(valid & (magnitude >= minimum_magnitude))
    if not len(valid_ids):
        return uv0, uv1, np.empty(0, dtype=np.int64)
    pixel_motion = np.linalg.norm(uv1 - uv0, axis=1)
    xy = np.floor(uv0[valid_ids] / cell).astype(np.int64)
    key = xy[:, 1] * 10000 + xy[:, 0]
    order = np.lexsort((-pixel_motion[valid_ids], key))
    sorted_key = key[order]
    first = np.r_[True, sorted_key[1:] != sorted_key[:-1]]
    return uv0, uv1, valid_ids[order[first]]


def _plot_deformation_direction(
    reference, posterior, partial, projectors, names, spacing, output,
):
    """Render the accepted 3D prior-to-posterior update as 2D vector fields."""
    magnitude = np.linalg.norm(posterior - reference, axis=1) / spacing
    positive = magnitude[magnitude > 0]
    vmax = float(np.quantile(positive, .98)) if len(positive) else 1.0
    norm = mpl.colors.Normalize(0., vmax, clip=True)
    cmap = mpl.colormaps["turbo"]
    for projector, name in zip(projectors, names):
        uv0, uv1, chosen = _select_vector_samples(
            reference, posterior, projector, magnitude,
        )
        fig, axis = plt.subplots(figsize=(5.2, 5.0))
        prior_image, _, _ = _solid_layer(reference, projector, FIXED * .72, radius=1)
        axis.imshow(prior_image)
        if len(chosen):
            delta = uv1[chosen] - uv0[chosen]
            axis.quiver(
                uv0[chosen, 0], uv0[chosen, 1], delta[:, 0], delta[:, 1],
                magnitude[chosen], cmap=cmap, norm=norm,
                angles="xy", scale_units="xy", scale=1., pivot="tail",
                width=.0042, headwidth=3.7, headlength=4.8,
                headaxislength=4.2, alpha=.94, zorder=3,
            )
        partial_mask, outline = _partial_silhouette(partial, projector)
        outline_image = np.zeros((*partial_mask.shape, 4), dtype=np.float64)
        outline_image[outline, :3] = PARTIAL
        outline_image[outline, 3] = 1.0
        axis.imshow(outline_image)
        _clean_axis(axis, f"Deformation direction — {name.replace('_', ' ').title()} view")
        scalar = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
        colorbar = fig.colorbar(scalar, ax=axis, fraction=.046, pad=.025)
        colorbar.set_label("Displacement / median spacing")
        colorbar.ax.tick_params(colors="white")
        colorbar.outline.set_edgecolor((1, 1, 1, .25))
        _save(fig, output / f"deformation_direction_{name}.png")


def _plot_deformation_direction_multiview(
    reference, posterior, partial, projectors, spacing, output,
):
    """Combine four camera-consistent direction fields without panel titles."""
    magnitude = np.linalg.norm(posterior - reference, axis=1) / spacing
    positive = magnitude[magnitude > 0]
    vmax = float(np.quantile(positive, .98)) if len(positive) else 1.0
    norm = mpl.colors.Normalize(0., vmax, clip=True)
    cmap = mpl.colormaps["turbo"]
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 9.8))
    for axis, projector in zip(axes.flat, projectors[:4]):
        uv0, uv1, chosen = _select_vector_samples(
            reference, posterior, projector, magnitude,
        )
        prior_image, _, _ = _solid_layer(reference, projector, FIXED * .72, radius=1)
        axis.imshow(prior_image)
        if len(chosen):
            delta = uv1[chosen] - uv0[chosen]
            axis.quiver(
                uv0[chosen, 0], uv0[chosen, 1], delta[:, 0], delta[:, 1],
                magnitude[chosen], cmap=cmap, norm=norm,
                angles="xy", scale_units="xy", scale=1., pivot="tail",
                width=.0042, headwidth=3.7, headlength=4.8,
                headaxislength=4.2, alpha=.94, zorder=3,
            )
        partial_mask, outline = _partial_silhouette(partial, projector)
        outline_image = np.zeros((*partial_mask.shape, 4), dtype=np.float64)
        outline_image[outline, :3] = PARTIAL
        outline_image[outline, 3] = 1.0
        axis.imshow(outline_image)
        _clean_axis(axis)
    for axis in axes.flat[len(projectors[:4]):]:
        axis.set_visible(False)
    scalar = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    colorbar = fig.colorbar(
        scalar, ax=list(axes.flat), fraction=.026, pad=.012, aspect=38,
    )
    colorbar.ax.tick_params(colors="white")
    colorbar.outline.set_edgecolor((1, 1, 1, .25))
    fig.subplots_adjust(left=.002, right=.91, bottom=.002, top=.998, wspace=.006, hspace=.006)
    _save(fig, output)


def _plot_vector_field(reference, posterior, partial, projectors, names, spacing, output):
    best_index = 0
    best_score = -np.inf
    projections = []
    for index, projector in enumerate(projectors):
        uv0, depth0 = projector.project(reference)
        uv1, depth1 = projector.project(posterior)
        valid = (
            (depth0 > 0) & (depth1 > 0)
            & (uv0[:, 0] >= 0) & (uv0[:, 0] < projector.image_shape[1])
            & (uv0[:, 1] >= 0) & (uv0[:, 1] < projector.image_shape[0])
            & (uv1[:, 0] >= 0) & (uv1[:, 0] < projector.image_shape[1])
            & (uv1[:, 1] >= 0) & (uv1[:, 1] < projector.image_shape[0])
        )
        pixel_motion = np.linalg.norm(uv1 - uv0, axis=1)
        score = float(np.quantile(pixel_motion[valid], .90)) if valid.any() else -np.inf
        projections.append((uv0, uv1, valid, pixel_motion))
        if score > best_score:
            best_score, best_index = score, index
    projector = projectors[best_index]
    uv0, uv1, valid, pixel_motion = projections[best_index]
    magnitude = np.linalg.norm(posterior - reference, axis=1) / spacing
    # One maximum-motion representative per image cell keeps the field legible.
    cell = 18
    xy = np.floor(uv0[valid] / cell).astype(np.int64)
    valid_ids = np.flatnonzero(valid)
    key = xy[:, 1] * 10000 + xy[:, 0]
    order = np.lexsort((-pixel_motion[valid_ids], key))
    sorted_key = key[order]
    first = np.r_[True, sorted_key[1:] != sorted_key[:-1]]
    chosen = valid_ids[order[first]]
    chosen = chosen[magnitude[chosen] >= .5]
    segments = np.stack([uv0[chosen], uv1[chosen]], axis=1)
    vmax = float(np.quantile(magnitude[chosen], .98)) if len(chosen) else 1.0
    norm = mpl.colors.Normalize(0., vmax, clip=True)
    cmap = mpl.colormaps["turbo"]

    fig, axis = plt.subplots(figsize=(6.2, 5.7))
    prior_image, _, _ = _solid_layer(reference, projector, FIXED * .72, radius=1)
    axis.imshow(prior_image)
    collection = LineCollection(
        segments, colors=cmap(norm(magnitude[chosen])), linewidths=1.15, alpha=.90,
    )
    axis.add_collection(collection)
    axis.scatter(uv1[chosen, 0], uv1[chosen, 1], c=cmap(norm(magnitude[chosen])),
                 s=4.0, linewidths=0, zorder=3)
    partial_mask, outline = _partial_silhouette(partial, projector)
    outline_image = np.zeros((*partial_mask.shape, 4), dtype=np.float64)
    outline_image[outline, :3] = PARTIAL
    outline_image[outline, 3] = 1.0
    axis.imshow(outline_image)
    _clean_axis(axis, f"Continuous deformation field — {names[best_index].title()} view")
    scalar = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    colorbar = fig.colorbar(scalar, ax=axis, fraction=.046, pad=.025)
    colorbar.set_label("Displacement / median spacing")
    colorbar.ax.tick_params(colors="white")
    colorbar.outline.set_edgecolor((1, 1, 1, .25))
    _save(fig, output)
    return names[best_index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--posterior", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--core-points", type=Path, required=True)
    parser.add_argument("--cohort-points", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=512)
    args = parser.parse_args()
    _style()

    reference = load_points(args.reference)
    posterior = load_points(args.posterior)
    partial = load_points(args.partial)
    if reference.shape != posterior.shape:
        raise ValueError("reference and posterior must be ordered carriers")
    spacing = _median_spacing(reference)
    core = _map_saved_points(reference, load_points(args.core_points), tolerance=.05 * spacing)
    cohort = _map_saved_points(reference, load_points(args.cohort_points), tolerance=.05 * spacing)
    displacement = np.linalg.norm(posterior - reference, axis=1)
    transition = (displacement >= .25 * spacing) & ~core & ~cohort
    projectors = load_manifest_projectors(args.manifest, resolution=args.resolution)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    names = [str(item.get("name", f"view-{index + 1}")) for index, item in enumerate(manifest["views"])]
    names = names[:len(projectors)]
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    _plot_before_after(
        reference, posterior, partial, projectors, names,
        output,
    )
    _plot_residual_evidence(
        reference, partial, projectors, names,
        output,
    )
    _plot_support_states(
        reference, partial, projectors, names, core, cohort, transition,
        output,
    )
    _plot_deformation_magnitude(
        reference, posterior, partial, projectors, names, spacing,
        output,
    )
    _plot_deformation_demand(
        reference, posterior, partial, projectors, names, spacing,
        output,
    )
    _plot_deformation_direction(
        reference, posterior, partial, projectors, names, spacing,
        output,
    )
    _plot_deformation_direction_multiview(
        reference, posterior, partial, projectors, spacing,
        output / "deformation_direction_multiview.png",
    )
    field_view = _plot_vector_field(
        reference, posterior, partial, projectors, names, spacing,
        output / "continuous_deformation_field.png",
    )
    report = {
        "ground_truth_used": False,
        "reference": str(args.reference.resolve()),
        "posterior": str(args.posterior.resolve()),
        "partial": str(args.partial.resolve()),
        "manifest": str(args.manifest.resolve()),
        "median_spacing": float(spacing),
        "core_points": int(core.sum()),
        "structural_cohort_points": int(cohort.sum()),
        "transition_points": int(transition.sum()),
        "fixed_points": int((~core & ~cohort & ~transition).sum()),
        "vector_field_view": field_view,
        "figures": sorted(str(path.resolve()) for path in output.glob("*.png")),
    }
    (output / "figure_manifest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
