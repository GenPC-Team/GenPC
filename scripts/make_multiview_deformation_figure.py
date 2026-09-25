#!/usr/bin/env python3
"""Create a paper-ready multi-view evidence and deformation-field figure."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch
import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.deformation_graph import local_surface_graph
from src.multiview_partial_evidence import load_manifest_projectors
from src.multiview_proximal_tto import (
    MultiViewProximalTTOConfig,
    _geodesic_trust_region,
    _median_spacing,
    _visible_ids,
    multiview_ordered_proposal_evidence,
)
from src.pointcloud_io import load_points


COLORS = {
    "prior": "#A8ACB3",
    "partial": "#168AAD",
    "arrow": "#E68A00",
    "support": "#C51B7D",
    "stable": "#2166AC",
    "transition": "#F4A340",
    "protected": "#C9CCD1",
    "after": "#D1495B",
    "text": "#202124",
}


def _select_spatially(
    xy: np.ndarray,
    score: np.ndarray,
    *,
    count: int,
    minimum_separation: float,
) -> np.ndarray:
    selected: list[int] = []
    for index in np.argsort(np.asarray(score))[::-1]:
        point = xy[index]
        if not np.isfinite(point).all():
            continue
        if selected and np.min(np.linalg.norm(xy[selected] - point, axis=1)) < minimum_separation:
            continue
        selected.append(int(index))
        if len(selected) >= int(count):
            break
    return np.asarray(selected, dtype=np.int64)


def _clean_axis(axis, resolution: int) -> None:
    axis.set_xlim(0, resolution)
    axis.set_ylim(resolution, 0)
    axis.set_aspect("equal")
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)


def _scatter_visible(axis, points, projector, *, color, size, alpha=1.0, zorder=1):
    uv, _ = projector.project(points)
    ids = _visible_ids(points, projector)
    axis.scatter(
        uv[ids, 0], uv[ids, 1], s=size, c=color, alpha=alpha,
        linewidths=0, rasterized=True, zorder=zorder,
    )
    return ids, uv


def _draw_evidence(axis, prior, partial, projector, *, diagonal: float, resolution: int) -> None:
    prior_ids, prior_uv = _scatter_visible(
        axis, prior, projector, color=COLORS["prior"], size=.85, alpha=.62, zorder=1,
    )
    partial_ids, partial_uv = _scatter_visible(
        axis, partial, projector, color=COLORS["partial"], size=1.45, alpha=.86, zorder=2,
    )
    _, prior_depth = projector.project(prior)
    _, partial_depth = projector.project(partial)
    tree = cKDTree(partial_uv[partial_ids])
    pixel_distance, nearest = tree.query(prior_uv[prior_ids], k=1, workers=-1)
    target_ids = partial_ids[np.asarray(nearest, dtype=np.int64)]
    depth_error = np.abs(prior_depth[prior_ids] - partial_depth[target_ids])
    valid = (
        (pixel_distance >= 3.0)
        & (pixel_distance <= .22 * resolution)
        & (depth_error <= .10 * diagonal)
    )
    source = prior_uv[prior_ids[valid]]
    target = partial_uv[target_ids[valid]]
    score = pixel_distance[valid] + 30.0 * depth_error[valid] / max(diagonal, 1e-9)
    keep = _select_spatially(
        source, score, count=20, minimum_separation=.045 * resolution,
    )
    for start, end in zip(source[keep], target[keep]):
        axis.add_patch(FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=7.5,
            linewidth=1.35, color=COLORS["arrow"], alpha=.98, zorder=4,
            shrinkA=0., shrinkB=0.,
        ))
    _clean_axis(axis, resolution)


def _support_regions(before, predictor, partial, projectors, config):
    graph, metric, _ = local_surface_graph(
        before, neighbours=int(config.neighbours), edge_ratio=float(config.edge_ratio),
    )
    spacing = _median_spacing(before)
    support_eligibility = np.ones(len(before), dtype=bool)
    if bool(config.gate_support_by_acquisition_visibility):
        acquisition_visible = np.zeros(len(before), dtype=bool)
        acquisition_visible[
            _visible_ids(before, projectors[int(config.acquisition_view_index)])
        ] = True
        support_eligibility, _ = _geodesic_trust_region(
            metric,
            acquisition_visible,
            radius=(
                float(config.acquisition_visibility_dilation_spacing_multiplier)
                * spacing
            ),
        )
    support, stable, confidence, evidence = multiview_ordered_proposal_evidence(
        partial, before, predictor, projectors, config=config,
        support_eligibility=support_eligibility,
    )
    partial_tree = cKDTree(partial)
    current_distance = partial_tree.query(before, k=1, workers=-1)[0]
    predictor_distance = partial_tree.query(predictor, k=1, workers=-1)[0]
    if np.any(support):
        residual_floor = np.quantile(
            current_distance[support], float(config.support_residual_quantile),
        )
        support &= current_distance >= residual_floor
        support &= predictor_distance < current_distance
    del graph
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    requested = np.linalg.norm(predictor[support] - before[support], axis=1)
    radius = float(config.propagation_spacing_multiplier) * spacing
    if len(requested):
        radius = max(radius, float(config.propagation_motion_multiplier) * np.quantile(requested, .75))
    radius = min(radius, float(config.maximum_propagation_diagonal_ratio) * diagonal)
    active, graph_distance = _geodesic_trust_region(metric, support, radius=radius)
    stable &= ~support
    transition = active & ~support & ~stable
    protected = ~active & ~stable
    focus = np.zeros(len(before), dtype=np.float64)
    if np.any(support):
        values = confidence[support]
        lower, upper = np.quantile(values, (.10, .95))
        normalized = np.clip((values - lower) / max(float(upper - lower), 1e-9), 0., 1.)
        focus[support] = .70 + .30 * normalized
    transition_distance = np.clip(graph_distance[transition], 0., 1.)
    focus[transition] = .12 + .53 * (1. - transition_distance)
    focus[stable] = .05
    evidence.update({
        "figure_support_points": int(support.sum()),
        "figure_stable_points": int(stable.sum()),
        "figure_transition_points": int(transition.sum()),
        "figure_protected_points": int(protected.sum()),
        "figure_propagation_radius": float(radius),
    })
    return support, stable, transition, protected, focus, evidence


def _view_residual_heat(
    before: np.ndarray,
    predictor: np.ndarray,
    partial: np.ndarray,
    projector,
    *,
    config: MultiViewProximalTTOConfig,
    diagonal: float,
):
    before_uv, before_depth = projector.project(before)
    predictor_uv, predictor_depth = projector.project(predictor)
    partial_uv, partial_depth = projector.project(partial)
    before_ids = _visible_ids(before, projector)
    predictor_ids = _visible_ids(predictor, projector)
    partial_ids = _visible_ids(partial, projector)
    common = np.intersect1d(before_ids, predictor_ids)
    tree = cKDTree(partial_uv[partial_ids])
    before_pixel, before_nearest = tree.query(before_uv[common], k=1, workers=-1)
    predictor_pixel, predictor_nearest = tree.query(predictor_uv[common], k=1, workers=-1)
    before_target = partial_ids[np.asarray(before_nearest, dtype=np.int64)]
    predictor_target = partial_ids[np.asarray(predictor_nearest, dtype=np.int64)]
    before_depth_error = np.abs(before_depth[common] - partial_depth[before_target])
    predictor_depth_error = np.abs(predictor_depth[common] - partial_depth[predictor_target])
    before_score = (
        before_pixel / max(float(config.proposal_pixel_radius), 1e-9)
        + before_depth_error / max(float(config.proposal_depth_ratio) * diagonal, 1e-9)
    )
    predictor_score = (
        predictor_pixel / max(float(config.proposal_pixel_radius), 1e-9)
        + predictor_depth_error / max(float(config.proposal_depth_ratio) * diagonal, 1e-9)
    )
    improvement = before_score - predictor_score
    valid = (
        (predictor_pixel <= float(config.proposal_pixel_radius))
        & (predictor_depth_error <= float(config.proposal_depth_ratio) * diagonal)
        & (improvement >= float(config.minimum_normalized_improvement))
    )
    return {
        "before_uv": before_uv,
        "before_ids": before_ids,
        "partial_uv": partial_uv,
        "partial_ids": partial_ids,
        "evidence_ids": common[valid],
        "evidence": improvement[valid],
    }


def _black_axis(axis, resolution: int) -> None:
    axis.set_facecolor("#050608")
    _clean_axis(axis, resolution)


def _style_dark_colorbar(colorbar, label: str) -> None:
    colorbar.set_label(label, color="white", labelpad=3)
    colorbar.ax.tick_params(colors="white", length=2, pad=2)
    colorbar.outline.set_edgecolor("#7E8288")
    for spine in colorbar.ax.spines.values():
        spine.set_edgecolor("#7E8288")


def _save_dark_figure(fig, stem: Path) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(stem.with_suffix(".png"), dpi=500, facecolor="#050608", bbox_inches="tight", pad_inches=.025)
    fig.savefig(stem.with_suffix(".pdf"), facecolor="#050608", bbox_inches="tight", pad_inches=.025)
    plt.close(fig)


def _save_residual_panel(record, name: str, *, vmax: float, resolution: int, output: Path) -> None:
    fig, axis = plt.subplots(figsize=(4.0, 4.0), facecolor="#050608")
    axis.scatter(
        record["before_uv"][record["before_ids"], 0],
        record["before_uv"][record["before_ids"], 1],
        s=1.0, c="#343940", linewidths=0, alpha=.82, rasterized=True,
    )
    evidence_plot = axis.scatter(
        record["before_uv"][record["evidence_ids"], 0],
        record["before_uv"][record["evidence_ids"], 1],
        s=2.1, c=record["evidence"], cmap="turbo", vmin=0., vmax=vmax,
        linewidths=0, alpha=.98, rasterized=True,
    )
    axis.scatter(
        record["partial_uv"][record["partial_ids"], 0],
        record["partial_uv"][record["partial_ids"], 1],
        s=.75, facecolors="none", edgecolors="#D7F4FF", linewidths=.22,
        alpha=.42, rasterized=True,
    )
    _black_axis(axis, resolution)
    axis.set_title(name, color="white", pad=3)
    colorbar = fig.colorbar(evidence_plot, ax=axis, orientation="horizontal", fraction=.045, pad=.015)
    _style_dark_colorbar(colorbar, "Positive residual improvement")
    fig.subplots_adjust(left=.01, right=.99, top=.94, bottom=.09)
    _save_dark_figure(fig, output)


def _save_scalar_panel(
    points: np.ndarray,
    values: np.ndarray,
    partial: np.ndarray,
    projector,
    *,
    title: str,
    label: str,
    cmap: str,
    vmax: float,
    resolution: int,
    output: Path,
) -> None:
    fig, axis = plt.subplots(figsize=(4.4, 4.0), facecolor="#050608")
    uv, _ = projector.project(points)
    ids = _visible_ids(points, projector)
    scalar_plot = axis.scatter(
        uv[ids, 0], uv[ids, 1], s=1.35, c=np.clip(values[ids], 0., vmax),
        cmap=cmap, vmin=0., vmax=vmax, linewidths=0, alpha=.98, rasterized=True,
    )
    partial_uv, _ = projector.project(partial)
    partial_ids = _visible_ids(partial, projector)
    axis.scatter(
        partial_uv[partial_ids, 0], partial_uv[partial_ids, 1],
        s=.65, facecolors="none", edgecolors="#D7F4FF", linewidths=.22,
        alpha=.38, rasterized=True,
    )
    _black_axis(axis, resolution)
    axis.set_title(title, color="white", pad=3)
    colorbar = fig.colorbar(scalar_plot, ax=axis, orientation="horizontal", fraction=.045, pad=.015)
    _style_dark_colorbar(colorbar, label)
    fig.subplots_adjust(left=.01, right=.99, top=.94, bottom=.09)
    _save_dark_figure(fig, output)


def _save_dark_overlay(
    complete: np.ndarray,
    partial: np.ndarray,
    projector,
    *,
    title: str,
    resolution: int,
    output: Path,
) -> None:
    fig, axis = plt.subplots(figsize=(4.0, 4.0), facecolor="#050608")
    _scatter_visible(axis, complete, projector, color="#F0445E", size=1.05, alpha=.78, zorder=1)
    _scatter_visible(axis, partial, projector, color="#D7F4FF", size=1.25, alpha=.78, zorder=2)
    _black_axis(axis, resolution)
    axis.set_title(title, color="white", pad=3)
    fig.subplots_adjust(left=.01, right=.99, top=.94, bottom=.015)
    _save_dark_figure(fig, output)


def _draw_overlay(axis, complete, partial, projector, *, complete_color, resolution):
    _scatter_visible(
        axis, complete, projector, color=complete_color, size=1.05, alpha=.72, zorder=1,
    )
    _scatter_visible(
        axis, partial, projector, color=COLORS["partial"], size=1.45, alpha=.85, zorder=2,
    )
    _clean_axis(axis, resolution)


def _draw_regions(axis, before, partial, projector, masks, *, resolution):
    ids, uv = _scatter_visible(
        axis, before, projector, color=COLORS["protected"], size=.8, alpha=.48, zorder=1,
    )
    support, stable, transition, protected = masks
    del protected
    for mask, color, size, zorder in (
        (transition, COLORS["transition"], 1.0, 2),
        (stable, COLORS["stable"], 1.05, 3),
        (support, COLORS["support"], 1.35, 4),
    ):
        selected = ids[mask[ids]]
        axis.scatter(
            uv[selected, 0], uv[selected, 1], s=size, c=color,
            linewidths=0, alpha=.86, rasterized=True, zorder=zorder,
        )
    partial_ids, partial_uv = _visible_ids(partial, projector), projector.project(partial)[0]
    axis.scatter(
        partial_uv[partial_ids, 0], partial_uv[partial_ids, 1], s=.5,
        facecolors="none", edgecolors=COLORS["partial"], linewidths=.22,
        alpha=.42, rasterized=True, zorder=5,
    )
    _clean_axis(axis, resolution)


def _draw_field(axis, before, after, partial, projector, *, diagonal, resolution):
    before_uv, _ = projector.project(before)
    after_uv, _ = projector.project(after)
    ids = _visible_ids(before, projector)
    displacement = np.linalg.norm(after - before, axis=1) / max(diagonal, 1e-9) * 100.0
    upper = max(float(np.quantile(displacement, .995)), .1)
    plot = axis.scatter(
        before_uv[ids, 0], before_uv[ids, 1], c=np.clip(displacement[ids], 0., upper),
        cmap="magma", vmin=0., vmax=upper, s=1.05, linewidths=0,
        rasterized=True, zorder=2,
    )
    partial_ids, partial_uv = _visible_ids(partial, projector), projector.project(partial)[0]
    axis.scatter(
        partial_uv[partial_ids, 0], partial_uv[partial_ids, 1], s=.55,
        facecolors="none", edgecolors=COLORS["partial"], linewidths=.25,
        alpha=.40, rasterized=True, zorder=1,
    )
    projected_motion = np.linalg.norm(after_uv - before_uv, axis=1)
    candidates = ids[(displacement[ids] >= np.quantile(displacement[ids], .90)) & (projected_motion[ids] >= 2.)]
    keep = _select_spatially(
        before_uv[candidates], displacement[candidates], count=24,
        minimum_separation=.045 * resolution,
    )
    for index in candidates[keep]:
        axis.add_patch(FancyArrowPatch(
            before_uv[index], after_uv[index], arrowstyle="-|>", mutation_scale=7.0,
            linewidth=1.0, color="#00A6A6", alpha=.9, zorder=5,
            shrinkA=0., shrinkB=0.,
        ))
    _clean_axis(axis, resolution)
    return plot, upper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--predictor", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--panel-output-dir", type=Path)
    parser.add_argument("--detail-view", default="side")
    parser.add_argument("--resolution", type=int, default=512)
    args = parser.parse_args()

    before = load_points(args.before)
    after = load_points(args.after)
    predictor = load_points(args.predictor)
    partial = load_points(args.partial)
    if before.shape != after.shape or before.shape != predictor.shape:
        raise ValueError("before, after, and predictor must be ordered carriers")
    projectors = load_manifest_projectors(args.manifest, resolution=int(args.resolution))
    names = ["Front", "Side", "Back", "Right"]
    if len(projectors) != 4:
        raise ValueError("the paper figure expects four saved diagnostic views")
    name_to_index = {name.lower(): index for index, name in enumerate(names)}
    detail_index = name_to_index.get(str(args.detail_view).lower())
    if detail_index is None:
        raise ValueError(f"unknown detail view: {args.detail_view}")
    detail = projectors[detail_index]
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-9)
    config = MultiViewProximalTTOConfig()
    support, stable, transition, protected, focus, _ = _support_regions(
        before, predictor, partial, projectors, config,
    )

    font_paths = (
        "/usr/share/fonts/opentype/urw-base35/NimbusRoman-Regular.otf",
        "/usr/share/fonts/opentype/urw-base35/NimbusRoman-Bold.otf",
        "/usr/share/fonts/opentype/urw-base35/NimbusRoman-Italic.otf",
    )
    for font_path in font_paths:
        if Path(font_path).is_file():
            font_manager.fontManager.addfont(font_path)
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Nimbus Roman", "Times New Roman", "DejaVu Serif"],
        "font.size": 10,
        "axes.titlesize": 10,
        "axes.titleweight": "regular",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    fig = plt.figure(figsize=(14.0, 7.2), facecolor="white")
    grid = fig.add_gridspec(2, 4, height_ratios=(1.0, 1.08), hspace=.18, wspace=.035)
    top_axes = [fig.add_subplot(grid[0, index]) for index in range(4)]
    bottom_axes = [fig.add_subplot(grid[1, index]) for index in range(4)]

    for axis, projector, name in zip(top_axes, projectors, names):
        _draw_evidence(
            axis, before, partial, projector, diagonal=diagonal,
            resolution=int(args.resolution),
        )
        axis.set_title(name, color=COLORS["text"], pad=2)
    fig.text(.012, .965, "(a) Multi-view positive residual evidence", color=COLORS["text"], fontsize=12)

    _draw_overlay(
        bottom_axes[0], before, partial, detail,
        complete_color=COLORS["prior"], resolution=int(args.resolution),
    )
    _draw_regions(
        bottom_axes[1], before, partial, detail,
        (support, stable, transition, protected), resolution=int(args.resolution),
    )
    field_plot, upper = _draw_field(
        bottom_axes[2], before, after, partial, detail,
        diagonal=diagonal, resolution=int(args.resolution),
    )
    _draw_overlay(
        bottom_axes[3], after, partial, detail,
        complete_color=COLORS["after"], resolution=int(args.resolution),
    )
    for axis, title in zip(bottom_axes, (
        "(b) Registered prior", "(c) Consensus regions",
        "(d) Continuous deformation field", "(e) Adapted posterior",
    )):
        axis.set_title(title, color=COLORS["text"], pad=2)

    legend = [
        Line2D([], [], marker="o", linestyle="none", markersize=5, color=COLORS["partial"], label="partial observation"),
        Line2D([], [], marker=">", linestyle="-", linewidth=1.2, markersize=4, color=COLORS["arrow"], label=r"prior $\rightarrow$ partial residual"),
        Line2D([], [], marker="o", linestyle="none", markersize=5, color=COLORS["support"], label="multi-view residual anchor"),
        Line2D([], [], marker="o", linestyle="none", markersize=5, color=COLORS["stable"], label="stable observed region"),
        Line2D([], [], marker="o", linestyle="none", markersize=5, color=COLORS["transition"], label="geodesic transition"),
        Line2D([], [], marker="o", linestyle="none", markersize=5, color=COLORS["protected"], label="protected prior"),
    ]
    fig.legend(
        handles=legend, loc="lower center", ncol=6, frameon=False,
        bbox_to_anchor=(.5, .006), handletextpad=.30, columnspacing=.85,
    )
    fig.subplots_adjust(left=.018, right=.993, top=.935, bottom=.165)
    field_position = bottom_axes[2].get_position()
    color_axis = fig.add_axes([
        field_position.x0 + .04 * field_position.width,
        .108,
        .92 * field_position.width,
        .014,
    ])
    colorbar = fig.colorbar(field_plot, cax=color_axis, orientation="horizontal")
    colorbar.set_label(r"Displacement magnitude  $\|u(x)\| / d_{\mathrm{partial}}$  (%)", labelpad=1)
    colorbar.set_ticks([0., .5 * upper, upper])
    colorbar.ax.tick_params(length=2, pad=1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    png = args.output.with_suffix(".png")
    pdf = args.output.with_suffix(".pdf")
    fig.savefig(png, dpi=500, facecolor="white", bbox_inches="tight", pad_inches=.03)
    fig.savefig(pdf, facecolor="white", bbox_inches="tight", pad_inches=.03)
    plt.close(fig)

    panel_dir = args.panel_output_dir or (args.output.parent / "separate_panels")
    residual_records = [
        _view_residual_heat(
            before, predictor, partial, projector, config=config, diagonal=diagonal,
        )
        for projector in projectors
    ]
    residual_values = np.concatenate([
        record["evidence"] for record in residual_records if len(record["evidence"])
    ])
    residual_vmax = max(float(np.quantile(residual_values, .98)), 1e-3)
    for name, record in zip(names, residual_records):
        _save_residual_panel(
            record, name, vmax=residual_vmax, resolution=int(args.resolution),
            output=panel_dir / f"evidence_{name.lower()}",
        )
    _save_scalar_panel(
        before, focus, partial, detail, title="Multi-view deformation priority",
        label="Consensus priority", cmap="turbo", vmax=1.0,
        resolution=int(args.resolution), output=panel_dir / "consensus_priority",
    )
    displacement = np.linalg.norm(after - before, axis=1) / diagonal * 100.0
    displacement_vmax = max(float(np.quantile(displacement, .995)), .1)
    _save_scalar_panel(
        before, displacement, partial, detail, title="Estimated deformation field",
        label=r"Displacement  $\|u(x)\| / d_{\mathrm{partial}}$  (%)",
        cmap="magma", vmax=displacement_vmax,
        resolution=int(args.resolution), output=panel_dir / "deformation_magnitude",
    )
    _save_dark_overlay(
        before, partial, detail, title="Before adaptation",
        resolution=int(args.resolution), output=panel_dir / "before_adaptation",
    )
    _save_dark_overlay(
        after, partial, detail, title="After adaptation",
        resolution=int(args.resolution), output=panel_dir / "after_adaptation",
    )
    print(png.resolve())
    print(pdf.resolve())
    print(panel_dir.resolve())


if __name__ == "__main__":
    main()
