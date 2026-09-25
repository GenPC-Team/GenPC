# Active plan

Historical exploration is preserved in git commit `f69e38a` and accepted
artifacts are recorded in `PROJECT_STATE.md`. This file tracks only the
released object-completion route and its immediate maintenance work.

## Current CompAgent object route

- [x] Rasterize the partial point cloud with its saved Camera-1 and produce a
  mask-locked, camera-consistent semantic observation.
- [x] Generate a textured Pixal3D prior, preserve the native MoGe observation,
  and retain its ordered 100k surface carrier.
- [x] Use the native Pixal--MoGe camera contract plus the pixel-indexed
  MoGe--partial bridge for proper-Sim(3) placement; start posterior inference
  from `registration_selected/<id>/camera1_amplified_registered_100k.ply`.
- [x] Build four saved views: Camera-1 plus three partial-visibility-aware
  auxiliary views. Missing pixels are unknown, not deletion evidence.
- [x] Run the same class-free `PosteriorAdapter` for exactly three outer
  rounds. Each round re-estimates Camera-1 Partial OT and four-view positive
  evidence from the preceding 100k carrier; it preserves all slots and uses no
  GT/CD/EMD, category labels, part labels, or sample-specific rules.
- [x] Report offline metrics only after inference with deterministic 16,384
  point FPS and seed 6145.

## Accepted selected-carrier evaluation (2026-09-20)

- [x] Reuse the retained semantic/Pixal assets and run the fixed three-round
  mainline on Redwood10 and Custom10. The complete artifact bundle is
  `workspace/tto_relinearized_selected_redwood_custom_20260920/`.
- [x] Verify all 20 `round_03/posterior_prior_100k.ply` predictions contain
  exactly 100,000 points. The offline-only scores are Redwood10
  CD-L1/EMD x100 `1.4872/2.4083` and Custom10 `1.8567/2.3406`.
- [x] Retain `workspace/tto_relinearized_redwood_custom_20260920/` only as an
  invalid diagnostic; it started Custom from stale pre-selection carriers and
  must not be cited or compared.

## Cleanup and regression

- [x] Save the full pre-cleanup code snapshot at `f69e38a` and push it to
  `origin/codex/agentic-01184-probe`.
- [x] Remove experimental rigid/structural posterior probes and their dormant
  solver paths, while retaining the accepted three-round posterior route.
- [x] Rename the accepted iterative solver and batch entrypoint without the
  `probe`/`tto` label, update user-facing documentation, and run a numerical
  single-case regression from the selected 01184 carrier. The cleaned
  `01184` `round_03` carrier is SHA-256 identical to the accepted package.
- [x] Run the focused posterior/registration test suite, verify a clean
  worktree apart from untracked datasets, then commit and push the cleaned
  mainline. The full suite passes `77` tests; the only remaining untracked
  paths are external dataset directories.

## Omni-Comp3D Synthetic single-scan evaluation (2026-09-21)

- [x] Remove the discarded Omni Redwood single-scan artifact package and run
  the complete frozen object route on all 20 Synthetic single-scan inputs
  (two scans for each of Dinosaur, Glass, Guitar, Headphone, Laptop, Robot,
  Shoe, Statue, Toilet, and Torch). Assets are retained at
  `workspace/omni_synthetic_single_scan20_compagent_20260921/`.
- [x] Save per-sample Camera-1 depth, GPT depth-conditioned semantic image,
  Pixal GLB/native-MoGe/100k carrier, registration stages, four-view
  diagnostics, and three PosteriorAdapter rounds. The environment had no EGL
  device, so the four-view evidence uses the existing registered-carrier
  point-rendering fallback; it preserves the same saved Camera-1 and
  partial-visibility-aware auxiliary cameras.
- [x] Complete offline-only 16,384-point FPS evaluation (seed 6145). Mean
  CD-L1/EMD x100 is `5.3543/7.1882`; the report is
  `metrics/omni_synthetic_single_scan_cd_emd.{csv,json}`. These are
  diagnostic generalization results, not an accepted baseline.

## King-crab end-to-end nonorthogonal sampling check (2026-09-21)

- [x] Add generic deterministic custom sampling through `--sample-spec` to
  `scripts/resample_custom_nonorthogonal_partials.py`, then sample
  `data/custom/glb/king_crab.glb` from the seeded nonorthogonal Camera-1
  `(azimuth=280.443346 deg, elevation=-14.762721 deg, seed=20260921)`.
  The source partial and GT have 16,384 points each.
- [x] Run the released route from the sampled partial through depth-conditioned
  GPT semantic preparation, Pixal native prior/MoGe, cross-camera Sim(3),
  four-view evidence, and the fixed three-round posterior update. All
  diagnostic assets and final 100k point carrier are retained at
  `workspace/king_crab_from_scratch_nonorthogonal_20260921/`; the final
  completion is `tto/king_crab/round_03/posterior_prior_100k.ply`.
- [x] Verify the final carrier exists with 100,000 points and run offline-only
  16,384-point evaluation (seed 6145): CD-L1/EMD x100 `5.5912/4.8668` in
  `metrics/king_crab_cd_emd.{csv,json}`. This is a fresh diagnostic result,
  not yet an accepted baseline.

## Cartoon-fox continuous-deformation stress test (2026-09-21)

- [x] Keep the semantic observation, Pixal carrier, selected registration,
  Camera-1, and four-view residual evidence frozen, then compare normalized,
  category-free posterior profiles only. The user visually approved the
  high-resolution six-round candidate at
  `workspace/fox_posterior_adaptation_20260921/high_resolution_expansive_stable/round_06/partial_gray_posterior_red.ply`.
- [x] Evaluate the fixed three-round carrier and the approved high-resolution
  candidate with identical GT, 16,384-point FPS, and seed `6145`. The stronger
  visual adaptation regresses offline CD-L1/EMD x100 from `2.3662/2.7546` to
  `2.6489/4.1928`; retain it as a deformation diagnostic rather than adopting
  it into the released shared configuration.
- [x] Diagnose the visual carrier-collapse failure as accumulated outer-round
  drift: each posterior update was locally protected only relative to its
  previous carrier. Add an optional, category-free reference-carrier line
  search that compares every outer update to the registered 100k carrier and
  enforces coverage, connectivity, and robust rest-edge strain. The focused
  `cartoon_fox` rerun is
  `workspace/fox_posterior_adaptation_20260921/high_resolution_complete_carrier_protected/`.
  It retains 100,000 points, one connected component, and reference coverage
  `0.9278`; offline CD-L1/EMD x100 is `2.3221/2.8175`. This optional mechanism
  is not yet part of the released mainline pending visual acceptance and
  cross-sample validation.
- [x] Add an optional proper-Sim(3) gain for graph-connected positive residual
  components and verify its default value `1.0` is behavior preserving.  The
  fox gain-`1.35` stress test is retained at
  `workspace/fox_posterior_adaptation_20260921/local_motion_component_sim3_gain135_core6_harmonic3_incremental_stretch25_six_rounds/`;
  no-GT four-view residual reaches `0.01018`, fixed-frame coverage is `0.9233`,
  and offline-only CD-L1/EMD x100 is `1.9350/2.7935` at round 5.
- [x] Test local distillation of an aggressive/collapsed posterior into the
  protected complete carrier.  Selection uses only nearest observed-surface
  improvement, residual quantiles, and rest-graph connectivity.  The q95
  candidate moves 4,293 high-benefit core points plus a finite transition band,
  retains the full ordered carrier, and has fixed-frame coverage `0.9161`
  versus approximately `0.6277` for the collapsed expert.  Outputs are at
  `workspace/fox_posterior_adaptation_20260921/collapse_expert_local_distillation_q95_core1_harmonic2_coverage91/`.
  Its offline-only CD-L1/EMD x100 (`2.0122/3.0659`) is worse than the gain-only
  candidate, so it remains a visual/local-fit experiment rather than a
  mainline replacement.
- [x] Preserve complete surface sampling after strong deformation by
  transferring the ordered-carrier field to the original mesh topology and
  sampling additional points only from expanded faces.  Both the deformed GLB
  and carrier-preserving 125k point visualization are stored under each
  candidate's `mesh_carrier_dense/` directory.  The method remains optional;
  the released 100k output contract is unchanged.
- [x] Replace one-shot local distillation with an experimental, category-free
  multi-view proximal TTO loop.  Bidirectional visible transport combines
  prior-to-partial and partial-to-proposal pixel/depth evidence; only
  correspondences supported by at least two saved cameras enter a
  graph-geodesic trust region.  A sparse embedded-SE(3) ARAP graph then moves
  the complete ordered carrier while stable observations and the carrier
  outside that trust region remain fixed.  On fox, the loop converges after
  eight accepted rounds at
  `workspace/fox_posterior_adaptation_20260921/bidirectional_multiview_proximal_embedded_tto/`.
  It improves offline CD-L1 x100 from `1.9350` to `1.8968`, while EMD x100
  changes from `2.7933` to `3.0926`; metrics were computed only after the
  frozen result and were not used by the optimizer.  Keep this as a focused
  visual experiment until the user accepts it and shared-parameter
  generalization is tested.
- [x] Test acquisition-visibility-gated distillation of the strong but
  collapsed six-round carrier into the intact registered carrier.  Dense
  Camera-1 surface patches are copied exactly only where the expert reduces
  observed residual; 46,229 points outside the finite geodesic transition
  band remain fixed to the complete prior.  The narrow-band candidate keeps
  one significant component, inherits 16,964 dense teacher points at full
  amplitude, and retains normalized orthographic coverage `0.9465` versus
  approximately `0.6277` for the collapsed teacher.  Outputs are at
  `workspace/fox_posterior_adaptation_20260921/visibility_gated_dense_expert_distillation_narrow_band/`.
  This is a focused no-GT fox experiment and does not modify the released
  mainline until visually accepted and validated with shared parameters.
- [x] Diagnose the remaining fox double-surface artifact as amplitude mismatch
  plus one-sided visibility: near observed samples were transported too far,
  while the hidden side of the same thin structure was not transported at all.
  Add a category-free residual-calibrated teacher trajectory and finite
  rest-surface structural cohorts.  The focused full-amplitude candidate is
  `workspace/fox_posterior_adaptation_20260921/residual_calibrated_structural_cohort_r5_full/`;
  it calibrates 16,964 visible targets, propagates their motion to 21,962
  geodesically local cohort samples, keeps 25,353 remote carrier samples fixed,
  and retains normalized hidden-view coverage `0.9030`.  Partial-to-posterior
  mean nearest-surface residual improves from `0.004276` for the accepted
  narrow-band candidate to `0.003927`.  Keep this as a focused no-GT candidate
  pending visual acceptance; the released mainline is unchanged.
- [x] Test a simpler no-teacher observation-driven posterior on fox.  The
  experiment feeds four-view pixel/depth evidence directly into the existing
  embedded-ARAP carrier, separates low-residual stable anchors from residual
  anchors, and retains reference-carrier coverage/connectivity constraints.
  The strongest no-GT candidate is
  `workspace/fox_observation_driven_posterior_20260923/confidence_residual_field_wide/round_02/`.
  It preserves the complete 100k carrier and improves four-view median
  residual from `0.01860` to `0.01264`, but its tail/extremity fit remains
  visibly weaker than the accepted structural-cohort result.  Keep it as an
  isolated simplification experiment; do not replace the accepted fox result
  or the released mainline without user approval.
- [x] Test an integrated residual-proximal interface that does not accept an
  aggressive expert as an external input.  The method takes only the
  registered complete prior, partial observation, saved cameras, and
  multi-view evidence; it generates the high-gain observation proposal as an
  internal TTO state and immediately projects it back to the intact ordered
  carrier.  The isolated fox result is
  `workspace/fox_residual_proximal_prior_20260923/`.  Its final 100k posterior
  is pointwise identical to the accepted residual-calibrated structural-cohort
  result (mean/RMSE/max coordinate difference all `0.0`) and retains the same
  16,964 calibrated visible targets, 21,962 structural-cohort points, 25,353
  fixed remote points, and 0.90 minimum hidden coverage.  This validates the
  simplified external method contract without changing the released mainline;
  cross-sample validation remains necessary before adopting it.
- [x] Run the same integrated residual-proximal configuration on the frozen
  `domestic_pig` inputs without changing any threshold or adding category/part
  logic.  Outputs are in `workspace/pig_residual_proximal_prior_20260923/`.
  The final carrier keeps all 100,000 ordered prior points, 38,416 remote
  complete-prior points fixed, and normalized hidden-view coverage `0.9725`.
  Partial-to-carrier mean/median nearest-surface residual improves from
  `0.01825/0.00932` for the registered prior and `0.00920/0.00716` for the
  previously accepted Pig probe to `0.00342/0.00213`.  Offline-only frozen
  CD-L1/EMD x100 is `2.8684/3.1155`, versus `3.5410/3.3689` for the accepted
  probe; GT was evaluated only after inference and did not affect selection.
- [x] Add a category-free low-frequency structural-motion branch to the
  residual-proximal projection.  A robust ordered-carrier affine estimate is
  projected onto its expansion-only polar stretch, anchored at reliable
  low-motion observations, and accepted only when the upper-tail visible
  residual falls by at least 15% while coverage and local edge strain remain
  valid.  The field is continuous; stable samples define its centre rather
  than being hard-reset after deformation.  On Pig, the selected full-amplitude
  mode is `1.1784 x 1.0 x 1.0`, the 5--95% principal extent changes from
  `0.8065` to `0.8392` (partial: `0.8413`), and offline CD-L1 x100 improves
  from `2.6913` to `2.6427`; EMD x100 changes from `3.0266` to `3.0827`.
  Outputs are at `workspace/pig_lowrank_continuous_20260923/`.  The same
  unchanged gate rejects the unnecessary Fox low-frequency proposal (6.5%
  tail gain), and `workspace/fox_lowrank_continuous_20260923/` is pointwise
  identical to the accepted Fox result.  GT metrics were computed only after
  both outputs were frozen and were not used by inference.
- [x] Recheck Pig after visual review found that the full low-frequency
  candidate weakened hind-limb structure.  The cause was not insufficient
  span in the generic posterior: the frozen `posterior_mainline.json` result
  already has a robust principal extent of `0.8509` versus `0.8413` for the
  partial.  Re-running the generic PosteriorAdapter from the same registered
  prior reproduces the previously accepted 100k carrier point-for-point at
  `workspace/pig_structure_preserving_mainline_rerun_20260923/`.  Therefore
  treat low-frequency expansion as a conditional structural correction, not
  an unconditional second deformation.  For Pig the no-GT extent diagnostic
  selects the generic posterior without additional expansion and preserves
  the better limb structure; its previously frozen offline CD-L1/EMD x100
  remains `1.6435/2.1145`.  Keep the low-frequency branch experimental until
  this routing decision is integrated and validated beyond Pig/Fox.
- [x] Freeze the accepted generic `posterior_mainline.json` configuration and
  run it unchanged on Redwood10 and all 12 available Custom samples.  The
  complete audit bundle is
  `workspace/posterior_mainline_generalization_20260923/`; every case retains
  the ordered 100,000-point prior carrier and provides red/gray, textured/blue,
  saved-view, virtual-view, support-state, OT, and deformation-field outputs.
  All 22 runs completed without failure.  Offline-only 16,384-point metrics
  are `1.5380/2.4835` mean CD-L1/EMD x100 on Redwood10 and
  `2.2990/2.8444` on Custom12.  The accepted Pig output is reproduced
  point-for-point.  `mirrorless_camera` and `king_crab` remain Custom metric
  outliers and should be diagnosed upstream rather than by changing the
  shared posterior thresholds.
- [x] Correct the 2026-09-23 generalization audit after visual inspection of
  `cartoon_fox`: the first batch exercised only the conservative generic
  PosteriorAdapter and therefore is not a reproduction of the later accepted
  residual-proximal structural-cohort result.  Preserve the conservative
  output as an ablation, and place the exact accepted, integrated result at
  `workspace/posterior_mainline_generalization_20260923/custom/cartoon_fox_visual_best/`.
  It is pointwise identical to the accepted structural-cohort carrier, keeps
  all 100,000 slots, and improves offline CD-L1/EMD x100 from
  `2.7667/3.2404` to `1.7859/2.4970`.  Do not present the conservative
  `custom/cartoon_fox/` output as the current Fox result.
- [x] Run the integrated residual-proximal method itself, with one unchanged
  category-free configuration, over Redwood10 and Custom12.  The new isolated
  bundle is `workspace/residual_proximal_generalization_20260923/`; every case
  includes the six-round internal observation proposal and final structural-
  cohort projection.  All 22 jobs completed and every final carrier contains
  exactly 100,000 ordered points.  Fox is reproduced point-for-point.  Offline
  CD-L1/EMD x100 is `1.5739/2.5362` on Redwood10 and `2.3221/2.8899` on
  Custom12.  The method strongly improves Fox, Hydra, light helicopter and
  Seahawk, but unconditionally applying the aggressive branch regresses Pig
  and mildly regresses most Redwood cases.  Treat it as a residual-triggered
  strong branch, not as an unconditional replacement for the conservative
  posterior; no GT-based routing was performed in this audit.
- [x] Export the user-confirmed integrated Fox result through the shared
  four-view observation-anchored fusion decoder.  The textured 100k carrier is
  `workspace/fox_residual_proximal_prior_20260923/fusion/observation_anchored_fused_100k_pixal_texture.ply`;
  12,007 collision-free carrier slots receive measured partial anchors while
  all slot colours remain the ordered Pixal3D texture.  Exact geometry and RGB
  provenance are recorded beside the output.
- [x] Render the accepted Fox keypoint-deformation side view and a tail-detail
  zoom with the existing Easy3D offscreen renderer.  Both panels use native
  `PointsDrawable::SPHERE` impostors at point size `4.0`, the frozen saved
  camera, Pixal3D carrier RGB, and blue partial evidence.  Separate full,
  detail, and composed assets plus their manifest are in
  `workspace/fox_residual_proximal_prior_20260923/paper_zoom_easy3d/`.
- [x] Re-render the user-selected Fox back/oblique view as two independent PPT
  assets: the complete view uses Easy3D sphere point size `5.0`, while the
  2x-resolution tail/leg detail uses point size `10.0`.  Only the five handles
  whose source and target both lie inside the tail/leg ROI are shown; all
  face, neck, and torso arrows are omitted.  After checking an inflated leg
  correspondence, pink endpoints were changed from nearest partial samples to
  the actual final positions of the same ordered posterior slots.  Outputs are
  in `workspace/fox_residual_proximal_prior_20260923/paper_zoom_easy3d_back_point5_zoom10_posterior_targets/`.
- [x] Replace the sparse Fox keypoint-arrow illustration with a deformation-
  field visualization derived from the ordered accepted prior/posterior
  carrier.  The full Easy3D sphere rendering encodes normalized displacement
  magnitude continuously on every prior point and overlays the partial only as
  a blue target silhouette.  The separate 2x tail/leg detail samples one
  high-motion vector per image-space cell; glyph lengths are fixed to avoid
  exaggerating leg motion, while Turbo colour encodes the true magnitude.
  Full point size is `5.0`, zoom point size is `10.0`, and all assets and the
  exact rendering manifest are in
  `workspace/fox_residual_proximal_prior_20260923/paper_deformation_field_easy3d/`.

## Posterior deformation modular refactor (2026-09-25)

- [x] Split the monolithic posterior implementation into five explicit,
  behavior-preserving modules: immutable contracts in `posterior_types.py`,
  structural Partial OT in `partial_transport.py`, embedded complete-carrier
  deformation in `posterior_deformation.py`, integrity and residual-motion
  projections in `carrier_protection.py`, and orchestration/audit assembly in
  `posterior_adapter.py`. Preserve the historical facade imports used by old
  experiment scripts while changing internal imports to their owning modules.
- [x] Add `scripts/check_posterior_regression.py`, which compares every ordered
  carrier slot and fails per sample rather than allowing aggregate metrics to
  hide a regression. The complete Python suite passes `95` tests.
- [x] Re-run the frozen shared `posterior_mainline.json` configuration on
  Redwood10 and Custom12 into
  `workspace/posterior_refactor_regression_20260925/`. All 22 outputs retain
  exactly 100,000 slots and are pointwise identical to the frozen baselines:
  maximum error and RMSE are `0.0` for every sample. Consequently the offline
  CD-L1/EMD x100 remains exactly `1.5380/2.4835` on Redwood10 and
  `2.2990/2.8444` on Custom12. Regression reports are
  `redwood_pointwise_regression.json` and `custom_pointwise_regression.json`.
- [x] Re-run the accepted Fox residual-proximal visual branch after the split.
  Its final 100k posterior is byte-identical (SHA-256
  `34f69b4363635480fb32e25488427e1718e33190e6bf3903e1c990aaec1dd716`) to
  `workspace/fox_residual_proximal_prior_20260923/prior_projection/posterior_expert_distilled_100k.ply`.
- [x] Make posterior artifact retention reviewable. Single-case and batch
  PosteriorAdapter entrypoints now default to `--output-profile lean`, keeping
  only the final 100k carrier, matched gray/red before/after overlays,
  Camera-1 projection, multi-view projection, and JSON audit. `debug`
  explicitly restores the
  coarse carrier, support visualization, OT table, and dense field. A
  zero-copy, numbered 22-sample review tree is available at
  `workspace/posterior_refactor_regression_20260925/review/`; the original
  complete audit artifacts were not deleted.
- [x] Correct the compact review index after it initially exposed the
  conservative Custom12 `cartoon_fox` carrier instead of the user-approved
  residual-proximal visual result. The review builder now supports explicit,
  auditable `SAMPLE=PATH` preferred-result overrides. Rebuild the Fox entry
  from `cartoon_fox_visual_best`, add its matching Camera-1 projection, and
  verify that `review/custom/cartoon_fox/01_final_posterior.ply` has the same
  SHA-256 (`34f69b...dd716`) as the accepted Fox carrier.
- [x] Add paired deformation comparisons to every compact review sample:
  `02_before_registered_partial_overlay.ply` combines the gray partial with
  the red registered complete prior, while
  `03_after_posterior_partial_overlay.ply` combines the identical gray partial
  with the red deformed complete posterior. Backfill both Redwood10 and
  Custom12, and use the accepted residual-proximal carrier for Fox.

## Pixal3D-stage reproduction package and workspace cleanup (2026-09-25)

- [x] Materialize the Redwood10 + Custom12 inference state at
  `workspace/compagent_pixal_reproduction_20260925/`. The package contains 22
  samples and 838 checksum-tracked physical files: Camera-1 depth/semantic and
  calibration, UV/object masks, partials, Pixal3D images/metadata/GLBs/100k
  carriers/native-MoGe caches, portable four-view camera manifests, selected
  registration checkpoints, final before/after overlays, metrics, and retained
  Fox paper assets. It contains no GT and no symlinks.
- [x] Add `scripts/package_mainline_reproduction.py` and
  `scripts/reproduce_packaged_mainline.py`. The replay restores the previously
  implicit shared Camera-1 broad continuation after initial two-camera
  registration. A full 01184 replay from retained Pixal3D assets reproduces
  both selected registration and the final 100k posterior byte-for-byte; the
  SHA-256 audit is stored at
  `reports/reproduction_smoke_01184.json` inside the package.
- [x] After the package checksum audit and all 95 tests passed, remove the 35
  legacy workspace experiment roots. `workspace/` now contains only the
  811 MiB reproduction package (previously approximately 17 GiB). Re-run 01184
  from that package after deletion and again reproduce selected registration
  and posterior byte-for-byte, proving that no deleted path is required.

## Redwood continuous observation fusion (2026-09-25)

- [x] Confirm that the packaged Redwood reference result stops at the complete
  PosteriorAdapter carrier even though four-view observation assimilation is
  already used inside posterior inference. Keep the historical exact-slot
  fusion mode for reproducibility, but do not use its loose one-view-supported
  replacements as the new default decoder.
- [x] Add a category-independent continuous fusion decoder. It requires at
  least two-view correspondence support, derives its residual radius from
  object scale and measured point spacing, fixes carrier samples outside a
  finite observation band, and reuses the embedded-ARAP line search to protect
  hidden coverage, connectivity and robust edge strain. It preserves all
  ordered carrier slots and can copy Pixal3D texture RGB slot-for-slot.
- [x] Run the same configuration on Redwood10. Geometry and textured final
  outputs are in
  `workspace/compagent_pixal_reproduction_20260925/redwood/final_fused/`,
  with diagnostics in the sibling `fusion_continuous/` tree. All ten outputs
  contain exactly 100,000 points; all textured variants contain exactly
  100,000 RGB values. Frozen offline-only CD-L1/EMD x100 changes from
  `1.5380/2.4835` before final fusion to `1.5235/2.4716` after fusion. Metrics
  are recorded in `reports/redwood_continuous_fusion_metrics.{csv,json}` and
  were not used by inference or parameter selection.
- [x] Apply the identical frozen fusion configuration to Custom12, using the
  user-approved residual-proximal visual-best carrier for `cartoon_fox` and
  the shared posterior carrier for every other sample. Geometry and textured
  100k outputs are in
  `workspace/compagent_pixal_reproduction_20260925/custom/final_fused/`, with
  auditable correspondence/field outputs under `custom/fusion_continuous/`.
  Every output retains exactly 100,000 carrier slots and RGB values. Against
  the actual input carriers, frozen offline-only CD-L1/EMD x100 changes from
  `2.2173/2.7825` to `2.1928/2.7633`; CD improves on 12/12 samples and EMD on
  11/12. GT was not available to fusion, line search, or stopping.
