# Waymo sparse-LiDAR adapter

This is an opt-in registration policy built on top of the frozen object
mainline. It does not modify the Redwood/Custom route. It addresses a specific
observability failure of extremely sparse LiDAR: occupied returns are reliable,
but missing pixels are not free space and cannot constrain the complete prior.

## Method

The semantic image, Pixal prior, native MoGe observation, and two-camera bridge
are reused from the object pipeline. The adapter changes only how their
registration evidence is trusted.

### 1. Native camera-ray gauge calibration

The generated prior and native MoGe surface already share the Pixal input
camera. For every shared visible pixel, the adapter measures the depth ratio

\[
r_p = z_p^{\mathrm{MoGe}} / z_p^{\mathrm{prior}}.
\]

After trimming the lowest and highest ten percent, their median estimates one
camera-origin scale. Scaling all camera coordinates by the same positive value
preserves perspective projection exactly while resolving monocular depth gauge.
The estimate is accepted only when its trimmed ratio spread is below 1.25, its
silhouette/coverage are preserved, and its no-GT depth objective improves.

### 2. Foreground-supported sparse bridge

Camera-1 LiDAR samples outside the dilated semantic foreground are removed from
the bridge fit. Remaining samples query a small pixel neighbourhood on the dense
native MoGe surface. A grid-balanced robust proper Sim(3) is estimated from
partial to dense MoGe and inverted. This direction prevents missing LiDAR mass
from pulling the complete surface toward a few scan strips.

The proposed residual refinement is accepted only if a one-sided sparse
observation objective improves:

\[
E_{obs}=0.70 E_{visible\mbox{-}3D}
       +0.25(1-\mathrm{coverage})
       +0.05E_{depth}.
\]

Prior-only pixels never contribute a leakage penalty.

### 3. Dense visible-surface assimilation

Reliable same-camera native-MoGe samples replace only matched visible slots of
the ordered 100k carrier. Unmatched and hidden slots remain unchanged. This
supplies dense local surface evidence without concatenating the sparse scan or
deleting complete geometry.

### 4. No-GT candidate routing

The frozen mainline candidate and sparse dense-bridge candidate are evaluated
using every positive LiDAR return through a one-sided partial-to-complete
surface distance. A robust mean/tail combination avoids depending on an
unstable sparse raster, while prior-only regions remain unpenalized. A
prior-protection term measures the 90th-percentile ordered-carrier residual
after factoring out the best proper Sim(3):

\[
E = 0.65\,\operatorname{mean}_{p\in P}d(p,X)
  + 0.35\,q_{0.9}\{d(p,X)\}
  + E_{prior}^{q90}.
\]

The lower candidate is selected. The router uses no category name, sample ID,
ground truth, CD, EMD, or hand-authored part rule. Consequently, a sample whose
native depth gauge is already reliable may retain the frozen mainline, while a
sample with a camera-depth failure can use the calibrated dense bridge.

## Reproduction

With accepted Waymo inputs already generated:

```bash
/opt/data/private/cr/miniconda3/envs/genpc/bin/python \
  scripts/run_waymo_sparse_ray_registration_batch.py \
  --mainline-root workspace/waymo8_original_mainline_20260911 \
  --bridge-root workspace/waymo8_original_mainline_20260911 \
  --output-root workspace/waymo8_camera_ray_gauge_sparse_adapter_20260912
```

The final prediction for each sample is `complete_100k.ply`. Detailed native
gauge, sparse fit, assimilation, candidate scores, and output paths are stored
in `sparse_ray_registration_info.json`.

When adjacent frames of the same Waymo track are available, run the independent
held-out positive-surface audit with:

```bash
/opt/data/private/cr/miniconda3/envs/genpc/bin/python \
  scripts/evaluate_waymo_temporal_holdout.py \
  --data-root data/waymo \
  --mainline-root workspace/waymo8_original_mainline_20260911 \
  --adapter-root workspace/waymo8_camera_ray_gauge_sparse_adapter_20260912 \
  --output workspace/waymo8_camera_ray_gauge_sparse_adapter_20260912/temporal_heldout_validation.json
```

This aligns only the source and adjacent partial scans, applies that same
frame transform to both completion candidates, and measures held-out
partial-to-complete distance. The held-out frame is never visible to inference
or the router.

## Camera-coordinate audit (experimental)

The retained Waymo views were exported with a physical 180-degree camera roll;
the value is baked into each saved camera and is therefore not an omitted
post-hoc image rotation. A second convention must nevertheless be handled.
The historical depth painter vertically flips its raster after projection,
whereas native monocular geometry is expressed in an OpenCV camera frame and
the saved Kaolin camera uses an OpenGL-style frame. Let (Q) denote this fixed
MoGe-to-saved-raster coordinate conversion. For the historical flipped raster,

\[
Q=\operatorname{diag}(1,1,-1,1).
\]

This matrix is a coordinate convention, not a learned object reflection. The
experimental audit applies (Q) explicitly and estimates only a proper,
camera-anchored residual similarity

\[
T(x)=sR_{C_1}^{\top}x+t,
\]

from foreground-supported pixel-indexed pairs. The existing bounded sparse
surface refinement then estimates only a small residual proper Sim(3). This
prevents a free rotation from explaining image/depth convention error.

The audit outputs are under
`workspace/waymo8_camera_convention_sparse_adapter_20260912`. Each sample
contains `partial_gray_aligned_moge_red.ply`, with partial in gray and aligned
native MoGe in red. The aggregate image
`partial_moge_previous_vs_camera_convention.png` compares the previous and
corrected alignments in Camera-1 image and depth planes. User visual review
rejected this route for promotion: Waymo completion quality remains poor and
only 3/7 held-out directions are non-regressive. It is retained solely as an
isolated coordinate-contract diagnostic and is not imported by the mainline.
