# GenPC++

GenPC++ completes a partial object point cloud with an image-conditioned 3D
prior, camera-aware registration, GPT-6 Astra geometric refinement, and
observation-anchored fusion. Ground truth and CD/EMD are used only after a
prediction is frozen.

```text
partial scan + saved camera
  → depth image → Prior Generation Agent → Image Gen semantic image
  → same-canvas review → RMBG transparent image → Pixal3D + MoGe-2 prior
  → Pixal–MoGe–partial registration → four-view residual diagnosis
  → GPT-6 Astra refinement → continuous observation fusion → 100k-point PLY
```

The Prior Generation Agent uses the saved acquisition camera when one exists.
Otherwise it selects an exterior/front view from partial-derived depth views,
avoiding the opposite or inside view of a hollow object. Its default Image Gen
instruction is short:

> 这是一个{物体}扫描出来的深度图。用 Image Gen 将图1补全成一张完整的{物体}图，遵循深度图可见部分的深度、轮廓约束，背景为纯白色。

Supply **the depth image** as Image Gen's image input. The observed depth
pixels constrain the visible contour, pose, part layout and near/far order;
unobserved pixels are unknown and allow a complete, naturally built object.
The agent resizes the entire generated image to the depth canvas without
cropping or translation, checks equal comparison dimensions, measures
approximate observed foreground coverage and reviews visible geometry,
category identity and structural plausibility. A coverage score alone cannot
accept an image. RMBG-2.0 makes the accepted image transparent **before** it
is sent to Pixal3D. MoGe-2 observes Pixal3D's saved preprocessed input.

## Run one object

Use the `genpc` interpreter and installed model assets from
[installation](docs/installation.md) and [models](docs/models.md):

```bash
PY=/home/chenrui/miniconda3/envs/genpc/bin/python
RUN=workspace/my_01184_run

$PY scripts/run_prior_generation_agent.py prepare \
  --sample 01184 \
  --partial data/redwood/partial/01184.ply \
  --object "带轮垃圾桶" \
  --camera-source workspace/astra_final/redwood/01184/inputs/camera/01184 \
  --output-root "$RUN"
```

The camera source directory must contain `depth.png`, `camera.pth`, and
`point_uv.npy`. Omit `--camera-source` only when those assets do not exist;
`prepare` then renders depth candidates from the partial scan and asks the
agent to choose a view. The command writes
`$RUN/prior_agent/round_00_prompt.txt` and prints the selected depth path.
Use **only that depth image and saved prompt** in Codex Image Gen, then save
its full-resolution result and review it:

```bash
$PY scripts/run_prior_generation_agent.py review \
  --candidate /absolute/path/to/imagegen_result.png \
  --output-root "$RUN"
```

If the review requests a revision, use its next saved prompt with the same
depth view. An accepted review writes the RGB semantic image, same-canvas
audits, exact prompt, and RMBG RGBA Pixal input under the run directory.
Continue the geometric stages on the visible GPU:

```bash
CUDA_VISIBLE_DEVICES=0 $PY scripts/run_four_stage_pipeline.py \
  --output-root "$RUN" --planned-local-motion
```

The final geometry is
`$RUN/fusion/01184/observation_anchored_fused_100k.ply`; the Pixal-coloured
carrier is beside it. The run also retains its depth/camera, prompt,
semantic image, alpha image, Pixal and MoGe assets, registration, view
diagnostics, refinement decisions, stage logs and manifests. The two agent
decisions use the logged-in Codex CLI model `gpt-6-astra`; Image Gen is an
interactive Codex tool.

## Local refinement

For experimental **autonomous semantic refinement** from an archived registered
case (no annotations, previous plan or per-case feedback):

```bash
CUDA_VISIBLE_DEVICES=0 /home/chenrui/miniconda3/envs/genpc/bin/python \
  scripts/run_semantic_refinement_continuation.py \
  --case-dir workspace/astra_final/custom/wolf \
  --output-dir workspace/autonomous_refinement/custom10/wolf \
  --autonomous --views 6 --rounds 32
```

Use a fresh output directory; `--resume` continues the same run from its own
saved state. `--rounds` is the total round ceiling, including completed rounds,
not an additional number of rounds. The current dataset suite allows 32 rounds and
can stop earlier after an evidence-based completion audit. In the current
experiment, budget-exhausted runs receive a common continuation to 64 total
rounds after their first checkpoint is archived under `budget_tranches/`.
Eligibility uses the recorded stop reason, never GT or metrics. A budget stop does
not mean convergence. The agent discovers mismatched parts, validates
cross-view correspondence, reviews local and global effects, and audits its
stopping decision. Outputs include `selected_100k.ply`,
`visualization/refined_red_partial_blue.ply`, before/after boards and the full
decision trace. `scripts/run_autonomous_refinement_batch.py` applies the same
policy to multiple archived cases. The five-dataset autonomous results are accepted;
the earlier fox reference was human assisted. See the
[method and limitations](docs/core_registration_pipeline.md#autonomous-refinement-mode).

The accepted Redwood10, Custom10, KITTI20, Waymo76 and Aircraft40 results
(156 cases) are packaged under `workspace/astra_final/<dataset>/<sample>/`. Each completed
sample has `completion.json`, `artifacts.json`, all upstream stages, the
refinement trace and fusion outputs. `fusion/final_red_partial_blue.ply`
combines the final carrier (red) with the observed partial (blue).
`scripts/run_updated_dataset_suite.py --rounds 32` runs this shared policy;
KITTI and Waymo additionally require the saved Astra prior audit and any
required accepted rebuild before dispatch. Offline metrics are in
`workspace/astra_final/offline_evaluation/`; all five dataset summaries are complete. KITTI/Waymo have no matched
complete object GT in this dataset package, so CD/EMD are unavailable there.
For those two datasets, `observed_support.csv` reports one-way distances from
observed points to each 100k carrier, normalized by the observed bounding-box
diagonal. These diagnostics measure observed fit and cannot establish the
accuracy of unobserved completion. They are computed offline after finalization.

The recommended `--planned-local-motion` mode adds GPT-6 Astra region planning,
bounded local translations, matched depth crops and cumulative attachment/core
checks inside refinement. It keeps the four-stage sequence and unchanged
continuous fusion. The common policy improves mean CD/EMD on Aircraft40,
Redwood10 and Custom10; see the [complete results and limitations](docs/planned_local_refinement_results.md).

Use a new run directory when changing the mode. `--coherent-local-motion`
is the mutually exclusive single-step ablation; omitting both options retains
the original refinement for reproducibility. No GT is used for inference.

## Accepted five-dataset experiment

All 156 samples are complete and accepted in `workspace/astra_final/`.
Every sample retains the full input, prior, registration, refinement and fusion
chain. `README.md`, `sample_index.csv`, `RESULTS.md`, `copy_manifest.json` and
`SHA256SUMS` provide navigation and verification. Historical JSON paths remain
unchanged; the manifest maps them to local archive files. Model weights and
original datasets are external, and the result package is not pushed to Git.

Offline 16,384-point FPS, seed-6145 evaluation gives the following final means
(CD-L1 / approximate EMD, both ×100): Redwood **1.520061 / 2.452078**,
Custom **1.892556 / 2.712018**, Aircraft **3.859079 / 6.392941**.
KITTI and Waymo have no matched complete-object GT; their tables report
observed support instead. Individual regressions are retained. Medium/low
reasoning and method changes are mixed, so this is not an Astra-only ablation.

See the [method and artifact contract](docs/core_registration_pipeline.md).
Project code is under the [MIT License](LICENSE); external models, datasets
and CUDA extensions retain their own licenses.

## Local point-cloud datasets

`data/redwood/partial/<id>.ply` and `data/redwood/gt/<id>.ply` use matching
names. The same convention now applies to the selected ScanSalon object pairs:
`data/scannet/partial/<category>_<id>.ply` and
`data/scannet/gt/<category>_<id>.ply`. Each of car, chair, lamp, sofa, and
table contributes its 10 matched samples with the most points in the **partial**
scan. `data/scannet/selection.csv` records the counts and original paths.
These ScanSalon objects are the ScanNet/ScanSalon source used for object-level
experiments, not the raw ScanNet room scans.

KITTI is under `data/kitti/partial/<category>/frame_<frame>_<category>_<index>.ply`,
with separate `car/` and `pedestrian/` directories.
The 10 car and 10 pedestrian samples with the most LiDAR points inside their
annotated 3D boxes are selected from the KITTI Detection training set. Points
are stored in each box's local coordinate system, with the KITTI box bottom
center as origin and annotation yaw removed. There is no matched object GT;
`data/kitti/gt/` is deliberately empty. `data/kitti/selection.csv` records
point counts and source LiDAR, label, and calibration files. To rebuild both
datasets from the locally installed sources, run:

```bash
/home/chenrui/miniconda3/envs/genpc/bin/python scripts/materialize_scan_datasets.py
```

`data/waymo/CAR/` retains the 25 local car scans with the most PLY vertices.
`data/waymo/CAR_top25_selection.csv` records the full 59-case ranking, including
the 34 removed cases and their original SHA-256 hashes. The PED and OTHER
directories were not changed by this selection.

The four STL aircraft models in `data/型号飞机模型.rar` have 10 synthetic depth
views each under [data/aircraft](data/aircraft/README.md): 40 matched
2,048-point partial and 16,384-point GT pairs. Each view also has a viewable
depth PNG, numeric depth NPZ, and camera metadata.

### Accepted paper archive

`workspace/astra_final/README.md` indexes all five datasets and their stages.
`copy_manifest.json` maps original paths to archived files, preserving historical
metadata verbatim. Old experiment directories and old baseline geometry are not
required to inspect the archive. Saved comparison metrics retain the old scores.
Verify the copied files and all 156 final carriers with:

```bash
/home/chenrui/miniconda3/envs/genpc/bin/python scripts/verify_experiment_archive.py workspace/astra_final
```

To package a newly completed suite into a fresh directory:

```bash
/home/chenrui/miniconda3/envs/genpc/bin/python scripts/package_updated_dataset_suite.py \
  --source workspace/my_completed_run --destination workspace/my_archive
```

Large experiment files and model weights are local assets, excluded from Git.

Start a fresh autonomous run from the accepted saved upstream stages (never
write experiments into the accepted archive):

```bash
/home/chenrui/miniconda3/envs/genpc/bin/python scripts/run_updated_dataset_suite.py \
  --source-root workspace/astra_final --output-root workspace/new_experiment \
  --datasets redwood custom kitti waymo aircraft --rounds 64 --gpus 0
```

The historical offline comparison runner requires its old baseline geometry.
After cleanup, use the preserved per-case comparison tables; the old point clouds
are intentionally not retained. New inference never reads those metrics.
