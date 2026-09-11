# Active plan

Historical exploration is preserved by git commit `e069181` and accepted
artifacts are recorded in `PROJECT_STATE.md`. This file tracks only the current
mainline work.

## Current object method

- [x] Use the saved partial camera to create depth and a camera-consistent
  semantic observation.
- [x] Generate a textured Pixal3D prior and preserve its native MoGe camera
  observation and ordered 100k carrier.
- [x] Register Pixal--MoGe--partial with the camera-aware 2D+3D proper Sim(3)
  chain.
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

## From-scratch direct-GPT debug run

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
