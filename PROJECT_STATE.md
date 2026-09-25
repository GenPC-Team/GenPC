# Accepted project state

## 2026-09-20 17:18:00 CST — accepted Seahawk test-time residual re-linearization

**User approval.** The user judged the three-round Seahawk test-time residual
re-linearization “效果非常好”.  Preserve every round and its valid input chain.
This is an accepted diagnostic result, not yet a promoted object-mainline
replacement.  Do not overwrite the accepted baseline in the next entry or
reuse rejected residual-motion probes.

**Sample, inputs and outputs.** Sample id: `seahawk_helicopter`.  Fixed inputs
are `workspace/seahawk_helicopter_from_scratch_sparse_20260919/inputs/partial/seahawk_helicopter.ply`,
`inputs/camera/seahawk_helicopter/{depth.png,camera.pth,point_uv.npy,mask.png,img.png}`,
and `residuals_depth_gauge_20260919/seahawk_helicopter/render/render_manifest.json`
under the same root.  The run output is
`posterior_tto_relinearized_probe_20260920/seahawk_helicopter`; it contains
`round_00_registered` and `round_{01,02,03}`, each with
`posterior_prior_100k.ply`, `partial_gray_posterior_red.ply`, Camera-1 and
four-view overlays, and `round_info.json`.  The accepted current result is
round 3: `round_03/{posterior_prior_100k.ply,partial_gray_posterior_red.ply}`.
All rounds retain exactly 100,000 carrier slots.  The full no-GT audit is
`tto_summary.json`; no GT, CD, or EMD enters any iteration.  Offline metrics
for this exact output: `UNKNOWN`.

**Models and generation.** The frozen semantic image is
`inputs/camera/seahawk_helicopter/img.png`, created from
`inputs/pixal/seahawk_helicopter/gpt_image_raw.png` at resolution `512`;
provider-side GPT model identifier, seed, steps, CFG/guidance, scheduler,
backend, resize policy and negative prompt are `UNKNOWN` / no negative prompt
recorded.  Frozen Pixal3D paths are `models/Pixal3D-weights`, DINO
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe `models/moge-2-vitl/model.pt`,
and RMBG `models/RMBG-2.0`; seed `42`, requested/actual resolution `1024`,
xFormers, sparse/shape/texture steps `12/12/12`, guidance `7.5/7.5/1.0`,
guidance-rescale `.7/.5/.0`, rescale-t `5.0/3.0/3.0`, decimation target
`300000`, texture size `2048`.  Frozen assets are
`inputs/pixal/seahawk_helicopter/{gpt_image.png,pixal3d_input.png,pixal3d.glb,pixal3d_sampled_100k.ply,pixal_moge_fp16_observation.npz}`.

**Exact semantic prompt (negative prompt: UNKNOWN/NONE).**

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a complete Seahawk helicopter with a main rotor, tail boom, tail rotor, cockpit, landing gear, and external equipment. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask. Additional structural constraints: preserve the observed diagonal pose, silhouette, framing, camera viewpoint, and all reliable visible structures from the depth image complete only the unobserved portions naturally; do not crop, rotate, mirror, or change the camera

**Test-time optimization configuration.** `scripts/iterative_posterior_tto.py`
recomputes the same exact-Camera-1 Partial OT and four saved-view positive
evidence after each round; it trains no weights.  It uses three outer rounds,
`update_strength=1.0`, `configs/posterior_mainline.json`, and the resolved
posterior configuration from the preceding baseline entry: `3072/6144`
partial/prior samples, OT `60` iterations/`.72` relaxation/`.012` floor,
coarse/fine graph passes `5/5`, and embedded four-view assimilation with data
weight `2.0`, screening `.004`, three internal iterations, `.05` displacement
ratio and `.03` anchor-residual ratio.  The four-view collision-free residual
median is `0.0139061` before optimization and `0.0093267`, `0.0054905`,
`0.0039487` after rounds 1--3.  This record approves the frozen data/config;
it does not approve a larger `update_strength` without a new visual review.


## 2026-09-20 17:15:34 CST — accepted Seahawk mainline posterior baseline

**User approval.** The user judged the current mainline Seahawk posterior
result “其实这个效果已经很不错了”.  Preserve this as the visual baseline for
any stronger-deformation probe.  Do not overwrite its input prior, registered
placement, or posterior output.  Any increased-strength attempt must write to
a new directory and retain the same saved cameras and no-GT inputs.

**Sample, inputs and outputs.** Sample id: `seahawk_helicopter`.  Inputs are
`workspace/seahawk_helicopter_from_scratch_sparse_20260919/inputs/partial/seahawk_helicopter.ply`,
`inputs/camera/seahawk_helicopter/{depth.png,camera.pth,point_uv.npy,mask.png,img.png}`,
and the four-view manifest
`residuals_depth_gauge_20260919/seahawk_helicopter/render/render_manifest.json`
under the same root.  The frozen registered 100k prior and its gray/red
comparison are
`registration_depth_gauge_20260919/seahawk_helicopter/final/camera1_amplified_registered_100k.ply`
and `camera1_amplified_partial_gray_pixal_red.ply`.  The accepted posterior,
gray/red comparison, saved-view board, virtual-view board, Partial-OT pairs,
and field are respectively
`posterior_depth_gauge_20260919/seahawk_helicopter/{posterior_prior_100k.ply,partial_gray_posterior_red.ply,posterior_saved_view_projection.png,posterior_virtual_views.png,partial_ot_pairs.npy,posterior_field.npz}`.
The output retains all 100,000 Pixal carrier slots.  Offline CD/EMD for this
exact accepted output: `UNKNOWN` (not used or recorded for this approval).

**Models and generation.** Direct GPT semantic completion source is
`inputs/pixal/seahawk_helicopter/gpt_image_raw.png`, installed at
`inputs/camera/seahawk_helicopter/img.png`, resolution `512`; model identifier,
seed, steps, CFG/guidance, scheduler, backend, resize policy and negative
prompt are `UNKNOWN` / no negative prompt recorded.  Pixal3D paths are
`models/Pixal3D-weights`, DINO `models/dinov3-vitl16-pretrain-lvd1689m`,
MoGe `models/moge-2-vitl/model.pt`, and RMBG `models/RMBG-2.0`; seed `42`,
requested/actual resolution `1024`, xFormers backend, sparse/shape/texture
steps `12/12/12`, guidance `7.5/7.5/1.0`, guidance-rescale
`.7/.5/.0`, rescale-t `5.0/3.0/3.0`, mesh-decimation target `300000`, texture
size `2048`.  Native assets are
`inputs/pixal/seahawk_helicopter/{pixal3d.glb,pixal3d_sampled_100k.ply,pixal_moge_fp16_observation.npz}`.

**Exact semantic prompt (negative prompt: UNKNOWN/NONE).**

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a complete Seahawk helicopter with a main rotor, tail boom, tail rotor, cockpit, landing gear, and external equipment. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask. Additional structural constraints: preserve the observed diagonal pose, silhouette, framing, camera viewpoint, and all reliable visible structures from the depth image complete only the unobserved portions naturally; do not crop, rotate, mirror, or change the camera

**Accepted posterior configuration.** Exact config is preserved in
`posterior_depth_gauge_20260919/seahawk_helicopter/posterior_info.json` and
`configs/posterior_mainline.json`: exact-Camera-1 structural Partial OT,
`3072/6144` partial/prior samples, transport `60` iterations with relaxation
`.72` and temperature floor `.012`; `24` low-frequency modes with
regularization `.035`; coarse/fine graph node fractions `.02/.055`, five
iterations each, data weights `2.5/4.0`, displacement ratios `.28/.12`; graph
integrity compression/stretch `.55/2.8`; and integrated four-view observation
assimilation (`6144` samples, data weight `2.0`, screening `.004`, three
iterations, displacement cap `.05` of partial diagonal).  No GT, CD, EMD,
category/part rule, fixed axis, or manually selected region enters inference.


## 2026-09-20 16:21 CST — accepted Pig residual-motion posterior probe

**User approval.** The user judged the Pig result “效果很好看起来”. Preserve it
as the accepted *probe* baseline for continuous posterior adaptation. Do not
promote it to the object-level mainline, replace its frozen input prior, or
change its normalized residual/attachment rules without a separate
cross-identity validation. Seahawk remains a separate unapproved stress test.

**Sample, inputs and outputs.** Sample id: `domestic_pig`. The fixed input
partial and Camera-1 camera are
`workspace/domestic_pig_depth_gauge_fixed_20260919/inputs/partial/domestic_pig.ply`
and `inputs/camera/domestic_pig/camera.pth`; the saved depth and installed
semantic are `inputs/camera/domestic_pig/depth.png` and `img.png` under the
same root. The frozen complete carrier is
`registration/domestic_pig/final/camera1_amplified_registered_100k.ply`.
The approved final carrier is
`residual_motion_attachment_continuation_probe_20260920/domestic_pig/residual_motion_posterior_100k.ply`;
the corresponding partial/prior overlay and before/after diagnostic boards are
`partial_gray_residual_motion_red.ply`, `before_virtual_views.png`, and
`after_virtual_views.png` in that directory. The metric-stage carrier is
`stage1_metric_prior_100k.ply`; exact residual, support, graph and transform
records are `residual_modal_info.json` and `residual_modal_field.npz`.

**Models and generation record.** The semantic source is
`inputs/pixal/domestic_pig/gpt_image.png`; its GPT image model/checkpoint,
seed, steps, CFG/guidance, scheduler, native resize policy and negative prompt
are `UNKNOWN`. The exact positive prompt is saved verbatim at
`inputs/pixal/domestic_pig/gpt_depth_completion_prompt.txt` and is reproduced
below; no separate negative prompt exists. The frozen Pixal prior is
`inputs/pixal/domestic_pig/{pixal3d.glb,pixal3d_sampled_100k.ply,pixal_moge_fp16_observation.npz}`.
Its metadata records `models/Pixal3D-weights`, DINO
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe
`models/moge-2-vitl/model.pt`, RMBG `models/RMBG-2.0`, xFormers, seed `42`,
1024px inference, 12 sparse/shape/texture steps, guidance strengths
`7.5/7.5/1.0`, decimation target `120000`, and texture size `1024`.

**Exact semantic prompt (negative prompt: NONE).**

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a complete domestic pig. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask. Additional structural constraints: Keep one connected torso, four naturally attached legs, two ears, one snout, and one tail.

**Accepted postprocessing.** The probe keeps every one of the 100,000 prior
carrier slots; it never appends or deletes partial points. It first estimates
Camera-1 structural OT, then projects its residual targets to a 2,048-node,
32-mode intrinsic low-frequency graph field. The accepted metric step is
`alpha=0.85`, reduces the no-GT Camera-1 transport median `0.17467567` to
`0.06478022`, and satisfies graph compression/stretch `0.45327/2.86119` with
occupancy retention `.91813`. The post-metric four-view route retains only
two-camera-supported matches; it accepts one 24.536-degree proper SE(3)
support (2,055 core points) with a four-ring attachment continuation.
No GT, CD, EMD, object part label, category rule, fixed axis, or manual region
is used by the geometry update. Offline metrics are `UNKNOWN` for this exact
new probe and must not be backfilled from a different run.

## 2026-09-19 18:04:08 CST — native Pixal--MoGe depth-gauge correction accepted for continuation

**User approval.** “ok 现在正常多了 可以跑后续步骤了.” The user visually
approved the native Pixal--MoGe alignment after replacing the fixed 4x native
depth-scale cap with camera-coordinate robust positive-depth calibration.
Continue this sample from the corrected bridge; do not reinstate the fixed
numeric cap or introduce a sample/category-specific scale rule.

**Sample and outputs.** Sample id: `single_engine_airplane`. The approved
native comparison is
`workspace/probe_single_engine_airplane_from_scratch_20260919/registration_depth_gauge_20260919/single_engine_airplane/native/pixal_native_moge_gray_pixal_red.ply`.
The continuation inputs are the bridge comparison
`workspace/probe_single_engine_airplane_from_scratch_20260919/registration_depth_gauge_20260919/single_engine_airplane/bridge/two_camera_pixal_moge_partial_gray_pixal_red.ply`
and registered carrier
`workspace/probe_single_engine_airplane_from_scratch_20260919/registration_depth_gauge_20260919/single_engine_airplane/bridge/two_camera_pixal_moge_registered_100k.ply`.
Inputs are
`workspace/probe_single_engine_airplane_from_scratch_20260919/inputs/partial/single_engine_airplane.ply`,
`inputs/camera/single_engine_airplane/{depth.png,camera.pth,point_uv.npy,img.png}`, and
`inputs/pixal/single_engine_airplane/{gpt_image_maskaligned.png,pixal3d_input.png,pixal3d.glb,pixal3d_sampled_100k.ply,pixal_moge_fp16_observation.npz,pixal3d_metadata.json}`
under the same run root.

**Models and generation.** Semantic completion was GPT image generation;
provider-side seed, scheduler, CFG, negative prompt and model identifier are
`UNKNOWN`. Pixal uses `models/Pixal3D-weights`, DINO
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe-2
`models/moge-2-vitl/model.pt`, and RMBG-2.0 `models/RMBG-2.0`; seed `42`,
requested/actual resolution `1024`, 12 sparse/shape/texture steps, sparse
guidance `7.5`, shape guidance `7.5`, texture guidance `1.0`, decimation
target `300000`, and texture size `2048`.

**Exact semantic prompt.**

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a single-engine light airplane with one propeller, fixed wings, tailplane, vertical tail fin, and tricycle landing gear. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask.

**Postprocessing and rationale.** A depth-mask-only horizontal global affine
of `0.985` was applied to the GPT image before semantic installation; no 3-D
geometry, GT, CD, or EMD was used. The installed 512px semantic audit passed
with depth coverage `0.840834`, center offset `0.0009766`, and bbox scales
`[1.10989, 1.10828]`. The native correction estimates the positive-depth
median ratio in the shared Pixal camera frame, rather than using image
resolution/crop or a fixed scale limit. On this 442px Pixal input, nearest
native-MoGe distance median changed `3.4345 -> 0.1840`; on an independent
retained 962px Custom Pixal input, it changed `3.9961 -> 0.1269`.


## 2026-09-11 10:49:35 CST — consolidated best Redwood10 and Custom10 delivery

**User request.** Preserve the best previous Redwood and Custom experiments,
including all intermediate artifacts, in one new directory. The selected route
is the shared exact Camera-1 structural-transport configuration documented in
`PLAN.md`; offline means are CD-L1/EMD x100 `1.5380/2.4848` for Redwood10 and
`1.9921/2.5377` for Custom10.

**Independent delivery.** The complete physical-copy root is
`workspace/best_redwood_custom_camera1_transport_20260911`. It contains, for
both datasets, partial/depth/semantic/camera inputs, GPT prompts and images,
Pixal3D GLBs and 100k priors, native MoGe artifacts, every initial registration
stage, the selected Camera-1 continuation, four-view residual evidence,
Partial OT and posterior fields, final 100k outputs, GT, and offline metrics.
No delivered file is hard-linked to the superseded experiment roots. Internal
text manifests were relocated to the new paths. All twenty
`final/<sample>/complete_100k.ply` files were checked at exactly 100,000 points
and SHA-256 matched against their selected posterior source before cleanup.

**Cleanup result.** After successful verification, the superseded source roots
`workspace/from_scratch_01184_debug_20260910` and
`workspace/custom_from_scratch_integrated_tuning_20260911` were removed from
the worktree and placed in the recoverable repository trash directory
`.codex-trash/20260911_best_redwood_custom_consolidation`. Omni, scene,
dataset, and unrelated experiment directories were not touched.

## 2026-09-11 00:04:06 CST — integrated PosteriorAdapter observation fusion

**User approval.** “确实 效果好特别多.” The approved experiment integrates
physical partial evidence into the smooth PosteriorAdapter deformation instead
of replacing points after deformation. Preserve these two outputs and the
shared configuration while running the remaining samples; do not overwrite
them with hard carrier-slot replacement.

**Outputs and inputs.** Approved predictions are
`workspace/from_scratch_01184_debug_20260910/posterior_integrated_fusion_v2/01184/posterior_prior_100k.ply`
and
`workspace/from_scratch_01184_debug_20260910/posterior_integrated_fusion_v2/07136/posterior_prior_100k.ply`.
Their partial overlays and four-view overlays are beside each prediction as
`partial_gray_integrated_red.ply` and `integrated_four_view_projection.png`.
Inputs are `data/redwood/partial/{01184,07136}.ply`, the registered priors under
`workspace/from_scratch_01184_debug_20260910/registration/<id>/final/`, and the
four-camera manifests under `residuals/<id>/render/render_manifest.json`.

**Upstream model record.** This experiment did not regenerate images or 3-D
priors. It reuses Pixal3D `models/Pixal3D-weights`, DINOv3
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe-2
`models/moge-2-vitl/model.pt`, and RMBG-2.0 `models/RMBG-2.0`; generation
resolution/seed/steps/guidance remain the saved upstream values in
`inputs/pixal/<id>/pixal3d_metadata.json`. New model call, scheduler, seed, CFG,
negative prompt, and semantic postprocessing: `NOT RUN` / `NOT APPLICABLE`.
The exact already-saved semantic prompt for 01184 is:

> Use case: sketch-to-render
> Asset type: camera-consistent semantic conditioning image for single-image 3D generation
> Primary request: Generate a complete, realistic RGB image by completing the object represented by Image 1, which is an incomplete depth map. The object category is a blue wheeled rubbish bin / outdoor garbage bin.
> Input images: Image 1 is the sole geometric and camera authority: an occluded depth rendering from a partial 3D scan.
> Scene/backdrop: pure white studio background, no floor clutter.
> Subject: one complete blue wheeled rubbish bin with a rectangular tapered bin body, closed hinged lid, rear handle/hinge structure, and exactly two black wheels mounted on the same axle. The two wheels must be front/back parallel wheels as implied by the depth image, not side-by-side decorations.
> Style/medium: clean realistic product photograph, coherent plastic and rubber materials, sharp boundaries, sufficient local detail for image-to-3D reconstruction.
> Composition/framing: preserve exactly Image 1's camera viewpoint, perspective, object orientation, apparent scale, image-plane center, crop, silhouette, body proportions, lid pose, and visible wheel locations. Complete only genuinely missing or occluded surfaces.
> Constraints: follow the depth silhouette and depth ordering closely; keep both wheels parallel and structurally attached; retain the slight three-quarter view; output one complete connected object. Do not rotate, mirror, recrop, rescale, recenter, tilt, shorten, widen, or redesign the bin. Do not add extra wheels, pedals, handles, text, logos, shadows that alter the silhouette, or any secondary object.
> Avoid: stylization, malformed geometry, detached parts, duplicated wheels, changed pose, changed camera, black background, text, watermark.

The exact already-saved semantic prompt for 07136 is:

> Use case: sketch-to-render. Create one complete, realistic RGB product image of a long black leather sofa from the supplied incomplete depth map. Image 1 is the sole geometric, camera, and foreground-mask authority. Treat every non-black depth pixel and its silhouette as a hard ControlNet-like spatial constraint: preserve exactly the oblique end-on camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, depth ordering, visible sofa end, seat plane, backrest line, and the strong foreshortening of the long sofa body. Complete only genuinely missing or occluded surfaces along the depth direction. Keep one coherent full-length sofa with a continuous seat, continuous backrest, two end armrests, and short attached feet, in dark leather on a pure white background. Do not turn it into a single chair or sectional sofa, do not shorten or widen the body, and do not rotate, mirror, recenter, rescale, tilt, redesign, or move observed surfaces. Sharp realistic boundaries and upholstery; no cushions detached from the sofa, text, logo, watermark, secondary object, clutter, or silhouette-changing shadow.

**Frozen integrated-fusion configuration.** Four saved cameras; 6144 spatially
sampled observation anchors; 1 px proposal radius; 2 px cross-view radius;
depth and metric anchor limits `.075` of partial diagonal; data weight `2.0`;
screening `.004`; three iterations; displacement cap `.05` of partial
diagonal; hidden coverage at least `.95`. The anchors enter the same embedded
ARAP carrier as soft targets with no hard point replacement, concatenation,
category rule, part rule, GT, CD, or EMD. Both outputs retain exactly 100,000
points and no new connected component. Offline-only CD-L1/EMD x100 are
`1.0650/2.0588` for 01184 and `1.7763/3.4295` for 07136.

## 2026-09-04 CST — Redwood-10 fixed registration + relaxed-anchor Gaussian edit

**User approval.** “效果非常好了 可以保存代码 提交到github上.” This is the
accepted result to preserve. Do not change the shared registration or Gaussian
parameters, regenerate upstream assets, or replace the 100k-prior carrier
without a new explicit experiment.

**Outputs.** The complete result root is
`workspace/relaxed_anchor_gaussian_redwood10_20260904`. For every sample
`01184, 05117, 05452, 06127, 06145, 06188, 06830, 07136, 07306, 09639`, the
registered prior is
`registration/<sample>/final/camera1_amplified_registered_100k.ply` and the
accepted prediction is
`gaussian/<sample>/decoded/partial_anchored_gaussian_decoded_100k.ply`.
Every prediction was checked to retain exactly 100,000 Pixal slots. The batch
manifest is `gaussian/batch_manifest.json`.

**Inputs.** The same root contains `inputs/partial/<sample>.ply`, saved-view
camera/depth/Qwen assets in `inputs/camera/<sample>/`, and GPT image,
Pixal input, GLB, sampled PLY and metadata in `inputs/pixal/<sample>/`.

**Upstream models and prompts.**

- Qwen model: `models/Qwen-Image-Edit-2511`; transformer:
  `models/nunchaku-qwen-image-edit/nunchaku_qwen_image_2511_balance_int4.safetensors`.
  Each full Qwen prompt follows exactly
  `生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的<label>，纯白背景`
  with labels `{rubbish bin, red chair, armchair, terracotta flower pot with
  leafy plant, table, red motorcyle, tricycle, leather sofa, red office trash
  can, Ergonomic Chair}` in the sample order above. Negative prompt is exactly
  ` `; true CFG is `4.0`; steps are `40`; input is `raw_depth.png`; Qwen seed,
  scheduler and backend are `UNKNOWN`.
- GPT clarity image prompt, model/version, seed, scheduler, CFG and negative
  prompt are `UNKNOWN` unless saved beside a retained input as `prompt.txt`.
  The fixed contract is clarity-only: preserve the Qwen camera, pose, scale,
  silhouette and observed part layout; do not rotate, rescale, recenter,
  mirror, add/remove parts, or alter articulated local geometry.
- Pixal3D: `models/Pixal3D-weights`; DINOv3:
  `models/dinov3-vitl16-pretrain-lvd1689m`; MoGe-2:
  `models/moge-2-vitl/model.pt`; RMBG-2.0: `models/RMBG-2.0`. Frozen Pixal
  generation uses seed `42`, 1024 cascade, 12 sparse/shape/texture steps,
  sparse/shape guidance `7.5`, texture guidance `1.0`, 300k decimation target,
  2048 texture and 100k surface samples.

**Frozen inference.** Registration is the fixed native Pixal--MoGe analytic
initialization, two-camera bridge, coupled residual and Camera-1 amplified /
wide-tilt / final-tilt continuation. Gaussian editing uses Camera-1 plus six
positive-overlap signed-PCA virtual views; 8-neighbor graph, edge ratio `1.8`,
screening `.0015`, anchor/displacement caps `.075`, six self-protection views
with weight `.01`, protection exclusion `.10`, remote gain `1.0`, CG tolerance
`1e-5`, and 240 iterations. The decoder performs collision-free one-to-one
partial-anchor replacement. No GT/CD/EMD/category/sample-specific routing is
used by inference.

**Offline-only evidence.** After the batch was frozen, the 16,384-point FPS
audit with seed `6145` reported mean CD-L1/EMD `1.58197163 / 2.51144224`
(×10²). Per-sample results and protocol are under
`postfreeze_cd_emd/{metrics_samples.csv,metrics_summary.json,protocol.json}`.
These values are reporting-only and must not become a test-time selection gate.

## 2026-09-04 CST — `01184` scratch Qwen → GPT → Pixal end-to-end validation

**User approval.** “现在流程已经没问题了.” This confirms the scratch
upstream path is valid. Preserve its saved-view geometry and the fixed
registration/Gaussian parameters; do not replace them with a replay asset or a
metric-selected variant.

**Inputs and outputs.** Partial and GT are respectively
`data/redwood/partial/01184.ply` and `data/redwood/gt/01184.ply`. The complete
run is `workspace/mainline_upstream_smoke_20260904`: Qwen depth/semantic and
Camera-1 assets are in `semantic/01184`; GPT input and prompt are in
`pixal_input/01184`; Pixal GLB/100k prior/metadata are in `pixal/01184`;
registration ends at
`registration/01184/final/camera1_amplified_registered_100k.ply`; and the
approved complete prediction is
`gaussian/01184/decoded/partial_anchored_gaussian_decoded_100k.ply`.

**Models and exact generation record.** Qwen pipeline is
`models/Qwen-Image-Edit-2511`, transformer is
`models/nunchaku-qwen-image-edit/nunchaku_qwen_image_2511_balance_int4.safetensors`;
input is `raw_depth.png`, output is 512 px, true CFG `4.0`, steps `40`, and
negative prompt is exactly ` `. The exact Qwen prompt is
`生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的rubbish bin，纯白背景`.
Qwen seed, scheduler and backend are `UNKNOWN`. The GPT asset is
`pixal_input/01184/gpt_image.png`; its full prompt is recorded verbatim in
`gpt_refinement_prompt.txt`; model/version, seed, scheduler, CFG and negative
prompt are `UNKNOWN`. Pixal uses `models/Pixal3D-weights`, DINOv3
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe-2
`models/moge-2-vitl/model.pt`, and RMBG-2.0 `models/RMBG-2.0`, with seed `42`,
1024 cascade, 12 sparse/shape/texture steps, guidance `7.5/7.5/1.0`, 300k
decimation, 2048 texture and 100k surface points.

**Post-processing and reporting.** The run uses deterministic 256-view
saved-camera selection, grayscale depth + OpenCV fill, Qwen completion, GPT
clarity edit, Pixal preprocessing, native Pixal--MoGe alignment, two-camera
bridge, Camera-1 continuation, and the fixed partial-anchored Gaussian edit
and decode. No GT is read before the final prediction. The offline 16,384-point
audit (seed `6145`) reported CD-L1×100 `1.16162859` and EMD×100 `1.80500858`;
these are reporting-only.

## 2026-09-05 CST — globally calibrated fixed registration/edit defaults

**Status.** User-directed calibration of the already fixed mainline. The
Qwen → GPT → Pixal assets, registration stage order, Gaussian edit/decode
algorithm, and 100k prior carrier are unchanged. Only two values are updated
globally for every sample: the final Camera-1 Sim(3) trust region is `1.0°`
and the saved/virtual positive-correspondence radii are `1.0 px`. There is no
sample/category branch, learned update, or inference-time GT/CD/EMD access.

**Outputs.** The complete candidate is
`workspace/fixed_mainline_calibration_20260905/combo_final100_pixel100`.
Its registration inputs are the ten final PLYs under
`workspace/fixed_mainline_calibration_20260905/registration_final100_replay/<id>/final/`;
the final predictions are
`combo_final100_pixel100/gaussian/<id>/decoded/partial_anchored_gaussian_decoded_100k.ply`.
All ten (`01184, 05117, 05452, 06127, 06145, 06188, 06830, 07136, 07306,
09639`) were verified to contain exactly 100,000 points. The no-override smoke
run is `workspace/fixed_mainline_default_smoke_20260905`; for `01184` both its
final registration PLY and decoded PLY are byte-identical to the selected
candidate.

**Inputs/models/prompts.** This calibration did not regenerate an image or a
3-D prior. It reuses the exact partial, Camera-1, Qwen/GPT/Pixal inputs from
`workspace/relaxed_anchor_gaussian_redwood10_20260904/inputs`; the complete
Qwen prompts, GPT prompt records, model paths, checkpoints, seeds, and upstream
generation parameters are therefore exactly those recorded in the preceding
2026-09-04 accepted Redwood-10 entry. New Qwen/GPT/Pixal generation prompt:
`NOT RUN`. New image/3-D generation seed, scheduler, CFG and negative prompt:
`NOT APPLICABLE`. Native registration uses the existing Pixal 100k prior plus
MoGe-2 `models/moge-2-vitl/model.pt` and RMBG-2.0 `models/RMBG-2.0` under the
same fixed two-camera route.

**Frozen numerical settings.** Standard/wide Camera-1 continuation remains
unchanged (32,000 points; wide trust region `1.0°`). The final continuation
uses levels `(0.010, 1.0°, 0.010)`, `(0.004, 0.35°, 0.004)`, and
`(0.001, 0.10°, 0.001)`. Gaussian edit/decode uses `1.0 px` for both saved and
virtual positive matches; six virtual views at 384 px; anchor/displacement
caps `.075`; 8-neighbour graph, edge ratio `1.8`, screening `.0015`; six
protection views, weight `.01`, exclusion `.10`; remote gain `1.0`; and CG
`1e-5/240`. Do not alter these values without a new complete global audit.

**Offline-only evidence.** The fixed 16,384-point audit with seed `6145`
reported CD-L1×100 / EMD×100:

| id | CD | EMD |
| --- | ---: | ---: |
| 01184 | 1.0610 | 1.7740 |
| 05117 | 1.6685 | 2.9317 |
| 05452 | 0.9441 | 1.5376 |
| 06127 | 2.3836 | 3.7654 |
| 06145 | 0.6561 | 1.0179 |
| 06188 | 1.2063 | 1.9679 |
| 06830 | 1.5183 | 2.7327 |
| 07136 | 1.2703 | 2.3600 |
| 07306 | 3.1936 | 3.9313 |
| 09639 | 1.7803 | 2.7671 |
| mean | **1.5682** | **2.4786** |

This improves the prior fixed baseline `1.5820 / 2.5114` on both metrics. The
metric file is `combo_final100_pixel100/metrics.{csv,json}` and is reporting
only; it was never read by registration or Gaussian editing.

## 2026-09-05 CST — accepted default broad Camera-1 basin capture

**User approval.** “可以 直接替换冻结主线成为新方案.” The fixed mainline must
therefore run the broad Camera-1 pixel-Sim(3) basin-capture stage by default.
It may be disabled only with `--no-coarse-basin-recovery` for an ablation; do
not restore the former disabled default without a new explicit instruction.

**Outputs.** The accepted Redwood-10 registration audit is
`workspace/mainline_results_20260905/redwood/registration/<id>/final/camera1_amplified_registered_100k.ply`, and the corresponding accepted 100k
predictions are
`workspace/mainline_results_20260905/redwood/gaussian/<id>/decoded/partial_anchored_gaussian_decoded_100k.ply`, for IDs `01184, 05117, 05452,
06127, 06145, 06188, 06830, 07136, 07306, 09639`. Offline-only metrics are
`workspace/mainline_results_20260905/redwood/metrics/coarse_basin.{json,csv}`.

**Inputs/models/prompts.** Registration used `data/redwood/partial/<id>.ply`,
Camera-1 assets under
`/opt/data/private/cr/lab/GenPC/workspace/redwood_onestage_rawdepth_512_stage2_20260714/<id>/`, and GPT/Pixal assets under
`/opt/data/private/cr/lab/GenPC/workspace/redwood_qwen_gpt_pixal_bidirectional_mainline_20260823/<id>/`.
No upstream image or 3-D generation was rerun. The Qwen model is
`models/Qwen-Image-Edit-2511`; transformer is
`models/nunchaku-qwen-image-edit/nunchaku_qwen_image_2511_balance_int4.safetensors`.
The full Qwen prompt is exactly `生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的<label>，纯白背景`, with labels `{rubbish bin, red chair, armchair,
terracotta flower pot with leafy plant, table, red motorcyle, tricycle,
leather sofa, red office trash can, Ergonomic Chair}` in the ID order above.
The Qwen negative prompt is exactly ` `; resolution is 512 px, true CFG is
`4.0`, steps are `40`, input is `raw_depth.png`, and Qwen seed/scheduler/backend
are `UNKNOWN`. The full GPT clarity prompt is stored beside each retained input
as `prompt.txt`; GPT model/version, seed, scheduler, CFG and negative prompt
are `UNKNOWN`. The GPT contract is preserve Qwen camera, pose, scale,
silhouette and observed part layout; do not rotate, rescale, recenter, mirror,
add/remove parts, or alter articulated local geometry. Pixal3D uses
`models/Pixal3D-weights`, DINOv3
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe-2
`models/moge-2-vitl/model.pt`, and RMBG-2.0 `models/RMBG-2.0`; inherited
Pixal parameters are seed `42`, 1024 cascade, 12 sparse/shape/texture steps,
guidance `7.5/7.5/1.0`, 300k decimation, 2048 texture, and 100k surface samples.

**Frozen route and parameters.** After native Pixal--MoGe alignment and the
two-camera bridge/coupled residual, every sample scores identity and shared
pixel-pair Sim(3) residual fractions `1/8, 1/4, 1/2, 3/4, 1` using a 30-degree,
scale `[0.45,2.40]`, translation `1.25` partial-bbox-diagonal capture region.
The winning transform feeds the unchanged narrow pixel residual, 32k-point
Camera-1 standard/wide/final continuations (wide/final `1.0°`), and the
existing Gaussian edit/decode: 1.0 px saved/virtual matches, six 384-px views,
`.075` anchor/displacement caps, 8-neighbor/1.8-edge graph, `.0015` screening,
six `.01` protection views, `.10` exclusion, remote gain `1.0`, and CG
`1e-5/240`. No GT/CD/EMD/category/sample-specific decision is used in inference.

**Offline-only evidence.** With 16,384 points and seed `6145`, the new route
reports mean CD-L1×100 / EMD×100 `1.5738481 / 2.4813253` compared with the
previous frozen route's `1.5682055 / 2.4785676` (`+0.36% / +0.11%`). This
small bounded regression was accepted to make the mainline robust to the large
wrong-basin failures independently observed on custom scans; offline metrics
remain reporting-only and do not control inference.

## 2026-09-05 CST — accepted scene wrapper single-instance registration POC

**User approval.** The user judged the registered scene mug as “配得确实不错”.
Keep this POC as the verified scene-coordinate-frame reference; do not change
the direct-RGB semantic contract, shared-Pixal-MoGe partial definition, or
textured-mesh export without a new scene audit.

**Sample and outputs.** `coffee_mug_0` from
`data/scene_samples/scene_3.png`. Inputs and all produced assets are under
`workspace/scene3_gpt_mask_poc/run/`: source mask/crop
`masks/coffee_mug_0.png` and `instances/coffee_mug_0/masked_crop.png`, partial
`inputs/partial/coffee_mug_0.ply`, frozen direct semantic
`inputs/camera/coffee_mug_0/img.png` (identical to
`inputs/pixal/coffee_mug_0/gpt_image.png` after 512px aspect-preserving white
padding), Pixal GLB `inputs/pixal/coffee_mug_0/pixal3d.glb`, final registration
`registration/coffee_mug_0/final/camera1_amplified_registered_100k.ply`, and
registered textured-mesh outputs
`scene_meshes/coffee_mug_0_registered_mesh.glb` and
`scene_meshes/completed_scene_registered_meshes.glb`.

**Generation contract.** GPT direct semantic prompt, verbatim:
`Starting only from this isolated RGB scene crop, produce exactly one complete plain white ceramic coffee mug on a pure white square background. Preserve the observed camera viewpoint, silhouette, aspect ratio, material, colour, and every visible structural detail. Complete only genuinely occluded or missing portions; do not rotate, resize disproportionately, or redesign the object. Do not output a depth map or add props, text, people, floor, wall, shadows, or a second object.`
Negative prompt: `NONE`. GPT model/version, seed, scheduler, CFG, and internal
generation resolution: `UNKNOWN`. The mask prompt is saved verbatim in
`gpt_image_actions.json`. No depth-to-semantic/Qwen step was run; the scene
partial is a 1-pixel-eroded GPT-mask subset of the single scene Pixal-MoGe
observation. The final POC predates the later generic stronger pose-lock text,
but preserves the accepted direct-RGB/no-rotation contract.

**Models and fixed post-processing.** Pixal metadata is preserved in
`inputs/pixal/coffee_mug_0/pixal3d_metadata.json`: Pixal3D
`models/Pixal3D-weights`, DINOv3
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe-2
`models/moge-2-vitl/model.pt`, RMBG-2.0 `models/RMBG-2.0`; seed `42`, 1024px,
12 sparse/shape/texture steps, guidance `7.5/7.5/1.0`, 300k decimation, 2048
texture, and 100k sampled points. Registration is the fixed two-camera
Pixal-MoGe Camera-1 continuation recorded in
`registration/batch_manifest.json`: no proposal gate, broad basin recovery
enabled, 32k Camera-1 points, and wide/final tilt trust regions `1.0°`.
The GLB is transformed only by the cumulative final registration Sim(3);
there is no point fusion, Gaussian edit, point deletion, GT, CD, or EMD use.

## 2026-09-05 CST — accepted five-scene direct-GPT textured mesh delivery

**User approval.** “ok 效果很好”. Preserve the isolated scene pipeline and
its shared scene-MoGe coordinate frame. In particular, do not reintroduce a
depth-shift trust-region cap or alter object-level mainline code without a new
scene audit.

**Samples and final outputs.** The accepted delivery root is
`workspace/final_scene_meshes_20260905/`, with source image, final textured
GLB, collision/placement manifest, and verbatim GPT action record in each of
`scene_1` through `scene_5`. The final files are
`scene_<n>/completed_scene_registered_meshes.glb`. Scene 3 is the previously
accepted seven-instance scene output copied from
`workspace/scene3_all_instances_mesh_erosion5_20260905/run/scene_meshes_scene_moge_collision_exact_20260905/`;
scenes 1, 2, 4, and 5 were run in
`workspace/scene_batch_all_instances_20260905/`. The delivery contains 4, 4,
7, 7, and 5 textured instance meshes for scenes 1--5 respectively. All GLB
nodes have identity transforms because every placement Sim(3) is baked into
the textured mesh vertices. `scene_5` additionally records the user-corrected
full left blue upholstered armchair mask in
`scene_5/scene5_instance_board_corrected.png`.
For reproducibility, the delivery also retains `scene_<n>/run/` for all five
scenes: scene-MoGe/context, masks, crops, frozen GPT RGB, Camera-1/Pixal
inputs, Pixal mesh/100k sample/native-MoGe artifacts, registration/bridge
transforms, and logs. A file-level audit verified this complete chain for
every 4/4/7/7/5-instance scene.

**Inputs, prompts, and models.** Inputs are exactly
`data/scene_samples/scene_<n>.png`. There is no Qwen/depth-to-semantic step:
one shared scene MoGe observation is inferred directly from each RGB input,
then a 5-pixel-eroded GPT instance mask extracts each visible object partial.
The complete per-instance mask and semantic prompts are copied verbatim in
each delivery `gpt_image_actions.json`. In literal template form, for an exact
recorded label `<label>`, the mask prompt is:
`Segment exactly one visible <label> in this scene. Preserve the source image pixel grid and output a binary mask at the exact same resolution: pure white for pixels belonging to this <label>, pure black for everything else. Do not include shadows, floor, wall, adjacent objects, or background. Do not redraw the object.`
The direct completion prompt is:
`Starting only from this isolated RGB scene crop, produce exactly one complete <label> on a pure white square background. POSE LOCK: the crop is the only camera reference. Preserve the exact observed object direction, left/right relation, yaw, pitch, roll, image-plane angle, perspective/foreshortening, silhouette, aspect ratio, material, colour, and visible structural details. Complete only genuinely occluded or missing portions behind the observed view. Never canonicalize it into a frontal, side, top-down, symmetric, catalog, or product-shot viewpoint; do not rotate, mirror, re-pose, resize disproportionately, or redesign it. Do not output a depth map or add props, text, people, floor, wall, shadows, or a second object.`
The exact `<label>` substitutions and asset paths are in those records. GPT
image model/version, seed, scheduler, CFG, negative prompt, and raw output
resolution are `UNKNOWN`; the installed Camera-1 and Pixal image is
aspect-preserving white-padded to 512 px. Pixal uses
`models/Pixal3D-weights`, DINOv3
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe-2
`models/moge-2-vitl/model.pt`, and RMBG-2.0 `models/RMBG-2.0`; seed `42`,
1024 cascade, 12 sparse/shape/texture steps, guidance `7.5/7.5/1.0`, and
100k-face decimation target. No GT, CD, or EMD is read during scene inference.

**Frozen post-processing.** Each complete textured Pixal mesh undergoes only
native Pixal--MoGe alignment plus the camera-2 → scene-MoGe bridge and a
common table-world transform. No point fusion, Gaussian editing, or mesh-face
pruning occurs. Exact `python-fcl` contact detection then moves only the
scene-MoGe-farther object along the original scene camera's positive depth
direction by the smallest collision-free distance; there is no object-scale
movement cap or lateral/table-normal adjustment. The re-exported scene 2 and
scene 4 reports have zero remaining pairs after shifts of `2.977501` for the
tent and `2.115/.318/.43575` for the coffee table/left side table/right side
table. Scene 1, scene 3, and scene 5 already report zero remaining FCL pairs.
The full project test suite passed `60/60` after the unbounded minimal-depth
solver change.

## 2026-09-07 CST — accepted bounded agentic Redwood-10 probe

**User approval.** The user judged the ten-sample agentic result as “效果非常好”.
Keep this isolated feasibility result, its explicit front/back re-plan for
07306, and the fixed conservative local-edit trust region unchanged unless a
new audit is requested. This is not the frozen object-mainline baseline.

**Samples and outputs.** Inputs are exactly `data/redwood/partial/<id>.ply`
for `01184, 05117, 05452, 06127, 06145, 06188, 06830, 07136, 07306, 09639`.
The consolidated ten-sample metric summary is
`workspace/agentic_redwood10_final_20260907/metrics/redwood10_offline.json`:
offline CD-L1x100 `1.5834`, EMDx100 `2.3454` at 16,384 points, metric seed
6145. GT was read only by this completed offline audit. All complete per-sample
traces are retained under `workspace/agentic_redwood10_final_20260907/samples/<id>/`,
with the selected predictions collected in
`workspace/agentic_redwood10_final_20260907/final_predictions/`. The
user-approved 07306 front-facing re-plan is retained as
`workspace/agentic_redwood10_final_20260907/samples/07306/`; its selected
conservative decoded 100k PLY is `final/agent_selected_100k.ply`.
The direct trace initially accepted the pre-edit registered carrier, but the
reported ten-sample summary intentionally substitutes this audited conservative
07306 decode. All final clouds contain 100,000 slots.

**Observation and prompt contract.** The planner selected the bounded
partial-only convex-hull candidate `base` for all samples except 07306. The
accepted 07306 re-plan selected the explicit antipodal `opposite_180`
candidate before any semantic/prior tool was run. Qwen received `raw_depth.png`
and the following prompts,
verbatim (negative prompt: `' '` for every sample):
```
01184: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的rubbish bin，纯白背景
05117: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的red chair，纯白背景
05452: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的armchair，纯白背景
06127: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的terracotta flower pot with leafy plant，纯白背景
06145: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的table，纯白背景
06188: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的red motorcyle，纯白背景
06830: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的tricycle，纯白背景
07136: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的leather sofa，纯白背景
07306: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的red office trash can，纯白背景
09639: 生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的Ergonomic Chair，纯白背景
```
Each exact `qwen_edit_prompt.txt`, depth raster, semantic image, camera,
pixel UV map, Pixal input, registration trace, and state-hashed decision is
stored under its corresponding probe root. Qwen uses
`models/Qwen-Image-Edit-2511` plus
`models/nunchaku-qwen-image-edit/nunchaku_qwen_image_2511_balance_int4.safetensors`,
40 steps, true CFG 4.0, 512px Camera-1 semantic output, and 1024px native
stage-1 generation. Qwen seed/scheduler: `UNKNOWN` (no explicit seed was
passed). No GPT clarity edit was used in this isolated probe.

**Prior, registration, and adaptation.** Pixal uses
`models/Pixal3D-weights`, DINOv3
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe-2
`models/moge-2-vitl/model.pt`, and RMBG-2.0 `models/RMBG-2.0`; Pixal seed
42, 1024px input, 12 sparse/shape/texture steps, guidance `7.5/7.5/1.0`, and
100k sampled carrier. Every trace uses the bounded native Pixal--MoGe,
pixel-indexed two-camera bridge, joint proper Sim(3), and three-stage
Camera-1 residual continuation; all continuous variables remain in these
deterministic executors. Gaussian adaptation is used only where stated in the
trace: historic 01184 uses the prior `.075` trial, 09639 uses `.020`, and the
accepted 07306 retry uses `.020` anchor/displacement ratios, 1px saved/virtual
pixel support, six virtual views, six prior-protection views, and 100k-slot
collision-free decode. The 07306 editable Gaussian motion is capped at 2% of
the partial diagonal; it anchors 26.427% of carrier slots while retaining the
complete unobserved prior support. No decision used GT, CD, or EMD.

**Approved constraints.** The old rejected rear-view 07306 trace was retired
during consolidation; do not overwrite the delivered front-facing re-plan.
Do not silently promote this probe over the frozen object mainline, and do not
loosen the agent-local 2% trust region without a cross-sample wheel/detail
audit.

## 2026-09-08 CST — domestic-pig camera-conditioned Gaussian diagnostic

**User feedback.** The user confirmed only that the `domestic_pig` result's
*global scale* is “确实好了不少”. They explicitly found the local front- and
rear-leg alignment still inadequate. Retain this output as a diagnostic
baseline, not as an accepted completion or a promotion candidate.

**Exact outputs.** The approved candidate is
`workspace/custom10_fixed_mainline_20260907/pig_camera_conditioned_gaussian_20260908c/`.
Its complete 100k Gaussian-mean carrier is
`camera_conditioned_gaussian_editable_prior_100k.ply`; the partial-gray / prior-red
overlay is `camera_conditioned_gaussian_partial_gray_prior_red.ply`; the saved
Camera-1 overlay is `camera_conditioned_gaussian_saved_view_projection.png`;
the six-view diagnostic is `adapted_virtual_views.png`; and
`camera_conditioned_gaussian_field.npz` records the means and
`editable/locked/protected/moved` masks.

**Inputs and execution.** The prior was the accepted global extent carrier
`workspace/custom10_fixed_mainline_20260907/pig_global_axis_scale_probe_20260907/principal_then_depth_extent/camera_axis_scaled_prior_100k.ply`.
The observed partial and Camera-1 are respectively
`workspace/custom10_fixed_mainline_20260907/inputs/partial/domestic_pig.ply`
and `workspace/custom10_fixed_mainline_20260907/inputs/camera/domestic_pig/camera.pth`;
the semantic image used only for the overlay is
`workspace/custom10_fixed_mainline_20260907/inputs/camera/domestic_pig/img.png`.
The tool was run with `CUDA_VISIBLE_DEVICES=0`, 512px render, padding `.15`,
Camera-1 residual threshold `.05` of partial diagonal, locked-support threshold
`.018`, and soft projection/depth data weight `.25`. No image or 3D generator
was invoked in this edit stage; model/checkpoint, seed, CFG, scheduler, prompt,
and negative prompt are therefore `N/A`.

**Method and diagnostic boundary.** The edit preserved all 100k prior slots,
used no GT/CD/EMD during inference, selected 562 coherent Camera-1 controls,
locked 2,091 aligned visible means, protected 48,015 unobserved means, and
moved 47,687 means through a local Gaussian graph field. Its no-GT control
projection/depth residual diagnostics fell by `28.84%/29.22%`. Do not overwrite
these artifacts while diagnosing the leg residual. Do not promote this
candidate or claim local alignment is solved; assess a camera-pixel status map
and a stronger partial-depth adaptation before any generalization or mainline
decision.

**Subsequent user feedback.** The user found the three-stage continuation
(`pig_camera_conditioned_gaussian_20260908f`) still insufficient to bridge the
local prior/partial discrepancy at the front and rear legs. Treat every
means-only candidate in `pig_camera_conditioned_gaussian_20260908[a-f]` as
rejected for final completion; retain them only as evidence that scale can
improve while missing observed support cannot be recovered by moving existing
prior slots alone.

## 2026-09-08 12:13:59 CST — accepted generic PosteriorAdapter pig result

**User approval.** The user judged the result “效果很顶级”. Preserve the
category-agnostic Partial-OT plus hierarchical embedded-ARAP posterior and its
fixed shared configuration while running the remaining Custom and Redwood
generalization audit. Do not add pig/animal/limb labels, coordinate-side rules,
manual regions, sample thresholds, or GT-driven selection.

**Exact inputs and outputs.** The fixed registered 100k carrier is
`workspace/custom10_fixed_mainline_20260907/registration/domestic_pig/final/camera1_amplified_registered_100k.ply`;
the observed partial, Camera-1, depth-derived semantic image, and upstream
Pixal assets are respectively
`workspace/custom10_fixed_mainline_20260907/inputs/partial/domestic_pig.ply`,
`workspace/custom10_fixed_mainline_20260907/inputs/camera/domestic_pig/camera.pth`,
`workspace/custom10_fixed_mainline_20260907/inputs/camera/domestic_pig/img.png`,
and `workspace/custom10_fixed_mainline_20260907/inputs/pixal/domestic_pig/`.
The accepted posterior root is
`workspace/custom10_fixed_mainline_20260907/pig_partial_ot_embedded_posterior_20260908h/`.
Its final fixed-cardinality result is `posterior_prior_100k.ply`; the exact
coarse output, OT table, support states, displacement field, saved-camera
overlay, six-view overlay, and complete diagnostic record are
`coarse_prior_100k.ply`, `partial_ot_pairs.npy`,
`posterior_support_status.png`, `posterior_field.npz`,
`posterior_saved_view_projection.png`, `posterior_virtual_views.png`, and
`posterior_info.json`. No prior point is deleted and no partial point is
concatenated. The rebuilt 10-neighbour output surface graph has exactly the
same two connected components and sizes as the input carrier: one 99,958-point
body and its pre-existing 42-point sampling island. Hidden-view occupancy is
`1.23948`, above the required 95% retention.

**Posterior execution parameters.** No learned model, prompt, negative prompt,
seed, scheduler, CFG, or image resize is used by this posterior-only step;
those fields are `N/A`. The full exact configuration is serialized verbatim in
`posterior_info.json`: partial/prior OT samples `3072/6144`, 24-neighbour local
features, 60 unbalanced-Sinkhorn iterations, relaxation `.72`, temperature
floor `.012`, normalized 3D/screen/depth gates `.34/.28/.34`, residual
quantiles `.22/.42`, graph-node fractions `.020/.055` bounded to `192--6144`,
four-node skinning, coarse graph `18` neighbours / `2.45` edge ratio / data
weight `2.5` / screening `.0008` / five iterations / displacement cap `.28`
partial diagonal, fine graph `10` / `1.85` / `4.0` / `.003` / five / `.12`,
attachment ratio `3.2`, minimum observed improvement `.025`, edge compression
`.55`, robust p99 edge-stretch cap `2.8`, hidden coverage `.95`, and coverage
resolution `160`. CUDA is used for batched OT; the sparse graph solve is
deterministic CPU SciPy. All geometric thresholds are dimensionless ratios,
median-spacing scales, residual quantiles, or visibility fractions.

**Upstream reproducibility.** The reused Qwen prompt is, verbatim,
`生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的domestic pig，纯白背景`;
negative prompt is one blank space (`' '`), true CFG `4.0`, 40 steps, 512px
Camera-1 semantic output, and 1024px native generation. Qwen seed and scheduler
are `UNKNOWN`. The GPT clarity prompt is copied verbatim in
`inputs/pixal/domestic_pig/prompt.txt`; GPT model/version, negative prompt,
seed, scheduler, CFG, and raw output resolution are `UNKNOWN`, so the upstream
image generation is not exactly reproducible from metadata alone. The reused
Pixal prior uses `models/Pixal3D-weights`,
`models/dinov3-vitl16-pretrain-lvd1689m`, `models/moge-2-vitl/model.pt`, and
`models/RMBG-2.0`, seed `42`, requested/actual resolution `1024`, xFormers,
12 sparse/shape/texture steps with guidance `7.5/7.5/1.0`, 300k-face target,
and 2048 texture size. The posterior step itself is exactly reproducible from
the four fixed inputs above.

**Offline firewall.** GT is
`data/custom/domestic_pig/gt_data/domestic_pig_gt.ply` and was opened only
after the posterior was frozen. At 16,384 points and seed 6145,
`offline_metrics.json` reports CD-L1x100 `1.47515414` and EMDx100
`1.84705555`; these values were never available to Partial OT, ARAP, line
search, support-state classification, or acceptance.

## 2026-09-08 18:08 CST — fresh Redwood10/Custom10 candidate (pending visual approval)

**Status.** This is a complete from-scratch generalization candidate, not an
accepted replacement for the frozen object mainline.  The user identified the
fresh `07136` sofa and `07306` waste-bin semantic observations as having
unreasonable views/local scale.  The recovery below changes only the generic
bounded view action and reruns the ordinary semantic, prior, registration and
posterior tools.  It contains no category, sample, part, coordinate-side or GT
condition.  Do not promote or delete the rejected attempts until the user has
visually reviewed the selected point clouds.

**Complete artifacts.** The immutable experiment root is
`workspace/posterior_adapter_e2e_redwood_custom_20260908/`.  Redwood final
100k carriers are hard-linked under `redwood/final_selected/<id>/` and Custom
final 100k carriers under `custom/final_selected/<name>/`.  Exact source
selection is in `redwood/final_selected/selection_manifest.json`; aggregate
and per-sample offline metrics are in each dataset's `offline_metrics.json`
and `offline_metrics.csv`.  Every generated image, native Pixal artifact,
registration state, verifier state, rejected candidate and PosteriorAdapter
diagnostic remains below this root.  The run summary is `RUN_SUMMARY.md`.
For convenient review, the selected artifacts are additionally organized by
sample under `workspace/posterior_adapter_selected_redwood_custom_20260908/`.
Each `redwood/samples/<id>/` and `custom/samples/<name>/` directory contains
the selected inputs/intermediates and one canonical `final_100k.ply`. These
are hard links to the immutable source artifacts, not regenerated copies; all
20 final files were verified at exactly 100,000 vertices.

**Generic view recovery.** The bounded candidate family is `base`,
`opposite_180`, and yaw rotations `+/-30`, `+/-60`, `+/-90` degrees around the
partial-derived camera.  A partial-only diagnostic board selects a discrete
camera; semantic/prior branches are accepted using silhouette, depth and
visible-3D verifier evidence, never GT/CD/EMD.  The selected sofa branch is
`redwood/view_retry_alt/07136/` (`opposite_180`), whose final posterior is
`redwood/view_retry_alt/posterior/07136/posterior_prior_100k.ply`.  The selected
waste-bin branch is `redwood/view_retry/07306/` (`opposite_180`), whose final
carrier is `redwood/view_retry/07306/final/agent_selected_100k.ply`.  The
rejected malformed sofa attempt is `redwood/view_retry/07136/`; the rejected
oblique-bin attempt is `redwood/view_retry_alt/07306/`.  A GPT clarity probe at
`redwood/gpt_bin_candidate/` was also rejected by the no-GT verifier and is not
the selected result.

**Semantic and model record.** Qwen prompts are saved verbatim next to each
candidate camera in its `qwen_edit_prompt.txt`; they use the fixed form
`生成一张图像，参考图1遮挡情况下的深度图，并遵循以下描述：完整的<类别名>，纯白背景`,
negative prompt one blank space (`' '`), true CFG `4.0`, 40 steps, a 512px
camera semantic result and 1024px native generation.  Qwen uses
`models/Qwen-Image-Edit-2511` with
`models/nunchaku-qwen-image-edit/nunchaku_qwen_image_2511_balance_int4.safetensors`;
seed and scheduler are `UNKNOWN`.  Pixal uses `models/Pixal3D-weights`,
`models/dinov3-vitl16-pretrain-lvd1689m`, `models/moge-2-vitl/model.pt`, and
`models/RMBG-2.0`, seed `42`, resolution `1024`, 12 sparse/shape/texture steps,
guidance `7.5/7.5/1.0`, xFormers, 300k-face target, 2048 texture and a 100k
point carrier.  The rejected GPT-bin prompt is copied verbatim in
`redwood/gpt_bin_candidate/inputs/pixal/07306/gpt_image_prompt.txt`; GPT model
version, seed, scheduler, CFG and negative prompt are `UNKNOWN`.

**Geometry and posterior record.** Registration uses the existing
Pixal--MoGe--partial cross-camera Sim(3) plus the ordinary three-stage
broad-to-narrow Camera-1 residual refinement.  The same accepted generic
PosteriorAdapter configuration recorded above is then applied; it preserves
all 100k prior slots and uses no GT.  On `07136` it intentionally returns the
identity because no coherent residual transport passes its structural gates.
On `07306` the existing uniform `.075` partial-anchored Gaussian action is
accepted because no-GT energy improves from `0.1045409` to `0.0948769`, while
both 1% and 2% visible-surface coverage reach `1.0` and all 100k slots remain.

**Offline-only report.** At 16,384 points and seed 6145, selected Redwood10
mean CD-L1x100/EMDx100 is `1.50174597/2.37392348`; selected Custom10 mean is
`2.01179441/2.99937962`.  The recovered `07136` is
`1.11914463/2.02244818` and `07306` is `3.47092301/3.88251394`.  These metrics
were computed only after each no-GT branch decision and were not exposed to
view selection, registration, adaptation or stopping.

**Visual-review update.** The user judged all ten consolidated Redwood outputs
good, but found that some Custom outputs lose too much local detail. Therefore
Redwood is visually acceptable, while the consolidated Custom candidate is
explicitly rejected for final promotion pending a category-independent audit
of OT confidence, stable-region drift and deformation-graph strain. Do not
interpret the improved Custom aggregate metric as approval, and do not tune
the repair using GT/CD/EMD or introduce sample/category branches.

## 2026-09-08T22:17:51+08:00 — accepted Pig cross-view residual image conditions

**User approval and boundary.** The user judged the final FRONT/SIDE/BACK
conditions “完全ok”. Preserve these images, their view order, Camera-1 anchor,
local contours, object identity, and prompt logic. This approval applies to
the image conditions only; the TRELLIS 3-D output and any later registration
remain pending visual/metric review and must not be presented as accepted.

**Exact inputs and accepted images.** The registered Pixal carrier and observed
partial are
`workspace/custom10_fixed_mainline_20260907/registration/domestic_pig/final/camera1_amplified_registered_100k.ply`
and `data/custom/domestic_pig/partial_data/single_scan/domestic_pig_partial.ply`.
The camera/render contract is
`workspace/trellis_pig_multiview_probe_20260908/conditions/original/render_manifest.json`.
The no-GT component evidence, numeric ledger, edit prompt, accepted generated
board, and final Camera-1-frozen TRELLIS inputs are respectively:

- `workspace/trellis_pig_multiview_probe_20260908/conditions/cross_view_ledger_v4/cross_view_residual_ledger_board.png`;
- `workspace/trellis_pig_multiview_probe_20260908/conditions/cross_view_ledger_v4/cross_view_residual_ledger.json`;
- `workspace/trellis_pig_multiview_probe_20260908/conditions/cross_view_ledger_v4/cross_view_residual_refinement_prompt.txt`;
- `workspace/trellis_pig_multiview_probe_20260908/conditions/cross_view_ledger_v4/gpt_cross_view_refined_front_side_back.png`;
- `workspace/trellis_pig_multiview_probe_20260908/conditions/cross_view_ledger_v4_hybrid/trellis_condition_{front,side,back}.png`.

The final front condition is copied byte-for-byte from the unedited registered
Pixal Camera-1 render; only the GPT side/back panels are retained from the
accepted generated board. The object-type argument is `domestic pig`. The
shared algorithm clusters residual partial points in 3-D and projects the same
component colour into every view; it contains no pig/animal/limb labels or
sample-specific direction, crop, threshold, or GT decision.

**Verbatim GPT prompt.** The built-in image generation/editing tool received:

```text
Use case: precise-object-edit
Asset type: cross-view geometry-conditioned input for 3D regeneration

Image 1 is the edit target: one clean FRONT / SIDE / BACK strip of the same complete domestic pig.
Image 2 is a four-row diagnostic board for the same cameras. In each view column the rows are prior RGB, prior depth, partial depth, and shared 3-D residual components. In the final row, dim points are current prior locations, bright points are observed target locations, and arrows point from prior to target. The same colour identifies the same connected 3-D residual component in every view.

Component ledger:
- C1 colour RGB (255, 92, 205), dominant correction: median/p90 residual 0.1565/0.1875 of the observed diagonal.
- C2 colour RGB (108, 238, 94), dominant correction: median/p90 residual 0.1689/0.1832 of the observed diagonal.
- C3 colour RGB (255, 168, 48), fine correction: median/p90 residual 0.0200/0.0355 of the observed diagonal.
- C4 colour RGB (77, 166, 255), fine correction: median/p90 residual 0.0156/0.0211 of the observed diagonal.
- C5 colour RGB (245, 226, 66), fine correction: median/p90 residual 0.0194/0.0247 of the observed diagonal.
- C6 colour RGB (174, 112, 255), fine correction: median/p90 residual 0.0164/0.0211 of the observed diagonal.

Refine Image 1 according to the component ledger. Dominant components require a clearly visible correction in every view where their evidence is visible; fine components permit only conservative contour refinement. Apply a component only where its target is supported by partial depth, and express the same connected 3-D correction consistently in every view where that component is visible. Use the depth rows to distinguish an image-plane contour shift from motion toward or away from the camera. Preserve low-residual regions and geometry without positive partial evidence. Propagate each accepted contour change smoothly through its attachment; never translate a structure as a detached piece.

Keep object identity, topology, material, texture, pose, view cameras, framing, lighting, complete unobserved support, and the FRONT / SIDE / BACK order unchanged. Output exactly one clean three-panel strip on pure white, with no labels, component colours, arrows, depth maps, text, borders, watermark, duplicated structures, missing structures, tears, or intersections.
```

GPT model/version, negative prompt, seed, scheduler, CFG, and exposed resize
policy are `UNKNOWN` because the built-in tool does not return them. Its raw
saved output is
`/root/.codex/generated_images/01a06637-4ce7-7450-a13c-54d3b9789130/exec-86e36c88-52c7-491a-8a73-d8d49b7a7103.png`;
the project copy above is the reproducibility asset.

**TRELLIS execution generated after image approval.** The pending 3-D candidate
is under
`workspace/trellis_pig_multiview_probe_20260908/trellis/cross_view_ledger_v4_hybrid_seed42/`.
It contains `trellis_mesh_raw.glb`, `trellis_mesh_raw.ply`,
`trellis_mesh_sampled_100k.ply`, `trellis_gaussian.ply`, the orbit preview and
`trellis_regeneration_info.json`. Model/checkpoint is
`models/TRELLIS-image-large`, official repository commit
`2301d7ba00f6f101695022123bc01363603e4828`; seed `42`, stochastic multi-image
mode, sparse sampler 12 steps / CFG 7.5, structured-latent sampler 12 steps /
CFG 3.0, 100,000 sampled points, 24 preview frames, xFormers attention and
native spconv. Generation took 10.24 seconds after model load and peaked at
10,868,974,080 bytes GPU memory. No RMBG, MoGe, registration, ICP, Gaussian
edit, GT, CD, or EMD was applied after this TRELLIS generation yet.

**Subsequent offline-only 3-D audit.** After the accepted images and TRELLIS
asset were frozen, the full-surface GT-only Sim(3) oracle produced
`workspace/trellis_pig_multiview_probe_20260908/registration/gt_oracle_cross_view_ledger_v4_trim100/`.
At 16,384 points and seed 6145 it reports CD-L1x100 `1.78322364` and EMDx100
`2.46681198`; the older hybrid under the identical oracle reports
`1.72000229/2.41813362`. The new candidate nevertheless improves observed
partial-to-prior normalized mean/p90 distance from `.013376/.032300` to
`.012526/.030124`, and 1%/2% coverage from `56.1401/75.4761%` to
`57.8918/78.7964%`. These values were unavailable to GPT and TRELLIS. Keep the
image conditions accepted, but keep the resulting 3-D candidate pending: it
has better observed-surface agreement but has not surpassed the older hybrid
in complete-shape metrics or passed no-GT registration.

**User promotion at 2026-09-08 after visual review.** The user judged the v4
generated prior “很顶级” and directed subsequent work exclusively to
registration. Treat the accepted GPT board, the Camera-1-frozen three TRELLIS
inputs, and `trellis/cross_view_ledger_v4_hybrid_seed42/` as immutable inputs
for registration experiments. Do not redraw the images, regenerate TRELLIS,
or substitute another seed without asking. This promotion does not approve
any existing TRELLIS-to-partial transform; registration remains the active
problem.

## 2026-09-09 CST — accepted Pig TRELLIS regeneration and depth-visible Sim(3)

**User approval.** The user judged the final result “非常非常好了”. Preserve
the v7 FRONT/SIDE/BACK images, seed-42 TRELLIS asset, and v37 residual Sim(3)
as the accepted Pig TRELLIS feasibility result. Do not replace it with v38:
that second local pass improved its sampled no-GT objective but regressed the
offline complete-shape result. This approval does not promote TRELLIS into the
frozen GenPC++ mainline or authorize sample-specific logic.

**Exact inputs and accepted outputs.** The observed input is
`data/custom/domestic_pig/partial_data/single_scan/domestic_pig_partial.ply`;
its saved camera, depth/pixel indexing and GT-for-offline-audit are
`camera.pth`, `depth.png`, `point_uv.npy`, and
`data/custom/domestic_pig/gt_data/domestic_pig_gt.ply`. The accepted edited
view strip is
`workspace/trellis_pig_multiview_probe_20260908/conditions/cross_view_shared_local_v7/shared_low_frequency_plus_local_front_side_back.png`;
the exact TRELLIS inputs are `stage2_local/{front,side,back}.png`, and the
camera-framing-normalized registration observations are
`camera_contract/{front,side,back}.png`. The accepted generated assets are
under `trellis/shared_low_frequency_local_v7_seed42/`, including
`trellis_mesh_raw.glb`, `trellis_mesh_raw.ply`,
`trellis_mesh_sampled_100k.ply`, `trellis_gaussian.ply`, and
`trellis_gaussian_orbit_preview.png`. The accepted registered output,
partial/prior coloured overlay, Camera-1 projection, and complete record are:

- `registration/trellis_shared_local_v7_depth_visible_sim3_v37/trellis_registered_100k.ply`;
- `registration/trellis_shared_local_v7_depth_visible_sim3_v37/partial_gray_trellis_red.ply`;
- `registration/trellis_shared_local_v7_depth_visible_sim3_v37/partial_camera1_projection.png`;
- `registration/trellis_shared_local_v7_depth_visible_sim3_v37/registration_info.json`.

All paths above are relative to
`workspace/trellis_pig_multiview_probe_20260908/` unless explicitly rooted
elsewhere.

**Image-edit reproducibility.** Stage 1 uses the full verbatim prompt in
`conditions/cross_view_shared_local_v7/stage1_shared_low_frequency_prompt.txt`;
stage 2 uses the full verbatim per-view prompts in
`stage2_local/{front,side,back}_prompt.txt`. Those files are the canonical
prompt record and must be copied byte-for-byte for replay. The prompts perform
one shared low-frequency update followed by local residual edits after
subtracting that shared motion; they contain the object argument `domestic
pig` but no fixed part, side, world-axis, GT, CD, or EMD rule. GPT image model
name/version, negative prompt, seed, steps, scheduler, CFG, and native resize
policy are `UNKNOWN`, so the image-edit stage is not exactly reproducible from
metadata alone. Final images are square 512px white-background conditions;
camera-contract normalization restores the original foreground centre and
isotropic framing before registration.

**TRELLIS reproducibility.** Model is
`/opt/data/private/cr/lab/GenPC/models/TRELLIS-image-large`; repository is
`/opt/data/private/cr/lab/LaS-Comp` at commit
`2301d7ba00f6f101695022123bc01363603e4828`. Exact settings are seed `42`,
stochastic multi-image mode, sparse sampler 12 steps / CFG `7.5`, structured
latent sampler 12 steps / CFG `3.0`, mesh and Gaussian decode, 100,000 sampled
surface points, 24 preview frames, xFormers, and native spconv. Python is the
`las-comp` environment with Python `3.10.19`, Torch `2.4.0`, CUDA `12.1`.
Generation took `7.4516` seconds after model loading and peaked at
`10,935,504,896` GPU bytes. The official multi-image API receives no camera
extrinsics; its three conditions constrain the asset but are not treated as
three calibrated exported cameras.

**Accepted registration.** Initial no-GT input is
`registration/trellis_shared_local_v7_camera_polish/trellis_registered_100k.ply`.
The accepted v37 method is the category-independent all-partial-support plus
saved-Camera-1 depth/visible-surface proper Sim(3) search implemented by
`src/partial_supported_sim3.py` and
`scripts/run_partial_supported_sim3.py`. Exact configuration is rotation
bound `22` degrees, scale bound `1.14`, translation bound `.18` partial
diagonal, 8,192 partial and 24,000 prior samples, population `5`, 14
iterations, seed `6145`, semantic silhouette weight `0`, and physical
Camera-1 visible score weight `1.2`. It recovers `8.65756` degrees, scale
`1.00291534`, and translation
`[.08896611,.01806257,.00118298]`, preserving all 100k complete-prior points.
No Gaussian/non-rigid edit, point deletion, partial concatenation, semantic
MoGe bridge, GT, CD, or EMD enters this accepted transform.

**Offline firewall and result.** After the transform was frozen, 16,384-point
evaluation with seed 6145 reports CD-L1x100 `2.05028020` and EMDx100
`2.78596357`. The GT-only diagnostic oracle is `1.9392/2.6391` and was used
only to estimate remaining headroom, never to initialize, score, select, or
stop v37. A subsequent v38 local pass reports `2.4164/3.2024` and is rejected.

## 2026-09-09 14:56 CST — promoted fusion-free object mainline

**User decision.** The user directed that the accepted TRELLIS regeneration
and registration be connected to the preceding semantic/Pixal stages and used
as the current mainline, explicitly excluding fusion for now. Preserve the
accepted Pig conditions, TRELLIS asset, final registration parameters, and
100k-point output while validating cross-category transfer. Do not silently
restore Gaussian fusion, PosteriorAdapter, axis-specific deformation, point
deletion, or partial concatenation to the mainline.

**Canonical implementation and output.** The resumable entry point is
`scripts/run_object_mainline.py`; its artifact schema is
`src/object_mainline.py`, and the method contract is
`docs/core_registration_pipeline.md`. The no-regeneration equivalence replay
is
`workspace/mainline_trellis_replay_20260909/final/domestic_pig/complete_100k.ply`
with manifest
`workspace/mainline_trellis_replay_20260909/manifests/domestic_pig.json`. Its
SHA-256 is
`de0efb3dbbbb18369f0395b6173b41e2166ac46e38bcf42f8ccbee5034d3a048`,
byte-identical to the accepted
`workspace/trellis_pig_multiview_probe_20260908/registration/trellis_shared_local_v7_depth_visible_sim3_v37/trellis_registered_100k.ply`.

**Inputs and generation record.** Input partial/camera/semantic/Pixal assets
remain exactly those in the immediately preceding accepted Pig entry. Stage-1
and per-view stage-2 prompts are copied verbatim in
`workspace/trellis_pig_multiview_probe_20260908/conditions/cross_view_shared_local_v7/`;
the accepted FRONT/SIDE/BACK images are `stage2_local/{front,side,back}.png`.
GPT model/version, negative prompt, seed, steps, scheduler, CFG, and native
resize policy remain `UNKNOWN`; the saved images and prompt files are therefore
required replay artifacts. TRELLIS remains
`models/TRELLIS-image-large` with repository commit
`2301d7ba00f6f101695022123bc01363603e4828`, seed 42, stochastic mode, sparse
12/CFG 7.5, structured latent 12/CFG 3.0, xFormers/native-spconv, and 100k
surface samples. Pixal/Qwen/RMBG/MoGe model paths and parameters are unchanged
from the preceding entry.

**Registration and postprocessing.** The fixed mainline performs three-view
semantic orientation capture, 128px/420-step nvdiffrast refinement, one
Camera-1 partial-to-prior inverse capture followed by 256px/400 steps, a
256px/500-step camera polish, and the accepted all-partial-support residual
Sim(3): 22-degree, 1.14-scale and 0.18-diagonal bounds, population 5,
14 iterations, seed 6145, silhouette weight 0, visible Camera-1 weight 1.2.
The replay recovers the same 8.65756-degree rotation, 1.00291534 scale, and
translation `[.08896611,.01806257,.00118298]`. No fusion or post-registration
shape edit is applied. Offline-only CD-L1x100/EMDx100 remains
`2.05028020/2.78596357`; neither quantity was exposed to inference.
## 2026-09-10 14:28:02 CST — accepted Pig four-view diagnosis plus strong continuous posterior

**User approval.** The user judged the stronger Pig result “效果非常好”.
Preserve the category-independent structural-OT plus embedded-ARAP low-frequency
posterior, the four-view diagnostic assets, and the complete 100k carrier. Do
not replace it with the rejected short-range silhouette deformation, and do not
add animal/limb labels, fixed axes, manual regions, or GT-driven decisions.

**Inputs and outputs.** Sample id/type is `domestic_pig`. The fixed registered
prior is
`workspace/custom10_fixed_mainline_20260907/registration/domestic_pig/final/camera1_amplified_registered_100k.ply`;
partial, Camera-1, semantic image, native Pixal GLB, and ordered source carrier
are respectively
`workspace/custom10_fixed_mainline_20260907/inputs/partial/domestic_pig.ply`,
`workspace/custom10_fixed_mainline_20260907/inputs/camera/domestic_pig/camera.pth`,
`workspace/custom10_fixed_mainline_20260907/inputs/camera/domestic_pig/img.png`,
`workspace/custom10_fixed_mainline_20260907/inputs/pixal/domestic_pig/pixal3d.glb`,
and
`workspace/custom10_fixed_mainline_20260907/inputs/pixal/domestic_pig/pixal3d_sampled_100k.ply`.
The accepted experiment root is
`workspace/geometry_first_multiview_proxy_pig_20260910/`. The canonical output
is `final_strong_continuous_posterior_100k.ply`, hard-linked to
`four_view_posterior_low_frequency_v3/posterior_prior_100k.ply`. Exact OT,
field, support, comparison, and diagnostic outputs are
`four_view_posterior_low_frequency_v3/{partial_ot_pairs.npy,posterior_field.npz,posterior_support_status.png,partial_gray_posterior_red.ply,posterior_info.json}`.
The accepted before/after visualization is
`four_view_posterior_low_frequency_v3/registered_before_gray_posterior_after_red_pca.png`.

**Four-view observation.** Four partial-visibility-selected cameras use FOV
`38` degrees and orbit yaws `0`, `180`, `315`, and `135` degrees, recorded with
their full poses in `render/render_manifest.json`. They cover `13,450 / 16,384`
partial points. The clean prior and prior-to-partial boards are
`evidence/prior_rgb_front_side_back_right.png` and
`evidence/partial_correspondence_overlay_front_side_back_right.png`. The
accepted stronger edited condition is `residual_edited_4view_v2_strong.png`,
split without resizing into `edited_conditions_v2/{front,side,back,right}.png`.
Generated resolution is `1254 x 1254`; source boards were supplied at their
native saved resolution. Image-generation model/version, seed, steps, CFG,
scheduler, and negative prompt are `UNKNOWN`; no later guess may be presented
as reproducibility metadata.

**Exact stronger edit prompt.**

```text
Use case: strong camera-consistent structural correction for 3D reconstruction.

Image 1 is the original clean 2x2 four-view RGB target. Image 2 is aligned geometric evidence: cyan is the observed partial-scan target, current prior/RGB-red locations are the source, and yellow arrows point from source to target. Image 3 is a previous edit attempt that was too conservative and failed to express enough low-frequency shape change.

Produce a stronger corrected version of Image 1. Infer one shared continuous three-dimensional deformation from all four evidence panels. Where distant but coherent observed structures lie beyond the current prior, increase the intervening object's low-frequency extent so the connected structures reach the observations. The correction must look like continuous stretching and proportional reshaping of the complete object, not detached endpoint translation. Make the corrected longitudinal proportions and spacing between connected structures visibly different from Image 3 whenever the evidence demands it. Then refine local contours and depth-relative placement consistently in all views.

For this domestic pig, preserve the same individual, anatomy and texture while making its observed body extent and limb placement agree much more strongly with the cyan evidence. All limbs must remain naturally attached; do not change their number.

Freeze the exact row-major 2x2 panel order, camera pose, perspective, crop, object orientation, object centre, white background, identity, topology, material, texture, ears, face and tail. Missing partial regions are UNKNOWN and must not be deleted. Apply one shared 3D correction across views—never independently redesign a panel.

Output only the clean corrected 2x2 RGB board. No diagnostic colours, arrows, text, labels, panel borders or watermark. No mirrored/swapped views, camera changes, detached parts, duplicated/deleted structures, or inconsistent anatomy.
```

**Posterior solver.** No learned model or image prompt is used by the accepted
geometry update itself. It uses `PosteriorAdapterConfig` serialized verbatim in
`posterior_info.json`: partial/prior samples `3072/6144`; 24-neighbour features;
60 unbalanced-OT iterations; coarse/fine graph fractions `.020/.055`; 24
low-frequency modes; five coarse and five fine ARAP iterations; attachment
ratio `3.2`; minimum hidden coverage `.95`. The complete exact numeric config
is the JSON record and must be used instead of a reconstructed summary. Main
axis extent changes from `.71222762` to `.94514656` (about 33%). All `100,000`
carrier slots are retained, significant component count stays one, no connected
component is added, and hidden coverage is `1.23948`. The no-GT verifier accepts
the candidate (`.0523111 -> .0505232`). The weaker broad-nearest-neighbour
result under `four_view_broad_to_narrow_v2/` is diagnostic only.

**Offline firewall.** GT is
`data/custom/domestic_pig/gt_data/domestic_pig_gt.ply` and is never opened by
view selection, image editing, OT, ARAP, or the verifier. Offline-only evaluation
at 16,384 points and seed 6145 gives CD-L1x100 `1.47515414` and EMDx100
`1.84783079` (the CUDA EMD approximation may vary slightly between runs).

## 2026-09-10 — accepted 01184 mask-locked direct-GPT from-scratch flow

**User approval.** The user judged the result “效果很好” and directed that the
same pipeline be run on the remaining Redwood samples. Preserve the saved
Camera-1 depth as the sole camera/framing authority, the direct-GPT semantic,
the mask audit, the Pixal prior, registration, four-view OT evidence, and the
complete 100k carrier. Do not restore the failed Qwen image as the active
semantic input.

**Exact artifacts.** The run root is
`workspace/from_scratch_01184_debug_20260910`. Input partial is
`data/redwood/partial/01184.ply`; depth/camera are
`inputs/camera/01184/{depth.png,camera.pth}`; direct-GPT source and installed
semantic are `inputs/pixal/01184/gpt_image.png` and
`inputs/camera/01184/img.png`. Prompt and framing audit are
`inputs/pixal/01184/gpt_depth_completion_prompt.txt` and
`inputs/camera/01184/semantic_install_manifest.json`. Pixal model outputs are
`inputs/pixal/01184/{pixal3d.glb,pixal3d_sampled_100k.ply,pixal3d_metadata.json,pixal_moge_fp16_observation.npz}`.
Registered and final outputs are
`registration/01184/final/camera1_amplified_registered_100k.ply` and
`final/01184/complete_100k.ply`. Four-view evidence is under
`residuals/01184/`; exact run metadata is `run_manifest.json`.

**Generation record.** The exact direct-GPT prompt is copied verbatim in the
prompt artifact and the semantic-install manifest. It constrains the image to
one blue wheeled rubbish bin, the saved depth camera/framing, exactly two
parallel wheels on one axle, and a white background. GPT image model/version,
seed, steps, CFG, scheduler, and native resize policy are `UNKNOWN`; therefore
the saved source image (SHA-256
`8bc8822cff48ff60b34261ff7c1a2228151639f468e8bf041277259c790052a3`) is required
for exact replay. Installation resizes to 512 square with Lanczos, then uses
`models/RMBG-2.0`. The audit reports center-offset ratio `.005259`, width/height
ratios `1.00909/1.01928`, mask IoU `.83034`, and depth coverage `.97212`.
Pixal3D source/checkpoint and DINO/MoGe paths are those recorded in
`inputs/pixal/01184/pixal3d_metadata.json`; no unrecorded model substitution is
allowed.

**Geometry and evaluation.** Registration uses the shared native
Pixal--MoGe, two-camera bridge, joint, and Camera-1 continuation implementation;
all exact transforms and stage settings are serialized under
`registration/01184`. Four visibility-valid views enter Partial OT through
`residuals/01184/render/render_manifest.json`. PosteriorAdapter preserves all
100,000 points and makes no deformation for this case because reliable
localized residual transport is insufficient; this is not a verifier rollback.
Offline-only CD-L1x100/EMDx100 are `1.34141147/2.33711749` and are not exposed
to generation, registration, OT, or stopping.

## 2026-09-11 14:30 CST — accepted 01027 single-scan CLIP-view depth-only GPT semantic

**User approval.** The user judged the direct depth-only completion “这样效果很好”.
Preserve this exact semantic image and its strict depth-authority prompt. Do not
replace it with the preceding unconstrained GPT result or the malformed Qwen
completion, and do not loosen the wheel-position, pose, scale, or camera
constraints without asking.

**Exact artifacts.** Input partial is
`data/Omni-Comp3D/Omni-Comp3D/redwood_preprocessed/01027/partial_data/single_scan/partial_0.ply`.
The CLIP-selected input depth and camera are
`workspace/omni_redwood_single_scan_clip_view_probe_20260911/01027_partial_0/depth.png`
and `camera.pth`; SHA-256 values are
`db1db578692e3a1e8a89ba9c6b8a7f8162004630cac780afd8a93cf3fb3b5d38`
and `e9b42a4c5a6c84a06c804d95256827c3d2a3f85c3ba9995d0af55efd10498216`.
The accepted output is
`workspace/omni_redwood_single_scan_clip_view_probe_20260911/01027_partial_0/gpt_semantic_depth_only_accepted.png`
(SHA-256 `39fd86124a9bd39e6863ccf537b555a45b4ddf111f7de9f787ef7d3bcec0765a`),
and the exact prompt is beside it as
`gpt_semantic_depth_only_accepted_prompt.txt`.

**Generation record.** The built-in image generation editor was given only the
512-square `depth.png` as its edit target; no previous generated RGB image was
included. It returned a 1254-square PNG. The full positive and negative
instructions are copied verbatim in the prompt artifact. Exact GPT image model
checkpoint, seed, inference steps, CFG/guidance scale, scheduler, and native
resize policy are `UNKNOWN`, so this result is not exactly reproducible without
the saved output. No RMBG, resize, MoGe, Pixal3D, registration, or point-cloud
postprocessing has yet been applied to this accepted image.

**View selection.** The reusable selector is frozen CLIP ViT-L/14@336 after
geometry pruning, with model files at
`/opt/data/private/cr/lab/GenPC/models/clip-vit-large-patch14-336`. The selected
azimuth/elevation/roll are `0/15/270`; the full category-conditioned prompt
ensemble, geometry scores and camera parameters are recorded in
`clip_view_ranking.json`. No GT, CD, or EMD was used.

## 2026-09-11 16:55 CST — accepted experimental upright 01027 CLIP-view GPT semantic

**User approval and scope.** The user approved saving the code after reviewing
the 180-degree-corrected depth and its GPT completion. This CLIP view selector
remains an opt-in feasibility probe and must not replace or alter the default
mainline. Preserve the upright Camera-1 export and semantic candidate; do not
apply the fixed raster correction to unrelated camera pipelines without an
explicit coordinate-contract check.

**Exact inputs and outputs.** Input partial is
`data/Omni-Comp3D/Omni-Comp3D/redwood_preprocessed/01027/partial_data/single_scan/partial_0.ply`.
The experimental output root is
`workspace/omni_redwood_single_scan_clip_gpt_20260911/01027_partial_0`.
The accepted input depth, camera and semantic are `depth.png`, `camera.pth` and
`gpt_semantic_upright_v2.png`, with SHA-256 values
`de96b6237e5e59dd85dd09add90c2dc68cbf75ea363d662d73088375425e5548`,
`47a53065005a85596926509deaea6d39787c633e2839618128283acb3b98a857` and
`78659fef017fa4e217115a2a0959fc6693a142ce7104c3dc136739566ee874b9`.
The exact prompt is beside the image as `gpt_semantic_upright_v2_prompt.txt`;
the visual audit is `upright_depth_gpt_comparison.png`. Pre-correction camera,
depth, mask, UV and point-depth artifacts are retained with the
`_before_upright` suffix.

**View and camera contract.** The frozen CLIP model is
`/opt/data/private/cr/lab/GenPC/models/clip-vit-large-patch14-336`. Geometry
pruning plus the category-conditioned prompt ensemble selected azimuth,
elevation and roll `0/15/270` degrees. Final export applies one systematic
image-coordinate roll offset of `180` degrees, yielding roll `90` degrees.
Depth, mask, `point_uv.npy`, `camera_point_depth.npy`, `viewpoint.npy`,
`target.npy` and `camera.pth` were all re-rendered together; this was not a
PNG-only rotation. The complete parameters are serialized in
`clip_view_ranking.json` under `output_view`.

**Generation record.** Built-in GPT image generation received only the
512-by-512 corrected `depth.png`; no earlier semantic/RGB image was provided.
It returned a 1254-by-1254 RGB PNG. Exact model checkpoint, seed, steps,
guidance/CFG, scheduler and native resize policy are `UNKNOWN`, so the saved
output is required for exact replay. No RMBG, Pixal3D, MoGe, registration,
fusion or point-cloud postprocessing has been run. No GT, CD or EMD was used.

## 2026-09-12 00:27 CST — accepted Waymo8 sparse-LiDAR MoGe-bridge route

**User approval and scope.** The user judged native MoGe alignment followed by
camera bridging more reliable than refining the complete prior directly toward
an extremely sparse partial scan. Preserve this as an isolated Waymo/sparse-
LiDAR route; do not replace the Redwood/Custom object mainline. After the
Camera-2-to-Camera-1 bridge, do not run partial-driven joint/final refinement,
PosteriorAdapter, non-rigid deformation, or carrier-slot fusion.

**Inputs and outputs.** The eight accepted inputs are every `.ply` under
`workspace/waymo8_original_mainline_20260911/inputs/partial`; they comprise
three `CAR_*` and five `PEDESTRIAN_*` samples. Their exact Camera-1 depth,
semantic image, mask, point UV and camera are under the matching
`inputs/camera/<sample>` directory; Pixal inputs, native MoGe observations,
GLBs, metadata and sampled priors are under `inputs/pixal/<sample>`. Complete
native/bridge diagnostics are under
`workspace/waymo8_sparse_lidar_moge_bridge_20260912/registration/<sample>`.
The retained final files are
`workspace/waymo8_sparse_lidar_moge_bridge_20260912/final/<sample>/complete_100k.ply`,
and the consolidated visual comparison is
`workspace/waymo8_sparse_lidar_moge_bridge_20260912/bridge_only_vs_mainline_registration.png`.
All eight final files are byte-identical copies of
`bridge/two_camera_pixal_moge_bridge_registered_100k.ply`, contain exactly
100,000 points, and report both partial micro-refinement and non-rigid
deformation as disabled. Waymo has no paired completion GT in this local
subset, so CD/EMD are unavailable and were not used.

**Car semantic prompt (verbatim; no separate negative prompt).**

> Use case: depth-constrained semantic completion for 3D reconstruction. The reference is a sparse grayscale depth observation of one car: every visible bright/gray pixel is measured surface evidence, while black pixels are unknown background rather than empty space. Generate a complete, realistic, structurally normal car isolated on a pure white background. HARD CONSTRAINT: preserve the observed local geometry exactly—same camera viewpoint, viewing direction, orientation, pose, image-plane location, bounding-box size, silhouette where observed, wheel/body locations, longitudinal direction, and depth-supported proportions. Do not rotate, mirror, recenter, enlarge, shrink, canonicalize, or reinterpret any observed part. Infer and complete only missing or occluded geometry, producing a continuous plausible body, roof, hood, rear, windows and four wheels with normal road-vehicle proportions. Preserve any depth-supported external structure. If ordinary object priors conflict with observed depth, the observed depth wins. Keep the entire car connected and fully visible. Clean photorealistic semantic RGB image, neutral materials, no road, no people, no scenery, no text, no logo, no watermark, no extra objects, no cropped parts.

**Pedestrian semantic prompt (verbatim; no separate negative prompt).**

> Use case: depth-constrained semantic completion for 3D reconstruction. The reference is a sparse grayscale depth observation of one Pedestrian: every visible bright/gray pixel is measured body/clothing surface evidence, while black pixels are unknown background rather than empty space. Generate one complete, realistic, full-body pedestrian isolated on a pure white background. HARD CONSTRAINT: preserve the observed local geometry exactly—same camera viewpoint, body facing direction, pose, articulation, lean, image-plane position, bounding-box size, observed silhouette, limb locations, and depth-supported proportions. Do not rotate, mirror, recenter, enlarge, shrink, canonicalize, straighten, or replace the observed pose with a standard pose. Infer and complete only missing or occluded body/clothing geometry. If anatomical priors conflict with measured depth, the measured depth wins. Keep the person anatomically plausible, naturally connected and fully visible. Plain neutral clothing, clean photorealistic semantic RGB image; no ground, no scenery, no extra people, no carried object unless supported by depth, no text, logo, watermark, or cropped limbs.

**Generation and postprocessing record.** GPT image checkpoint/version, seed,
steps, CFG/guidance scale, scheduler and native resize policy are `UNKNOWN`, so
the saved semantic images are required for exact replay. Pixal3D uses
`/opt/data/private/cr/lab/GenPC/models/Pixal3D-weights`, DINOv3 at
`models/dinov3-vitl16-pretrain-lvd1689m`, MoGe at
`models/moge-2-vitl/model.pt`, RMBG at `models/RMBG-2.0`, xFormers, seed `42`,
1024 resolution, 300k mesh-face decimation target and 2048 texture size. Its
sparse-structure/shape/texture samplers each use 12 steps; guidance strengths
are `7.5/7.5/1.0`, guidance rescale values are `0.7/0.5/0.0`, and rescale-t
values are `5.0/3.0/3.0`. Per-sample FOV, distance, image size, bounds, hashes
and exact file paths are serialized in `pixal3d_metadata.json` and
`pixal_native_moge_info.json`. Registration first uses the cached native MoGe
observation produced from the exact `pixal3d_input.png`, then composes the
pixel-indexed Camera-2-to-Camera-1 bridge with the analytic Pixal-to-native-
MoGe transform. No later ICP, partial refinement, deformation, point deletion,
resampling, or fusion is applied.

**Exact replay verification.** A clean rerun with `--bridge-only --no-resume`
and two independent sample workers is stored at
`workspace/waymo8_sparse_lidar_moge_bridge_rerun_20260912`. All eight jobs
terminate at `pixal_native_moge_then_camera2_to_camera1_bridge`; every final
contains 100,000 points and is SHA-256 byte-identical to the first accepted
run. The rerun batch manifest is `registration/batch_manifest.json`, and its
uniform final entry points are `final/<sample>/complete_100k.ply`.

## 2026-09-20 — accepted selected-carrier iterative posterior mainline

**User approval.** The user accepted the corrected selected-carrier,
three-round residual re-linearization as the object-completion mainline. Keep
the `registration_selected` start point and the fixed three-round schedule;
do not revert to the stale `registration_initial` carrier or add category- or
sample-specific branches without asking.

**Exact artifacts.** The standalone result bundle is
`workspace/tto_relinearized_selected_redwood_custom_20260920/`. Final carriers
are `redwood/tto/<id>/round_03/posterior_prior_100k.ply` and
`custom/tto/<id>/round_03/posterior_prior_100k.ply`; all 20 have exactly
100,000 points. The complete sample list, no-GT residual histories, source
paths, and fixed execution parameters are in `experiment_manifest.json`.
Offline-only reports are
`metrics/redwood10_tto_selected_round03.{csv,json}` and
`metrics/custom10_tto_selected_round03.{csv,json}`.

**Inputs and generation record.** This acceptance covers post-registration
adaptation only; it performs no new semantic-image or 3D generation. The
unchanged camera, semantic image, Pixal prior, partial and four-view residual
manifest for every case are copied under the bundle's `redwood/inputs`,
`redwood/residuals`, `custom/inputs`, and `custom/residuals` directories. Full
per-case generation prompts, negative prompts, model paths/checkpoints,
resize policies, and image-generation parameters are the copied source
artifacts from
`workspace/best_redwood_custom_camera1_transport_20260911/`; no new prompt,
seed, scheduler, CFG, resolution, or backend is introduced here. Prompt and
image-generator parameters for this TTO stage are therefore **NOT APPLICABLE**;
the only learned geometric component is the already-installed local
`PosteriorAdapter` implementation, with no checkpoint or task-data training.

**Frozen postprocessing.** The exact start point is
`registration_selected/<id>/camera1_amplified_registered_100k.ply`, followed
by three outer residual re-linearization rounds at update strength `1.0` using
`configs/posterior_mainline.json`. Each round re-estimates class-free partial
OT and four-view positive evidence, preserves every carrier slot, and uses no
GT/CD/EMD for inference, action selection, or stopping. Offline evaluation
uses deterministic 16,384-point FPS (seed `6145`) after inference only.

**Accepted result.** Corrected offline CD-L1/EMD (both x100) are
`1.4872/2.4083` on Redwood10 and `1.8567/2.3406` on Custom10. These supersede
the earlier Custom `10.3660/9.4913` audit, which is invalid because it started
from stale pre-selection carriers. Do not use that earlier Custom report in
comparisons.

## 2026-09-21 — accepted cartoon-fox high-resolution posterior-adaptation candidate

**User approval.** The user judged the high-resolution continuous deformation
for `cartoon_fox` to be materially better ("看起来确实好多了"). Preserve this
candidate and its exact profile for comparison; it is a focused stress-test
candidate, not yet a replacement for the accepted shared mainline.

**Inputs.** The fixed partial, GT, Camera-1 calibration, semantic image,
Pixal carrier, selected registration and four-view residual evidence are,
respectively:
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/inputs/partial/cartoon_fox.ply`,
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/gt/cartoon_fox.ply`,
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/inputs/camera/cartoon_fox/camera.pth`,
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/inputs/camera/cartoon_fox/img.png`,
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/inputs/pixal/cartoon_fox/pixal3d_sampled_100k.ply`,
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/registration_selected/cartoon_fox/camera1_amplified_registered_100k.ply`, and
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/residuals/cartoon_fox/render/render_manifest.json`.

**Semantic generation record.** Pixal3D model/checkpoint:
`/opt/data/private/cr/lab/GenPC/models/Pixal3D-weights`; model seed `42`;
requested/actual resolution `1024`; native camera
`camera_angle_x=0.9110264018111831`, `distance=1.0206727981567383`,
`mesh_scale=1.0`. The image-completion model/checkpoint, transformer,
negative prompt, image seed, steps, CFG/guidance, scheduler, backend, and
resize policy are **UNKNOWN** in the preserved source record. The semantic
image was recorded at resolution `512`. Its full prompt, copied verbatim, is:

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a complete seated stylized cartoon fox. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask. Additional structural constraints: Keep one connected body, exactly four naturally attached legs or paws, two ears, and one tail.

**Frozen posterior-adaptation execution.** Starting from the selected
registered 100k carrier, six residual re-linearization rounds were executed
by `scripts/iterative_posterior_tto.py` on CUDA with render size `512`,
padding `0.15`, update strength `1.0`, and the category-free profile
`workspace/fox_posterior_adaptation_20260921/high_resolution_expansive_stable_profile.json`.
The profile uses 6,144 partial samples, 12,288 prior/assimilation samples,
32-neighbor normals, 80 transport iterations, 96 structural-rescue candidates,
12 intrinsic landmarks, 16 intrinsic graph neighbors, normalized residual
gates, and the recorded coarse/fine/assimilation regularizers. It retains every
one of the 100,000 prior carrier slots, uses no category or part labels, and
does not use GT, CD, or EMD during inference.

**Accepted artifacts.** Final carrier:
`workspace/fox_posterior_adaptation_20260921/high_resolution_expansive_stable/round_06/posterior_prior_100k.ply`.
The approved partial-gray/prior-red overlay is
`workspace/fox_posterior_adaptation_20260921/high_resolution_expansive_stable/round_06/partial_gray_posterior_red.ply`; the PCA diagnostic is
`workspace/fox_posterior_adaptation_20260921/high_resolution_expansive_stable/round_06/partial_gray_posterior_red_pca_768.png`.
Do not overwrite these outputs without copying them first.

**Offline diagnostic (not used for selection).** With the same 16,384-point
FPS and seed `6145`, the fixed three-round mainline scores CD-L1/EMD x100
`2.3662/2.7546`, while this six-round high-resolution candidate scores
`2.6489/4.1928`; reports are
`workspace/fox_posterior_adaptation_20260921/metrics/baseline_round03.json`
and
`workspace/fox_posterior_adaptation_20260921/metrics/high_resolution_expansive_stable_round06.json`.
Thus the candidate is visually closer in the approved partial overlay but
regresses the global GT metrics and must not replace the mainline without a
separate decision.

## 2026-09-22 — retained cartoon-fox structure-propagated complete-carrier candidate

**User feedback.** The user judged this protected deformation to improve the
front legs substantially and to improve the tail, while asking for a stronger
version. Preserve it as the current non-collapsing comparison baseline; it is
not yet an accepted replacement for the shared mainline.

**Inputs and model record.** The input partial, GT, Camera-1 calibration,
semantic image, selected Pixal carrier and four-view manifest are exactly the
same files listed in the preceding 2026-09-21 cartoon-fox entry. Pixal3D is
`/opt/data/private/cr/lab/GenPC/models/Pixal3D-weights`, seed `42`, at native
camera `camera_angle_x=0.9110264018111831`, distance
`1.0206727981567383`, `mesh_scale=1.0`; semantic resolution is `512` and
Pixal input resolution is `1024`. Image-completion checkpoint, transformer,
negative prompt, image seed, steps, CFG/guidance, scheduler, backend and
resize policy are `UNKNOWN` in the source run. The full semantic prompt is:

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a complete seated stylized cartoon fox. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask. Additional structural constraints: Keep one connected body, exactly four naturally attached legs or paws, two ears, and one tail.

**Execution.** `scripts/iterative_posterior_tto.py` ran six CUDA rounds from
the fixed selected registration using the high-resolution profile above,
reference-prior protection, incremental re-linearization, local-motion
selection, component-wise proper Sim(3) projection with `4` rest-graph core
hops, one graph-median smoothing pass, and `6` continuation hops. The robust
p99 edge-stretch budget was `10.0`. This remains category-, part- and
coordinate-free; it reads no GT/CD/EMD during inference, retains all 100,000
carrier slots, and does not append or delete partial points.

**Retained artifacts.** The before/after comparison is
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core4_harmonic6_incremental_stretch10_six_rounds/comparison/fox_before_after_structure_propagation.png`.
The registered-before overlay is
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core4_harmonic6_incremental_stretch10_six_rounds/round_00_registered/partial_gray_posterior_red.ply`;
the retained round-4 overlay and 100k posterior are
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core4_harmonic6_incremental_stretch10_six_rounds/round_04/partial_gray_posterior_red.ply`
and
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core4_harmonic6_incremental_stretch10_six_rounds/round_04/posterior_prior_100k.ply`.

**Offline diagnostic only.** Deterministic 16,384-point FPS, seed `6145`,
gives CD-L1/EMD x100 `2.2220/2.9622` for round 4, improving on the preceding
protected candidate's `2.2864/3.0544`. These values were measured only after
the run and did not select the output or alter its parameters.

## 2026-09-22 — accepted cartoon-fox high-amplitude structured posterior

**User approval.** The user judged the stronger structured deformation to be
good ("确实不错了"). Preserve this candidate; later strength trials use separate
output roots and must not overwrite it.

**Inputs and generation record.** Inputs, semantic image, Pixal carrier,
Pixal3D model `/opt/data/private/cr/lab/GenPC/models/Pixal3D-weights`, seed
`42`, native camera (`camera_angle_x=0.9110264018111831`, distance
`1.0206727981567383`, `mesh_scale=1.0`), semantic/Pixal resolutions
`512/1024`, and all `UNKNOWN` image-generation parameters are exactly those
listed in the preceding 2026-09-22 fox entry. The full prompt is:

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a complete seated stylized cartoon fox. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask. Additional structural constraints: Keep one connected body, exactly four naturally attached legs or paws, two ears, and one tail.

**Frozen execution.** Six CUDA residual re-linearization rounds used the
category-free profile
`workspace/fox_posterior_adaptation_20260921/high_resolution_expansive_stable_profile.json`,
incremental reference-prior protection, local-motion selection, component-wise
proper Sim(3) with `6` core hops, zero motion-smoothing passes, `3`
continuation hops, and robust p99 edge-stretch budget `15.0`. It has no
category/part rule, fixed coordinate direction, GT/CD/EMD input or point
addition/deletion; all 100,000 carrier slots remain present.

**Accepted artifacts.** Final overlay and posterior:
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core6_harmonic3_incremental_stretch15_six_rounds/round_06/partial_gray_posterior_red.ply`
and
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core6_harmonic3_incremental_stretch15_six_rounds/round_06/posterior_prior_100k.ply`.
The review board is
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core6_harmonic3_incremental_stretch15_six_rounds/comparison/fox_before_after_stretch15.png`.

**Offline diagnostic only.** Deterministic 16,384-point FPS/seed `6145` gives
CD-L1/EMD x100 `1.9121/2.8281`; coverage is 92.48%. Metrics were measured
after inference only and did not control any choice.

## 2026-09-22 — accepted cartoon-fox stretch-20 structured posterior

**User approval.** The user judged the stronger `stretch20` deformation to be
substantially better ("确实好很多了"), while identifying local carrier-density
holes in the stretched body as the next issue. Preserve this candidate as the
strongest accepted fox alignment baseline; do not overwrite it.

**Inputs and generation record.** Inputs, model/checkpoint
`/opt/data/private/cr/lab/GenPC/models/Pixal3D-weights`, seed `42`, native
camera (`camera_angle_x=0.9110264018111831`, distance
`1.0206727981567383`, `mesh_scale=1.0`), resolution `512/1024`, and unknown
image-generation fields are exactly those of the preceding 2026-09-22 entry.
The full prompt is:

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a complete seated stylized cartoon fox. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask. Additional structural constraints: Keep one connected body, exactly four naturally attached legs or paws, two ears, and one tail.

**Frozen execution.** The class-free six-round CUDA configuration is unchanged
except for robust p99 edge-stretch budget `20.0`: incremental reference-prior
protection, local-motion selection, component-wise proper Sim(3), `6`
core-hops, zero smoothing passes and `3` continuation hops. It retains all
100,000 original carrier slots and uses neither category/part rules nor
GT/CD/EMD during inference.

**Accepted artifacts.** Final overlay and posterior:
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core6_harmonic3_incremental_stretch20_six_rounds/round_06/partial_gray_posterior_red.ply`
and
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core6_harmonic3_incremental_stretch20_six_rounds/round_06/posterior_prior_100k.ply`.
The review comparison is
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_core6_harmonic3_incremental_stretch20_six_rounds/comparison/fox_before_after_stretch20.png`.

**Offline diagnostic only.** Deterministic 16,384-point FPS/seed `6145` gives
CD-L1/EMD x100 `1.8802/2.8259`, four-view residual `0.01124`, and fixed-frame
carrier coverage `92.25%`; none were used to control inference.

## 2026-09-22 — accepted fox visibility-gated dense expert distillation

**User approval.** The user judged the combination of local fit and complete
shape to be substantially better ("可以可以 好很多了"), while requesting a
slightly stronger displacement at remaining tail/leg boundary samples.
Preserve this candidate and do not overwrite it; stronger trials use separate
directories.

**Inputs.** Sample id: `cartoon_fox`. Registered complete carrier:
`workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_gain135_core6_harmonic3_incremental_stretch25_six_rounds/round_00_registered/posterior_prior_100k.ply`.
Strong local-fit teacher:
`workspace/fox_posterior_adaptation_20260921/high_resolution_expansive_stable/round_06/posterior_prior_100k.ply`.
Partial, GT, Camera-1, semantic image, Pixal carrier and four-view manifest are:
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/inputs/partial/cartoon_fox.ply`,
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/gt/cartoon_fox.ply`,
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/inputs/camera/cartoon_fox/camera.pth`,
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/inputs/camera/cartoon_fox/img.png`,
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/inputs/pixal/cartoon_fox/pixal3d_sampled_100k.ply`, and
`workspace/tto_relinearized_selected_redwood_custom_20260920/custom/residuals/cartoon_fox/render/render_manifest.json`.

**Generation record.** Pixal3D model/checkpoint:
`/opt/data/private/cr/lab/GenPC/models/Pixal3D-weights`; seed `42`; semantic
resolution `512`; Pixal input resolution `1024`; native camera
`camera_angle_x=0.9110264018111831`, distance `1.0206727981567383`, and
`mesh_scale=1.0`. Image-completion checkpoint, transformer, negative prompt,
image seed, steps, CFG/guidance, scheduler, backend, and resize policy are
`UNKNOWN` in the source run. The full recorded semantic prompt is:

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a complete seated stylized cartoon fox. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask. Additional structural constraints: Keep one connected body, exactly four naturally attached legs or paws, two ears, and one tail.

**Postprocessing and exact focused configuration.**
`scripts/distill_visibility_gated_expert.py` uses the physical Camera-1
z-buffer only for teacher visibility, residual quantile `0.10`, minimum
improvement `0.25` median spacings, no visibility dilation, a finite
transition radius capped at `0.02` partial diagonals (`5` spacings and `0.5`
times the q75 teacher motion), minimum hidden coverage `0.92`, exact teacher
targets, embedded ARAP propagation, and fixed complete-prior points outside
the band. No GT/CD/EMD, category, part, or fixed-axis rule was used. It keeps
all 100,000 ordered carrier slots; 16,964 teacher points are inherited at full
amplitude, 46,229 points lie outside the active band, the result has one
significant component, and normalized coverage is `0.9465`.

**Accepted artifacts.** Output root:
`workspace/fox_posterior_adaptation_20260921/visibility_gated_dense_expert_distillation_narrow_band/`.
Final carrier, partial overlay, textured/blue overlay, six-view board and full
report are respectively `posterior_expert_distilled_100k.ply`,
`partial_gray_posterior_expert_distilled_red.ply`,
`partial_blue_posterior_pixal_texture.ply`,
`posterior_expert_distilled_views.png`, and
`expert_distillation_report.json` in that directory.

## 2026-09-22 — accepted fox residual-calibrated structural-cohort posterior

**User approval.** The user judged this candidate "非常好了" and requested
publication-style figures explaining its deformation process. Preserve the
entire output directory and do not overwrite its carrier, report or overlays.

**Inputs and generation record.** Sample id: `cartoon_fox`. The registered
carrier, collapsed local-fit teacher, partial, GT, Camera-1, semantic image,
Pixal carrier, Pixal3D model/checkpoint, native camera, seed, resolutions,
verbatim semantic prompt, and all `UNKNOWN` image-generation fields are
exactly those recorded in the preceding accepted fox visibility-gated entry.

**Exact focused configuration.** The accepted output was generated by
`scripts/distill_visibility_gated_expert.py` with residual quantile `0.10`,
minimum improvement `0.25` median spacings, no Camera-1 visibility dilation,
`17` trajectory samples, first-near-optimal trajectory tolerance `0.20`
spacings, structural-cohort radius `5.0` spacings, cohort minimum motion `0.75`
spacings, transition spacing/motion/diagonal controls `10.0/1.25/0.04`, hidden
coverage floor `0.90`, carrier edge-compression floor `0.34`, and node
edge-compression floor `0.20`. It uses no GT/CD/EMD, category, semantic part,
or fixed-coordinate rule. Of the complete ordered carrier, 16,964 Camera-1
teacher points are residual-calibrated, 21,962 geodesically local hidden-side
cohort points follow their nearest visible structural seed, and 25,353 remote
carrier points remain fixed. The accepted full-amplitude solve retains all
100,000 slots, one significant component, normalized hidden-view coverage
`0.9030`, and robust p01 edge ratio `0.3442`.

**Accepted artifacts.** Output root:
`workspace/fox_posterior_adaptation_20260921/residual_calibrated_structural_cohort_r5_full/`.
Final carrier, gray/red overlay, Pixal-textured/blue overlay, multi-view board,
calibrated targets, cohort samples and exact report are respectively
`posterior_expert_distilled_100k.ply`,
`partial_gray_posterior_expert_distilled_red.ply`,
`partial_blue_posterior_pixal_texture.ply`,
`posterior_expert_distilled_views.png`, `calibrated_target_points.ply`,
`structural_cohort_points.ply`, and `expert_distillation_report.json`.

**Equivalent integrated export (confirmed 2026-09-24).** The user identified
`workspace/fox_residual_proximal_prior_20260923/prior_projection/partial_blue_posterior_pixal_texture.ply`
as the intended accepted Fox visualization.  Its first 100,000 ordered carrier
slots are coordinate-identical to the accepted posterior above; the matching
carrier is `prior_projection/posterior_expert_distilled_100k.ply`.  A requested
observation-anchored fusion export is stored at
`workspace/fox_residual_proximal_prior_20260923/fusion/observation_anchored_fused_100k_pixal_texture.ply`.
It retains 100,000 slots, replaces 12,007 slots with collision-free measured
partial anchors supported by the four saved cameras, and inherits RGB
slot-for-slot from the user-confirmed Pixal3D-textured visualization.  Fusion
uses the shared default parameters recorded in `fusion/fusion_info.json`; it
does not concatenate points, perform a second deformation, or use GT/CD/EMD.
The exact export provenance and hashes are in
`fusion/observation_anchored_fused_100k_pixal_texture_info.json`.

**No-GT diagnostic.** Partial-to-posterior mean nearest-surface residual is
`0.003927`, improving from `0.004276` for the preceding accepted narrow-band
candidate. This diagnostic was measured after freezing the output and was not
used as GT supervision.

## 2026-09-23 18:02 +0800 — accepted domestic-pig structure-preserving posterior

**User approval.** The user judged this rerun "非常非常好了" after rejecting
the experimental full-amplitude low-frequency candidate for weakening the
hind-limb structure. Preserve this directory and do not overwrite the final
carrier or its overlays. For this Pig input, do not append the experimental
low-frequency expansion unless a new shared, cross-sample gate is explicitly
validated first.

**Sample and inputs.** Sample id: `domestic_pig`. Registered complete carrier,
partial, Camera-1, semantic image, four-view manifest, and original textured
Pixal carrier are respectively:
`workspace/domestic_pig_depth_gauge_fixed_20260919/registration/domestic_pig/final/camera1_amplified_registered_100k.ply`,
`workspace/domestic_pig_depth_gauge_fixed_20260919/inputs/partial/domestic_pig.ply`,
`workspace/domestic_pig_depth_gauge_fixed_20260919/inputs/camera/domestic_pig/camera.pth`,
`workspace/domestic_pig_depth_gauge_fixed_20260919/inputs/camera/domestic_pig/img.png`,
`workspace/domestic_pig_depth_gauge_fixed_20260919/residuals/domestic_pig/render/render_manifest.json`, and
`workspace/domestic_pig_depth_gauge_fixed_20260919/inputs/pixal/domestic_pig/pixal3d_sampled_100k.ply`.

**Semantic generation record.** The recorded method is
`depth_mask_conditioned_direct_gpt_semantic_completion`. The exact GPT model,
negative prompt, image seed, number of steps, CFG/guidance, scheduler, backend,
and resize policy are `UNKNOWN`; therefore the semantic generation itself is
not exactly reproducible from the surviving metadata. The verbatim prompt is:

> Generate one complete, realistic RGB object image from the supplied incomplete depth map. The object is a complete domestic pig. Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, apparent width and height, crop, orientation, visible silhouette, depth ordering, and all observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or redesign the observed object. Complete only genuinely missing or occluded regions, connect them naturally to the observed structure, and keep a single coherent object on a pure white background. Produce sharp boundaries and realistic materials suitable for image-to-3D reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that change the foreground mask. Additional structural constraints: Keep one connected torso, four naturally attached legs, two ears, one snout, and one tail.

**Pixal generation record.** Pixal3D checkpoint:
`/opt/data/private/cr/lab/GenPC/models/Pixal3D-weights`; DINO:
`/opt/data/private/cr/lab/GenPC/models/dinov3-vitl16-pretrain-lvd1689m`;
MoGe: `/opt/data/private/cr/lab/GenPC/models/moge-2-vitl/model.pt`; RMBG:
`/opt/data/private/cr/lab/GenPC/models/RMBG-2.0`; xFormers backend; seed `42`;
requested/actual resolution `1024`; decimation target `120000`; texture size
`1024`. Sparse/shape/texture stages each use `12` steps, guidance strengths
`7.5/7.5/1.0`, guidance rescale `0.7/0.5/0.0`, and rescale-t `5.0/3.0/3.0`.
Native camera parameters are `camera_angle_x=0.6790872770960652`, distance
`1.4155343770980835`, and `mesh_scale=1.0`.

**Accepted posterior execution.** Run `scripts/run_posterior_adapter.py` with
the preceding inputs, CUDA, and the unchanged shared configuration
`configs/posterior_mainline.json`. The method uses exact Camera-1 structural
transport, four-view local observation assimilation, coarse/fine embedded
ARAP deformation, topology projection, and the complete ordered 100,000-point
carrier. It uses no category/part rule and no GT/CD/EMD during inference. The
rerun is point-for-point identical to the previously frozen Pig posterior.

**Accepted artifacts.** Output root:
`workspace/pig_structure_preserving_mainline_rerun_20260923/`. Final carrier,
gray/red overlay, Pixal-textured/blue overlay, virtual-view board, saved-view
projection, support status, OT pairs, deformation field, and complete report
are respectively `posterior_prior_100k.ply`, `partial_gray_posterior_red.ply`,
`partial_blue_posterior_pixal_texture.ply`, `posterior_virtual_views.png`,
`posterior_saved_view_projection.png`, `posterior_support_status.png`,
`partial_ot_pairs.npy`, `posterior_field.npz`, and `posterior_info.json`.

**Offline diagnostic only.** Deterministic 16,384-point FPS with seed `6145`
gives CD-L1/EMD x100 `1.6435/2.1145`. The robust 5--95% principal extent is
`0.8509`, already covering the partial extent `0.8413`; this is why additional
global expansion is not selected. These measurements were made only after the
result was frozen and did not guide the posterior solve.

## 2026-09-25 20:35 +0800 — accepted Pixal3D-stage reproduction package

**User approval and scope.** The user approved the cleaned posterior result and
requested that depth images, semantic images, Pixal3D products and camera
parameters be retained so the accepted Redwood/Custom route can be replayed
from Pixal3D before legacy workspace experiments are removed. The canonical
physical-copy package is
`workspace/compagent_pixal_reproduction_20260925/`. Do not replace it with
symlinks or remove it during workspace cleanup.

**Samples and inputs.** The package contains Redwood10 and Custom12 (22
samples). For every sample, `inputs/camera/<sample>/` contains the original
depth PNG/array when available, raw depth, semantic image, `camera.pth`,
`camera.json` when available, `point_uv.npy`, `viewpoint.npy`, masks and audit
metadata; `inputs/partial/<sample>.ply` is the observed partial;
`inputs/pixal/<sample>/` contains the exact Pixal input, GPT semantic copy and
verbatim prompt files, `pixal3d.glb`, `pixal3d_sampled_100k.ply`,
`pixal3d_metadata.json`, and `pixal_moge_fp16_observation.npz`. Exact source
paths and SHA-256 values for all 838 retained files are in `manifest.json`.

**Models, prompts and generation parameters.** No image or 3-D model was
regenerated while building this package. Per-sample Pixal model/checkpoint,
seed, resolution, decimation, camera and generation parameters are copied
verbatim in each `pixal3d_metadata.json`. The exact positive prompt is copied
verbatim in each available `gpt_depth_completion_prompt.txt`/JSON and the
semantic-install manifest; no negative prompt was newly supplied. Fields not
recorded by the original generation remain explicitly `UNKNOWN` in the
historical accepted entries and are not guessed here.

**Postprocessing and replay.** `scripts/reproduce_packaged_mainline.py` starts
from the retained ordered Pixal carrier/native MoGe observation, runs the
fixed Pixal--MoGe--partial bridge and Camera-1 initial registration, then runs
the shared monotonic broad continuation with levels
`[[0.08,8,0.08],[0.03,3,0.03],[0.01,1,0.01]]`, at most six passes, minimum
relative improvement `0.025`, 32k search samples and two candidate workers.
It then runs `configs/posterior_mainline.json`; the accepted Fox visual result
uses the recorded six-round residual-proximal proposal configuration. Saved
four-view manifests retain only portable FOV/camera-pose evidence. No GT,
CD/EMD, category rule or part rule is read during replay.

**Verification.** The complete package has no symlinks and passed SHA-256
verification. A clean 01184 replay reproduces selected registration SHA-256
`4914f127a0c04180034fe605c588f9acb7db3e68c47ff6f57fe5673e8cfc6ecf`
and final posterior SHA-256
`c3bb208f8eb2d7334a2656fedd880125d2ed5ead3d619d6df24d256bc65ed0e6`
byte-for-byte. The report is
`workspace/compagent_pixal_reproduction_20260925/reports/reproduction_smoke_01184.json`.
The complete Python suite passes 95 tests. Retained Fox paper figures,
textured/blue overlay and textured observation-anchored fused carrier are in
the package's `paper_assets/cartoon_fox/` directory.

**Cleanup completion.** After the checksum/test gate, 35 legacy experiment
directories were permanently removed from `workspace/`; they are not
recoverable from the filesystem. The canonical package was explicitly
excluded and is now the only workspace directory (811 MiB versus roughly
17 GiB before cleanup). A second full 01184 replay was then run after deletion
using only the package and repository code; both hashes above remained exact,
so the package has no runtime dependency on a removed experiment path.

## 2026-09-26 00:57 +0800 — accepted continuous final observation fusion

**User approval and scope.** The user requested that the current final fusion
scheme be saved and pushed as the active shared method after it was run on
Redwood10 and Custom12. Preserve this category-independent configuration and
the accepted posterior inputs; do not silently restore the older loose
exact-slot decoder as the default. `--mode exact` remains available only for
historical Fox export reproduction.

**Inputs and samples.** Fusion starts from the frozen package at
`workspace/compagent_pixal_reproduction_20260925/`. Redwood uses
`redwood/reference_result/<id>/posterior_prior_100k.ply`; Custom uses
`custom/reference_result/<sample>/posterior_prior_100k.ply`, except
`cartoon_fox`, which intentionally uses the accepted
`posterior_expert_distilled_100k.ply`. Physical observations are
`<dataset>/inputs/partial/`, four-camera contracts are
`<dataset>/residuals/<sample>/render/render_manifest.json`, and ordered RGB is
copied from `<dataset>/inputs/pixal/<sample>/pixal3d_sampled_100k.ply`.
Samples are Redwood10 (`01184`, `05117`, `05452`, `06127`, `06145`, `06188`,
`06830`, `07136`, `07306`, `09639`) and all 12 packaged Custom samples.

**Models and prompts.** NOT APPLICABLE to this fusion stage: no image model,
3-D generator, checkpoint, positive prompt, negative prompt, seed, CFG,
scheduler, or generative resolution is invoked. Upstream semantic/Pixal3D
assets are unchanged; their exact model metadata, verbatim prompts and known
generation parameters remain beside each sample in `inputs/pixal/` and
`inputs/camera/`. Unknown historical fields remain `UNKNOWN` and are not
inferred here.

**Method and exact shared parameters.** `src/observation_anchored_fusion.py`
implements `continuous_multiview_observation_fusion`; the single and batch
runners are `scripts/run_observation_anchored_fusion.py` and
`scripts/run_observation_anchored_fusion_batch.py`. Four views use pixel radius
`1.0`, cross-view radius `2.0`, normalized depth gate `0.03`, at least two-view
support, maximum residual ratio `0.03`, residual quantile `0.90`, partial
spacing multiplier `6.0`, carrier/partial influence multipliers `12.0/4.0`,
node fraction `0.04`, node bounds `192/6144`, 10 graph neighbours, edge ratio
`1.85`, attachment ratio `3.2`, data weight `4.0`, screening `0.004`, three
iterations, minimum improvement `0.01`, edge compression/stretch bounds
`0.70/1.80`, minimum hidden coverage `0.98`, and coverage resolution `160`.
Cross-view collision-free anchors drive a finite-support embedded-ARAP field;
carrier samples outside the observation band are fixed. No point is appended
or deleted, and no GT/CD/EMD enters correspondence, line search, or stopping.

**Accepted artifacts and postprocessing.** Local complete outputs are
`workspace/compagent_pixal_reproduction_20260925/<dataset>/final_fused/<sample>/complete_100k.ply`
and `complete_100k_pixal_texture.ply`; full no-GT audit files are under the
sibling `fusion_continuous/` trees. Every geometry output has exactly 100,000
ordered slots and every textured output has 100,000 slot-aligned RGB values.
The decoder performs only confidence gating, continuous carrier assimilation,
and ordered RGB transfer; it does not concatenate, resample, crop, or invoke a
new shape generator.

**Offline diagnostics only.** Frozen Redwood10 CD-L1/EMD x100 changes from
`1.5380/2.4835` to `1.5235/2.4716`. Against the actual Custom input carriers
(including visual-best Fox), Custom12 changes from `2.2173/2.7825` to
`2.1928/2.7633`; CD improves on 12/12 and EMD on 11/12 samples. Reports are
`reports/redwood_continuous_fusion_metrics.{csv,json}` and
`reports/custom_continuous_fusion_metrics.{csv,json}` inside the local package.
Metrics were computed only after outputs were frozen. Package checksum
verification passes and the complete test suite passes 96 tests.
