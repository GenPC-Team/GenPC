# Active plan

Historical exploration is preserved by git commit `e069181` and accepted
artifacts are recorded in `PROJECT_STATE.md`. This file tracks only the current
mainline work.

## Current object method

- [x] Use the saved partial camera to create depth and a camera-consistent
  semantic observation.
- [x] Generate a textured Pixal3D prior and preserve its native MoGe camera
  observation and ordered 100k carrier.
- [x] Register Pixal--MoGe--partial with Observation-Consistent Prior
  Registration under a proper-Sim(3) camera chain.
- [x] Diagnose the registered prior with Camera-1 plus three views selected by
  incremental partial visibility. Treat absent partial pixels as unknown.
- [x] Use exact Camera-1 for structure-aware Partial OT, then apply the same
  category-independent `PosteriorAdapter` and coarse-to-fine embedded ARAP
  deformation; the four diagnostic views remain local assimilation evidence.
- [x] Fuse the deformed complete posterior with physical partial samples using
  exactly the four saved diagnostic cameras and collision-free carrier-slot
  replacement; no concatenation, deletion, or second deformation is used.
- [x] Preserve every prior carrier slot, stable support, attachments, and
  unobserved coverage; retain no-GT visible evidence as diagnostics only.
- [x] Keep GT/CD/EMD in a separate offline evaluator.

## Accepted pressure test

- [x] `domestic_pig` accepted output:
  `workspace/geometry_first_multiview_proxy_pig_20260910/final_strong_continuous_posterior_100k.ply`.
- [x] The method increases the deficient principal extent continuously without
  detaching observed structures, keeps 100,000 points, creates no new connected
  component, and achieves offline CD-L1/EMD x100 `1.4752/1.8478`.
- [x] Exact inputs, parameters, prompts, and reproducibility caveats are stored
  in `PROJECT_STATE.md` under `2026-09-10 14:28:02 CST`.

## Mainline cleanup and generalization run

- [x] Save and push a pre-cleanup anchor commit (`e069181`).
- [x] Remove rejected TRELLIS, Pixal3D-MV, MVP, axis-stretch, component-motion,
  and redundant deformation prototypes from the current worktree.
- [x] Extract reusable deformation-graph and posterior-visualization helpers.
- [x] Provide a manifest-driven batch runner and a separate four-view diagnostic
  command.
- [x] Rewrite README, method, installation, model, and package documentation to
  describe only the current object mainline and independent scene extension.
- [ ] Run a one-sample byte/numerical regression after refactoring.
- [ ] Run frozen PosteriorAdapter inference for Redwood10 and Custom10 in a new
  output directory using one shared configuration.
- [ ] Evaluate frozen outputs offline, compare with the accepted generalization
  run, record paths and risks, then commit and push the cleaned mainline.

## Test-time residual re-linearization batch (2026-09-20)

- [x] Apply the visually accepted, class-free three-round residual
  re-linearization to the retained Redwood10 and Custom10 assets.  Reuse only
  the saved semantic observations, Pixal priors, Camera-1 registrations and
  four-view residual manifests from
  `workspace/best_redwood_custom_camera1_transport_20260911/`; do not
  regenerate images or priors and do not use GT/CD/EMD during inference.
  Package all copied inputs, registrations, residual evidence, round outputs,
  configuration and script in
  `workspace/tto_relinearized_redwood_custom_20260920/` so the delivery is
  standalone.  The shared configuration is `configs/posterior_mainline.json`,
  with three outer rounds and update strength 1.0, exactly as the accepted
  Seahawk TTO run.  This is an experiment pending batch visual review, not a
  mainline promotion.  All 20 cases finished: 10 Redwood and 10 Custom.  Each
  package entry has copied semantic/Pixal/camera/partial inputs, native and
  bridge registration evidence, four-view residuals, `round_00_registered`,
  three re-linearization rounds and a no-GT summary.  Validation confirmed
  every round keeps exactly 100,000 points, all 20 summaries are present, the
  package carries 10 semantic images and 10 Pixal GLBs per dataset, and copied
  JSON manifests no longer resolve through the previous experiment directory.
  Offline-only 16,384-point evaluation of the `round_03` carrier is saved as
  `metrics/redwood10_tto_round03.{csv,json}` and
  `metrics/custom10_tto_round03.{csv,json}`.  The initial audit reports
  Redwood10 `1.5678/2.5804` and Custom10 `10.3660/9.4913` CD-L1/EMD x100, but
  the Custom number is **not a valid method result**: the batch runner used
  stale `registration_initial/<id>/final/` carriers instead of the validated
  post-Sim(3) `registration_selected/<id>/` carriers.  For example, the
  initial/selected complete diagonal is `.280/1.108` for Light Helicopter and
  `.299/1.274` for Single Engine Airplane; bounded posterior adaptation cannot
  recover this global mismatch.  The next run must begin from the selected
  carrier (and package that stage), then reevaluate.  These metrics did not
  influence the TTO loop or its output selection.
- [x] Re-run the same three-round residual re-linearization from the validated
  `registration_selected/<id>/camera1_amplified_registered_100k.ply` carrier
  for all Redwood10 and Custom10 cases. Save a separate, self-contained
  package at `workspace/tto_relinearized_selected_redwood_custom_20260920/`,
  retain the earlier initial-carrier package as an invalid diagnostic only, and
  recompute the offline-only 16,384-point CD-L1/EMD reports after all cases
  finish. No semantic image, Pixal prior, GT-dependent selection, or
  category-specific setting may change. All 20 final carriers contain exactly
  100,000 points. The corrected offline-only report is Redwood10
  `1.4872/2.4083` and Custom10 `1.8567/2.3406` CD-L1/EMD x100, using
  deterministic 16,384-point FPS with seed 6145. Per-sample CSV/JSON reports
  are stored in the package `metrics/` directory.

## From-scratch direct-GPT debug run

## Sparse Custom Seahawk smoke run (2026-09-19)

### Unpromoted residual-motion posterior probe (2026-09-20)

- [ ] Replace the rejected pointwise residual-field/collar probe with one
  category-free **residual-motion posterior** experiment.  Each four-view
  prior-to-partial residual arrow is a 3D observation of both direction and
  magnitude.  The solver must decompose those observations by explanatory
  motion, rather than decide a motion type from an object class, coordinate
  axis, or hand-drawn region:
  - a spatially coherent set whose arrows are explained by one proper SE(3)
    moves as one structural unit, so a blade, handle, limb, or wing rotates or
    translates without bending;
  - a connected set whose arrows instead require a smooth, non-isometric
    metric change is represented by a low-frequency deformation-graph field,
    so a short torso, tall backrest, or long appendage changes extent
    continuously rather than detaching.
  The two alternatives share the same confidence-weighted Partial OT, stable
  support, attachment graph, and no-GT residual objective.  The carrier mesh
  is used only as a geometry scaffold; its sampled 100k points remain the
  rendering/export carrier.  No category names, part labels, fixed axes, GT,
  CD, or EMD may enter the classification or solve.
- [ ] First test the frozen Seahawk inputs, explicitly audit whole-unit motion,
  attachment strain, and four-view visible error.  Then run the *unchanged*
  configuration on the frozen Pig inputs before considering any mainline
  integration.  The existing graph-cut/collar outputs and the first intrinsic
  Fiedler-hierarchy attempt remain diagnostic only: their arbitrary regions
  can absorb part of a rotor/body and create excessive strain, so they are
  rejected as a structural-unit estimator.
- [x] Implement the first two-level probe in
  `scripts/probe_residual_modal_posterior.py`: Camera-1 transport supplies a
  low-frequency metric update, then post-update four-view correspondences
  with at least two-camera support propose proper SE(3) units.  A unit is a
  connected, data-improving support with a narrow two-ring attachment
  transition; it is rejected if its own observed residual does not improve or
  its graph strain/coverage becomes unsafe.  This is still unpromoted and has
  no object-name, part, axis, GT, CD or EMD branch.
- [x] Run the unchanged two-level configuration on frozen Seahawk and Pig:
  `workspace/seahawk_helicopter_from_scratch_sparse_20260919/`
  `residual_motion_twolevel_probe_20260920/seahawk_helicopter` and
  `workspace/domestic_pig_depth_gauge_fixed_20260919/`
  `residual_motion_twolevel_probe_20260920/domestic_pig`.  Pig's Camera-1
  metric update reduces its transport residual median `0.17468 -> 0.11827`
  (32.3%) and accepts one subsequent coherent local motion (1,473 carrier
  points).  Seahawk accepts two coherent local motions (1,045 carrier points)
  after its conservative metric pass.  Each output preserves exactly 100,000
  carrier slots.  Await visual review before deciding whether the residual
  support model is sufficiently complete to test broader generalization.
- [x] Add a topology-aware metric gate and an iterative four-view residual
  loop to the probe only.  The metric gate no longer treats changed prior
  silhouette as deletion: it constrains carrier count, graph strain and
  spacing-normalized stable motion.  The residual loop re-estimates
  two-camera-supported correspondences and proper-motion hypotheses after
  every accepted update, at most three times, instead of reusing stale rotor
  residuals.  The accepted Pig record is
  `workspace/domestic_pig_depth_gauge_fixed_20260919/`
  `residual_motion_attachment_continuation_probe_20260920/domestic_pig`:
  alpha `.85`, Camera-1 median residual reduction `62.9%`, and one 2,055-point
  24.54-degree coherent motion with four-ring attachment continuation.
  The Seahawk iterative diagnostic is
  `workspace/seahawk_helicopter_from_scratch_sparse_20260919/`
  `residual_motion_iterative_probe_20260920/seahawk_helicopter`; its four-view
  supported-anchor median is `0.00907 -> 0.00528` after three no-GT rounds
  (versus `0.00792` after one round), while retaining all 100k carrier slots.
  This remains unpromoted pending review on further identities.
- [x] Test a replacement for the provisional BIC-only metric decision with an adaptive
  correntropy transport test in the residual-motion probe only.  A global
  metric field now requires simultaneous improvement of the median, 75th
  percentile, and correntropy residual; BIC remains an audit statistic rather
  than a decision signal.  On the frozen Seahawk this correctly rejects the
  low-frequency metric warp (whose affine median/correntropy are worse), so
  only connected local proper-SE(3) units act and the fuselage is not globally
  dragged.  On the unchanged Pig it retains the metric update (relative
  median/q75/correntropy gains `28.3%/30.3%/33.4%`, selected alpha `.85`).
  Outputs are `workspace/seahawk_helicopter_from_scratch_sparse_20260919/`
  `residual_motion_correntropy_gate_probe_20260920/seahawk_helicopter` and
  `workspace/domestic_pig_depth_gauge_fixed_20260919/`
  `residual_motion_correntropy_gate_probe_20260920/domestic_pig`.  Visual
  review rejected this probe because its subsequent local-motion updates still
  distort the Pig torso relative to the retained mainline posterior.  It is a
  rejected test artifact and must not be promoted or used as a baseline.
- [x] Run a test-only **iterative residual re-linearization** on the accepted
  Seahawk mainline posterior.  Reuse the unchanged partial, Camera-1,
  four-view manifest and `PosteriorAdapter` configuration; each round starts
  from the previous 100k carrier and recomputes the same class-free OT and
  four-view positive evidence.  Save all rounds and their no-GT residual
  diagnostics.  Do not change the accepted baseline or promote the loop
  before visual review.  The first run is
  `workspace/seahawk_helicopter_from_scratch_sparse_20260919/`
  `posterior_tto_relinearized_probe_20260920/seahawk_helicopter`: all rounds
  preserve 100k slots and its no-GT four-view collision-free residual median
  decreases `0.01391 -> 0.00933 -> 0.00549 -> 0.00395` across the registered
  input and three re-linearizations.  This is unpromoted pending visual review.

- [x] Add `seahawk_helicopter.glb` as a reproducible Custom datum.  Its
  normalized complete reference is sampled at 16,384 points and the new
  oblique saved-camera partial is sampled at 8,192 points; the source camera,
  raw depth, mask, UVs and `camera.pth` are saved under
  `data/custom/seahawk_helicopter/`.
- [x] Run the complete direct-GPT/Pixal/native-MoGe/Observation-Consistent
  Prior Registration/four-view posterior/fusion route without GT feedback at
  `workspace/seahawk_helicopter_from_scratch_sparse_20260919/`.  The final
  fixed-carrier prediction is
  `fusion_depth_gauge_20260919/seahawk_helicopter/observation_anchored_fused_100k.ply`.
  Offline-only 16,384-point CD-L1/EMD x100 is `1.6027/3.2960`.
- [x] Confirm the new partial-count CLI is backwards compatible by regenerating
  the Seahawk with `--partial-count 8192 --gt-count 16384`; existing Custom
  entries retain the default 16,384-point observation count.
- [x] Probe category-independent residual-consensus rigid fields after global
  registration.  The field estimates local proper SE(3) motions solely from
  four-view collision-free partial correspondences, freezes low-residual
  support with a spacing-normalized transition, and preserves all 100k carrier
  slots.  On sparse Seahawk it reduces Camera-1 visible 3D error
  `0.02725 -> 0.01886` while retaining connectivity and all initially stable
  points.  The broad graph-harmonic propagation variant was rejected because
  it spread a local motion to 96% of the carrier.  The retained local-field
  probe is at
  `workspace/seahawk_helicopter_from_scratch_sparse_20260919/`
  `posterior_transform_supported_rigid_smoothlock_probe_20260919/`.
  The same configuration on unchanged `domestic_pig` preserves connectivity
  and reduces no-GT visible objective `0.12627 -> 0.10210`, but its offline
  CD-L1/EMD x100 slightly regresses `1.6435/2.1145 -> 1.6436/2.1260`.
  Therefore this remains an opt-in diagnostic probe, not a mainline change.

- [ ] Replace the native Pixal--MoGe fixed 4x depth-gauge cap with the
  camera-coordinate robust positive-depth calibration, then regression-check
  the same rule on the current Custom airplane and retained Redwood/Custom
  assets. This must remain invariant to semantic image resolution and crop;
  do not introduce a sample-specific scale rule. The 2026-09-19 airplane
  check passes on both the current 442px preprocessed Pixal input and an
  independent retained 962px Custom input: the native nearest-surface median
  improves from `3.4345 -> 0.1840` and `3.9961 -> 0.1269`, respectively.
  The corrected complete no-GT run is at
  `workspace/probe_single_engine_airplane_from_scratch_20260919/`
  `registration_depth_gauge_20260919`, `residuals_depth_gauge_20260919`,
  `posterior_depth_gauge_20260919`, and `fusion_depth_gauge_20260919`.
  Remaining risk: run the frozen correction across distinct Redwood and
  Custom identities before promoting it as the full-batch default.

- [x] Regenerate Redwood 01184 from its partial scan in
  `workspace/from_scratch_01184_debug_20260910`.
- [x] Keep Camera-1 plus three incremental-visibility partial observations,
  direct GPT depth completion, Pixal3D/MoGe assets, every registration stage,
  four-view residuals, Partial OT, posterior fields, and offline metrics.
- [x] Feed visibility-valid pixel/depth evidence from all four views into
  Partial OT; retain residual/integrity measurements as diagnostics rather
  than a final output-selection gate.
- [x] Replace Qwen in the from-scratch branch with direct GPT conditioned by a
  mask-locked depth prompt, and reject framing drift before 3D generation.
- [x] Visually approve the direct-GPT 01184 chain and promote it to the
  remaining Redwood samples without changing the shared geometric parameters.
- [x] Regenerate 05452 with a depth-locked thin-shell chair prompt before
  Pixal3D inference; retain the rejected thick attempts for audit.
- [x] Finish the remaining Redwood registration, four-view evidence,
  PosteriorAdapter deformation, and offline CD/EMD evaluation in
  `workspace/from_scratch_01184_debug_20260910`.
- [x] Diagnose 07306 as a Camera-1 concave/interior-view ambiguity, switch to
  the partial-only `opposite_180` camera, regenerate its semantic/Pixal prior,
  and rerun the unchanged geometry chain. This reduces offline CD-L1 x100 from
  24.1892 to 2.4226 without a GT-guided inference decision.
- [x] Run four-view observation-anchored fusion on Redwood10. It improves mean
  CD-L1/EMD x100 from 1.7442/2.8163 to 1.5136/2.6334, with all ten CD values
  and nine of ten EMD values improved; inference uses no GT or offline metric.
- [x] Add an opt-in integrated observation-assimilation experiment inside
  `PosteriorAdapter` without changing its default route. Four-view partial
  anchors drive the same smooth embedded-ARAP carrier instead of replacing
  points. On 01184 it reaches 1.0650/2.0588 CD-L1/EMD x100; on 07136 it reaches
  1.7763/3.4295 while preserving 100k points, connectivity, and at least 95%
  hidden coverage. The user visually approved both pressure tests on
  2026-09-11; preserve their outputs and run the remaining Redwood samples
  with this exact category-independent configuration before promotion.
- [x] Run the identical integrated configuration over all Redwood10 at
  `workspace/from_scratch_01184_debug_20260910/posterior_integrated_fusion_v2`.
  All outputs retain exactly 100k carrier points, create no new connected
  component, and preserve at least 95% hidden coverage. Offline-only metrics
  are stored in `metrics/redwood10_integrated_v2.{csv,json}`: mean
  CD-L1/EMD x100 is `1.6475/2.6676`; relative to the unfused posterior, 8/10
  samples improve in CD and 9/10 improve in EMD. Keep 07306 and 09639 visible
  as generalization diagnostics rather than introducing sample-specific gates.

## Shared Redwood--Custom parameter study

- [x] Freeze the existing Redwood semantic images, Pixal3D priors, cameras, and
  registrations; they are immutable inputs during parameter selection.
- [x] Stage all ten Custom partial scans, saved cameras, depth observations,
  prompts, and a fresh artifact tree at
  `workspace/custom_from_scratch_integrated_tuning_20260911`.
- [x] Regenerate all ten Custom semantic images and Pixal3D/MoGe priors from
  scratch, using depth-locked GPT completion and saved camera audits.
- [x] Diagnose the failed Custom registration as a Camera-1 contract mismatch:
  Open3D pinhole/top-left `point_uv` was interpreted with the historical
  Kaolin bottom-left convention, and the perspective camera was later replaced
  by a normalized orthographic projection. The partial clouds themselves are
  byte-identical to the retained 2026-09-08 run; all ten saved cameras,
  semantic images, and generated priors differ.
- [x] Make Camera-1 projection dataset-independent: preserve and read the exact
  pinhole intrinsic/extrinsic sidecar when present, infer normalized UV origin
  from observed foreground support, and retain the legacy path otherwise.
  Redwood 01184 resolves to bottom-left and is numerically unchanged; all ten
  Custom samples resolve to top-left. Their top-left foreground support is
  94.4--100%, and the subsequent cross-camera transferred-match ratio is
  74.5--99.8% after target-view visibility filtering.
- [x] Add no-GT monotonic broad-to-narrow continuation to the existing Camera-1
  proper-Sim(3) refinement. It uses one shared trust-region schedule and stops
  when relative visible-objective improvement falls below 2.5%.
- [x] Run the fixed registration, four-view evidence builder, and integrated
  PosteriorAdapter on all ten Custom samples. The catastrophic registered mean
  falls from `10.8105/9.8261` to `2.3929/2.9281`; the shared posterior result is
  `2.0316/2.6529` CD-L1/EMD x100.
- [x] Evaluate the same continuation and posterior setting on Redwood10. The
  result is `1.5631/2.5336`, versus the retained `1.5820/2.5114`; CD improves
  while EMD differs by +0.0222. A denser-assimilation probe was rejected because
  it did not improve the hard Custom cases consistently.
- [ ] Decide whether to promote the continuation schedule after visual review.
  Do not claim the remaining ~0.02 Custom CD difference is a registration
  regression: this from-scratch run uses different cameras, semantic images,
  and generated priors from the old `2.0118/2.9994` run.
- [x] Diagnose the weak current Pig deformation as an evidence-role regression:
  four reframed orbit projectors can dilute the exact saved Camera-1 extent and
  depth signal. The exact-Camera-1 probe keeps Camera-1 as the
  sole structural-transport authority while retaining the four homogeneous
  manifest views for local positive observation assimilation. On unchanged Pig
  inputs this improves offline CD-L1/EMD x100 from `3.7756/3.5845` to
  `1.6403/2.1470`, preserves all 100k slots and one connected component, and
  retains hidden coverage `1.1194`. No class, part, GT, CD, or EMD logic enters
  inference.
- [x] Run the same Camera-1 transport probe over Custom10 and Redwood10 without
  changing inputs or parameters. Direct replacement changes Custom mean from
  `2.0316/2.6529` to `1.9921/2.5377` and Redwood mean from
  `1.5631/2.5336` to `1.5380/2.4848`. The gain is concentrated in Pig, Wolf,
  and Redwood 06830; mirrorless camera, drill, and Redwood 05452 regress, and
  four cases fall slightly below 95% hidden coverage despite retaining 100k
  slots and introducing no connected component. Therefore keep the policy
  opt-in rather than replacing the four-view default. Outputs are under
  `workspace/custom_from_scratch_integrated_tuning_20260911/`
  `posterior_camera1_transport_manifest_assimilation_20260911`.
- [x] A two-hypothesis no-GT policy probe was evaluated but not retained: the
  user selected exact Camera-1 transport as the single mainline action to keep
  inference simple and avoid doubled runtime. The frozen full-batch result is
  `1.9921/2.5377` on Custom10 and `1.5380/2.4848` on Redwood10; the known
  mirrorless-camera, drill, and 05452 regressions remain documented rather than
  hidden behind category-specific branches.

## Omni-Comp3D Redwood single-scan evaluation

- [x] Resolve the ten Redwood IDs from the official Redwood scan metadata and
  stage both `single_scan/partial_0.ply` and `partial_1.ply` as twenty
  independent no-GT inference cases.
- [x] Run the current Camera-1 transport mainline from saved-view depth through
  direct-GPT semantic completion, Pixal3D prior generation, registration,
  four-view evidence, PosteriorAdapter and observation-anchored carrier fusion.
- [x] Preserve every intermediate and final artifact under
  `workspace/omni_redwood_single_scan_camera1_mainline_20260911`; all final
  predictions contain 100k points, add no connected component and retain at
  least 95% hidden coverage.
- [x] Evaluate only after inference. Final CD-L1/EMD x100 is
  `9.6951/11.3174` over twenty cases. The poor mean is dominated by the `sign`
  and one `chair` case; their mismatch is already visible at semantic-prior and
  global-registration stages, rather than being introduced by final fusion.
- [ ] Before treating Omni as a paper result, improve the category-independent
  view/semantic-prior reliability check for sparse, open and ambiguous partial
  scans; eleven semantic masks currently retain explicit audit warnings.
- [x] Run the frozen geometry-pruned CLIP selector on the Omni 01027
  `single_scan/partial_0` for direct comparison with random-crop. It selects
  azimuth/elevation/roll `0/15/270` (geometry rank 2); the saved camera, depth,
  complete ranking and Top-12 board are under
  `workspace/omni_redwood_single_scan_clip_view_probe_20260911/01027_partial_0`.
  The two-wheel layout is more legible than the random-crop input, although
  disconnected sparse scan fragments remain visible and CLIP still does not
  reliably choose the cleanest candidate by human judgement.
- [x] Extend the same frozen selector to all twenty Omni Redwood single-scan
  inputs (`partial_0/1` for ten IDs) in one model-reusing batch. Each sample
  uses its own dataset category text while sharing the candidate lattice,
  prompt templates and score weights. All depths, cameras, Top-12 boards and
  rankings are under `workspace/omni_redwood_single_scan_clip_gpt_20260911`;
  `clip_selected_depths_20.png` is the complete review board. Stop before GPT
  completion pending visual approval of these cameras.
- [x] Probe direct-GPT completion on bicycle, open-top trash container, sofa
  and chair. Pixel-hard completion preserves sparse support but can inherit
  scan outliers; globally relaxed prompts recover plausible shape but
  canonicalize the camera. Replace the reusable prompt contract with a robust
  coherent-support constraint plus category-normal topology and test an
  optional minimal second-pass repair that keeps the first pass as its camera
  and geometry base. Artifacts and the three-way comparison board are under
  `workspace/omni_redwood_single_scan_clip_gpt_20260911`. This probe is not yet
  accepted for the remaining sixteen samples.
- [x] Correct the systematic 180-degree Camera-1 raster orientation at export
  time and re-render `01027_partial_0` together with its camera, UV, depth and
  mask metadata. A direct-GPT retry from the upright depth produces one
  coherent bicycle with normal proportions; the selected candidate is saved
  as `gpt_semantic_upright_v2.png`. The original camera artifacts remain beside
  it with the `_before_upright` suffix. Batch rollout remains pending review.

## Omni-Comp3D Redwood random-crop evaluation

- [ ] Stage both `random_crop/partial_0.ply` and `partial_1.ply` for the same
  ten official Redwood IDs as twenty independent inference cases.
- [x] Add and test an isolated category-free completion-aware camera probe that
  ranks a deterministic 120-view lattice by visible support, projection
  collision, depth information, connectivity, footprint and perturbation
  stability. The first 01027 probe is stored at
  `workspace/omni_redwood_random_crop_completion_view_probe_20260911/01027_partial_0`.
  Geometry alone selects azimuth/elevation `225/30`; visual inspection still
  finds semantic ambiguity, so this probe is not promoted without a Top-K
  semantic/depth self-consistency stage.
- [x] Run a three-view Qwen comparison for 01027 using the unchanged 40-step
  Qwen-Image-Edit-2511/Nunchaku configuration and the canonical occluded-depth
  prompt. Outputs are under
  `workspace/omni_redwood_random_crop_semantic_verify_20260911/01027_partial_0`.
  The highest geometry-ranked view completes a plausible bicycle but drifts
  from the depth camera; the other two preserve more observed geometry but
  remain incomplete or malformed. This confirms that neither geometry score
  nor semantic plausibility alone is sufficient for view selection.
- [x] Add an isolated frozen-CLIP view-ranking probe for 01027. Geometry first
  prunes the 120-view lattice to 36 candidates; CLIP ViT-L/14@336 then scores
  four in-plane rolls and three render modalities with a shared category-text
  prompt ensemble. The generic canonical-view revision selects azimuth,
  elevation and roll `210/-30/90`; outputs, the complete ranking and reusable
  camera are stored under
  `workspace/omni_redwood_random_crop_clip_view_probe_v2_20260911/01027_partial_0`.
  The view is recognizable but the Top-12 board shows that CLIP ranking alone
  still prefers a somewhat foreshortened projection over several visually
  clearer candidates, so this remains an opt-in diagnostic rather than a
  promoted mainline selector.
- [x] Complete the CLIP-selected 01027 depth with the built-in GPT image editor
  using a strict camera/mask-preservation prompt. The resulting semantic image
  and verbatim prompt are saved beside the selected depth as
  `gpt_semantic.png` and `gpt_semantic_prompt.txt`. The result is a coherent
  bicycle and broadly follows the selected oblique pose, but exact silhouette
  fidelity has not yet been accepted or promoted.
- [x] Run the frozen local Qwen baseline on the identical CLIP-selected raw
  depth (`40` steps, CFG `4.0`, 512 input/output). Its output and verbatim
  settings are stored as `qwen_semantic.png` and `qwen_semantic_prompt.txt` in
  the same directory. Qwen follows the visible large-wheel silhouette more
  literally than GPT but leaves the bicycle incomplete and introduces malformed
  attachments, so this particular view does not make Qwen completion reliable.
- [ ] Run the unchanged Camera-1 transport mainline from partial-only depth and
  direct-GPT semantic completion through Pixal3D, two-camera registration,
  four-view evidence, PosteriorAdapter, and observation-anchored fusion.
- [ ] Preserve bridge-only and fully refined registration artifacts for direct
  visual comparison, then compute CD/EMD only in the offline evaluator.

## Hydra relaxed-deformation diagnostic

- [x] Diagnose why the four-view residual board did not produce a comparable
  3D correction for `hydra_creature`. The coarse structural stage rejected all
  502 coherent residual rows because their normalized support fraction
  (`0.2544`) exceeded the original localization bound (`0.20`); the later
  assimilation stage also limited usable anchors to a 3% object-diagonal
  radius and selected a quarter-strength update.
- [x] Run an isolated, category-agnostic relaxed-deformation probe without
  changing the mainline or using GT for optimization. The probe raises the
  localization bound to `0.27`, expands the multiview anchor radius to 7.5% of
  the partial diagonal, permits 12% displacement, and relaxes hidden coverage
  and robust edge-strain limits. Outputs are under
  `workspace/hydra_relaxed_deformation_probe_20260911`; the final comparison
  point cloud is `posterior/partial_gray_posterior_red.ply` and the consolidated
  review board is `baseline_vs_relaxed.png`.
- [x] Verify that the relaxed probe activates both coarse and fine structural
  deformation (492 and 149 residual anchors), preserves one connected 100k
  carrier and 95.51% hidden-view coverage, and improves the no-GT visible-3D
  residual from `0.04822` to `0.02320`. Offline-only evaluation improves Hydra
  from CD/EMD `1.52096/2.41688` to `1.02560/1.78171` (both x1e2). This is still
  a focused probe, not a promoted default; the 99th-percentile edge stretch of
  `2.72` requires cross-sample validation before adopting the relaxed limits.
- [x] User decision: do not promote the relaxed Hydra configuration. Continue
  with the original mainline deformation parameters. The probe remains only as
  an isolated diagnostic artifact and no production configuration or source
  implementation was changed by it.

## Waymo8 original-mainline evaluation

- [x] Stage three `car` and five `Pedestrian` partial point clouds under
  `workspace/waymo8_original_mainline_20260911`. Exclude cars 1 and 3 by user
  decision; the retained vehicles are the earlier car 2, 4 and 5 selections.
- [x] Reuse the user-approved finite-orbit GPT camera choices and their saved
  cameras. This selector remains an isolated Waymo input-preparation probe and
  is not promoted into the frozen object mainline.
- [x] Install the accepted depth-constrained GPT semantic images together with
  their exact prompts, Camera-1 depth, mask, UV and camera metadata. Three very
  sparse Pedestrian observations retain explicit semantic-audit warnings; no
  sample-specific threshold was introduced to hide them.
- [x] Run fresh Pixal3D/MoGe prior generation, original
  Observation-Consistent Prior Registration, four-view diagnostics,
  Camera-1-transport PosteriorAdapter, and final carrier-slot observation
  fusion for all eight retained samples.
- [x] Keep all four saved views in sparse acquisition cases. If the configured
  image radius yields too few candidates, the view proposes nearest visible
  pairs and the unchanged depth, cross-view, 3-D and collision-free checks
  determine whether they can affect the carrier. No view-abstention or
  sample-specific branch is used.
- [x] Preserve all stage artifacts under
  `workspace/waymo8_original_mainline_20260911`. All eight final predictions
  exist at `final/<sample>/complete_100k.ply`, contain exactly 100k points and
  preserve the complete carrier. A consolidated inspection image is
  `waymo8_fused_contact_sheet.png`. Waymo has no paired completion GT in this
  local subset, so CD/EMD are intentionally not reported.

## Waymo8 sparse-LiDAR prior-placement probe

- [x] Keep the object mainline unchanged and evaluate an isolated route for
  extremely sparse LiDAR observations.
- [x] Register the complete Pixal carrier to its dense native MoGe observation,
  then apply only the Camera-2-to-Camera-1 pixel bridge estimated from the
  sparse scan. Do not run partial-driven joint/final registration,
  PosteriorAdapter, or observation-slot fusion.
- [x] Preserve the ordered 100k carrier and export partial/prior overlays for
  all eight retained Waymo samples under a new workspace directory.
- [x] Compare the bridge-only placement with the original mainline using only
  no-GT visible-surface diagnostics and visual inspection; do not promote this
  sparse-input route to the standard Redwood/Custom pipeline.
- [x] The retained artifacts are under
  `workspace/waymo8_sparse_lidar_moge_bridge_20260912`: each
  `registration/<sample>/native` directory contains Pixal--MoGe alignment and
  each `registration/<sample>/bridge` directory contains the composed
  Camera-2-to-Camera-1 placement. The consolidated comparison is
  `bridge_only_vs_mainline_registration.png`. A stricter fixed-axis bridge was
  tested and rejected because sparse/outlier correspondences degraded vehicle
  placement; its code and outputs were removed instead of adding another
  fragile method branch.
- [x] Re-run the accepted bridge-only route from the retained Pixal/MoGe and
  Camera-1 inputs with `--no-resume`. All eight 100k outputs under
  `workspace/waymo8_sparse_lidar_moge_bridge_rerun_20260912/final` are
  byte-identical to the first run, confirming exact deterministic replay.

## Waymo8 observability-adaptive sparse-LiDAR adapter

- [x] Diagnose why the bridge-only probe did not improve the retained Waymo
  cases. Three vehicle priors were silhouette-aligned to native MoGe but had
  median same-pixel log-depth errors of `0.4570--0.6347`; the historical 12%
  camera-ray cap left their monocular depth gauge unresolved. Pedestrian
  priors already had native log-depth errors below `0.0101`.
- [x] Implement an opt-in camera-origin ray-gauge calibration. It estimates a
  trimmed same-pixel depth ratio, verifies ratio concentration and projection
  invariance, and reduces the three vehicle native log-depth residuals to
  `0.0026`, `0.0069`, and `0.0056` without changing the mainline.
- [x] Filter Camera-1 bridge points by coherent semantic foreground, fit sparse
  partial queries to the dense native MoGe surface, and accept the residual
  proper-Sim(3) only under a one-sided sparse-observation objective. Missing
  LiDAR pixels never act as free-space or leakage evidence.
- [x] Assimilate reliable dense native-MoGe visible samples into fixed ordered
  carrier slots while preserving all hidden and unmatched prior slots.
- [x] Add a category-free no-GT router between the frozen mainline and the
  sparse dense-bridge candidate. The score combines one-sided visible 3D,
  partial coverage and depth evidence with ordered-carrier prior distortion.
  A first Camera-1-raster score incorrectly selected one additional vehicle;
  an adjacent-frame held-out scan showed that its frozen result was better.
  The corrected router uses all positive LiDAR returns through a one-sided
  partial-to-surface mean/tail distance plus prior protection. It selects the
  calibrated dense bridge only for the two mainline-unobservable cases and
  retains the frozen result for the other six, without inspecting class names
  or sample IDs.
- [x] Run the shared configuration over all eight retained samples. Every final
  result contains exactly 100k finite carrier points under
  `workspace/waymo8_camera_ray_gauge_sparse_adapter_20260912/<sample>/complete_100k.ply`.
  Waymo has no paired GT in this local subset, so only no-GT diagnostics and
  visual overlays are reported. Reproduction and equations are documented in
  `docs/waymo_sparse_lidar_adapter.md`.
- [x] Validate on seven available adjacent same-track source-to-held-out scan
  directions using one common partial-to-partial frame transform for both
  candidates. The selected result is non-regressive in `7/7` directions and
  strictly improves the two previously unobservable vehicle cases. Normalized
  held-out one-sided mean distance falls from `0.2007` to `0.0364`; median and
  p90 fall from `0.1965/0.2504` to `0.0212/0.0941`. The held-out scan is used
  only by `scripts/evaluate_waymo_temporal_holdout.py`, never by inference.
- [x] Prepare the consolidated `sparse_candidate_vs_selected.png` review sheet
  and keep the adapter Waymo-only. Do not record it as a user-accepted result
  in `PROJECT_STATE.md` or promote it beyond Waymo without explicit approval.

## Waymo Camera-1 coordinate-contract audit

- [x] Verify the suspected 180-degree projection rotation. All retained Waymo
  views store `roll_degrees: 180.0`, and the roll is applied to the physical
  Kaolin camera basis before `camera.pth`, depth, and UV export. It was not
  omitted from the saved camera.
- [x] Identify the remaining convention error: the historical depth painter
  flips the completed raster vertically after projection, while native MoGe
  uses OpenCV camera coordinates and Kaolin uses an OpenGL-style camera frame.
  A free proper Sim(3) cannot represent this fixed coordinate conversion and
  was compensating with spurious 15--35 degree object rotations.
- [x] Isolate the fixed MoGe-to-saved-raster axis conversion from the estimated
  geometry, then estimate a camera-anchored positive scale and translation and
  run the existing bounded proper-Sim(3) residual refinement. The conversion
  is derived only from the saved raster contract; no category, sample id, GT,
  CD, or EMD is consulted.
- [x] Re-run all eight retained Waymo samples under
  `workspace/waymo8_camera_convention_sparse_adapter_20260912`. Each sample
  contains `partial_gray_aligned_moge_red.ply`; the consolidated before/after
  diagnostic is `partial_moge_previous_vs_camera_convention.png`. Mean no-GT
  visible-surface objective falls from `0.1449` to `0.0873`.
- [x] User review rejects promotion: Waymo visual quality remains poor despite
  the improved diagnostic objective. Keep this route only as an isolated
  coordinate-contract experiment. It must not replace, configure, or be called
  by the object mainline. Only 3/7 held-out directions are non-regressive, so
  aggregate error alone is not evidence of a usable completion method.

## Light-helicopter broad-deformation probe

- [x] Keep the frozen object mainline unchanged and diagnose the insufficient
  rotor deformation from its saved registration, partial, Camera-1 and
  multiview residual manifest.
- [x] Confirm that the baseline coarse posterior stage rejected the broad
  coherent residual (`0.5448 > 0.20` localization bound), leaving only a
  `0.0157` maximum observation-assimilation displacement.
- [x] Run two category-free relaxed profiles under
  `workspace/light_helicopter_relaxed_deformation_probe_20260912`. The broad
  profile accepts wide coherent residual support and reaches `0.0871` maximum
  coarse displacement; the balanced profile retains the same structural
  correspondences while imposing stronger rigidity and hidden-view coverage.
- [x] Evaluate strictly offline. The saved baseline posterior is
  CD-L1/EMD `1.1937/2.0162`, the assimilation-only relaxed probe is
  `1.0838/1.8687`, the broad profile is `0.7172/1.3730`, and the balanced
  profile is `0.6911/1.3774` (all x1e2). These values did not enter transport,
  deformation, line search, or stopping.
- [x] Preserve the probe outputs and configs for visual review. Do not promote
  either profile to the shared mainline: both improve visible alignment but
  cumulative hidden coverage falls below their configured integrity target,
  so cross-sample validation is required before any method change.
- [x] After visual review found one long rotor bent by the broad profile, run a
  category-free strong-smooth variant with a coarser control graph, denser
  graph neighbourhood and eight-node skinning. It preserves the broad
  `0.0874` maximum coarse motion while reducing fine-stage displacement to
  `0.0255`; offline CD-L1/EMD are `0.7029/1.3895` (x1e2). Keep it isolated for
  review because cumulative hidden coverage remains below the configured
  diagnostic target.
- [x] The smooth graph alone remained visibly curved. Add an opt-in,
  mainline-disabled covariance detector that identifies elongated carrier
  regions without labels or axes and projects each region onto its best-fit
  proper SE(3), with graph-neighbourhood blending at attachments. A 95th
  percentile linearity threshold and aspect ratio 4 initially identified two
  long rotor regions. The foreshortened third region had only `227` seeds and
  fell below the old `300`-point support floor; lowering the normalized floor
  from `0.3%` to `0.2%` identifies all three regions (`3,164` carrier points).
  The resulting CD-L1/EMD are `0.7162/1.3726` (x1e2); preserve it for user
  visual review and do not promote without cross-category validation.
- [x] Reframe the remaining bend as an ARAP limitation: edge-preserving ARAP
  permits nearly isometric bending of thin structures even when the original
  Pixal geometry is correct. Add an opt-in displacement-biharmonic term to
  preserve the prior's differential coordinates during strong deformation.
  The `strong_bending` probe keeps `0.0865` maximum coarse motion, passes the
  integrity audit with `0.9240` hidden coverage, and reduces final strain to
  p01/p99 `0.523/2.412`. Offline CD-L1/EMD are `0.7299/1.4656` (x1e2). The
  default regularization is zero, and all posterior tests pass, so the frozen
  mainline remains unchanged.
- [x] Diagnose the remaining unmoved rotor as a prior-frame regularization
  error rather than a missing category rule. The world-frame biharmonic term
  resisted rigid rotation in unsupported regions. Replace it with a
  co-rotational differential-coordinate term and strengthen generic
  near-contact attachment construction with rotation-carrying edge bundles.
  The isolated `strong_corotated_bending` probe preserves all 100k slots,
  introduces no new connected component, improves the no-GT visible objective
  from `0.1393` to `0.0940`, and passes all five posterior-adapter tests.
  Offline CD-L1/EMD are `0.7544/1.4551` (x1e2); do not promote it until visual
  review and cross-category validation, because it trades a small CD increase
  for the intended rotation propagation and structural continuity.
- [x] Sweep co-rotational anti-bending weights `5` and `8` without changing
  transport or displacement limits. Weight `8` is the stable candidate:
  hidden coverage `0.8946`, no integrity failure, CD-L1/EMD
  `0.7485/1.4597` (x1e2). Weight `5` is rejected because hidden coverage
  falls to `0.8090` and integrity fails.
- [x] Combine weight `8` with the existing category-free covariance detector
  for highly linear structures. Three automatically detected regions are
  projected to their best-fit proper SE(3) after deformation, removing the
  residual bending without undoing propagated rotation. The result preserves
  100k points, passes integrity with `0.8971` hidden coverage, and obtains
  CD-L1/EMD `0.7495/1.4556` (x1e2). Keep this as an isolated visual candidate
  until user review; mainline defaults remain unchanged.

## Structural residual-field probe (unpromoted)

- [x] Replace the earlier finite-collar-only exploratory field with an opt-in
  category-free structural proposal in
  `scripts/probe_structural_residual_field.py`: collision-free multi-view
  residual anchors first vote for local proper SE(3) motions, then an s-t
  minimum cut over the fixed prior-affinity graph finds the smallest coherent
  carrier separated from stable support. A short graph collar only smooths
  the attachment; no class, part, axis, GT, CD, or EMD enters this route.
- [x] Add greedy proposal validation before composing motions. Each candidate
  must reduce its own observed-anchor residual by a normalized fraction while
  preserving the carrier graph's normalized edge-compression/stretch bounds;
  stable observations are hard locked. This rejected an unsafe large motion
  in the pig probe while retaining two continuous smaller motions, using the
  exact same frozen rules as Seahawk.
- [x] Save the Seahawk diagnostic under
  `workspace/seahawk_helicopter_from_scratch_sparse_20260919/structural_graph_cut_validated_probe_20260919/seahawk_helicopter`.
  It moves 22,645/100,000 carrier points through three accepted structural
  motions, improves the multi-view anchor median `0.01773 -> 0.01592`, and
  leaves all 1,288 stable points exactly fixed. The matching pig safety probe
  is `workspace/domestic_pig_depth_gauge_fixed_20260919/structural_graph_cut_validated_probe_20260919/domestic_pig`.
- [ ] Keep this separate from the mainline until visual assessment confirms
  that the stronger rotor alignment is worth the local structural change and
  validation covers further Custom and Redwood identities.
