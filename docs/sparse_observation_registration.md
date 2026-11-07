# Optional sparse observation registration

`--sparse-observation` is **off by default**. It is never enabled by a dataset
name or point count. The accepted `workspace/astra_final` experiments and the
default registration/refinement/fusion route remain unchanged.

## Scope and motivation

The usual Camera-1 objective includes silhouette IoU and leakage. On LiDAR
fragments, a pixel without a return is unknown, so that objective can favour
an inappropriate orientation or size. Pixel-indexed MoGe/partial fitting can
also be dominated by a densely sampled patch. This option adds a separate
candidate and a conservative geometric selection; it does not replace the
image generator, complete carrier, or refinement agent.

1. Compute the original registration candidate with the unchanged main route.
2. Reuse native Pixal/MoGe geometry and image-indexed correspondences. Balance
   observations across a 4x4 partition of observed image coordinates, then fit
   proper Sim(3) with Cauchy reweighting. Never densify the scan into fabricated
   measurements; never use missing pixels as negative evidence.
3. Derive the MoGe-to-partial orientation prior from the saved camera, with
   explicit OpenCV/Kaolin axis conversion. Compare rotation fractions
   0, 0.25, 0.5 and 1 of the robust freely fitted rotation. Four spatial
   holdouts and a one-standard-error rule choose the smallest supported
   freedom. Poor spatial support retains camera orientation. These fractions
   are model candidates, not a universal cap on a part's motion.
4. Fit only scale and translation against visible complete-carrier samples,
   with rotation frozen. Select the earliest ICP iterate within spatial
   holdout uncertainty of the best. This step compensates Pixal/MoGe shape
   differences without introducing a new tilt or a silhouette leakage loss.
5. Compare this candidate to the original registration using only observed
   partial points. Require positive median-distance gain across image cells
   beyond its standard error, lower overall mean distance, and non-increasing
   p95 distance. Otherwise retain the original result. Preserve both candidates
   and the selection receipt for inspection/ablation.

All operations are global proper similarities, retaining carrier order and
count. No GT, category-specific dimensions, assumed vehicle headings, or
sample-specific thresholds enter the method. Saved synthetic cameras provide
an orientation prior; they are not treated as physical LiDAR origins and do
not imply free-space measurements. The native Pixal/MoGe alignment remains
shared with the main method.

## Usage

For a newly prepared and accepted prior, add the flag to the usual command:

```bash
/home/chenrui/miniconda3/envs/genpc/bin/python scripts/run_four_stage_pipeline.py \
  --output-root workspace/my_sparse_run --sparse-observation --stop-after diagnostics
```

Continue through the existing autonomous refinement and continuous fusion.
The option affects registration only. It does not alter the agent model,
reasoning effort, prompt, action policy or fusion configuration.

The lower-level `scripts/run_fixed_pixal_moge_registration.py` accepts the
same flag along with the normal `--samples`, `--pixal-root`, `--camera-root`,
`--partial-root` and `--output-root` arguments. Use a **new output root**;
mode switching on an existing final result is rejected. The option is not
compatible with the scene-specific `--bridge-only` route. Sparse input and
implementation hashes are checked on resume. The dataset-suite runner reuses
saved registration; it does not implicitly rerun this new option.

For an isolated replay on accepted archive inputs:

```bash
/home/chenrui/miniconda3/envs/genpc/bin/python scripts/audit_sparse_observation_registration.py \
  --archive-root workspace/astra_final \
  --output-root workspace/my_sparse_audit --datasets kitti waymo
```

This replay reuses saved native geometry and pixel matches and evaluates
registration only. It does **not** run new Image Gen, refinement or fusion.
The output root must be fresh and separate from the accepted archive.

## Evidence and limits

The validation bundle is `workspace/sparse_observation_validation/`:
`guarded/` is the current candidate-selection replay; root dataset folders
contain the bridge-only ablation; `surface_fit/` adds positive-surface fitting
without the final comparison guard. Every candidate and regression is retained.
The original dense candidate may itself be wrong. Retaining it when evidence
is weak does not certify correctness. Point-to-surface distances cannot prove
correct semantic correspondence, front/back orientation or unseen geometry.
MoGe depth errors and incorrect generated priors can affect both routes.
The unchanged main candidate still requires its usual valid bridge inputs;
this feature does not guarantee recovery when that stage cannot initialize.

Mean/p95 observed distances are normalized by the partial bounding-box diagonal
and expressed in percent, **not CD/EMD**. Because the selection uses observed
support, gains in this same metric are a mechanism check, not an independent
accuracy evaluation. A complete-shape or semantic-quality claim requires
separate evidence. No downstream quality claim follows from this replay.

## 2026-11-06 registration-only validation

| Dataset | Cases | Sparse candidate selected | Mean observed distance (%) | p95 observed distance (%) |
|---|---:|---:|---:|---:|
| kitti | 20 | 7 | 3.070801 → 2.746071 | 10.662269 → 9.068790 |
| waymo | 76 | 10 | 2.338762 → 2.193958 | 7.309667 → 6.709620 |

All 96 cases completed; all original input hashes were rechecked unchanged.
31 targeted tests passed. A real runner smoke/resume passed, and its unchanged
mainline candidate was byte-identical to the archived registration. Full
refinement/fusion reruns remain outside this registration-only validation.

## ScanNet car observation (2026-11-07)

The user explicitly enabled this option for the ten `car_*` samples in the
ScanNet50 Astra-Light run; other ScanNet categories retain the default route.
For `car_200`, the unrestricted native-MoGe-to-partial bridge rotation differs
by 173.6 degrees from the saved-camera orientation. Although 92.3% of partial
pixels find a nearby image pixel, only 44.0% of the resulting 3D bridge pairs
are inliers. The default final Camera-1 projected IoU remains 0.0854, so its
small local objective gains do not recover the orientation.

An isolated no-GT replay selects the sparse candidate by spatial positive
support: mean/p95 observed distance is 12.538/51.209% of partial diagonal for
the default registration and 2.221/5.081% for the sparse candidate. After
freezing both candidates, offline GT evaluation at the same protocol gives
registration CD-L1/EMD x100 of 30.845/34.563 and 3.878/4.284 respectively.
The experiment and overlays are retained under
`workspace/scannet50_astra/diagnostics/car_200_sparse_bridge/`. The complete
ScanNet rerun with the per-category opt-in is tracked in `PLAN.md`.
The subsequent 16-round Astra-Light refinement and continuous fusion of the
selected sparse candidate completed with 100,000 output points; its offline
CD-L1/EMD x100 is 3.809647/4.112972 versus the superseded default fused
result 30.875215/33.896536. This single case demonstrates correction of the
observed failure, while the ten-car rerun remains the broader check.
