# Best Redwood10 and Custom10 Camera-1 transport results

This directory is an independent physical copy of the selected Camera-1
transport experiments. It contains the full upstream and geometric artifact
chain needed for inspection; no file is a hard link to the old experiment
roots.

## Reported offline metrics

- Redwood10: CD-L1 x100 `1.5380`, EMD x100 `2.4848`.
- Custom10: CD-L1 x100 `1.9921`, EMD x100 `2.5377`.

Ground truth and these metrics are reporting-only and were not exposed to
inference.

## Layout

Both `redwood/` and `custom/` contain:

- `inputs/`: partial clouds, depth and semantic observations, saved cameras,
  GPT prompts/images, Pixal3D GLBs, sampled priors, and native MoGe caches;
- `registration_initial/`: native Pixal--MoGe, two-camera bridge, joint, and
  Camera-1 registration stages;
- `registration_selected/`: the selected broad-to-narrow Camera-1 continuation;
- `residuals/`: four-view render, depth, visibility, and correspondence evidence;
- `posterior/`: Partial OT, coarse deformation, support states, deformation
  field, overlays, and selected 100k posterior;
- `final/<sample>/complete_100k.ply`: convenient copy of the selected output;
- `metrics/`: per-sample and aggregate offline CD/EMD;
- `gt/`: evaluation ground truth.

Every `final/*/complete_100k.ply` was verified to contain exactly 100,000
points and to match the selected posterior by SHA-256.
