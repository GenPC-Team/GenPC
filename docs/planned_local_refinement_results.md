# Planned local refinement: validated result

The common policy `planned_local_v2_visible_regions_fixed_rest` improves
mean full-fusion CD and EMD on all three frozen datasets. The four stages
remain prior generation agent → registration → refinement agent → fusion.
Generation, cameras, Pixal/MoGe and registration are reused exactly; the
planned local loop runs inside refinement, after the standard rounds.

| Dataset | Cases | Original CD×100 | Planned CD×100 | Original EMD×100 | Planned EMD×100 |
|---|---:|---:|---:|---:|---:|
| aircraft | 40 | 4.52870972 | 4.51448453 | 7.04923825 | 7.03586992 |
| redwood | 10 | 1.53703572 | 1.53187150 | 2.47234073 | 2.46418532 |
| custom | 10 | 2.01922931 | 2.00722932 | 2.76870379 | 2.75527649 |

## Reproduction and artifacts

For browsing and paper figures, the consolidated package is
`workspace/refinement_final/{aircraft40,redwood10,custom10}/{sample}/`.
Each sample contains inputs, prior generation, registration, diagnostics,
standard/local refinement, fusion, metrics and logs. `artifacts.json` indexes
the current relative paths; `fusion/final_100k.ply` is the final output.
Dataset roots contain `metrics.csv` and `metrics.json`. Original paths in
copied execution records remain historical; the package copy manifest maps
them to their current locations and records verified SHA-256 hashes.

Use a new output root with the accepted prior and run the usual four-stage
entrypoint with `--planned-local-motion --gpt-model gpt-6-sol`. This selects
the validated three-attempt planner. The option is mutually exclusive with
`--coherent-local-motion`; omitting both reproduces the original refinement.
The ordinary continuous fusion stage always follows refinement.

All experiment files are in `workspace/structure_refinement_20261104/`:

- `planned_v2/{dataset}/{sample}/`: numbered views, fixed square crops,
  bounded proposals, full planning/review traces, protected core indices,
  selected 100k carrier, prompts/config and source/input hashes.
- `planned_v2_fused/{dataset}/{sample}/`: refined carrier, final 100k carrier,
  fusion files/logs and provenance. Unchanged carriers reuse the original
  fusion by exact input equality.
- `metrics/planned_v2_{dataset}_paired.json`: all paired raw measurements.
- `metrics/planned_v2_{dataset}_audited.csv`: every sample's CD/EMD.
- `metrics/planned_v2_evidence_audit.json`: complete 60-case verification.
- `metrics/planned_v2_final_structure.json`: post-fusion structure comparisons.
- `planned_v2/frozen_policy.json` and `planned_v2/code/`: frozen source snapshot.
- `frozen_baselines.json`, `frozen_custom_baselines.json`: original inputs and
  outputs, with all 360 hashes verified unchanged.

Offline metrics use 16,384-point FPS, seed 6145, CD-L1 and approximate EMD
(epsilon .005, 50 iterations), multiplied by 100. Three independent EMD
solves use the same sampled clouds. Identical prediction pairs share the
same measurements. All three mean EMD differences have numerical-noise
95% intervals below zero; these describe solver variability, not statistical
uncertainty over unseen categories. The original EMD numbers here are the
paired measurements, so they differ slightly from older single-run scores.
GT is supplied only to offline evaluation, never to inference or stopping.
No per-case or per-dataset parameter/strategy selection is used.

## Capability and limits

GPT-6 Sol chooses a supported observed/prior region or keeps the current
shape. The deterministic tool translates a coherent core and tapers its
motion along the surface graph. Matched depth crops preserve aspect, camera
and depth shading. Visible-only region labels avoid assigning an occluded
region to a front surface. Review checks correspondence, attachments and
unaffected structures. A fixed local-stage rest graph and accepted-core
constraints limit cumulative deformation over up to three attempts.

All 60 outputs retain 100,000 finite ordered points. Post-fusion graph audits
found no significant component splits or merges relative to the frozen
original final carriers. Maximum displacement was 2.4525% of the original
complete bounding-box diagonal. Across cases, affected-edge p01/p99 extremes
were 0.6819/1.6263: fusion is not exactly rigid, and this result does not claim
zero local distortion. The local rest reference starts after standard
refinement, so it cannot undo earlier distortion. Geometric regions are not
semantic part segmentation; substantial part rotations remain unsupported.

These are aggregate gains. Aircraft has 5 cases with higher CD and 16 with
higher measured EMD; Custom has 1 with higher measured EMD. No cases were
discarded or replaced by a GT-selected alternative. The EMD counts include
numerical variation. Inspect the per-case CSVs before making individual-case
claims. The hosted GPT checkpoint/seed are UNKNOWN, so exact response
reproduction is not guaranteed; its model name, reasoning setting and full
prompt builders are retained.

The optional differentiable residual-registration experiment is not part of
this validated policy. It remains off; this result isolates refinement and
keeps registration and final fusion fixed.
