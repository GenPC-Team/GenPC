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

For KITTI, Waymo and ScanNet runs without a saved acquisition camera,
`prepare --view-candidates 20` uses the configured 256-point Fibonacci sphere.
It ranks the views by hidden-point visible count on a partial-only FPS sample,
greedily retains the first 20 at least 25° apart, and renders those depths.
Four five-view boards go to `gpt-6-sol`, which chooses the exterior view whose
visible part layout most resembles the known object class. The complete
ranking, counts, viewpoints, boards, choice and camera are saved. Ground
truth and completion metrics do not enter view selection.

Image Gen receives the chosen **depth image**, not a previous generated image,
and this category-filled instruction:

> 这是一个{物体}扫描出来的深度图。用 Image Gen 将图1补全成一张完整的{物体}图，遵循深度图可见部分的深度、轮廓约束，背景为纯白色。

For ambiguous partial scans, `run_prior_generation_agent.py enrich` asks
`gpt-6-sol` to interpret the saved depth before image generation. The agent
records whole-object pose, visible part identity and count, part locations,
attachments, each part's base-to-end axis, its separate terminal direction,
near/far order, and semantic front/rear facing direction. When the saved camera
JSON has an explicit world-up vector, the agent also receives whether the
acquisition camera is above or below the object; this helps distinguish an
aircraft's upper surface from its underside. A head can be at
the far end while still facing the camera, so position and facing are checked
separately. When supported, the agent adds a visible-facing cue, such as
showing the back of a head rather than eyes and a mouth facing the camera.
This distinction also matters when, for example, a limb
extends sideways but its claws point down. It states uncertain regions rather
than inventing hidden structure. One or two short, grounded sentences are
appended to the unchanged base prompt. The interpretation and exact resulting
prompt are saved beside the candidate. User observations about a part can be
passed as `--feedback`; the code contains no per-category prompt templates.
When the additional cue exceeds the short-prompt budget, the builder first
removes redundant part-count prose, then shortens the image hint while keeping
the facing and canvas cues; it records whether trimming occurred.
For a distant object that Image Gen tends to enlarge, `enrich
--include-depth-framing` appends the partial-only observed bounding box as
approximate canvas percentages. It keeps those visible parts in place while
allowing unobserved structure to extend naturally. The same option asks Image
Gen to fill black scan gaps with continuous surface rather than copying
point-scan speckles into the generated material.

The depth raster represents partial evidence. Valid depth pixels constrain
visible contour, pose, orientation, part position, and near/far order;
unobserved pixels do not assert empty space. The semantic image should
complete the entire object naturally, including physically plausible
connections, materials, repeated supports, and functional proportions.

`run_prior_generation_agent.py review` resizes the **whole** generated canvas
to the saved depth size without cropping or translation. It verifies that
comparison depth, RGB and overlay are the same dimensions before comparing
corresponding pixels. Small provider canvas aspect variations (at most 3%)
are mapped by full-canvas axis resize and recorded; larger differences are
rejected. RMBG-2.0 provides the foreground mask. A tolerant
positive-support gate tests whether the generated foreground covers observed
depth pixels approximately (default floor 0.65 for the partial-scan review);
image center, box size and IoU are diagnostics.
The GPT-6 Sol reviewer separately checks front/back orientation, visible
structure, depth ordering, category identity and natural completeness. It
has a separate front/rear-axis check that rejects a reversed head, lens or
nose direction even when those parts occupy the right locations. It
receives the saved part interpretation and any explicit human candidate
feedback, so a grayscale shape with ambiguous identity does not by itself
reverse a confirmed part relation. Short protrusions marked uncertain in the
saved interpretation are not forced into a particular wing or fin during
review, even if an intermediate retry prompt guessed one. Review treats that
prompt as provenance rather than independent evidence. The candidate must still match the
positive observed support and remain a plausible complete object.
An inferred wingtip or other missing part may extend naturally into black,
unobserved pixels; the partial scan's bounding box is not a hard object
boundary, and such an extension alone is not a rejection reason. Small tip
offsets of a few canvas percentage points are treated as approximate matches
when the observed support and part connections still agree.
Small isolated black voids within a visible surface are missing scan samples;
the reviewer requires natural continuous material unless that object normally
has openings there.
For a sparse point scan, a candidate must reconstruct a finished object
surface instead of copying point-scan speckles, patch gaps or disconnected
scan fragments into the material.
For a sparse person scan, a wide lower-body patch may be clothing or overlapping
limbs. The reviewer does not force an exact hip boundary unless the scan
actually separates those parts; it still checks the visible limb direction
and positive support.
Likewise, scattered lower-body returns on a sparse vehicle scan do not define
an exact wheel center unless a distinct wheel or arch is visible. The reviewer
checks approximate support for confidently observed wheels and permits a
plausible wheel location within an ambiguous lower-body region.
If repeated candidate reviews for an unknown-camera scan expose a persistent
viewpoint ambiguity, `run_prior_generation_agent.py reselect` asks GPT-6 Sol
to choose another member of the already ranked 20 partial-only views. It
excludes previously failed views, records the no-GT reason and new selection,
reinstalls that camera, and clears failed candidate rounds before generating
a new depth interpretation. Accepted fixed-camera samples cannot be reselected.
MoGe-2 ordinal depth agreement on observed pixels is supporting evidence,
not a hard threshold because monocular depth is uncertain. A failed depth
order judgment requires a visible part, occlusion or shape contradiction,
not just a low monocular-depth score. A candidate can
be rejected despite good foreground coverage. The prompt, candidate, image
hashes, dimensions, review decision and audit outputs are saved per round.
When an Image Gen candidate is edited using a previous image, the generation
record also lists the extra reference image path and SHA-256. An explicit
prompt file may be supplied to the recording script when the operator refines
the reviewer's suggested text; the file must contain the exact submitted
prompt.
When a candidate is reviewed again, the reviewer uses the prompt recorded
with that candidate's image hash, so a later retry prompt cannot be
mistakenly attributed to the earlier image.
Image Gen records are archived by candidate SHA-256, including any extra edit
reference, so revisiting an earlier accepted candidate preserves its exact
generation provenance. A transient Codex CLI error event is retried up to
three times for prior and refinement decisions; an actual tool call remains
forbidden and fails immediately.
Retry prompts start from the same depth-grounded base and add only the latest
specific correction; prior failed corrections are not concatenated.
After repeated semantic failures, the retry uses the validated short depth
sentence plus the latest observed correction, dropping the initial semantic
hint if it may conflict with the review evidence.
Review corrections state locations as percentages of the full canvas, since
the saved comparison raster and native Image Gen image can have different
pixel dimensions.
When the visible-support gate fails, the review records the mismatch and
writes a retry prompt with the observed depth bounding box as approximate
canvas percentages; this keeps the partial evidence in place while allowing
unobserved geometry to be completed.

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

`run_prior_generation_agent.py prepare` → optional `enrich` → interactive Codex Image Gen →
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
