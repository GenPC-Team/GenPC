# GenPC++ object completion method

This document describes the current four-stage object pipeline. A partial
point cloud and its acquisition camera are inference inputs. Ground truth,
CD, EMD, and sample-specific score thresholds never enter generation,
registration, refinement, or fusion.

## Current MLLM configuration

New runs use `gpt-6-astra` with reasoning effort `low` (Light) for prior generation
interpretation/review and refinement planning/review, as requested on 2026-11-05.
Existing validated experiments retain their recorded GPT-6 Sol provenance.

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
Four five-view boards go to `gpt-6-astra`, which chooses the exterior view whose
visible part layout most resembles the known object class. The complete
ranking, counts, viewpoints, boards, choice and camera are saved. Ground
truth and completion metrics do not enter view selection.

New synthetic 20-view runs center the orbit on the observed partial's bounding
box center. The orbit distance is `r / sin(fovy/2)`, where `r` is half the box
diagonal. Thus the observed bounding sphere fits the square depth canvas and
the cameras remain outside it across metric scales and translations. The
depth rasterizer still applies its existing partial-derived normalized UV
crop; the framing rule determines physical perspective, not a new raster crop.
The diversity calculation uses directions relative to this center. This changes
neither the point coordinates nor saved acquisition cameras. An explicitly
documented physical up axis is carried through camera construction; KITTI's
rectified-camera object coordinates use `[0,-1,0]`. Unknown axes are not
guessed. Astra receives candidate camera geometry, including signed elevation
when up is known, alongside depth boards, to distinguish informative exterior
views from misleading underside views. Failed, unaccepted synthetic priors can
use `refresh-views`; previous camera, prompt and review evidence is archived
under the same sample before regenerating depth, UV and camera together.

Image Gen receives the chosen **depth image**, not a previous generated image,
and this category-filled instruction:

> 这是一个{物体}扫描出来的深度图。用 Image Gen 将图1补全成一张完整的{物体}图，遵循深度图可见部分的深度、轮廓约束，背景为纯白色。

For ambiguous partial scans, `run_prior_generation_agent.py enrich` asks
`gpt-6-astra` to interpret the saved depth before image generation. The agent
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
removes redundant part-count prose, then asks the same model to express the
grounded relations as complete concise Chinese sentences. It does not slice
directional sentences by character count. Raw interpretation and any semantic
compaction request/result are retained beside the exact final prompt.
For regeneration from an unchanged audited view, interpretation also receives
the previous machine audit's suspected mismatch and uncertainty. It must
recheck those claims against depth before turning them into a correction;
machine feedback is separate from human instructions. A newly selected or
refreshed camera does not inherit old-view directional claims.
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
The GPT-6 Astra reviewer separately checks front/back orientation, visible
structure, depth ordering, category identity and natural completeness. It
also checks that the completed object contains the functionally necessary
supports implied by its category and confident depth interpretation. A
horizontal stretcher or overlap does not stand in for a missing leg; a truly
occluded leg need not be drawn if its 3D placement is plausible. Missing,
disconnected or short necessary supports fail natural construction and whole
object completeness even when the observed partial contour aligns.
It
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
viewpoint ambiguity, `run_prior_generation_agent.py reselect` asks GPT-6 Astra
to choose another member of the already ranked 20 partial-only views. It
excludes previously failed views, receives their failure explanation and camera
geometry, and records the no-GT reason and new selection. The old selected camera,
prompts and reviewed candidates are archived before installing the new camera
and generating a fresh depth interpretation. A repeated visible-support failure
can also justify exploring another view even when the generated object looks
coherent overall. `audit_saved_priors.py --latest-review` provides an independent
check against candidate depth boards; a favorable whole-object audit does not
override a failed regional review. Accepted fixed-camera samples cannot be reselected.
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

### Explicit sparse-observation option

`--sparse-observation` adds an independent sparse camera bridge candidate.
Spatial balancing, robust fitting and spatial holdouts determine how much
rotation evidence supports beyond the saved camera orientation. Positive
visible-surface fitting adjusts scale/translation without changing that
rotation. Empty scan pixels incur no penalty in this candidate. The unchanged
mainline result remains a candidate; conservative observed-support checks
choose between them before diagnostics/refinement. Default-off behavior,
archive results and downstream policies are preserved. Full method, command
and evidence limitations: [sparse observation registration](sparse_observation_registration.md).

## 3. Geometric Refinement Agent

The registered prior and partial are rendered in the acquisition camera and
three auxiliary views. Only visible partial samples are positive evidence;
missing projected pixels are unknown. The views show prior-to-partial
residuals and support for the GPT-6 Astra refinement controller. It chooses
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

## Validated local planning within refinement

The recommended runner invocation adds `--planned-local-motion`. After the
standard refinement rounds, GPT-6 Astra chooses among numbered observed/prior
region hypotheses or stops. Matching numbers are hypotheses, not asserted
part identities. Labels use visible region points. Fixed square local crops
include the prior core and observed target, preserve off-canvas padding and
use identical before/after cameras and shared depth shading.

Spatially connected, direction-consistent partial residuals propose bounded
rigid core translations. Motion tapers along the surface graph, leaving
nearby disconnected surfaces fixed. A common line search protects stable
observed support, observation fit and attachment strain. GPT review checks
correspondence, core shape, attachments and unaffected structures. Up to
three plan/action/review attempts share one rest graph, with previously
accepted core edges protected against subsequent distortion. The rest
reference is the start of this local loop, after standard refinement.

This is a geometric region method, not semantic part segmentation. The
production local operator is translation; arbitrary part rotations are not
inferred. Local rigidity does not extend exactly through the subsequent
continuous fusion. Neither GT nor CD/EMD is available to the agent, proposal
generator, acceptance checks or stopping rule. The common configuration and
code hashes were verified across all 60 cases, without dataset routing.

After unchanged continuous fusion, mean CD-L1×100 / EMD×100 improves on
Aircraft40, Redwood10 and Custom10. Full values, raw repeated measurements,
per-case regressions and final structural limits are recorded in
[the validated experiment report](planned_local_refinement_results.md).
All original baseline artifacts remain unchanged.

`--coherent-local-motion` retains the single-step ablation; it is mutually
exclusive with `--planned-local-motion`. Omit both for the original baseline.
Changing policy requires a new run directory. The optional
`--residual-registration` performs a bounded differentiable proper Sim(3)
after the fixed Pixal–MoGe bridge, using saved-camera positive 2D/3D evidence.
It is experimental and is not part of the validated local-planning route.
Missing partial pixels remain unknown, rather than empty-space constraints.

## Execution and evidence

`run_prior_generation_agent.py prepare` → optional `enrich` → interactive Codex Image Gen →
`run_prior_generation_agent.py review` → `run_four_stage_pipeline.py` is the
current execution path. The runner verifies accepted input hashes, executes
Pixal3D, registration, four-view diagnostics, GPT refinement and fusion,
and records exact stage commands and logs in one run directory. Qwen-Image-
Edit-2511 with Nunchaku remains an optional local semantic-completion
alternative; it was not used in the accepted Redwood10 result.

The current accepted package is `workspace/astra_final/`, containing all
156 sample chains across Redwood, Custom, KITTI, Waymo and Aircraft. Full
stage evidence, prompts, metrics and hashes are local assets, not Git source.
Its `copy_manifest.json` maps historical paths to archived files. GT remains
restricted to offline evaluation. See the package's `RESULTS.md` for current
metrics, per-sample regressions and mixed-effort comparison limitations.

## Experimental agent-controlled alignment and semantic handles

`run_semantic_refinement_probe.py` starts at the existing fixed registration.
GPT-6 Astra (low / Light) can choose `REFINE_ALIGNMENT`, `DEFORM_REGION`, or
`KEEP_CURRENT`; actions are not forced to alternate. Alignment uses a proper
Sim(3) with visible camera/3D correspondence and region-balanced validation.
For deformation the agent proposes corresponding visible surface landmarks
and two-view part windows. Numeric tools lift the landmarks and fit a proper
part motion with a smooth intrinsic attachment transition. Whole-object
observations, edge strain, connectivity and MLLM review gate adoption.
The first sparse-handle ARAP experiment was rejected for excessive strain.

Current semantic plans provide separate prior and observed-part windows in
the same two views. Lifted source and target landmarks are reprojected into
both sets of windows before solving. This detects inconsistent part assignments
that a prior-only polygon check misses, though window inclusion alone is not
proof of semantic identity. Optional `--feedback-images` supplies user-annotated
diagnostic boards as hints; fresh control coordinates still come from the
current paired grids. Such trials must be labelled human-assisted. Once a
remaining mismatch is localized, planning prioritizes that part and its
attachment rather than substituting distributed score gains elsewhere.
The review also receives same-canvas crops of that part in both selected
views. Its 3D support error uses the intersection of the observed windows
and the fixed prior slots selected before deformation; unrelated nearby
surfaces cannot supply the nearest-distance match. These are positive-support
diagnostics, not a segmentation guarantee or a universal acceptance threshold.
The separate whole-object gain/regression crops remain available to expose
attachment changes and regressions elsewhere.

The continuation runner supports a category-independent six-view diagnostic
policy (`src/diagnostic_view_policy.py`): retain the four source cameras and
append elevations of -35 and +35 degrees about the first camera's right axis,
around the same object centre, with the same distance and field of view.
These constants are shared across samples, not selected from semantic parts
or offline metrics. The rule is equivariant to world rotation, translation,
and positive uniform scale. Synthetic views reproject the existing partial;
they supply no additional observed geometry, and missing pixels remain unknown.
Paired partial/prior panels share camera, canvas, and projection settings.
Tests verify preservation of the original cameras, similarity equivariance,
and complete six-view board rendering. This validates the implementation,
not a cross-dataset performance gain. Four versus six views must be compared
with the same initial carrier, controller, and refinement budget before promotion.

`scripts/audit_diagnostic_view_policy.py` measures the union of already scanned
point slots exposed by these diagnostic projections (512-pixel, no splatting).
On the 60 archived manifests, the added pair increases mean unique visibility
by 0.0012 percentage points on Aircraft40, 1.8811 on Custom10, and 2.7370 on
Redwood10. These are visibility diagnostics, not completion gains; extra
perspectives may also clarify geometry without exposing additional point slots.
The recorded audit is `workspace/semantic_refinement_astra/view_policy_audit.json`.

The experimental continuation now audits every candidate against the loop's
frozen initial carrier, with edge strain on a fixed rest graph. Previously
approved outputs are comparison baselines, not immobile parts: approval does
not automatically create protected slots. Only an explicit fixed-coordinate
constraint supplies optional protected indices and exact-coordinate/hash checks.
Saved-camera observation tiles check local fit against both the current and
loop-start carrier, reusing the registration method's regional trust limits.
This permits supported local and global motion while limiting regional
regressions. Cumulative strain is descriptive evidence, not a fixed allowable
stretch ratio. There is no universal p99 < 1.5 or p01 > 0.6 acceptance rule:
a generated prior can require substantial proportional correction. Large
strain calls for inspection of supported deformation and natural structure,
not automatic rejection. In the new experimental route,
`enforce_edge_strain_limits=False` propagates through both the continuous-field
and PosteriorAdapter solvers, including their graph-node and full-carrier
levels. Connectivity is checked on candidate geometry instead of declaring
rest edges broken solely because of their length ratio. Historical default
settings remain available for reproducing the old baseline. The audit does
not certify earlier deformation branches. Numerical
checks and the visual reviewer both receive these measurements. Local review
crops use identical camera windows and include the greatest measured observed
gain and greatest regression (or smallest gain). Observed-to-carrier nearest
distance measures positive support, not semantic correctness or hidden shape.

With `--allow-observation-field`, the existing narrow continuous observation
field is an additional tool, using fixed full/half/quarter displacement steps.
Candidate hashes prevent repeated review of identical ordered geometry. Once
all field candidates are exhausted at an unchanged carrier, that deterministic
action is removed until the carrier changes. The controller must use the
concrete failure evidence to change route or stop. `--allow-posterior` also
offers the existing coarse-to-fine PosteriorAdapter with mainline configuration
and actual saved-camera transport. It uses the same candidate fractions and
checks, including the adapter's own integrity gate. Both tools are optional
actions; enabling the adapter does not prove it was selected. Complete-route
performance claims still require a matched end-to-end experiment.

### Autonomous refinement mode

`run_semantic_refinement_continuation.py --autonomous` starts exclusively from
the case's archived fixed-registration output. It rejects feedback text/images,
cached plans, externally supplied initial carriers and protected-slot hints.
The shared category-independent planning contract is in
`src/semantic_refinement_policy.py`. It uses GPT-6 Astra at low (Light) reasoning.

Each round inspects all six views and lists a whole-object mismatch inventory.
Automatically chosen positive-support residual crops provide attention cues;
their selection discounts observed point slots already shown in another crop.
They supply no semantic labels, and missing scan regions remain unknown.
The agent identifies corresponding parts, their attachment boundaries, paired
windows and visible surface landmarks itself. A common global offset can select
proper Sim(3); local pose/shape differences select semantic deformation; broad
surface residuals can select PosteriorAdapter or the narrow observation field.
Tool availability is not evidence of utility: selection and acceptance are logged.
Numerical rejections include the failed checks, measured before/after distances,
connectivity and applicable criteria in the agent's history. Passing regional
support and carrier-integrity audits alone does not imply that a proposal
passed every gate. The `numerical_rejection_v1` evidence revision records its
starting round; it exposes existing checks without changing their thresholds.

Qualified local candidates retain weaker steps for review backtracking if the
stronger proposals from both operators are rejected. A proposed stop with no
actionable inventory entries is checked by a separate review call to the same
model. It can request reassessment with concrete part/view evidence. Exhausting
the iteration budget is recorded separately from adequate fit or uncertain
residuals. The current Custom, KITTI, Waymo and Aircraft suite has a shared
32-round ceiling, extended from eight rounds without adding human hints or
GT feedback. Resuming retains
the original fixed reference and its own decision history; `--rounds` counts
total rounds across continuations. The process exports a red refinement / blue partial PLY overlay
alongside full views, local crops, prompts, controls, candidates and reviews.
The current experiment queues budget-exhausted runs for a second tranche up
to 64 total rounds, preserving the initial checkpoint, fusion, method snapshot
and offline metrics under `budget_tranches/`. Early evidence-based stops are
unchanged. The continuation rule never uses GT or scores; any remaining budget
stop is still reported as unresolved rather than converged.
The stage runner can reuse complete cached assets after a scheduling GPU-index
change; it preserves the original stage command and runtime provenance. This
does not rerun inference. Changed backends/source paths or missing outputs do
not receive this exception.
Part size and affected-point fraction are reported rather than capped at a
universal percentage: a natural component can occupy most of an object.
The selection must contain supported surface points and leave an external
carrier; attachment transitions, observation checks and structural review
assess the resulting change. This removes the earlier 40%/45% point quotas.

The current accepted autonomous results are under `workspace/astra_final/`;
this mode refines fixed registration. The earlier human-assisted fox trace is
historical provenance, and its separate experiment directory was removed at
the user’s request after accepting the five-dataset run.
Semantic window/landmark errors and cumulative deformation remain risks.
Codex requests allow 600 seconds per attempt and at most three attempts;
`COMPAGENT_CODEX_TIMEOUT_SECONDS` overrides the per-attempt timeout. Partial
responses from timed-out attempts cannot accept an update. Successful decisions
record attempt/timeout counts, separately from geometric iteration history.
Cross-case results must be assessed before promoting this experiment to the
validated mainline. No GT enters inference or candidate selection.

### LiDAR prior orientation audit

New prior calls use Astra low (Light). Policy `prior_mining_v24_image_plane_orientation`
requires separate depth and RGB landmark ordering on the identical canvas
(x right, y down). It checks top/bottom inversion, mirroring and material roll
changes independently of silhouette coverage, front/rear facing and near/far
order. A plausible upright RGB cannot pass if it contradicts the observed
orientation. Sparse or missing landmarks remain uncertain.

`scripts/audit_saved_priors.py` reviews archived KITTI/Waymo depth/RGB pairs
alongside their saved candidate-view boards, without historical acceptance or
GT as evidence. It returns keep, regenerate, reselect a concrete saved view,
or uncertain. Reselection requires a clearer informative exterior view; an
adequate current view is retained. A changed image or camera requires a fresh
transparent Pixal input, Pixal/MoGe assets and registration before refinement.
Existing accepted artifacts remain preserved with their original metadata.

Synthetic camera creation accepts an explicit dataset `--world-up` vector.
It changes the actual look-at camera and re-rasterizes depth, UVs and masks
together; an optional `camera.json` records the axis and camera up vector.
Fixed acquisition cameras reject this override. The historical +Y convention
is preserved when no metadata is supplied. KITTI's local crop exporter retains
rectified-camera Y downward (it only removes yaw), so its declared physical up
is `[0, -1, 0]`. This is input-coordinate metadata, not a semantic/GT estimate.
Other datasets must provide evidence for their own axis rather than borrowing
the KITTI convention.

## Accepted five-dataset archive (2026-11-06)

The 156 accepted autonomous results and every saved intermediate are packaged
under `workspace/astra_final/{redwood,custom,kitti,waymo,aircraft}/<sample>/`.
New requests use Astra low; historical medium/low decisions stay unchanged.
Per-case inputs, prompts, cameras, Pixal/MoGe assets, registration, diagnostics,
refinement iterations, fusion and metrics remain together. Global execution
records and prior rebuild audits are under `experiment/`.
The copy manifest maps historical absolute-path provenance to archived files.
The source archive is immutable; use the suite runner with `--source-root`
and a fresh `--output-root` for new experiments. Original baseline point
clouds were removed at user request; comparison metrics are retained.
