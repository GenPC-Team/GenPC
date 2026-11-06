# Active plan

## 2026-11-06 — accepted Astra archive and source push (complete)

- Completed: packaged all 156 accepted cases and intermediate evidence in workspace/astra_final.
  141,796 copied files (49,297,122,787 bytes) passed independent SHA-256 checks.
  Removed the other 13 workspace experiment directories only after verification;
  no old baseline archive was retained, as requested. Cleanup manifest is in the archive.
  50 targeted tests and post-cleanup archive-only preparation passed.
- Preserve historical absolute-path provenance and verify file hashes.
- Completed source review, documentation and targeted tests. Commit 71a6b74
  was pushed to origin/codex/gpt-refine-v7-20261031 as Tumb1eweed.
  Large artifacts remain local; archive method/source contains the code snapshot.


## 2026-11-06 — five-dataset goal complete

- All 156 requested cases finalized, verified and evaluated: Redwood10,
  Custom10, KITTI20, Waymo76, Aircraft40. All ten budget continuations completed.
- Final report: workspace/refinement_updated/RESULTS.md.
- Completion evidence: workspace/refinement_updated/completion_audit.json and
  artifact_verification.json (full --require-complete passed).
- All stage outputs and per-case metrics are grouped under each dataset.
- Current defaults are Astra low; historical medium records are preserved.
  Mixed settings and combined method changes prevent an Astra-only claim.
- KITTI/Waymo lack matched complete GT; their reported scores are observed
  support only. Individual regressions and unresolved residuals are retained.


## 2026-11-06 — goal extended to Redwood

- Add a fresh autonomous Astra-low Redwood run without modifying accepted
  Redwood10 outputs. User confirmed the ten packaged baselines; exclude the
  three additional raw partials. Total scope is 156 cases across five datasets.
- Use the same 64-round maximum and GT-only offline evaluation.
- Outputs: workspace/refinement_updated/redwood/<sample>/.
- Scheduling: rebalance_redwood.py waits for Aircraft GPU 1/2/3 workers
  to finish, drains the current Redwood child, then runs remaining cases on
  GPU 1/2/3/4. It checks ownership and finalized reports before handoff.
- All ten baselines prepared; suite_redwood.json launched on GPU 4 with
  64 rounds and Astra low. Log: /tmp/updated_redwood.log.


## 2026-11-06 — requested reasoning setting change

- New prior/refinement processes use gpt-6-astra with low effort (Codex
  Light tier). Both Codex transport and direct refinement API are updated.
- Already running Python workers retain medium until their current case ends;
  subsequent workers and budget continuations load low. Historical decision
  metadata is preserved. Dataset summaries derive efforts from saved decisions.
- Validation: prior/refinement transport tests passed (23 tests); CLI calls
  explicitly request model_reasoning_effort=low and API requests effort=low.
- First new Waymo worker has saved a low-effort plan for
  PEDESTRIAN_1002394760240072_1552440207862641_A4kzX4tBck4XcFuUOPA6Lg;
  live transition is verified in refinement/round_01/plan.json.
- The dataset experiment therefore spans medium and low settings; it is not
  a controlled effort ablation. Accepted prior audits remain valid.


## Full updated-route run: Custom, KITTI, Waymo, Aircraft (2026-11-06, active)

- User set the explicit goal to finish all four datasets with the updated
  method: Custom 10, KITTI 20, Waymo 76, Aircraft 40 (146 current inputs).
  Custom/Aircraft reuse saved upstream assets with original provenance.
- Updated scope: KITTI/Waymo require a fresh Astra-medium prior audit because
  some selected views are poor and some RGB/depth pairs are vertically
  reversed. Improve shared view/orientation verification, audit all 96 cases,
  regenerate/reselect failed cases, then rerun downstream geometry wherever
  prior/camera changed. Do not launch their refinement from stale priors.
- Apply the shared autonomous refinement policy with Astra medium and up to
  32 total rounds, then the continuous observation fusion stage. Retain all
  per-stage outputs grouped by dataset and sample, including colored overlays.
- Custom and Aircraft have matched GT for frozen offline evaluation. KITTI and
  Waymo have no matched complete object GT here: report no-GT diagnostics and
  completion counts without inventing CD/EMD. GT must not affect decisions.
- Visual inference resumed successfully after transport recovery; the full
  dataset queues are active. Dataset completion and final metrics are pending.
- Queue and consolidated outputs: `workspace/refinement_updated/{custom,kitti,waymo,aircraft}/<sample>/`.
  `scripts/run_updated_dataset_suite.py` copies upstream stages, resumes the
  shared refinement, executes the existing four-view continuous fusion and
  verifies 100,000-point outputs. Fox's finished autonomous trace and fusion
  have been imported; the Custom/Aircraft queue handles the other 49 cases.
- `prior_mining_v24_image_plane_orientation` adds explicit signed image-plane
  landmark ordering to interpretation/review and independently checks saved
  priors against alternative depth boards. Prior tests: 11 passed, including
  rejection of upside-down RGB despite perfect mask coverage. Astra audits of
  all 20 KITTI and 76 Waymo cases are running in `*_prior_audit/`. Geometry
  dispatch requires a fresh keep verdict or a newly accepted repaired prior.
- KITTI exporter verification found that its local clouds retain camera Y
  downward while synthetic camera rendering assumed +Y up. Added a general
  explicit `--world-up` camera option; KITTI uses documented `[0,-1,0]`, with
  depth/UV/mask/camera regenerated together. Default and fixed cameras retain
  their conventions. All 20 KITTI priors will be regenerated/reviewed with this
  corrected camera policy; Waymo's unknown coordinate convention is not guessed.
  Camera-axis + prior tests: 14 passed. Original KITTI audit finished: 15 keep,
  4 regenerate, 1 uncertain; one explicit top/bottom reversal was identified.
- First corrected KITTI prior (`frame_000153_pedestrian_0`) passed Astra review;
  Pixal/MoGe/registration is running. First Waymo repair was rejected for
  near/far reversal, then its second generated candidate passed. A legacy
  prompt-length truncation could cut English directional phrases mid-sentence;
  removed character slicing in favor of concise Chinese hints and same-model
  semantic compaction when necessary. Raw interpretations are retained before
  formatting, so failed formatting no longer loses the model result.
- Fox autonomous run stopped at round 22 with explicitly unresolved tail/rear
  correspondence, then completed continuous fusion. Consolidated case:
  `workspace/refinement_updated/custom/cartoon_fox/`. Frozen offline CD-L1 x100 /
  EMD x100 (three repeats): old fusion 2.336866 / 2.465049; new refinement
  1.917369 / 2.779507; new fusion 1.913367 / 2.751561. CD improved, EMD regressed;
  do not claim uniform gains. This offline result is not fed to active agents.

- Synthetic candidate cameras now use the observed bounding center and FOV-derived
  distance instead of a fixed metric distance around the coordinate origin.
  Angular diversity is center-relative. Astra receives signed camera elevation
  when physical up is documented. Fifteen prior/camera tests passed, including
  scale/translation equivariance and upside-down prior rejection. Unaccepted
  poor-camera cases are being refreshed with archived provenance; accepted
  priors remain unchanged. Dataset-wide results remain pending.
- Same-view prior repair now carries the independent machine audit's suspected
  mismatch and uncertainty into depth interpretation for rechecking. It is
  explicitly separated from human feedback and never reused after a camera
  change. Existing generated prompts retain their exact provenance.

- Waymo independent audit finished all 76: 65 retained and 11 regenerate.
  Failed priors are being rebuilt; none is dispatched using its rejected RGB.
  KITTI has 20 new camera tasks, with 14 semantic priors accepted so far.
- Custom domestic_pig (23 rounds) and dragon_character (26 rounds) completed
  refinement and 100k fusion. Both explicitly retain unresolved appendage
  correspondence issues; they are finalized runs, not claims of perfect fit.
  Offline frozen evaluation is running separately. Shared prior/camera tests
  now pass 16 tests, including machine-versus-human feedback separation.

- Frozen offline results for the next two Custom cases are mixed: pig old/new
  final CD/EMD x100 = 2.749922/2.956048 -> 2.708269/2.979379; dragon =
  2.429804/3.825285 -> 2.926682/4.392943. These scores are recorded only in
  offline evaluation and never sent to inference/checkpoint selection.

- All 11 Waymo replacement priors passed review; all 65 retained cases have
  been dispatched exactly once across three manifests. KITTI has 19 accepted
  priors. One candidate repeatedly failed regional support despite an independent
  whole-object keep verdict: preserve that disagreement and explore another
  ranked view through Astra, without overriding the failed regional gate.
  `reselect` now archives previous camera/prompts/reviews and receives camera
  geometry plus the reason for the failed attempt.
- 2026-11-05 20:49 UTC: verified 5 Custom, 1 KITTI and 4 Waymo completion
  receipts; remaining queues use the same 32-round ceiling. Dependency
  receipts `queue_geometry.json` and `queue_remaining.json` defer remaining
  KITTI geometry and the 29 rebuilt-prior cases until prerequisites finish.
  Five-case frozen Custom mean old/new final CD/EMD x100 is
  2.135925/3.039933 -> 2.097145/3.181095. This partial report is offline only,
  with mixed per-case effects; full-dataset conclusions remain pending.
- All 20 refreshed KITTI priors and all 11 Waymo replacements now pass Astra
  medium review. `workspace/refinement_updated/validated_rebuilt_priors.json`
  verifies acceptance, orientation, source/installed/Pixal hashes, transparent
  RGBA input and equal depth/RGB canvas sizes for all 31. The final KITTI case
  passed after autonomous view reselection and two feedback revisions; no
  failed regional gate was overridden. Remaining geometry/refinement is pending.
- Remaining KITTI geometry now runs on free GPU 0 while Waymo geometry uses
  GPU 1. Found and fixed a resume-only issue: completed stage caches can be
  reused when only the dispatch GPU index changes, retaining their original
  recorded device. Backend/source changes or missing outputs still reject
  reuse. Five focused stage tests pass. The dependency queue retries the first
  already-complete KITTI stage rejected before this fix; inference outputs
  are unchanged and all receipts must succeed before remaining dispatch.
- The real completed KITTI stage successfully reused all three geometry
  stages on GPU 0 after the cache fix. `verify_artifacts.py` in the experiment
  root independently checked 6 Custom, 2 KITTI and 5 Waymo completed cases:
  finite 100k carriers, frozen hashes, exact red-carrier/blue-partial overlay
  coordinates and colors, original registration/partial, six-view autonomous
  Astra-medium decision provenance, stage directories and LiDAR prior gates.
  `artifact_verification.json` lists all 146 expected inputs and marks the
  others pending. Remaining dispatch now starts already-verified geometry
  cases on GPUs 1/4 before waiting for the last KITTI rebuilds, with disjoint
  ready/deferred sample lists and unchanged inference settings.
- All 11 Waymo repaired-prior geometry chains completed. The ready refinement
  batch is live on GPUs 1/4 with 7 KITTI + 11 Waymo cases; 11 KITTI cases remain
  in its disjoint deferred list. Main manifests account for the other 117
  cases, giving the full 146-input scope without duplicate dispatch.
- Offline evaluation now also writes `observed_support.{json,csv}` for
  KITTI/Waymo: mean and 95th-percentile one-way observed-to-carrier distance,
  normalized by the observed bounding-box diagonal, with old/new stage hashes.
  This is explicitly not full-shape CD/EMD or unobserved-quality evidence.
  The first 2 KITTI and 6 Waymo completed cases evaluated successfully; no
  inference prompt or selection uses these offline reports.
- The seventh completed Custom case, mirrorless_camera, regressed offline:
  old/new fused CD/EMD x100 = 3.464327/3.679289 -> 4.511006/4.316076.
  Seven-case means are now 2.329605/3.082755 -> 2.262056/3.131537.
  Keep the full frozen cohort, including regressions; do not use these scores
  to select inference checkpoints or change the in-progress method.
- Runtime trace inspection found one 32-round Waymo budget stop with an
  actionable roof residual and a completion-audit REASSESS verdict. Its agent
  could not see the actual numerical rejection reason: the compact summary
  omitted mean-distance improvement and connectivity fields. Expose existing
  gate checks, criteria and numeric evidence in new requests, recording
  `numerical_rejection_v1` and its starting round. This changes feedback
  serialization, not solver thresholds or acceptance rules. Earlier histories
  keep their original metadata. Arrange a common 64-total-round continuation
  for budget-stopped runs, preserving their 32-round checkpoint and offline
  evaluation, without using GT to decide eligibility. This continuation is
  pending dispatch after geometry frees GPU 0.
- Nine evidence tests pass. The first budget-stop case has 46 historical
  numerical rejections recoverable from its saved solver JSON; resume restores
  these omitted measurements without changing past decisions or geometry.
  `workspace/refinement_updated/run_budget_continuations.py` is live, waiting
  for GPU-0 geometry completion, then checks all four datasets for budget
  exhaustion below 64 total rounds. Each eligible run archives its old
  checkpoint, method, fusion, completion and metrics before resuming; GT is
  not an eligibility input. Receipt: `budget_continuations.json`.
- `comparison_protocol.json` verifies identical old/new input-partial hashes
  for all 146 cases and records each baseline trace: all use GPT-6 Sol.
  The updated experiment changes controller/actions/budget as well as model,
  and changes KITTI plus 11 Waymo priors. Therefore report full-route effects,
  not an isolated Astra-versus-Sol causal ablation. Nine Custom, four KITTI
  and eight Waymo outputs passed the artifact audit; Aircraft inference has
  started. Full evaluation and budget continuations remain pending.
- [x] Custom10 first tranche: all ten 100k results passed the artifact audit.
  Frozen first-pass table and hashes are in
  `workspace/refinement_updated/offline_evaluation/custom10_first_pass.{csv,json}`.
  Old/new final CD/EMD x100 means: 2.007229/2.754905 -> 1.893382/2.712598;
  CD improves in 6/10 and EMD in 5/10 cases. Wolf stopped on the 32-round
  budget and remains queued for continuation; this is not a final full-goal
  completion claim. Aircraft inference is now running on both Custom-freed GPUs.
- Added an experiment-root `README.md` with stage paths, point-count/color
  meanings, evaluation scope and continuation records. The archive audit found
  that nested source provenance had not been copied by the consolidation
  helper. The runner now retains it under `provenance/upstream/`; all 50
  prepared Custom/Aircraft cases were backfilled and hash-verified in
  `upstream_provenance_copy_audit.json`. Artifact verification now checks these
  original pipeline/finalization records as well as the geometric outputs.
- Aircraft's first case (`J-15_view00`) completed and passed the same artifact
  and offline evaluation protocol. Old/new fused CD/EMD x100:
  1.396145/2.505877 -> 1.311500/2.352304. This is one case, not a dataset claim.
- Queue scheduling follow-up: the original 39-case Waymo keep batch is longer
  than its 18- and 8-case peers. When a shorter queue frees a GPU, redistribute
  unfinished cases after letting the current child finish; preserve active
  inference and existing completion/continuation records. No rebalance has
  been performed yet.
- [x] All 31 rebuilt-prior geometry chains are complete and verified in
  `validated_rebuilt_geometry.json`: 20 KITTI + 11 Waymo, input fingerprints,
  nonempty stage outputs and 100k carriers. The cached-GPU recovery finished
  successfully. The common 64-round continuation queue is now live on GPU 0,
  starting with wolf at round 33. Its 32-round selected/fused hashes and
  archived metrics were verified under `custom/wolf/budget_tranches/round_32/`.
- [x] Custom10 final evaluation for this experiment is complete. Wolf accepted
  one further update at round 33 and stopped after independent review at round
  35, with paw/hidden-surface uncertainty still explicit. Final dataset files:
  `workspace/refinement_updated/custom/metrics.csv` and `custom/summary.json`.
  Old/new fused CD/EMD x100 means: 2.007229/2.754905 -> 1.892556/2.712018;
  CD improves in 6/10, EMD in 5/10 cases. All ten finalized carriers and their
  provenance passed the artifact audit. Other datasets and their extensions
  remain active; the four-dataset objective is not complete.
- 2026-11-05 21:58 UTC artifact audit: Custom 10, KITTI 8, Waymo 14,
  Aircraft 2 verified; 112 inputs remain pending. The first Waymo CAR budget
  extension finished at round 34 with unresolved residuals explicitly retained,
  rather than claiming geometric convergence. Its original round-32 outputs
  remain under `budget_tranches/round_32/`. The continuation watcher and all
  dataset queues remain active; refreshed offline evaluation is running.
- 2026-11-05 22:02 UTC: Aircraft now has three verified/evaluated cases;
  current complete scope is 35/146 (Custom 10, KITTI 8, Waymo 14, Aircraft 3).
  `offline_evaluation/summary.json` records the matching partial report.
  Newly completed samples' final red/blue overlay links were backfilled into
  `artifacts.json`; the original seven dataset workers and budget watcher
  remain live. No whole-dataset Aircraft improvement is claimed yet.
- Added `scripts/summarize_updated_dataset_suite.py` to export dataset-local
  CSV/JSON tables from frozen offline evaluations, with expected counts,
  budget-extension status, selected/accepted action counts, and explicit
  no-GT limitations for KITTI/Waymo. It excludes withdrawn/replaced runs by
  completion hash and round count. Current tables cover 10/8/14/3 cases;
  Custom means agree with the previous complete table.
- Started experiment-only `workspace/refinement_updated/rebalance_waymo.py`
  (`queue_waymo_rebalance.json`). After the eight-case GPU-7 batch succeeds,
  it suspends only the long GPU-5 scheduling parent, lets its active child
  finish, then assigns the unfinished long-batch cases to GPUs 5 and 7.
  Completed and budget-continuation cases are excluded; unexpected live or
  unfinalized case ownership fails visibly. Original manifests/rounds remain
  intact. This changes scheduling only, not prompts, budgets or geometry.
- KITTI finished 20/20 with verified artifacts and frozen observed-support
  evaluation. Its final 11-case queue succeeded. Aircraft handoff finished draining
  its workers; old scheduling parent 2806524 was replaced by 1540665.
  `suite_aircraft_rebalanced.json` owns the remaining 21-case tranche,
  including fusion of the two drained cases. Four workers use GPUs 1/2/3/4.
  `suite.json` retains an explicit handoff link; do not restart the old queue.
- Aircraft scheduling handoff: `workspace/refinement_updated/rebalance_aircraft.py`
  waits for the remaining KITTI batch to finish successfully, drains the two
  current Aircraft workers, then assigns all unfinished Aircraft cases to
  GPUs 1/2/3/4. It excludes completed and budget-continuation cases and checks
  for conflicting ownership. No inference settings or method changes.
- Waymo 18-case GPU-6 batch completed successfully (`suite_waymo_second.json`).
  Parent 3064218 exited normally; remaining Waymo work belongs to the
  rebalanced queue on GPUs 5/7. GPU 6 is now available.
- Aircraft J-36_view03 reached the initial 32-round budget and automatically
  resumed under the shared 64-round policy and finished at round 43.
  Round-32 artifacts remain archived; extended fusion and frozen offline
  evaluation are complete. Uncertain terminal correspondences remain explicit.
- Aircraft J-36_view08 reached the 32-round budget and automatically resumed
  under the shared 64-round policy; round 33 is running. Round-32 outputs
  are archived, and its current completion receipt is withdrawn until finish.
- Final verified/evaluated scope is 156/156: Redwood 10, Custom 10, KITTI 20,
  Waymo 76, Aircraft 40. Budget continuations can temporarily withdraw receipts;
  dataset-local tables filter to currently finalized evaluated cases. Dataset-local tables include all current finalized cases.
  All active inference children advanced; no failed job was found.
- The eight-case Waymo GPU-7 batch finished successfully. Rebalancer PID
  1295347 let child 2621543 finish, then replaced scheduling parent 2925798.
  New parent 3071275 runs the remaining 31-case tranche on GPUs 5/7 using
  `suite_waymo_rebalanced.json` (including fusion of the drained case).
  All original 39 cases are accounted for by finalized receipts, preserved
  budget tranches or this new queue. `suite_waymo_first.json` retains its old
  results plus an explicit handoff link; its incomplete batch count is not
  a failed or missing run. Do not restart the old parent.
- The 18-case ready-prior batch finished successfully. Dispatcher 3854296
  started the remaining 11 KITTI cases on GPUs 1/4, suite parent PID 3018278,
  manifest `suite_lidar_remaining.json`. The original 3895312 ready-batch
  parent has finished; it should not be restarted.
- Waymo `CAR_1006130543087548_1552933157019682_f_z2h8bug3T2gY5LSZkElQ`
  exhausted 32 rounds and automatically entered the common 64-round extension.
  Its round-32 selected/fused archive hashes were verified. This case is not
  counted as finalized while its extension ran. It has now stopped after
  independent review at round 34 with terminal-panel/roof-corner uncertainty
  retained; its new fusion and provenance passed the artifact audit and are
  included in the current 23-case Waymo offline support table.
- Aircraft `J-15_view09` exhausted the 32-round budget and completed the shared
  extension at round 47 after independent review, retaining rear-shape
  uncertainty. Original selected/fused hashes were verified under
  `aircraft/J-15_view09/budget_tranches/round_32/`. New fusion/provenance passed
  verification and entered the current Aircraft table. Old/new final CD/EMD
  x100: 2.131895/3.751948 -> 1.494855/2.870346. No GT or score was used for
  extension eligibility, decisions or stopping.

## Autonomous semantic refinement and Custom transfer (2026-11-05, active)

- User approved the final fox local correction and red/blue overlay. Exact
  copies, complete prompts and provenance are in
  `workspace/semantic_refinement_astra/custom10/cartoon_fox/approved_local_round02/`.
  Preserve this human-assisted reference; approval does not prove autonomy.
- Consolidate the shared planning contract and add an autonomous entrypoint:
  no user feedback, annotation, previous plan or approved intermediate carrier.
  Start from each case's archived fixed-registration result. Use partial-only
  residual inspection crops, a whole-object mismatch inventory, paired part
  windows, fixed-slot support review and explicit evidence-based stopping.
- User explicitly confirms that discovering and correcting residuals never
  mentioned by a human is desirable. Judge them by observed support, semantic
  correspondence and structural effects; do not restrict work to known hints.
- Keep proper Sim(3) available only as an agent-selected remedy for a common
  global pose offset; record its selection/acceptance instead of assuming
  contribution. Fox's three recent branches selected it zero times.
- Validate on fox from registration and three other Custom cases representing
  different structures: wolf, handheld power drill, single-engine airplane.
  Same policy, model (Astra medium), cameras and budget; no case-specific
  feedback, GT or metric-driven selection. Store under one dataset directory.
- Freeze decisions before offline CD/EMD evaluation. Report both gains and
  regressions, action use and unresolved issues. Further transfer is pending;
  do not claim the process is fully validated based on the accepted fox alone.
- Initial v9 transfer found a generic hidden limitation: the drill's valid
  housing selection contained 46,834/100,000 points, so the old 40% part and
  45% affected-point quotas rejected it before solving. Removed both quotas;
  retain nonempty supported part/external carrier, attachment transitions,
  observed regression, connectivity and structural review. Added rigid/RBF
  regression tests for a component occupying more than half the carrier.
  Interrupted v9 before acceptance; diagnostics retained separately. All four
  v10 runs restart from registration with no previous plans or human hints.
- The first eight-round tranche still lists actionable residuals. Continue
  eligible runs from their own automatic state to a shared 32-round ceiling (user explicitly authorized a larger budget),
  with the same fixed initial reference and no human/GT feedback. A budget stop
  is not convergence. Original commands plus continuation commands are retained.
- Four concurrent model requests later exceeded the previous 300-second
  subprocess timeout. Preserve pre-recovery code/checkpoints under each case's
  `transport_interruptions/attempt_01/`, and record the interruption in
  `transport_recovery.json`. Transport now retries timeouts (three attempts,
  600 seconds each, configurable), discarding incomplete answers. Geometry,
  prompts, model and reasoning policy remain unchanged. Eleven controller tests
  pass, including bounded retry and stale-answer rejection. An interrupted
  wolf review is explicitly unreviewed, not a rejected or accepted candidate.
- 2026-11-06 (Asia/Shanghai): all four first recovery attempts exhausted
  model timeout retries. They are interrupted runs, not converged results;
  preserve their checkpoints under `transport_interruptions/attempt_02/`.
  A fresh Astra-medium text probe succeeded; resume actual visual inference
  before drawing conclusions about transport recovery. Offline evaluation
  excludes interrupted statuses even if an older tranche left `artifacts.json`.

## Same-part correspondence (2026-11-05, local candidate verified)

- User approved `joint_refinement_run/round_05/after_0.png` overall, except
  the SAME remaining foot indicated in views 2 and 5. Exact point cloud,
  images, full prompts, solver parameters and user annotations are frozen in
  `workspace/semantic_refinement_astra/custom10/cartoon_fox/approved_joint_round05/`.
  PROJECT_STATE.md records full approval provenance. No geometric freezing.
- Add generic paired source/target part windows in two matching views. Lifted
  controls must reproject into both the prior and observed windows, so a
  landmark on an adjacent part cannot silently satisfy only the source check.
- Accept optional user feedback images as experimental correspondence hints;
  infer fresh coordinates from current paired grids. No sample coordinates,
  foot rules or category branches enter the implementation.
- New continuation: `.../cartoon_fox/local_correspondence_run/`, starts from
  the user-approved round-05 checkpoint. Annotation-guided human-assisted
  diagnostic, with GPT-6 Astra medium and the same generic six-view policy.
  Semantic tests: 8 passed, including rejection of an inconsistent target part.
- Round 2 accepted a local RBF correction after round 1 failed cross-view
  correspondence validation. Added a fixed-slot same-part support audit and
  two-view before/after crops (`part_specific_review_v8`) so a neighbouring
  surface cannot substitute for the intended part. Evidence tests: 6 passed,
  including a distractor surface coincident with the scan. Round-2 posthoc
  audit is explicitly separate from its original v7 acceptance evidence.
- Four-round continuation completed: round 1 failed correspondence validation;
  round 2 accepted; both reviewed candidates in rounds 3 and 4 rejected.
  `local_correspondence_run/selected_100k.ply` is exactly the accepted round-2
  hash. Independent posthoc review with fixed-slot part evidence accepted it.
  Same-part 3D mean: 0.027727 -> 0.007575; one view-local regression remains.
- Frozen offline CD-L1 x100 / EMD x100: approved baseline 2.559833 / 3.189849;
  candidate 2.311149 / 2.785310. No GT selection, final fusion or mainline
  promotion. User subsequently approved this local round-02 result and its
  colored overlay; it is frozen under `approved_local_round02/`. The earlier
  approved round 05 is unchanged.
  Summary and comparison paths are indexed in the sample's `artifacts.json`.
  Combined semantic/evidence tests: 14 passed. This is annotation-assisted
  local validation, not cross-dataset efficacy evidence.
- Joint rounds 6/7 remain automatic diagnostic candidates, not user-approved
  replacements for the chosen visual reference. Frozen offline scores never
  choose the branch or its landmarks.

## Remove unjustified hard stretch ratios (2026-11-05, active)

- User correctly rejected a universal edge-length-ratio validity limit.
  Removed p01 > 0.6 / p99 < 1.5 from both semantic experiment runners and
  the cumulative audit. Per-step and fixed-rest strain remain review evidence;
  no replacement hard strain ratio is introduced.
- Propagate `enforce_edge_strain_limits=False` through experimental continuous
  fusion and PosteriorAdapter, including embedded and node-level ARAP solvers.
  Their connectivity check now uses candidate geometry rather than deleting
  rest edges above a stretch ratio. Legacy defaults reproduce old baselines.
  Backend/evidence/fusion/module tests: 11 passed, including a supported 1.7x
  expansion passing both nested solvers despite legacy strain-limit values.
- Finite ordered geometry, explicit constraints only when actually requested,
  observed regional support, connectivity, available fold diagnostics, and
  grounded multi-view structural review determine candidate acceptance.
- `joint_refinement_run/` completed through round 7 with policy
  `strain_diagnostic_v6_backend`; user chose round 5 visually as the next local
  experiment's baseline. Old policy rejections do not exhaust a tool under
  the corrected policy. Historical records remain unchanged.
- Source snapshots and full prompts for the revision are stored beside the
  same run. New tests check that both >1.5 expansion and <0.6 compression are
  reported without automatic rejection. Whole-object naturalness still needs
  semantic/structural evidence and cannot be inferred from passing this audit.

## Approval clarification and joint refinement (2026-11-05, active)

- User clarified that an approved region may still improve. Approval is an
  archived comparison baseline, not an instruction to lock coordinates.
  The earlier 8,762-slot tail freeze was an assistant interpretation, now revoked.
- Stop the locked continuation; keep its three accepted observation-field steps
  as a diagnostic branch. Start `joint_refinement_run/` from the same two-paw
  semantic checkpoint with **no protected indices**; every region can improve.
- Use common saved-camera regional support checks against both the current
  carrier and the fixed loop-start carrier, alongside fixed-rest strain and
  visual review. Reuse the registration method's regional trust limits.
  These gates assess observed fit; they are not semantic part guarantees.
- Restore optional `UPDATE_POSTERIOR` using the existing mainline configuration
  and saved-camera transport. Keep semantic motion, proper Sim(3), and narrow
  observation-field actions available to the same controller.
- New run: `workspace/semantic_refinement_astra/custom10/cartoon_fox/joint_refinement_run/`.
  Model GPT-6 Astra medium, four-round diagnostic ceiling, six fixed views.
  New regional/evidence/view/registration tests: 13 passed. Full new-run
  outputs and frozen offline evaluation are pending; no mainline promotion.

## Evidence-complete refinement loop (2026-11-05, active)

- [x] Diagnose repeated observation-field rejection: exact protected-slot
  preservation was enforced but absent from review evidence; the deterministic
  candidate was repeatedly regenerated at unchanged input geometry.
- [x] Add frozen-reference coordinate/hash audits, fixed-rest cumulative strain,
  deterministic candidate deduplication, and measured local before/after crops.
  Crops include both largest observed gain and largest regression/smallest gain;
  nearest-distance gains are explicitly not semantic correspondence evidence.
- [x] Add common full/half/quarter observation-field candidates and remove that
  action at unchanged geometry after its candidates are exhausted. No category
  thresholds or GT-driven selection. Existing accepted checkpoints are frozen.
- [x] Check fixed six-view policy on 60 existing manifests across three datasets:
  all preserve the first four cameras and append the same +/-35-degree pair.
  Record: `workspace/semantic_refinement_astra/view_policy_audit.json`.
  This is a camera-policy audit, not a completion-performance benchmark.
- [ ] Verify the new controller on fox in
  `workspace/semantic_refinement_astra/custom10/cartoon_fox/evidence_v2_run/`;
  record accepted decisions, protected-tail displacement and frozen offline metrics.
- [ ] Cross-dataset autonomous efficacy and matched four/six-view ablation.

Focused evidence/rendering tests: 16 passed. The separate semantic-helper suite
also passed. All MLLM calls remain GPT-6 Astra, medium. This iteration starts
from the accepted two-paw semantic continuation; it is a human-assisted pilot,
not a replacement for the previously validated complete refinement/fusion route.

## Active fox diagnostic and generic policy changes (2026-11-05)

- User approved the tail shown in `flexible_run/round_01/after_0.png`.
  Exact `smooth_1.0.ply`, image, prompt and parameters are frozen in
  `workspace/semantic_refinement_astra/custom10/cartoon_fox/approved_tail/`;
  full acceptance provenance is in PROJECT_STATE.md. Feet remain unresolved.
- Six diagnostic views use one fixed rule: preserve four original views,
  append +/-35-degree elevations in the reference-camera basis. No category,
  part identity, GT or manually selected fox angle enters the view rule.
  All three view-policy tests passed (2026-11-05): original-camera preservation,
  world-similarity equivariance, and six-view board rendering. Cross-dataset
  four-versus-six ablation remains pending; do not infer generalization from fox.
- Semantic correspondence validation now reprojects lifted controls into both
  selected windows and returns explicit failures/marked images to the agent.
  This corrects the previous generic-feedback failure; do not relax the gate.
- The six-view continuation is in the same case's `six_view_run/`. Round 4
  accepted a smooth front-paw update; all 8,762 protected tail slots have
  exactly zero displacement. Continue examining remaining limb residuals.
- Generic geometry tools: proper global Sim(3), coherent part SE(3), and
  regularized low-frequency RBF deformation, each with observation/structure
  checks. Preserve accepted surfaces via a smooth intrinsic protection taper.
- Frozen stage GT evaluation is offline-only under `offline_evaluation/`;
  results never enter agent payloads, geometry acceptance, or stopping.
  Distinguish the human-assisted pilot from future autonomous generalization
  and the separate fine-registration ablation from the actual execution chain.

## Region-balanced fine registration (2026-11-05, active)

- [x] Implement an isolated proper Sim(3) continuation with visibility-valid
  joint camera/3D reciprocal correspondences, robust equal-area weighting,
  and fixed-region validation. No category routing, GT or per-case parameters.
- [ ] Verify transform recovery, density imbalance, occlusion and identity
  behavior; run matched correspondence/weight ablations on multiple datasets.
- [ ] Save candidates and regional before/after evidence together by dataset;
  preserve the accepted baseline and keep experimental until local alignment
  and whole-object stability are verified. Semantic deformation remains a
  separate outstanding stage below.

**Current scope:** user requested a fox-only pilot starting from the existing
registration, with the agent choosing alignment or semantic local deformation.
Cross-dataset extension stopped after 44 complete comparison records under
`workspace/registration_method_v1/`; this is not a completed benchmark or a
mainline promotion. Five numerical registration tests passed.

**Model change:** all new MLLM entrypoint defaults are `gpt-6-astra`, reasoning
`medium`; preserve historic GPT-6 Sol records. Combined focused tests: 27 passed.

**Fox pilot:** `workspace/semantic_refinement_astra/custom10/cartoon_fox/`.
Sparse ARAP surface handles produced excessive strain and were rejected;
`coherent_run/` tests whole-part SE(3) from the same semantic correspondences
with an intrinsic attachment transition. Current accepted carrier and decision
trace are saved in that run. No baseline replacements or new final metrics.

**Pilot completed:** Astra accepted one coherent tail-part update, then chose
KEEP_CURRENT because attachment and leg correspondences remain ambiguous.
`coherent_run/comparison.png`, `selected_100k.ply`, `summary.json` and
`report.json` contain the result and limitations. No global action was chosen;
this therefore does not validate an alternating loop. Tail remains incompletely
aligned, legs have no dedicated accepted correction, and no fusion/CD/EMD was
run. Focused tests: 27 passed plus the added rigid-core preservation test passed.
Next progress depends on stronger cross-view semantic correspondence and
attachment support, not relaxing the shape guard or claiming this solved fox.

## Semantic local correspondence refinement (2026-11-05, active)

- [x] Clarify fox feedback: the tail was already misaligned in the original
  result; this is an unresolved local deformation, not established regression
  from packaging or the new local loop. Aggregate metric gains are insufficient.
- [ ] Diagnose registration → standard refinement → local refinement → fusion
  using matched views and visible partial evidence; preserve accepted originals.
- [ ] Extend agent capability from choosing nearest-neighbour translations to
  proposing explicit observed/prior part correspondences, with attachment and
  endpoint evidence. Numeric transformations remain geometry-tool outputs.
- [ ] Test supported part rotation/bending with attachment preservation and
  matched local before/after review. Require local alignment and natural shape,
  not merely better whole-object coverage or CD/EMD. Keep this experimental
  until verified; avoid fox-specific rules and GT-driven correspondences.

## Dataset-organized result package (2026-11-05)

- [x] Copy all 60 validated sample chains into `workspace/refinement_final/`
  with dataset → sample → stage directories, per-sample metrics and dataset
  summaries. Preserve frozen originals; verify every copied file hash and
  each final carrier against the paired metrics before publishing the package.
  Published: 12,492 copied files (7,238,261,986 bytes), every source/destination
  SHA-256 matched; all 60 final carriers matched paired candidate metrics and
  finalization records. Physical copies, frozen originals unchanged. Dataset
  summaries and sample-relative `artifacts.json` indexes provide current paths;
  historical execution metadata retains original paths for provenance.

## Structure-preserving local refinement (validated 2026-11-05)

**Scope:** preserve prior generation agent → registration → refinement agent
→ fusion; improve common-policy full-fusion CD/EMD on Aircraft40, Redwood10
and Custom10 without sample-specific or GT-driven inference decisions.

- [x] Freeze and verify original inputs and outputs (360 matching SHA-256s).
- [x] Add bounded rigid-core translations with smooth graph transitions,
  stable-observation and attachment/connectivity checks.
- [x] Add GPT-6 Sol region planning, visible-only labels, matched square depth
  crops, explicit correspondence review, up to three attempts, fixed local
  rest graph and protection of previously accepted cores.
- [x] Integrate `--planned-local-motion` into the four-stage runner and retain
  the original and single-step modes for reproducible ablations. All 33
  focused tests passed, including stage propagation and structural guards.
- [x] Complete all 60 frozen-policy inference reports, unchanged final fusion
  and three-repeat paired offline metrics. Two transport failures were
  retried with the identical policy and recovered; batch records reconciled.
- [x] Audit all 60 final carriers, exact metric/output hashes, shared config,
  original baseline preservation and final structural changes.
- [x] Verify both mean metrics improve on all three datasets. All three EMD
  numerical-noise intervals exclude zero. Update the canonical method,
  README and detailed report with the recommended explicit invocation.

| Dataset | Cases | Original CD×100 | Planned CD×100 | Original EMD×100 | Planned EMD×100 |
|---|---:|---:|---:|---:|---:|
| aircraft | 40 | 4.52870972 | 4.51448453 | 7.04923825 | 7.03586992 |
| redwood | 10 | 1.53703572 | 1.53187150 | 2.47234073 | 2.46418532 |
| custom | 10 | 2.01922931 | 2.00722932 | 2.76870379 | 2.75527649 |

**Outputs:** `workspace/structure_refinement_20261104/planned_v2/` and
`planned_v2_fused/`; raw metrics, audited per-case CSVs, evidence and structure
reports are in `metrics/`. The current reproducible method and limitations
are in `docs/planned_local_refinement_results.md`. The prior single-step
reference is preserved under `local_v2/` and `local_v2_fused/`.

**Limits and decisions:** the numerical operator is local translation, not
semantic part segmentation or arbitrary rotation. Final fusion is not exactly
rigid: no significant graph split/merge was found, but affected-edge strain
and individual metric regressions remain. Exact hosted GPT checkpoint/seed
are UNKNOWN. Improvements are aggregate on these three tested datasets.
The optional residual-registration experiment was audited separately and
was not adopted; its incomplete combined run is not evidence for this result.
No source push is part of this follow-on task. The requirement-by-requirement
completion audit passed and is saved as `completion_audit.json` under the
experiment root; no required work remains for this objective.

## Follow-on aircraft, unknown-camera datasets and Redwood ablations (2026-11-03)

- [x] Immediately after Custom10 completes, run the current aircraft dataset
  first: 40 partial/GT pairs in `data/aircraft/{partial,gt}/`, four aircraft
  types × ten saved projection views. Use the supplied per-view camera JSON
  and rasterize each partial at that fixed view; do not select a new camera.
  Generate, review and run the same four-stage chain, then evaluate all 40
  frozen predictions with CD/EMD under the stated offline protocol. All 40
  fixed-camera inputs and prior-agent manifests are prepared under
  `workspace/aircraft40_imagegen_20261103/` from the 2,048-point partials;
  the denser saved depth scans and GT were excluded. The preparation script is
  `scripts/prepare_aircraft_saved_camera_inputs.py`; one depth/camera pair was
  visually and numerically checked before preparing all 40.
  `scripts/record_imagegen_candidate.py` records exact prompts and hashes.
  All 40/40 candidates passed the prior review and all 40/40 fused PLYs
  exist with exactly 100,000 vertices. The frozen offline metric has 40 rows
  in `workspace/aircraft40_imagegen_20261103/aircraft40_metrics.json` and
  `.csv`: mean CD-L1 ×100 = 4.528710, mean EMD ×100 = 7.051503 (16,384 FPS,
  seed 6145). These scores were not available to the prior agent or used to
  tune generation. `J-15_view01` initially showed the aircraft
  upper surface even though its saved camera was 20° below; a revised
  underside candidate passed review. The generic depth interpretation now
  passes a saved camera above/below cue when `world_up` is recorded. Distant
  aircraft can also use the optional partial-only canvas framing hint.
  During the aircraft batch, the generic positive-support floor was relaxed
  from 0.80 to 0.75: the scan is incomplete, while the semantic reviewer
  still checks visible part structure, depth order and natural construction.
  The review now explicitly permits plausible extension into unobserved
  pixels instead of treating the partial bounding box as a hard boundary.
  Retry text now keeps only the latest correction, drops a possibly wrong
  initial semantic hint after repeated failures, and uses relative canvas
  positions. A provider output of 1240×1269 exposed a small aspect mismatch;
  the full-canvas mapping now records axis scales and permits at most 3%
  variation without cropping. Larger mismatches remain rejected.
  The reviewer now treats isolated black scan voids inside a visible surface
  as missing data rather than real holes, unless the object category supports
  openings at those locations.
  `J-36_view08` was reopened after a manual check found rendered holes in the
  aircraft skin. Its earlier acceptance is retained only as a superseded audit
  record; a revised continuous-skin candidate passed review and completed fusion.
  `J-35_view03` required an underside edit; the reviewer initially overfit
  an ambiguous short scan protrusion to a specific far-wing feature. The
  saved depth interpretation had explicitly marked that part uncertain, so
  the generic review now treats retry prompts as provenance rather than
  evidence when they over-specify uncertain scan details. The candidate
  passed re-review and its geometry chain completed. A Qwen diagnostic on
  that case produced a washed-out depth-like image and was not used.
  Image Gen edit experiments now record the exact second input image and
  hash in `generation.json`. `运-20_view01` passed semantic review and fusion.
  An isolated, frozen `J-15_view00` pilot offline score is stored in
  `workspace/aircraft40_imagegen_20261103/pilot_J-15_view00_metrics.json`;
  it was not used to tune subsequent prompts. Evaluate and report the full
  aircraft batch was evaluated after all 40 predictions were frozen.

- [x] After Custom10 and aircraft, run
  every available current KITTI (`data/kitti/partial`: 20), Waymo
  (`data/waymo/{CAR,PED,OTHER}`: 76) and ScanNet/ScanSalon
  (`data/scannet/partial`: 50) partial. KITTI and Waymo have no matched
  complete GT here, so report completion counts and no-GT checks only;
  evaluate ScanNet against its 50 matched GT files only after inference.
  KITTI pilot `frame_000782_car_1` completed 20-view preparation and GPT-6
  Sol view choice. Its third Image Gen candidate passed the no-GT prior review
  after making a continuous finished car surface and moving the observed roof
  and wheels closer to the sparse scan. All 20 KITTI samples now have saved
  20-view selection and depth interpretations. Three fused 100k outputs exist
  under `workspace/kitti20_imagegen_20261103/`; the remainder are in semantic
  review or the geometry chain. A sparse car candidate copied point scan
  speckles into paint, so the shared depth-framing prompt now requires a
  continuous finished surface. The reviewer initially over-constrained full
  object width to the partial scan's bounding box; the general no-GT rule now
  permits natural 15–25% extension beyond observed support when visible part
  scale and overlap agree. Its earlier 91% support candidate then passed
  re-review, while an artificially shrunk 57% support edit was rejected.
  Waymo and ScanNet view preparation reached 57/76 and 47/50 respectively;
  simultaneous Codex CLI `error` events interrupted both loops and require
  retries without changing their selection protocol. Both now have all
  views selected (Waymo 76/76, ScanNet 50/50), and their depth interpretation
  passes are running. The same transient `error` event interrupted one KITTI
  refinement. Prior and refinement Codex calls now retry such events up to
  three times while preserving the existing ban on actual tool calls; the
  failed refinement is resuming from its saved Pixal/registration/diagnostic
  stages. Candidate generation metadata is now archived by image SHA-256
  to preserve provenance across retries and re-review.
  KITTI reached 20/20 accepted semantic images and 20/20 fused 100k outputs,
  verified against the saved manifests and PLY vertex headers on 2026-11-03.
  No matched complete GT PLY exists for KITTI, so no CD/EMD was calculated.
  The sole
  remaining car repeatedly inverted the scanned near/far perspective despite
  four no-GT reviews; the general `reselect` command now excludes failed
  views among the saved 20 candidates, records the reason, reinstalls the
  newly selected camera and clears only rejected candidate rounds. Its view
  changed from `view_088` to GPT-6 Sol's `view_083`; the new depth
  interpretation and corrected ordinary-car generation passed review. All
  20 KITTI semantic images are accepted; both remaining geometry chains
  completed after GPU contention. The sparse-person review also
  stopped forcing an exact hip boundary from an ambiguous lower-body patch,
  allowing the natural high-support KITTI pedestrian to pass re-review.
  Waymo 76/76 and ScanNet 50/50 depth interpretations and prompt files now
  exist. A ScanNet chair hint once exceeded the short prompt budget; the
  generic builder now drops redundant count text and, if needed, clips the
  image hint while preserving facing and canvas cues. The first Waymo car
  passed prior review and completed fusion; the first six Waymo images have
  four accepted and two rejected for specific structural corrections.
  A sparse Waymo car's three successive candidates kept a natural van body
  and matched the observed near/far view, but review repeatedly demanded an
  exact front-wheel center from scattered underbody returns. The generic
  reviewer now distinguishes a clearly visible wheel/arch from an ambiguous
  lower-body patch before imposing an exact center; re-review must still
  verify positive support and overall pose. A separate `OTHER_VEHICLE` case
  failed positive-support coverage twice and was reselected from saved view
  `view_098` to `view_107` before regeneration, without using GT.
  KITTI's 20/20 final carriers passed the vertex-count audit. One Waymo car
  moved from `view_088` to `view_041` after repeated uncertain wheel-center
  interpretations; its new semantic passed review. A ScanNet shell chair
  moved from `view_195` to `view_060` after repeated concave/convex and
  near/far reversals; the new semantic passed review. A ScanNet lamp needed a
  thicker observed support and a natural unobserved base before acceptance.
  All reselections used the saved partial-only view set, and all exact prompts,
  source images, review audits and accepted transparent Pixal inputs remain
  in the corresponding sample roots.
  On 2026-11-04 all 50/50 ScanNet semantic candidates passed prior review and
  all 50 fused PLYs under `workspace/scannet50_imagegen_20261103/` were
  verified to contain exactly 100,000 vertices. Each five-stage manifest
  records `ground_truth_used: false`. The frozen offline 16,384-FPS,
  seed-6145 evaluation at `scannet50_metrics.json` and `.csv` has 50 rows:
  mean CD-L1 x100 = 5.408549, mean EMD x100 = 7.748956. The
  `sofa_scene0128_00_1` depth-order reversal was
  resolved by reselecting from `view_249` to `view_020` and then restoring a
  complete natural seat/back. A table required several review-driven retries
  to recover its outward-flared supports and continuous finished surface.
  Waymo now has all 76/76 accepted semantics under
  `workspace/waymo76_imagegen_20261103/`; all 76 fused PLYs were verified
  after the geometry queue completed on 2026-11-04. One ordinary-clothed
  pedestrian candidate initially triggered an Image Gen safety rejection,
  then passed with an explicitly adult, normally dressed prompt and corrected
  head placement. Several low-support pedestrian views were reselected
  from their frozen 20-view partial-only sets after failed edits, then passed
  no-GT review.
  No GT entered any of these corrections. The geometry queue processes
  accepted Waymo cases on five separate GPUs and records failures per sample.
  After repeated no-GT audits of sparse pedestrians, the current review
  entry floor was lowered from 0.75 to 0.65. A visible torso/limb candidate
  exceeded 0.82 support above the foot/ground band, while a broad horizontal
  lower scan strip reduced whole-canvas support to about 0.68. This remains
  only an entry gate: GPT-6 Sol still checks the full same-canvas overlay,
  part structure, facing and depth order before acceptance. Earlier accepted
  samples and the frozen ScanNet metric were not re-reviewed or retuned.
  A final audit of KITTI20, ScanNet50 and Waymo76 found zero missing or
  rejected semantic inputs, zero non-RGBA Pixal inputs, zero incomplete
  five-stage manifests, zero GT-used flags, and exactly 100,000 vertices in
  every fused PLY. KITTI and Waymo have no matched complete GT and therefore
  no CD/EMD was computed for them.
- [x] For these three datasets, generate a deterministic Fibonacci sphere of
  candidate camera views, rank by partial-only visible point count, retain
  the first 20 with a documented minimum angular separation, and let
  `gpt-6-sol` choose the candidate depth view that most resembles the known
  object class. Save all view scores, selected camera and prompt evidence;
  never use GT to select a view. Then use the Custom-tested depth semantics,
  Image Gen, review, Pixal3D, registration, refinement and fusion route.
  All 146 unknown-camera samples have 20 saved candidate views, a selected
  view among them, and a `gpt-6-sol` view-selection record. View reselections
  for rejected candidate images used only the saved partial-only views.
- [x] After those datasets, run controlled ablations on Redwood10 only,
  holding the frozen input/camera and offline 16,384-FPS seed-6145 ×100
  evaluation protocol fixed. Compare each feasible variant against the
  corresponding full route and report all ten sample CD/EMD rows plus means,
  exact artifact paths and no-GT inference provenance. Define variant
  switches and accepted reference before launching; do not tune with GT.
  Frozen reference: the ten accepted final fused carriers under
  `workspace/redwood10_final/`. Predeclared variants are the saved registered
  Pixal carrier (remove refinement and fusion), the saved refined carrier
  (remove fusion), and continuous fusion applied directly to that registered
  carrier (remove refinement), using the same partial and saved four-view
  cameras. Place only ablation outputs and offline metric files in
  `workspace/redwood10_final/ablations/`; leave the accepted sample chains
  untouched. Relocate copied manifest paths to the package before invoking
  fusion, because their original source run was removed. Evaluate all ten
  cases per variant after outputs are frozen, without GT-driven selection.
  Completed on 2026-11-04 in `workspace/redwood10_final/ablations/`:
  `comparison.csv`/`.json` contain all ten paired rows and means for four
  variants. Registered only: CD-L1 x100 1.766813, EMD x100 2.723830;
  refined without fusion: 1.535004, 2.456332; registered plus continuous
  fusion without refinement: 1.743406, 2.696517; frozen full route:
  1.537036, 2.474640. All ten no-refinement fusion outputs have 100,000
  vertices and no-GT provenance; the copied four-view manifests were
  relocated and every referenced file exists. The complete route's CD
  matches the previously saved Redwood result exactly, while its approximate
  EMD varies slightly across identical offline runs (the saved package mean
  was 2.472180; this run is 2.474640). A repeat for `01184` is under
  `diagnostics/` and also shows small EMD variability with unchanged CD.
  The full route is slightly worse on the ten-case mean than refinement
  without fusion; this is reported as measured rather than tuned with GT.

## Aircraft STL synthetic scan pairs (2026-11-04)

- [x] Use the four STL models in `data/型号飞机模型.rar` (J-15, J-35,
  J-36, 运-20) to make ten first-hit depth scans per model. Keep one
  deterministic 16,384-point complete surface sample per model and save
  matching 2,048-point partial/GT PLY filenames for all 40 views under
  `data/aircraft/`. Normalize each STL by its bounding-box center and largest
  extent; the STL physical unit is unknown. Generation code is
  `scripts/materialize_aircraft_stl_scans.py`; source STLs remain extracted
  under `data/aircraft/source/` and the original RAR remains in `data/`.
- [x] Save 40 camera JSONs, 40 numeric depth NPZs, 40 viewable depth PNGs,
  seeds, source/archive hashes, normalization and per-pair PLY hashes in
  `data/aircraft/generation_manifest.json`. The 40-view contact sheet at
  `data/aircraft/view_contact_sheet.png` was inspected: four aircraft have
  visible silhouettes in every view. All 40 PLY pairs, depth arrays, camera
  hit counts, and hashes were checked; each model's 10 GT copies have the same
  hash. The minimum inter-camera direction angle is 51.8°, and the 40
  768×768 depth views have 19,053–114,154 valid hit pixels. Partial-to-GT
  nearest-neighbor means are below 0.0042 normalized units. A synthetic box
  test confirms first-hit visibility. The scans are noise-free synthetic depth
  observations, not real LiDAR; raw STL physical units remain unknown.

## Waymo CAR dense-case retention (2026-11-03)

- [x] Rank the 59 local `data/waymo/CAR/*.ply` cases by PLY vertex count,
  breaking ties by filename. Keep the 25 densest and remove the other 34 CAR
  PLYs. The rank-25/rank-26 boundary is 5,988/5,985 points.
- [x] Record all 59 pre-prune filenames, point counts, ranks, retention
  status, and SHA-256 hashes in `data/waymo/CAR_top25_selection.csv`.
  Leave `data/waymo/PED/` and `data/waymo/OTHER/` unchanged.

## Local ScanSalon and KITTI dataset materialization (2026-11-03)

- [x] Copy ScanSalon object-level partial/GT pairs into `data/scannet/` using
  matching category-prefixed filenames. For each of car, chair, lamp, sofa,
  and table, select the 10 matched samples with the most partial points.
  `data/scannet/selection.csv` records source paths and point counts. All 50
  partials and 50 GTs were checked bytewise against source; category top-10
  rankings were independently checked against all 764 source candidates.
- [x] Extract KITTI Detection training LiDAR points inside annotated 3D car
  and pedestrian boxes, select the 10 densest partials per class, and write
  them under `data/kitti/partial/{car,pedestrian}/` with
  `data/kitti/selection.csv`. Keep
  `data/kitti/gt/` free of PLY files because matched complete object GT is
  unavailable. Car selected point counts range 4,405–7,621; pedestrian
  counts range 1,445–1,892.
- [x] Verify KITTI car/pedestrian counts (10 each), global top-10 ranks from
  five full-training shards, PLY vertex counts, and bytewise correspondence
  to re-extracted raw LiDAR points. The earlier 3,181 unclassified temporary
  KITTI copies and all shard caches were removed. The data directories now
  contain only 20 KITTI partial PLYs and 50 ScanSalon partial/GT pairs.

## Fixed-camera Custom10 four-stage run (2026-11-03)

- [x] Prepare all ten current `data/custom/<category>/` partial scans using
  each saved `camera.pth`/`camera.json`. Derive depth and point UV only from
  the partial scan where the checked-out data omits them; keep the saved view
  fixed. All ten 512×512 camera inputs and `fixed_camera_preparation.json`
  records exist under `workspace/custom10_imagegen_20261103/source_camera/`;
  ten prepared sample roots are in the same Custom10 directory.
- [x] Use each directory name (spaces for the image prompt) as its category
  label. Keep the validated short depth sentence and, when needed, append a
  `gpt-6-sol` interpretation of visible part identity/count, attachments,
  part axes versus tip directions, near/far order and uncertainty. Review
  same-canvas visible support, pose, depth order, category and natural
  construction; make the accepted Pixal input transparent. Camera and light
  helicopter have accepted RGB candidates and transparent inputs; camera was
  explicitly praised by the user. Hydra still misses the saved depth support,
  and dragon remains under revision after confusing a wing with a second
  head and downward claws with downward arms. The general interpretation
  schema was strengthened; do not accept those earlier images.
  All ten images then passed a first review, but the user identified a missed
  Hydra front/rear failure: its far heads looked back toward the near tail.
  That Hydra candidate and its partial downstream files were invalidated;
  the generic agent now records semantic facing separately from part location
  and requires `front_rear_axis_match` in review. A further Hydra candidate
  showing the backs of all three heads, with the tail toward the camera,
  passed both the 0.80 visible-support gate and the new facing check;
  `workspace/custom10_imagegen_20261103/hydra_creature/` now contains the
  replacement RGB, exact prompt and new transparent Pixal input. Its geometry
  pipeline is complete. All other nine accepted candidates remain frozen.
- [x] Run Pixal3D, MoGe registration, GPT-6 Sol refinement and continuous
  fusion for every accepted image. After freezing outputs, evaluate available
  Custom ground truth under the same 16,384-FPS/seed-6145 ×100 protocol and
  retain all sample artifacts and prompts together. All ten pipeline manifests
  have five complete stages and ten fused PLYs each have 100,000 vertices.
  `workspace/custom10_imagegen_20261103/custom10_metrics.json` and `.csv`
  contain offline CD/EMD for all ten; mean CD-L1 ×100 = 2.019229 and mean
  EMD ×100 = 2.766696. The corrected Hydra sample is CD-L1 ×100 = 2.172856,
  EMD ×100 = 2.695512. The exact Image Gen backend/seeds are unavailable
  from the provider and remain marked UNKNOWN in generation records.

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

- 2026-11-06: Offline evaluator now skips receipts withdrawn between listing
  and reading, and filters publication against current final hashes/rounds.
  Verified by a successful full evaluator rerun after the observed race.
  J-36_view08 completed 64 rounds and fusion; remaining residuals are explicit.

- Redwood 01184 finalized autonomously after 8 rounds. Offline old/new
  fusion CD-L1 x100 / EMD x100: 1.041444/1.844156 -> 1.151346/1.978593.
  Both regress; retained as an honest result, not fed to inference. Original
  accepted outputs remain preserved. Dataset comparison is still pending.

- Aircraft main batch finished all 21 scheduled cases successfully; only
  运-20_view07 budget extension remains on GPU 0. Redwood rebalancer
  4063280 suspended scheduler 3983101 while its current 05117 child drains.
  This is an intentional handoff, not a stalled inference process.

- Aircraft40 is fully finalized, artifact-verified and evaluated including all
  budget continuations. Dataset means and improvements are in
  workspace/refinement_updated/aircraft/summary.json; no GT informed decisions.

- Redwood handoff completed: queue_redwood_rebalance.json runs nine remaining
  cases (including 05117 fusion-only completion) on GPUs 1/2/3/4. Original
  suite_redwood.json records the handoff; stopping its scheduler was intentional.

- Last Waymo pedestrian reached round 32 and automatically resumed under
  the shared 64-round policy. Its round-32 artifacts are archived; final
  completion is pending. Redwood 07136 remains active independently.

- Redwood10 completed all fresh Astra-low runs and fusion; all ten verified
  and evaluated. Final summary: workspace/refinement_updated/redwood/summary.json.
  Only the last Waymo budget continuation remains active.
