# GenPC++ object completion mainline

This document is the canonical specification of the released object-level
method.

## 1. Inference contract

Given a partial point cloud \(P\), GenPC++ predicts a complete ordered carrier
\(X^*\) without task-specific training. Inference may use only partial-derived
images, saved cameras, generated priors, and no-reference residuals. Ground
truth, CD, EMD, dataset labels, part labels, and sample-specific thresholds are
forbidden.

The method has four conceptual stages:

1. create and register a complete image-conditioned prior;
2. diagnose positive partial evidence in camera-consistent views;
3. iteratively infer a structure-preserving posterior over the complete carrier;
4. decode reliable measured observations into that fixed complete carrier when
   a measurement-assimilated output is requested.

## 2. Observation and complete prior

A saved partial camera rasterizes a depth observation and stores its camera
parameters. A semantic completion model reconstructs a clean object image
while preserving the observed pose, silhouette, scale, and articulation.
Pixal3D converts that image to a textured GLB and an ordered 100k surface
carrier. Its native MoGe observation is retained as a camera bridge.

Camera-1 has an explicit projection contract. For a pinhole observation, the
intrinsic matrix, world-to-camera extrinsic, raster size, and top-left UV origin
are saved in `camera.json` and reused exactly by every registration and
diagnostic stage. Historical normalized-camera assets retain their original
projection path. When an older asset does not declare its normalized UV origin,
the bridge chooses top-left or bottom-left using only the fraction of projected
partial samples supported by the observed foreground mask. This prevents a
dataset-dependent coordinate convention from being mistaken for geometric
misalignment.

The initial placement composes native Pixal-to-MoGe geometry, pixel-indexed
MoGe-to-partial evidence, and bounded Camera-1 Observation-Consistent Prior
Registration.  Native Pixal-to-MoGe placement first calibrates the free
monocular metric gauge by the robust ratio of their positive camera depths.
This calibration is independent of raster resolution, image resampling, and
foreground crop; it does not impose a fixed numerical scale cap. Its
projective-consistency and visible-surface-consistency terms jointly constrain
every global transform to be a proper similarity,

\[
T(x)=sRx+t, \qquad R\in SO(3),\quad s>0.
\]

This stage solves the global pose, translation, and isotropic scale while
preserving the complete prior.

The residual Camera-1 search may be repeated as a monotonic broad-to-narrow
continuation. Each pass uses the same proper-Sim(3) visible objective; identity
is included in the candidate lattice, and continuation stops when the relative
no-GT objective reduction falls below a fixed threshold. The mechanism changes
neither the objective nor the action space and introduces no category or sample
branch.

## 3. Agentic observation diagnosis

Camera-1 and three auxiliary orbit views form a compact observation state. The
auxiliary views maximize incremental visibility of physical partial points
subject to a yaw-separation constraint. In each selected camera the system
renders the registered textured prior and projects the partial scan with a
z-buffer.

Only visible partial samples are positive evidence. Missing pixels are unknown
and never imply that prior geometry should be removed. Residual arrows point
from the current prior surface toward the supported partial target. Exact
physical Camera-1 proposes the low-frequency structural transport, while the
four consistently reframed diagnostic views provide local observation
assimilation. This separates acquisition-view scale and depth from auxiliary
view reframing. The physical deformation is solved in 3D by one shared action
rather than independent per-view edits.

## 4. Structure-aware Partial OT

Nearest-neighbour matching fails when corresponding structures are separated
by a substantial shape or extent error. GenPC++ therefore estimates an
unbalanced Partial OT coupling using extrinsic camera evidence and intrinsic
surface evidence:

\[
C_{ij}=\lambda_{3d}C^{3d}_{ij}
      +\sum_v w_{ij}^{(v)}(\lambda_{xy}C^{xy,(v)}_{ij}+\lambda_zC^{z,(v)}_{ij})
      +\lambda_nC^n_{ij}
      +\lambda_{\Sigma}C^{\Sigma}_{ij}+\lambda_gC^g_{ij}.
\]

The view weight is nonzero only when the partial observation and candidate
prior surfel are both visible in view (v). The terms compare screen
position, camera depth, normals, Euclidean distance,
local covariance spectra, and graph-geodesic signatures. Unbalanced transport
may leave unsupported mass unmatched. Its confidence and robust residual
quantiles induce three states without semantic labels:

- `supported-stable`: reliable and already aligned; kept rigid;
- `supported-residual`: reliable but inconsistent; drives deformation;
- `unsupported`: no positive observation; follows only structural propagation.

All thresholds scale with median spacing, robust quantiles, partial extent, or
visibility ratios.

## 5. Prior-preserving posterior deformation

The registered complete carrier is represented by a multi-resolution surface
graph. Coarse low-frequency modes absorb continuous extent differences; a
fine embedded ARAP field then resolves local supported residuals. Gaussian
means are controlled by neighbouring graph nodes:

\[
x_i'=\sum_k w_{ik}\left[R_k(x_i-g_k)+g_k+t_k\right].
\]

The objective combines transported observation evidence with stable anchors,
ARAP rigidity, Laplacian smoothness, attachment preservation, and unobserved
prior protection:

\[
\min_{\Pi,\Phi}
\langle C(\Phi(X),P),\Pi\rangle
+\lambda_s E_{\mathrm{stable}}
+\lambda_a E_{\mathrm{ARAP}}
+\lambda_l E_{\mathrm{lap}}
+\lambda_c E_{\mathrm{attach}}
+\lambda_p E_{\mathrm{prior}}.
\]

Correspondence and deformation are alternated coarse-to-fine. The solver never
deletes or concatenates points: all 100k prior slots remain the prediction.
Unobserved regions preserve relative structure and coverage, but may move with
their connected support. The released mainline repeats this same frozen
PosteriorAdapter update three times: every round re-estimates Partial OT and
four-view positive evidence from the previous carrier. This fixed
re-linearization schedule introduces neither training nor a sample-specific
decision rule.

### Implementation boundaries

The implementation follows the mathematical stages instead of collecting all
posterior logic in one file:

- `posterior_types.py` owns the immutable configuration and transport result;
- `partial_transport.py` owns visibility-aware structural OT and support-state
  estimation;
- `posterior_deformation.py` owns embedded-ARAP, attachment edges, coverage,
  and complete-carrier deformation;
- `carrier_protection.py` owns reference-carrier integrity, finite residual
  propagation, topology repair, and optional structure projections;
- `posterior_adapter.py` is the orchestration facade and audit-record builder.

The facade preserves historical experiment imports. A refactor is accepted
only when every ordered carrier slot matches the frozen Redwood and Custom
outputs within the configured numerical tolerance; aggregate CD/EMD gains
cannot compensate for a regressed sample.

## 6. Four-view confidence-gated carrier assimilation

The posterior deformation resolves shape disagreement, but an adapted prior is
still an estimate rather than a physical measurement. The final decoder reuses
exactly the four selected cameras from Section 3. In each camera it z-buffers
the posterior and partial, proposes only visibility-valid pixel matches, and
checks both image displacement and camera-depth agreement. Only physical pairs
supported by at least two cameras may influence the final carrier.

For sparse observations whose projected supports do not initially overlap,
the same camera still proposes its nearest visible pixel correspondences.
These proposals do not bypass acceptance: the existing camera-depth,
cross-view support, 3-D residual and collision-free assignment checks remain
the sole conditions for changing a carrier slot.

A deterministic collision-free assignment maps at most one partial sample to
each carrier slot and at most one carrier slot to each partial sample. Its
metric gate is the smaller of a dimensionless object-diagonal cap and an
adaptive measured-density threshold. Reliable residuals then define a finite
continuous field on the existing embedded-ARAP graph:

\[
\min_{\Phi}\;\sum_{(j,i)\in\mathcal A}c_{ij}
\lVert\Phi(X_i^*)-P_j\rVert^2
+\lambda E_{\mathrm{ARAP}}(\Phi)
+\mu\sum_{i\in\mathcal U}\lVert\Phi(X_i^*)-X_i^*\rVert^2.
\]

Here \(\mathcal U\) contains carrier samples outside a point-spacing-normalized
observation band, and therefore supplies fixed boundary conditions. A no-GT
line search accepts the largest field amplitude satisfying hidden-view
coverage, connectivity, and robust edge-strain bounds. This is neither
concatenation nor free global deformation: all ordered 100k slots are retained,
motion decays continuously to zero outside observed support, and unsupported
complete geometry remains fixed. Ground truth and offline metrics are not
available to correspondence construction. The former exact slot-replacement
decoder is retained only as `--mode exact` for historical reproduction.

## 7. No-GT posterior diagnostics

The runner records the full saved-view objective and these integrity
diagnostics for inspection:

- no new significant connected component;
- bounded robust graph-edge strain;
- stable-support motion near zero;
- normalized hidden-view coverage.

GT metrics are computed later by a separate process and cannot affect
inference.

## 8. Artifact contract

`scripts/run_posterior_adapter.py` and its batch wrapper default to a lean
six-file contract: final posterior, registered-prior/partial comparison,
posterior/partial comparison, Camera-1 projection, multi-view projection, and
the JSON audit. Numerical arrays and
solver-only visualizations are written only with `--output-profile debug`.
This changes artifact retention only; it does not change inference.

For environment migration and workspace cleanup,
`scripts/package_mainline_reproduction.py` materializes a self-contained
Pixal3D-stage package. It copies rather than symlinks the Camera-1 observation,
partial, Pixal3D GLB/carrier/metadata, native MoGe cache, selected four-camera
poses, selected-registration checkpoint, lean posterior review, and inference
configs. `scripts/reproduce_packaged_mainline.py` replays the fixed initial
registration followed by the shared monotonic Camera-1 broad continuation and
then posterior inference. Package integrity is checked by SHA-256 before any
replay; no GT is included.

For each sample, `scripts/iterative_posterior_tto.py` writes a registered
round and three re-linearized rounds:

```text
round_00_registered/posterior_prior_100k.ply
round_01/posterior_prior_100k.ply
round_02/posterior_prior_100k.ply
round_03/posterior_prior_100k.ply
round_03/partial_gray_posterior_red.ply
round_03/posterior_saved_view_projection.png
round_03/posterior_virtual_views.png
tto_summary.json
```

Each `round_info.json` records the fixed configuration, support counts,
deformation diagnostics and no-GT residual audit. `tto_summary.json` records
the fixed schedule and the residual trajectory; it is not a GT-based selector.
The released mainline parameters are stored in
`configs/posterior_mainline.json`; they enable integrated observation
assimilation with a dimensionless anchor residual ratio of 0.03.

The optional fixed-cardinality measurement decoder additionally writes:

```text
observation_anchored_fused_100k.ply
partial_gray_fused_red.ply
fused_four_view_projection.png
fusion_anchor_pairs.npy
fusion_positive_pairs.npy
fusion_info.json
```

When an ordered Pixal3D colour carrier is supplied, it also writes
`observation_anchored_fused_100k_pixal_texture.ply`; RGB remains associated
with the same ordered carrier slots after geometry assimilation.

The isolated GPT-refine experiment keeps this decoder as a separate stage,
using `scripts/fuse_agentic_refine_batch.py` to pair each frozen refined
carrier with its original partial, saved four-camera manifest and ordered
Pixal3D colour carrier. This wrapper invokes the unchanged continuous fusion
solver and writes a separate fused 100k result; it does not concatenate
points, feed GT to inference, overwrite the unfused carrier, or replace the
released fixed-three mainline. Future GPT batch experiments may invoke it
after refine with `--fusion-output-root` in
`scripts/run_agentic_refine_batch.py`.

## 9. Scene-level extension

The scene route remains independent. Scene MoGe and instance masks provide a
shared coordinate system; each complete textured instance mesh is registered
into that frame and composed with minimum camera-depth collision correction.
It does not change the object-level posterior solver.
