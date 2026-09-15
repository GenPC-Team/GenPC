# Fresh Redwood10 + Custom10 PosteriorAdapter run

This directory is the retained from-scratch generalization run from 2026-09-08.
All semantic observations and native 3D priors were regenerated; no retained
semantic image, GLB, registered carrier, or prediction was replayed. Ground
truth was unavailable to view selection, semantic conditioning, registration,
candidate verification, Gaussian adaptation, and PosteriorAdapter.

## Final outputs

- Redwood selected 100k clouds: `redwood/final_selected/<id>/partial_anchored_gaussian_decoded_100k.ply`
- Redwood selection audit: `redwood/final_selected/selection_manifest.json`
- Redwood offline metrics: `redwood/final_selected/offline_metrics.{json,csv}`
- Custom selected 100k clouds: `custom/final_selected/<name>/posterior_prior_100k.ply`
- Custom offline metrics: `custom/offline_metrics.{json,csv}`

All intermediate depth/camera, semantic, Pixal GLB/100k prior/native MoGe,
cross-camera registration, Gaussian and posterior artifacts remain below the
corresponding `redwood/` or `custom/` subtree. Redwood `07136` and `07306`
also retain rejected view attempts for audit under `view_retry*` and
`gpt_bin_candidate`.

## Offline-only results

| Split | CD-L1 x100 | EMD x100 |
| --- | ---: | ---: |
| Redwood10 | 1.5017 | 2.3739 |
| Custom10 | 2.0118 | 2.9994 |

The two fresh Redwood observation failures were repaired without sample-level
geometry parameters. A bounded partial-only camera family was exposed to the
planner. It selected the antipodal view for both cases before prior generation.
For `07136`, this changed the fresh result from `7.4015/10.5119` to
`1.1191/2.0224`; for `07306`, the result changed from `20.2171/24.5511` to
`3.4709/3.8825`. These CD/EMD values were computed only after the no-GT view,
prior and adaptation decisions had been frozen.
