# GenPC++ object completion method

This document describes the current four-stage object pipeline. A partial
point cloud and its acquisition camera are inference inputs. Ground truth,
CD, EMD, and sample-specific score thresholds never enter generation,
registration, refinement, or fusion.

## 1. Prior Generation Agent and semantic completion

The partial scan is projected into a depth raster with saved camera
parameters and point-to-pixel mapping. If the acquisition camera is already
saved, `run_prior_generation_agent.py prepare --camera-source` copies its
`depth.png`, `camera.pth`, and `point_uv.npy` and keeps that view fixed.
Otherwise the agent selects an exterior/front view from four partial-derived
depth candidates. This avoids reversing the observed surface or looking into
the back of an open object.

Image Gen receives the chosen **depth image**, not a previous generated image,
and this category-filled instruction:

> 这是一个{物体}扫描出来的深度图。用 Image Gen 将图1补全成一张完整的{物体}图，遵循深度图可见部分的深度、轮廓约束，背景为纯白色。

The depth raster represents partial evidence. Valid depth pixels constrain
visible contour, pose, orientation, part position, and near/far order;
unobserved pixels do not assert empty space. The semantic image should
complete the entire object naturally, including physically plausible
connections, materials, repeated supports, and functional proportions.

`run_prior_generation_agent.py review` resizes the **whole** generated canvas
to the saved depth size without cropping or translation. It verifies that
comparison depth, RGB and overlay are the same dimensions before comparing
corresponding pixels. RMBG-2.0 provides the foreground mask. A tolerant
positive-support gate tests whether the generated foreground covers observed
depth pixels approximately; image center, box size and IoU are diagnostics.
The GPT-6 Sol reviewer separately checks front/back orientation, visible
structure, depth ordering, category identity and natural completeness.
MoGe-2 ordinal depth agreement on observed pixels is supporting evidence,
not a hard threshold because monocular depth is uncertain. A candidate can
be rejected despite good foreground coverage. The prompt, candidate, image
hashes, dimensions, review decision and audit outputs are saved per round.

After acceptance, the RGB semantic image is retained for refinement. RMBG
converts it to transparent RGBA before Pixal3D. Pixal3D crops/composites from
that alpha image and saves the exact preprocessed image seen by MoGe-2. Its
GLB and ordered 100k-point carrier provide complete shape and texture prior.

## 2. Camera-aware registration

`run_fixed_pixal_moge_registration.py` aligns the native Pixal3D geometry,
MoGe-2 camera observation and acquisition-camera partial scan. The source
image, MoGe cache and Pixal camera metadata must describe the same
preprocessed Pixal input. Their bridge estimates a proper similarity

\[
T(x)=sRx+t,\qquad R\in SO(3),\ s>0,
\]

using positive visible surface and projective evidence. The saved camera
intrinsics, extrinsics, raster size and point UV convention are reused, so a
view or crop change cannot silently alter the registration target. A bounded
Camera-1 continuation refines the placement without changing the complete
carrier's point order.

## 3. Geometric Refinement Agent

The registered prior and partial are rendered in the acquisition camera and
three auxiliary views. Only visible partial samples are positive evidence;
missing projected pixels are unknown. The views show prior-to-partial
residuals and support for the GPT-6 Sol refinement controller. It chooses
among bounded geometric proposals from the deterministic Partial OT and
deformation solver, verifies integrity and no-GT residuals, and accepts or
continues. Stable observed support is anchored; reliable residuals drive a
smooth graph field; unsupported complete geometry is protected. The solver
keeps the ordered 100k carrier and does not add or delete points. Agent
decisions, proposals, diagnostic views and final refined carrier are logged.

## 4. Continuous observation fusion

`run_observation_anchored_fusion.py --mode continuous` uses the saved views
to select visibility-valid partial/prior correspondences. Cross-view support,
camera-depth agreement and collision-free assignment bound the accepted
measurements. A finite-support embedded deformation assimilates those
residuals into the refined carrier while protecting geometry away from the
observed region. A no-GT line search checks coverage, connectivity and edge
strain. The final output still has exactly 100,000 ordered points; fusion is
not point concatenation. An optional textured PLY carries the Pixal colours
on those same slots.

## Execution and evidence

`run_prior_generation_agent.py prepare` → interactive Codex Image Gen →
`run_prior_generation_agent.py review` → `run_four_stage_pipeline.py` is the
current execution path. The runner verifies accepted input hashes, executes
Pixal3D, registration, four-view diagnostics, GPT refinement and fusion,
and records exact stage commands and logs in one run directory. Qwen-Image-
Edit-2511 with Nunchaku remains an optional local semantic-completion
alternative; it was not used in the accepted Redwood10 result.

The local accepted package is `workspace/redwood10_final/`, with ten complete
sample chains, fused PLYs, prompt and review evidence, stage manifests,
`metrics.csv`, `copy_manifest.json`, and `SHA256SUMS`. The copied manifests
still contain original absolute run paths, which were removed during workspace
cleanup; package-relative paths are in `copy_manifest.json`. The package is
not checked into Git. Ground truth was used only for frozen offline
16,384-point FPS, seed-6145 evaluation. Redwood10 mean CD-L1 ×100 is
`1.537036` and mean EMD ×100 is `2.472180`; the ten individual rows are in
`workspace/redwood10_final/metrics.csv`.
