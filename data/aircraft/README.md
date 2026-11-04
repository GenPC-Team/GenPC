# Aircraft STL synthetic scan pairs

The source archive is `data/型号飞机模型.rar`. Its four binary STL meshes are
extracted under `data/aircraft/source/`: J-15, J-35, J-36, and 运-20.
STL does not declare physical units. Each mesh is centered at its source
bounding-box center and divided by its largest extent; the exact transform,
source hash, and triangle count are in `generation_manifest.json`. The source
meshes have their thin axis along Z, so the camera orbit uses Z as up.

Each model contributes 10 distinct camera views, for 40 matched pairs:

```text
partial/<model>_viewNN.ply      2,048 first-hit scan points
gt/<model>_viewNN.ply          16,384 complete surface points
depth/<model>_viewNN.png       viewable, per-image contrast-scaled depth
depth/<model>_viewNN.npz       numeric camera-Z depth in normalized units
metadata/<model>_viewNN.json   camera intrinsics, extrinsics, seed, hit count
```

The same deterministic complete GT sample is copied under all 10 view names
for a model. GT is sampled by triangle area. Each partial is produced with a
pinhole depth camera using [Open3D first-hit ray casting](https://www.open3d.org/docs/latest/python_api/open3d.t.geometry.RaycastingScene.html),
then 8,192 visible pixel hits are candidates for 2,048-point farthest-point
sampling. The 10 angles cover eight oblique horizontal directions plus high
and low views. The raster starts at 768×768 and uses 1024×1024 only if there
are too few visible hits. Invalid depth pixels are zero in the NPZ. The PNG
is for visual inspection and rescales contrast separately for each view; use
the NPZ for measurements. No range noise or background points were added.
These are synthetic depth scans, not real LiDAR acquisitions.

The 2,048/16,384 counts follow a common point-cloud completion convention;
the local PCN complete clouds use 16,384 points, while partial density varies.
See the [PCN project](https://wentaoyuan.github.io/pcn/) for that benchmark
context. `view_contact_sheet.png` shows all 40 depth PNGs together.
`generation_manifest.json` contains source STL, archive, and output hashes plus every
pair's paths and camera angles.

To verify or regenerate from the extracted STL meshes:

```bash
/home/chenrui/miniconda3/envs/genpc/bin/python scripts/materialize_aircraft_stl_scans.py
```

The generator verifies complete existing model outputs before skipping them.
