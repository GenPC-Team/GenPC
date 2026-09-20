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
