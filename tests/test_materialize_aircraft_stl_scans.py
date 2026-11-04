import numpy as np
import trimesh

from scripts.materialize_aircraft_stl_scans import (
    GT_COUNT,
    PARTIAL_COUNT,
    mesh_bounds,
    open_binary_stl,
    raycasting_scene,
    render_partial,
    sample_complete,
)


def test_first_hit_scan_sees_near_face_only(tmp_path):
    path = tmp_path / "box.stl"
    trimesh.creation.box(extents=[2.0, 1.0, 0.3]).export(path)
    triangles = open_binary_stl(path)
    low, high = mesh_bounds(triangles)
    center = (low + high) / 2
    scale = float(max(high - low))
    gt, _ = sample_complete(triangles, center, scale, 6145)
    scene = raycasting_scene(triangles, center, scale)
    partial, depth, camera = render_partial(
        scene, ((low - center) / scale, (high - center) / scale), 0.0, 0.0, 7117
    )
    assert gt.shape == (GT_COUNT, 3)
    assert partial.shape == (PARTIAL_COUNT, 3)
    assert np.allclose(partial[:, 0], 0.5, atol=1e-5)
    assert int((depth > 0).sum()) == camera["hit_pixels"]
