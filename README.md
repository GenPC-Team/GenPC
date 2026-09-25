# GenPC++

GenPC++ is a zero-shot point-cloud completion system built around complete 3D
generative priors. It keeps generation, geometric inference, and offline
evaluation separate: neither ground truth nor CD/EMD is available to the
inference path.

The object pipeline is:

```text
partial point cloud
  -> saved-camera depth
  -> mask-locked direct-GPT semantic completion
  -> textured Pixal3D prior and native MoGe observation
  -> camera-aware Pixal--MoGe--partial Sim(3) registration
  -> four informative prior/partial residual views
  -> exact Camera-1 structure-aware Partial OT
  -> three rounds of prior-preserving posterior re-linearization
  -> complete 100k-point prediction
```

The depth raster is the camera and foreground-layout authority for semantic
completion. Direct GPT is instructed to preserve its mask, center, apparent
size, crop, orientation, and visible part locations; an automatic mask audit
rejects images that drift before any 3D generation is run.
The shared audit allows small boundary uncertainty on thin structures but has
no category- or sample-specific bypass.

Prepare the external GPT task and install the returned image with:

```bash
PY=/opt/data/private/cr/miniconda3/envs/genpc/bin/python

$PY scripts/run_semantic_stage.py \
  --output-root workspace/run/inputs/camera \
  --samples 01184 --depth-only

$PY scripts/prepare_depth_gpt_semantic_task.py \
  --depth workspace/run/inputs/camera/01184/depth.png \
  --object "a blue wheeled rubbish bin" \
  --constraint "Keep exactly two wheels parallel and attached to the same axle." \
  --output workspace/run/inputs/pixal/01184/gpt_depth_completion_prompt.txt

# Run GPT image generation with the saved depth and exact prompt, then:
$PY scripts/install_depth_conditioned_semantic.py \
  --sample 01184 \
  --semantic workspace/run/inputs/pixal/01184/gpt_image.png \
  --depth workspace/run/inputs/camera/01184/depth.png \
  --camera-dir workspace/run/inputs/camera/01184 \
  --rmbg-model models/RMBG-2.0
```

The four-view observation exposes where the registered prior disagrees with
positive partial evidence. Exact physical Camera-1 supplies the structural
Partial-OT correspondence authority, while the four consistently reframed
diagnostic views supply local observation assimilation. One category-
independent `PosteriorAdapter` performs the physical update and preserves every prior
carrier slot, anchors already aligned surface, propagates reliable residuals
through a deformation graph, and protects unobserved structure. Missing
partial pixels are unknown rather than deletion evidence.

The final fusion is not point concatenation and does not run a second shape
deformation. The same four saved cameras establish visibility-valid 2-D/depth
correspondences; a collision-free one-to-one decoder writes reliable measured
partial samples into an equal number of posterior carrier slots. All unmatched
slots remain unchanged, so observed geometry becomes exact while complete and
unobserved prior support is retained at a fixed 100k-point density.

## Quick start from a selected registered prior

Use the project interpreter explicitly:

```bash
PY=/opt/data/private/cr/miniconda3/envs/genpc/bin/python

CUDA_VISIBLE_DEVICES=0 $PY scripts/iterative_posterior_tto.py \
  --prior workspace/run/registration_selected/01184/camera1_amplified_registered_100k.ply \
  --partial data/redwood/partial/01184.ply \
  --camera workspace/run/inputs/camera/01184/camera.pth \
  --semantic workspace/run/inputs/camera/01184/img.png \
  --multiview-manifest workspace/run/residuals/01184/render/render_manifest.json \
  --config-json configs/posterior_mainline.json \
  --outer-rounds 3 \
  --output-dir workspace/posterior_run/01184
```

For heterogeneous datasets, write a JSON case manifest:

```json
[
  {
    "sample_id": "01184",
    "prior": "/absolute/path/to/registered_prior.ply",
    "partial": "/absolute/path/to/partial.ply",
    "camera": "/absolute/path/to/camera.pth",
    "semantic": "/absolute/path/to/img.png",
    "multiview_manifest": "/absolute/path/to/render_manifest.json"
  }
]
```

Then run the same frozen configuration over all cases:

```bash
CUDA_VISIBLE_DEVICES=0 $PY scripts/run_iterative_posterior_batch.py \
  --source-root workspace/best_redwood_custom_camera1_transport_20260911 \
  --output-root workspace/posterior_run \
  --registration-stage selected \
  --outer-rounds 3
```

Single-pass PosteriorAdapter runs use the `lean` output profile by default.
It keeps only the final carrier, matched before/after partial overlays,
Camera-1 image, multi-view board, and JSON audit. Use
`--output-profile debug` only for a
focused diagnosis that needs coarse carriers, support masks, OT pairs, or the
dense deformation field. An existing full experiment can be exposed as a
compact, zero-copy review tree with `scripts/make_posterior_review_bundle.py`.

For a portable, cleanup-safe replay beginning at the retained Pixal3D stage,
build a physical-copy package with `scripts/package_mainline_reproduction.py`.
The accepted Redwood10 + Custom12 package is
`workspace/compagent_pixal_reproduction_20260925/`. It contains Camera-1
depth/semantic assets, camera/UV data, partials, Pixal3D GLBs and ordered 100k
carriers, native MoGe caches, portable four-view camera manifests, selected
registration checkpoints, final posterior reviews, metrics, and paper assets.
Replay one sample with:

```bash
CUDA_VISIBLE_DEVICES=0 $PY scripts/reproduce_packaged_mainline.py \
  --bundle-root workspace/compagent_pixal_reproduction_20260925 \
  --dataset redwood --samples 01184 \
  --output-root workspace/replay_01184
```

The replay performs the initial Pixal--MoGe registration, the shared monotonic
Camera-1 broad continuation, and the posterior solve. Its SHA-256 report must
match the packaged registered carrier and posterior before legacy workspace
artifacts are removed.

The final prediction is
`workspace/posterior_run/<sample>/round_03/posterior_prior_100k.ply`. Each
sample also contains the registered start point, every intermediate carrier,
OT pairs, support states, the deformation field, camera overlays, and no-GT
residual and integrity diagnostics.

## Optional four-view diagnosis

When a textured GLB and its ordered pre/post-registration carriers are
available:

```bash
$PY scripts/run_multiview_diagnostics.py \
  --glb workspace/run/inputs/pixal/01184/pixal3d.glb \
  --source-carrier workspace/run/inputs/pixal/01184/pixal3d_sampled_100k.ply \
  --registered-prior workspace/run/registration/01184/final/camera1_amplified_registered_100k.ply \
  --partial data/redwood/partial/01184.ply \
  --camera workspace/run/inputs/camera/01184/camera.pth \
  --output-dir workspace/posterior_run/01184/multiview
```

Camera-1 is retained and three auxiliary views are selected by incremental
visibility of physical partial points with a minimum yaw separation.

## Offline evaluation

Run metrics only after predictions are frozen:

```bash
CUDA_VISIBLE_DEVICES=0 $PY scripts/evaluate_completions.py \
  --prediction-root workspace/posterior_run \
  --ground-truth-root data/redwood/gt \
  --output workspace/posterior_run/metrics/redwood
```

## Repository layout

```text
src/posterior_types.py                immutable posterior configuration/results
src/partial_transport.py              visibility-aware structural Partial OT
src/posterior_deformation.py          embedded-ARAP complete-carrier deformation
src/carrier_protection.py             integrity and residual-motion projection
src/posterior_adapter.py              posterior stage orchestration facade
src/deformation_graph.py              reusable graph and strain primitives
src/multiview_diagnostics.py          informative camera selection/rendering
src/multiview_partial_evidence.py     prior-to-partial residual visualization
scripts/iterative_posterior_tto.py    three-round one-sample re-linearization
scripts/run_iterative_posterior_batch.py dataset-independent batch inference
scripts/check_posterior_regression.py pointwise frozen-output regression gate
scripts/run_multiview_diagnostics.py  optional four-view audit
src/observation_anchored_fusion.py    four-view positive observation evidence
scripts/run_scene_completion.py       independent scene-level extension
```

See [installation](docs/installation.md), [models](docs/models.md), the
[canonical object method](docs/core_registration_pipeline.md), and the
[scene-level route](docs/scene_completion.md).

## License

Project code is released under the [MIT License](LICENSE). External models,
datasets, and CUDA extensions retain their own licenses.
