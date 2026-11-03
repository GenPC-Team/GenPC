# Active plan

## Current handoff and source push (2026-11-03)

- [x] Keep the accepted Redwood10 experiment as the sole directory under
  `workspace/`: `workspace/redwood10_final/`. It contains the ten complete
  sample chains, ten fused PLYs, metric tables, copy manifest and SHA-256 list.
  The three other local workspace directories were deleted at the user's
  request. Paths to those directories in older entries below are historical
  and no longer usable. The copied JSON manifests retain old absolute paths;
  use the package's relative `copy_manifest.json`.
- [x] Update README, AGENTS and related method, installation, model and
  documentation index Markdown for the validated short-prompt Image Gen route, GPT-6 Sol
  prior review, transparent Pixal input, registration, refinement and fusion.
  Remove the obsolete fixed-three and mask-locked route from current
  documentation. Qwen/Nunchaku remains an optional backup.
- [x] Validate the source/documentation diff and test the current code:
  126 repository tests pass, targeted prior tests pass, touched Python files
  compile, `git diff --check` passes, and the remote branch matches local
  HEAD before commit. Commit the code and Markdown together on
  `codex/gpt-refine-v7-20261031`. Keep the large Redwood10 package local;
  do not stage `data/waymo/` or the tracked deletion of the older workspace
  package as part of this code push.

## Depth-faithful semantic prior revision (2026-11-03)

- [x] Generate all ten fixed-camera Redwood semantic images with one short depth-conditioned sentence per sample; save their images, verbatim prompts, input hashes, and a 10-case depth/image contact sheet under `revision_v2/imagegen_sentence_redwood10/`. The user approved all ten visually, including 07136; exact accepted-image records are in `PROJECT_STATE.md`. Do not overwrite these RGB images. The 1254×1254 source images and 512×512 depth rasters require an explicit same-canvas resize before numeric comparison.
- [x] Make the short sentence the default Image Gen prior prompt. The Prior Generation Agent selects the acquisition/front-side partial view when a view choice exists and reviews the complete candidate for approximate observed contour, pose, depth order, category identity, and natural construction. The entire 1254×1254 generated image is resized without crop or translation to the saved 512×512 depth canvas; depth, RGB, and overlay dimensions are checked before review, and the mapping is saved. All ten user-approved candidate hashes are unchanged, and all ten passed the no-GT agent review. Their per-case audit and RMBG transparent Pixal inputs are in `revision_v2/imagegen_sentence_redwood10/<id>/prior_agent/`; aggregate evidence is `revision_v2/imagegen_sentence_redwood10/prior_review_summary.json`. Visible coverage spans 0.874–1.000. The 06830 monocular ordinal-depth Spearman is only 0.402, so its later geometry deserves explicit inspection; this diagnostic is not a hard gate because monocular depth on thin parts is uncertain.
- [x] Use all ten approved semantic priors for RMBG transparent Pixal inputs and the four-stage pipeline. Every sample completed Pixal3D, registration, diagnostics, GPT-6 Sol refinement and fusion with 100k final carriers. Frozen offline Redwood 16,384-FPS, seed-6145, ×100 evaluation gives ten-case mean CD-L1 `1.537036` and EMD `2.472180`, versus same-run old mean `1.918897` and `2.935511`; exact rows are in `revision_v2/imagegen_sentence_redwood10/redwood10_metrics.{json,csv}`. The user explicitly authorized replacing all ten old result entries, including regressions; the old entries now point to the unified new sample directories and previous real directories were moved without duplicate bytes under `imagegen_sentence_redwood10/previous_current/`. Full path mapping is `promotion_manifest.json`. The paper-use physical copy was moved to `workspace/redwood10_final/`: all ten complete sample chains (1,705 files, 1,137,603,981 bytes), ten quick-access fused PLYs, metrics, README, and SHA-256 checksum list. Every copied sample file was checked against its source. Qwen/Nunchaku remains an optional backup.
- [ ] Keep Qwen-Image-Edit-2511 and Nunchaku as an optional backup. Their ModelScope assets are installed and Nunchaku was rebuilt against the local Torch ABI; the first 07136 probe hit CUDA OOM while other GPU users were active. Do not let this backup block the approved ten-image Image Gen route.
- [x] Diagnose the Redwood-nine gap against the GenPC paper and the preserved September Redwood baseline. Paper Ours is CD-L1/EMD ×100 `1.74/2.88`; current remaining-nine mean `2.1493/3.2633` is a different nine-sample mean. Under the same local offline FPS protocol, the old Redwood10 baseline is `1.5380/2.4835`. Stage-by-stage offline diagnostic results are in `workspace/agentic_redwood9_fixedcamera_20261103/stage_diagnostic_metrics.json`: 05452, 06830, and 07136 are already poor after registration, while posterior refinement reduces but does not remove their error; 07306 degrades slightly after registration. Current 07136 semantic image shortens a long sofa into a single-seat form, 05452 thickens a thin curved chair, and 07306 resembles drinkware rather than an office waste bin. Positive depth-mask coverage alone missed all three semantic failures.
- [x] Record the user's exact SHA-verified approvals of the earlier 07136 long sofa and 05452 thin curved chair images in `PROJECT_STATE.md`. These are semantic visual references only, with historical unknown generation fields explicit. Do not feed or copy their pixels into a new run; use their failure-mode lessons to improve the general method.
- [x] Add a generic prior review contract for observed visible structure, depth order, category identity, plausible category material and natural construction. Reuse installed MoGe-2 to report ordinal depth agreement on observed pixels; this is no-GT diagnostic evidence, not a metric-based image selector. Targeted tests pass. Keep reference images out of new Image Gen inputs.
- [x] Replace fixed-camera free-form Image Gen prompts with a deterministic composer in `src/prior_generation_agent.py`, fed by the agent's separate observed/completion geometry fields; retain its draft only as provenance. The first v6 wording overconstrained the scan envelope: the user rejected its 07136 sofa as incomplete despite good observed-mask overlap. V7 now treats depth as partial geometric evidence and explicitly requires a complete natural object beyond the scanned mask. Candidate review has a separate whole-object completeness decision. The earlier rejected sofa and bin runs were stopped; do not use their generated images as references. Prompt-text tests pass after this correction.
- [x] Replace the earlier representative-image experiment with the user-approved ten-image short-sentence batch under `revision_v2/imagegen_sentence_redwood10/`. Each `semantic.png` and its exact prompt remain frozen; preparation of all ten saved-camera prior manifests confirms that the code-generated prompt matches the accepted prompt byte-for-byte.
- [x] Run the ten reviewed priors through Pixal3D, fixed camera registration, GPT-6 Sol refinement and fusion. Compare all frozen predictions offline under the same 16,384-FPS protocol, then promote all ten as explicitly authorized. The old 01184 pilot and other previous content remain archived; the September source files were not altered.
- [x] Complete and promote the visually thin 05452 pilot: all four stages verified, CD-L1×100 `2.689835 → 1.445329`, EMD×100 `4.143065 → 2.301014`. The current 05452 path now resolves to the unified `revision_v2/05452` directory; `redwood9_metrics.json` and `.csv` reflect this, and the nine-sample means are `2.010975/3.058645`. Provenance and preservation limits are in `PROJECT_STATE.md`. The pilot image used the earlier v4 free-form prompt, so its gain does not by itself validate the new v6 composer.

## GPT-6 Sol Redwood remaining-nine run (2026-11-03)

- [x] For `05117, 05452, 06127, 06145, 06188, 06830, 07136, 07306, 09639`, use the existing Redwood saved cameras under `workspace/compagent_pixal_reproduction_20260925/redwood/inputs/camera/<id>/`. All nine fixed-camera prompts and accepted image manifests are under `workspace/agentic_redwood9_fixedcamera_20261103/<id>/prior_agent/`; every manifest records the source camera hashes and no GT. The obsolete exploratory view-selection batch was removed after the replacement was prepared.
- [x] Generate and review all nine Image Gen priors against positive observed support and visible pose, including exterior/interior side, opening direction, and the paper's convex/concave viewpoint ambiguity. Require the complete object to look naturally constructed and physically plausible without a rigid category-wide topology rule. The user rejected an unnatural 07306 rim and inconsistent 09639 chair spokes; the revised 07306 round 1 and 09639 round 2 passed agent review, without implied user approval. Each agent-accepted RGB and RMBG transparent RGBA image is frozen in its sample root; all nine hashes and alpha ranges were verified. 05452 has soft-mask maximum alpha 254, so validation checks effective transparency/opacity rather than requiring exactly 255. The earlier 01184 pilot used Pixal's internal RMBG from RGB and is a separate user-approved baseline recorded in `PROJECT_STATE.md`.
- [x] Run Pixal3D, fixed registration, GPT-6 Sol refinement, and fusion for each accepted prior. All nine `four_stage_pipeline.json` manifests report five completed stages, no GT during inference, and `gpt-6-sol`; all Pixal, registered, refined, and fused carriers were verified at exactly 100,000 points. The accepted image hashes and RMBG transparent Pixal inputs were verified. Frozen-output Redwood GT evaluation used 16,384-point FPS, seed 6145, and no GT in agent decisions. The nine per-sample results and mean CD-L1×100 `2.1493`, EMD×100 `3.2633` are in `workspace/agentic_redwood9_fixedcamera_20261103/redwood9_metrics.{json,csv}`. Risks: 06830 visible wheel scale remained wrong after five rejected prior revisions; 07136 and 07306 have relatively high offline CD. These results are an experimental batch, not user-approved baselines.
- [x] Focused no-GT prior diagnostic for 06830: the first frozen result at `workspace/agentic_redwood9_fixedcamera_20261103/06830/` has Camera-1 partial coverage 0.924 after registration, but final overlays show oversized front/rear wheels; offline CD-L1×100 is 3.222 versus the earlier fixed-three control 1.501. Five Image Gen revision candidates were tested against positive support and visible wheel size/position; none passed both, so no revised image entered Pixal3D and the first result remains the honest batch output. Rejected images were removed as requested. The concise decision is at `workspace/agentic_redwood9_fixedcamera_20261103/06830/wheel_scale_diagnostic.json`, with the no-GT overlay in `06830/final_diagnostics/`. Risk: a single fixed-camera image plus Image Gen did not reliably preserve these small observed wheel details.

## GPT-6 Sol four-stage object pipeline pilot (2026-11-03)

- [x] Add an isolated Prior Mining Agent: compare four partial-derived depth views, select Camera-1, write an exact Image Gen prompt, and review each saved candidate against the positive observed-support audit and pose. Keep every prompt, candidate, Codex decision, and camera artifact. For Redwood 01184, the eighth review accepted `prior_agent/round_06/imagegen_candidate.png`; the user rejected an earlier upright candidate. All evidence is under `workspace/agentic_redwood_01184_20261103/prior_agent/`. The user later approved this result, and its available provenance and unknown fields are recorded in `PROJECT_STATE.md`.
- [x] Run the agent-reviewed 01184 image through Pixal3D, fixed Pixal--MoGe--partial registration, four-view diagnostics, GPT-6 Sol geometric refinement, and continuous observation fusion in that order. Every stage exited 0 and its required files exist; Pixal, registered, refined, fused, and textured fused carriers each have exactly 100,000 vertices. The GPT trace used five decisions and stopped with `gpt_accept`; both its trace and the pipeline manifest declare no GT. The final carrier is `workspace/agentic_redwood_01184_20261103/fusion/01184/observation_anchored_fused_100k.ply`, and the complete stage provenance is in `workspace/agentic_redwood_01184_20261103/four_stage_pipeline.json`.
- [x] Run the repository regression suite: 109 passed with the Qwen test excluded, plus Python compilation and `git diff --check`. Render a final no-GT four-view diagnostic under `workspace/agentic_redwood_01184_20261103/final_diagnostics/`; its silhouette retains the slanted body and base in side views. Install `xformers==0.0.29.post2` from the CUDA 12.6 wheel into `genpc` with no dependency changes, and verify a finite CUDA attention output against Torch 2.6.0+cu126. The pilot Pixal stage used SDPA, so the xFormers kernel test is separate. Risks: Image Gen review is agent-accepted but has no user approval yet; only one case was run; the alternate view candidates were generated before the corrected hidden-point filtering and were not selected; the candidate silhouette may differ modestly at sparse boundaries. The experiment is isolated from accepted historical baselines.
- [x] After freezing inference, run the repository's offline GT metric protocol on the fused 01184 carrier: 16,384-point FPS, seed 6145, Redwood GT `data/redwood/gt/01184.ply`. `workspace/agentic_redwood_01184_20261103/offline_gt_evaluation/fused_01184.json` records raw CD-L1 0.0109018926, CD-L2 0.00045841135, EMD 0.0184088424. The GenPC paper/table convention reports CD-L1 and EMD multiplied by 100: 1.09018926 and 1.84088424. The GT remained outside the inference stages. Build the repository EMD CUDA extension into `genpc` for future offline metric runs; no compiled binary is tracked in the repository.

## Recomputed MoGe-to-partial bridges for the 21 inherited bundle gaps (2026-10-31)

- [x] Recompute native Pixal-to-MoGe and MoGe-to-partial bridge for all 21 Custom12/Redwood9 gaps using only the frozen per-sample partial, Camera-1 mask/UV/camera, Pixal ordered 100k prior, Pixal-input FP16 MoGe cache and RMBG model. Outputs are under each case's `03_registration/recomputed_initial/{native,bridge}` in `workspace/gpt_refine_v7_paper_bundle_20261031/`. The frozen registered prior, GPT refine and fusion files were not changed.
- [x] Fox pilot passed a saved-view visual check, 16,183 pixel matches and continuation relative RMSE 1.62e-16. All 21 now pass positive Camera-1 matches (8,191–96,226), proper Sim(3), three ordered 100k bridge/native carrier checks and bridge-to-frozen-prior continuity (maximum relative RMSE 8.34e-16). The recovered continuation matrix is a diagnostic net transform, not the missing historical optimizer trajectory. No GT was read by the bridge computation.
- [x] Add resume-safe `scripts/rebuild_paper_bundle_bridges.py`, `bridge_rebuild_index.json`, per-case `rebuild_manifest.json`, code and RMBG weight hashes, saved commands, logs and paper-bundle `BRIDGE_REBUILD.md`. Verified all 462 new output-file checksums (524,349,279 bytes), 5,488 original sample-file checksums unchanged, no symlinks and 117 repository tests. Exact byte-identical replay of the 21 historical full initial registration chains remains impossible because their intermediate files were not archived; these results are explicitly labelled recomputed.

## GPT v7 paper artifact bundle (2026-10-31)

- [x] Inventory and archive all 53 v7 sample chains at `workspace/gpt_refine_v7_paper_bundle_20261031/`: Custom 12, KITTI 11, Redwood 10, ScanNet 10, Waymo 10. The stage-ordered archive includes partial/depth/semantic/camera, Pixal3D/MoGe, exact historical native/bridge/initial registration for 32 cases, selected registered prior, four-view manifest, accepted GPT trajectory, and fusion. The other 21 inherited Custom/Redwood registration-info files declare historical paths in a removed September work directory; those bridges could not be recovered from agent-probe and are explicitly marked unavailable, not replaced with other experiments. All 53 are complete from registered prior onward.
- [x] Add reusable, checksum-verified, resume-safe `scripts/package_refine_agent_paper.py`, per-sample SHA-256/provenance manifests and `replay_agent.sh`, source-code/config snapshot, root index/CSV, and paper-facing README. Keep GT separate: `offline_gt_evaluation/redwood_custom.{json,csv}` scores all 22 Custom/Redwood cases with deterministic 16,384-point FPS/seed 6145 after inference; GT/fixed-three source files are not copied into the no-GT bundle. Frozen mainline experiment directories were not modified.
- [x] Verify 53 bundles, 5,586 archived files (including 98 code files), 5,044,504,425 sample bytes, every recorded checksum, all required 100k carrier headers, all replay input paths and shell syntax, absence of symlinks, and expected dataset counts. The bundled code entrypoints load successfully; repository suite passes 115 tests. Reproducibility limits: 21 historical initial bridges missing, external model weights/Codex GPT access required, and GPT decisions may vary on replay.

## GPT v7 batch throughput without changing geometry (2026-10-31)

- [x] Profile the ongoing batch. The expensive optional structural route runs a six-round residual-proximal proposal plus graph projection; among the first 23 completed cases it was attempted 21 times but accepted only 3. A single KITTI case spent roughly 2m47s in that route. The batch also processed samples serially. Do not skip the route based on dataset/category: Fox, Hydra, and light helicopter benefited from it.
- [x] Add resume-safe two-worker per-sample scheduling to `scripts/run_agentic_refine_batch.py`, capped at two workers for the 24GB GPU. Each case keeps the identical GPT controller, six-round safety ceiling, structural candidate, verifier, and output schema; only the independent case scheduling changes. Shared `batch_index.json` is written by the parent after each finished case. New scheduler/resume test and full suite pass (112 tests).
- [x] Resume the existing 53-case v7 run with two workers after Redwood 01184 finished. The parallel parent reused completed carriers without rerunning their geometry; observed GPU use stayed within 24 GB. Four cases hit transient Codex/GPT request errors, then succeeded in a one-worker, resume-safe retry. Final refine index: 53/53 complete. Fusion and no-GT audit also completed; the runner and finalizer have exited.

## GPT v7 adaptive-stop all-available-samples run (2026-10-31)

- [x] Replace the fixed three-round ceiling with an explicitly bounded evidence-driven loop: GPT can choose `ACCEPT` at any observation, a hard verifier can reject/stop a route, two consecutive accepted updates with negligible four-view coverage, p90 and p99 gains stop as a plateau, and six rounds is only the safety ceiling. Record the stop reason and per-step progress without GT. The initial v6 batch at `workspace/gpt_refine_v6_all_20261031/` was stopped during the first Fox case before any completed output to avoid mixing strategies; its incomplete files are retained as an audit trail. The v7 policy passes 111 repository tests.
- [x] Run the no-GT GPT v7 refine controller with the opt-in structured proposal on all 53 complete input chains: Custom 12, KITTI 11, Redwood 10, ScanNet 10, Waymo 10. Per-case inputs, labeled boards, decision traces, stop reasons, and ordered 100k carriers are under `workspace/gpt_refine_v7_adaptive_all_20261031/agent/`; accepted mainline outputs were not modified. The 12 older KITTI/Waymo partials without matching priors/manifests remain listed as incomplete inputs, not silently substituted. `agent/batch_index.json` has 53 complete records; `no_gt_batch_audit.json` reports no issues. All 53 carrier files exist with 100,000 vertices. Fox CD-L1 0.01691 and Pig 0.01472 were checked offline after freezing, not used by the agent.
- [x] Run separate accepted continuous observation fusion at `workspace/gpt_refine_v7_adaptive_all_20261031/fusion/`. `fusion/fusion_batch_index.json` has 53 complete records; all 53 fused geometry and 53 Pixal-textured PLYs exist with 100,000 vertices. The 49 previously fused cases were reused and only the four recovered cases recomputed. No-GT audit and terminal process checks passed.

## GPT refine observation and structural-route correction (2026-10-31)

- [x] Make each GPT diagnostic view explicitly separate observed partial projection, complete prior projection, and registered overlay; label colors and camera identity so the model cannot conflate positive observation with unobserved prior geometry. The new four-view board uses blue A=physical partial, red B=complete prior, and C=same-camera overlay, with an explicit warning that red-only is unobserved rather than wrong. Verified on Fox and Pig boards in `workspace/gpt_refine_pilot_20261031/` and covered by `tests/test_gpt_refine_agent.py`.
- [x] Add an opt-in structured geometric proposal route for persistent coherent residuals, reusing the existing residual-proximal/embedded-graph solver from the original registered prior rather than adding a new model or free-form GPT coordinates. Keep the accepted fixed-three and previous GPT outputs unchanged. The agent selects a bounded route; deterministic coverage and integrity checks accept or reject it. A rejected or failed structured solver falls back to observation-field and Camera-1 candidates, as Pig demonstrated in `workspace/gpt_refine_pilot_20261031/domestic_pig/live_v6_fallback/`. The branch remains experimental and is not promoted to mainline.
- [x] Run Fox from the same frozen registered prior, review four-view tail evidence and verify no-GT completeness, then compare frozen Fox/Pig/Redwood controls offline. Fox's GPT v6 carrier has 100k points and offline CD-L1 0.01774 versus v4 0.02382; its separate continuous-fusion output is CD-L1 0.01769. Pig's fallback carrier has 100k points and CD-L1 0.01489 versus v4 0.01516, while CD-L2 is slightly worse. Redwood 06830's v6 carrier has 100k points and CD-L1/CD-L2/EMD 0.01549/0.00131/0.02685 versus v4 0.02332/0.00215/0.04092, but still trails the fixed-three control 0.01501/0.00108/0.02678. Four-view final evidence was visually checked, and the full test suite passes 110 tests. GT was used only after freezing inference. This is an encouraging three-case pilot, not enough to promote the experimental policy to mainline; Redwood's residual gap and the structured candidate's runtime are risks.

## Part-coherent refine and post-refine fusion (2026-10-30)

- [x] Connect the frozen GPT-refine 100k carrier to the accepted continuous
  four-view observation fusion as a separate, resumable stage. Reuse the exact
  partial, camera manifest, and ordered Pixal3D colours; keep unfused and fused
  files distinct and audit all carrier slots. No GT in inference.
  `scripts/fuse_agentic_refine_batch.py` completed all 53 available cases in
  `workspace/gpt_refine_fused_v4_20261030/`: 53/53 fused 100k carriers and
  53/53 ordered Pixal-textured carriers, all active and accepted by the
  original continuous decoder. The source carrier is never overwritten.
  Offline GT evaluation of Redwood10/Custom12 is in
  `redwood_custom_offline_gt.{json,csv}` under that output root. Fusion changes
  Custom mean CD-L1 from 0.01992 to 0.01983 and Redwood from 0.01520 to
  0.01510, with no GT in fusion. The gain is modest and does not repair the
  underlying shape regressions. New GPT batch runs can request this separate
  stage directly with `--fusion-output-root`, with explicit `--fusion-pilot`
  mappings for any previously excluded cases.
- [x] Diagnose no-GT part/structure failures from the existing trace, especially
  Redwood 06830 and Custom Hydra, while keeping Fox/Pig/Seahawk as preservation
  cases. Prototype a simple category-free coherent-region correction using
  partial/visible residual evidence and the existing graph solver, not a new
  semantic model or sample-specific part labels.
  An isolated `scripts/probe_part_coherent_refine.py` experiment uses existing
  Partial OT, coherent residual targets, and a geodesically linked
  positive-component similarity projection (opt-in; default code path
  unchanged). On Hydra, 222 sparse OT seeds formed two coherent moving
  regions (66 and 70 supported samples) after geodesic connection, but the
  protected output improved CD-L1 only 0.01392 -> 0.01383 and still lagged the
  fixed-three baseline 0.01032. On Redwood 06830, the protected output was
  0.02265 vs 0.02332 before and 0.01501 fixed-three; subsequent protected
  rounds plateaued. The raw proposal improves visible fit more but is not
  consistently safe. This hypothesis is therefore *not promoted*.
- [ ] Run same-input before/after and post-fusion tests on representative
  cases, then all Redwood/Custom. Evaluate CD-L1, CD-L2, EMD only after the
  outputs are frozen; reject a proposed policy if it materially regresses
  accepted carriers or damages unobserved completeness.
- [x] Correct a feasible-action failure in the isolated GPT reviewer: the
  final candidate can no longer request `TRY_NEXT_CANDIDATE` when no route
  remains, and review now sees the prior candidates' hard-verifier results.
  This changes only the experimental GPT branch, not the accepted mainline.
  On Redwood 06830, a fresh no-GT run accepted three rounds, reduced the
  visible partial-to-carrier p90 residual 0.02698 -> 0.01058 and increased
  reference coverage 0.90735 -> 0.94022. Frozen offline CD-L1 improved from
  0.02332 (old GPT v4) to 0.01842, but still trails the fixed-three 0.01501.
  The separate continuous post-refine fusion produced CD-L1 0.01826 on the
  same sample. See `workspace/gpt_refine_feasible_review_probe_20261030/`.
  Hydra shows the same feasible-action correction: the last verified field
  candidate is accepted in round three, and offline CD-L1 moves from
  0.01392 to 0.01362, still behind fixed-three 0.01032. Both cases remain
  diagnostic; the candidate policy is not promoted as a general part-aware
  deformation method. The full repository suite passes 109 tests after these
  opt-in changes.

## GPT-driven refine-agent correction (2026-10-30)

- [x] Replace the experimental rule-only decision path with an explicit GPT
  decision backend that sees saved-camera diagnostic images and no-GT geometry
  statistics. Preserve the frozen deterministic experiment as a separate mode;
  never relabel its outputs as GPT results. The opt-in switch is
  `--decision-backend gpt --gpt-model MODEL`.
- [x] Restrict GPT to choosing a bounded action/profile/transport route and
  reviewing solver proposals. Keep Partial OT, PosteriorAdapter, and hard
  topology/coverage checks deterministic; save every GPT decision and image.
- [x] Install the OpenAI Python SDK in `genpc`, pass mocked API tests, and
  render the real Fox four-view observation board at
  `workspace/gpt_refine_pilot_20261030/cartoon_fox/round_01_before_board.png`.
- [x] Use the logged-in Codex CLI with `gpt-6-sol` as the real GPT vision
  decision backend, without an API key. Keep the optional OpenAI API path
  separate. The first live Fox/Pig pilot is saved under
  `workspace/gpt_refine_pilot_20261030/{cartoon_fox,domestic_pig}/live_v1/`.
  Its GPT decisions were genuine, but both cases regressed against the
  deterministic controller and fixed-three controls in offline GT metrics;
  do not promote the first policy or label it a successful result.
- [x] Evaluate the general, non-sample-specific v2 evidence prompt on Pig.
  The model correctly selected a structural update, but incorrectly used all
  synthetic auxiliary cameras as global OT cameras. After three accepted
  rounds, the visible p90 residual fell from 0.02446 to 0.00441 while offline
  CD-L1 remained 0.03781, far worse than the deterministic Camera-1 result
  (0.01513). The no-GT coverage verifier alone did not catch this regression.
  Output: `workspace/gpt_refine_pilot_20261030/domestic_pig/live_v2/`.
- [x] Test the v3 model prompt that distinguishes the physically calibrated
  Camera-1 transport from synthetic orbit-view diagnosis/assimilation. Pig
  completed with CD-L1/CD-L2/EMD 0.01541/0.000834/0.01992, versus deterministic
  0.01513/0.000885/0.01951. Fox remained worse (0.02620/0.00372/0.03064
  versus deterministic 0.02382/0.00332/0.02774). Both live outputs and
  offline-only metric JSONs are under
  `workspace/gpt_refine_pilot_20261030/{domestic_pig,cartoon_fox}/`.
- [x] Evaluate v4 view-option evidence on Fox/Pig. The v3 Fox GPT plan
  temporarily switched from adaptive orbit to saved four views during round
  two without being shown that the latter see only 82.1% of partial points,
  versus 87.3% for adaptive orbit. The v4 prompt provides these no-GT
  visibility statistics before the discrete GPT decision. Fox completed three
  GPT-selected/reviewed Camera-1 + adaptive-orbit rounds and produced an
  identical carrier to the old deterministic result (CD-L1/CD-L2
  0.02382/0.00332). Pig completed one structural and two observed-local rounds
  (0.01516/0.000825), near the deterministic 0.01513/0.000885. Outputs and
  offline metrics are in `workspace/gpt_refine_pilot_20261030/`.
- [x] Test v4 on Seahawk and Redwood 01184. Seahawk's GPT-selected three-round
  carrier is byte-identical to the prior deterministic result. Redwood 01184
  completed after one transient SIGTERM/retry: CD-L1/CD-L2/EMD
  0.01111/0.000504/0.01995 vs deterministic 0.01102/0.000522/0.02003.
  The first interrupted Redwood directory has no final trace and must not be
  interpreted as an output; the successful one is `live_v4_retry`.
- [x] Run the remaining 49 complete input chains through the genuine GPT v4
  backend in `workspace/gpt_refine_cross_dataset_v4_20261030/`. The four
  pilot cases are excluded from repeat inference, and 12 older source
  candidates missing a registered prior or saved manifest remain listed as
  incomplete (not silently substituted). Batch index is resume-safe and
  records backend, model, provider and prompt version. Then audit outputs and
  evaluate Redwood/Custom offline against GT; do not use GT in the agent.
  The batch was started with `gpt-6-sol` through Codex login; its progress
  and any failures are in `batch_index.json` under the output root. An
  interrupted sample may have intermediate PLYs without a final trace; only
  `status=completed` or `completed_existing` is a verified batch result.
  All 49 completed after one transient Codex exit-code-1 failure on ScanNet
  `bed__scene0178_00_14` was retried with the same configuration. The 49
  outputs passed the final 100k-carrier/trace audit with zero issues in
  `no_gt_batch_audit.json`. The four v4 development cases were reused, giving
  53 complete chains. Offline GT comparison covered all 22 Redwood/Custom
  cases in `redwood_custom_offline_gt.{json,csv}`. Custom mean CD-L1/CD-L2/EMD
  was 0.01992/0.00315/0.02628 versus fixed-three
  0.02135/0.00405/0.02629; Redwood was 0.01520/0.00105/0.02523 versus
  fixed-three 0.01473/0.00099/0.02412. Redwood 06830 (+55% CD-L1 versus
  fixed-three), Custom Hydra (+35%), and Custom single-engine airplane
  (+14%) are material regressions. Do not promote this GPT policy to mainline
  on the basis of these results; the no-GT verifier can reject deformations
  that improve complete-shape GT quality.

## Cross-dataset isolated refine-agent evaluation (2026-10-30)

- [x] Audit the frozen post-registration input chains. Available complete
  chains: Redwood 10, Custom 12, ScanNet/ScanSalon 10, KITTI 11, Waymo 10.
  The three previously tested objects are excluded from repeat inference.
  KITTI prefers the newer style rerun when present, then the earlier pilot.
  Missing older KITTI/Waymo candidates without a registered prior or saved
  multiview manifest are listed in the batch index, not silently substituted.
- [x] Run the no-GT refine agent on the remaining 50 samples under
  `workspace/agentic_refine_cross_dataset_20261030/`, with one trace and
  ordered 100k final carrier per case. This is post-registration refinement;
  it does not rerun semantic generation or fusion. All 50 completed and passed
  the carrier/trace audit (`no_gt_batch_audit.json`); the earlier three
  development cases remain under `workspace/agentic_posterior_20261028/`.
- [x] Run same-input fixed-three controls on Redwood and Custom, then evaluate
  CD-L1, CD-L2 and EMD offline against GT. ScanNet, KITTI and Waymo are
  reported with no-reference observations because matched complete GT was not
  established. All 22 controls and offline GT evaluations completed; outputs
  are `fixed_three_controls/` and `redwood_custom_offline_gt.{json,csv}`.
- [x] Check all outputs, failures, view counts and regression cases before
  deciding whether any agent policy should be promoted. Keep mainline intact.
  The no-GT agent's Custom mean CD-L1/CD-L2 is 0.01995/0.00317 versus fixed
  0.02135/0.00405, but Redwood is 0.01488/0.00101 versus fixed
  0.01473/0.00099. Custom Hydra (+32% CD-L1), Custom single-engine airplane
  (+14%), and Redwood 06830 (+20%) regress despite passing the no-GT partial
  coverage verifier; the latter's visual projections show close partial
  alignment, illustrating that observed-fit gain alone is insufficient to
  guarantee complete-shape quality. No promotion to the released mainline.

## Isolated post-registration agentic refinement experiment (2026-10-28)

- [x] Create independent `codex/agentic-posterior-loop` worktree from the
  committed probe baseline. Read frozen registered priors, partials and saved
  cameras from the original reproduction package without writing there.
- [x] Add a bounded, category-free observe/decide/act controller around the
  existing Partial OT and PosteriorAdapter. It audits four saved views and
  directed 3-D residual, greedily selects 2–6 active orbit views by incremental
  physical-partial visibility, and routes between full transport and the
  existing local observation field. The verifier checks graph integrity,
  per-view partial coverage, and cumulative reference-prior coverage. The
  latter has a separate 0.85 floor so a coherently moved part is not rejected
  solely for leaving its *old* location. This executable prototype uses a
  deterministic policy because no text-model API credential is available.
- [x] Compare Redwood 01184, Custom domestic pig and Seahawk with the fixed
  three-round mainline from the same registered prior. Frozen 100k carriers,
  decision traces, four-view review images and *offline-only* GT evaluations
  are under `workspace/agentic_posterior_20261028/`. Final agent outputs are
  `final_{redwood_01184,domestic_pig,seahawk_helicopter}/agent_selected_posterior_100k.ply`.
- [x] Record benefits and regressions. Pig and Redwood 01184 improve CD-L1,
  CD-L2 and EMD over fixed three rounds; Seahawk is nearly tied but slightly
  worse (CD-L1 0.01552 vs 0.01548). All decisions use only the registered
  prior, partial, saved camera and multiview evidence. GT is imported only by
  `scripts/evaluate_agentic_refine.py` after inference. These three development
  cases do not establish held-out generalization; keep the branch experimental
  and leave the released mainline unchanged.

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
