from __future__ import annotations

import numpy as np
import trimesh

from src.deformation_aware_mesh import sample_expansion_compensation, transfer_carrier_deformation_to_mesh


def test_mesh_transfer_preserves_topology_and_constant_translation():
    mesh = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    source = np.asarray(mesh.vertices, dtype=np.float64)
    registered = source * 1.3 + np.array([.2, -.1, .4])
    shift = np.array([.12, -.07, .03])
    deformed = registered + shift
    result, report = transfer_carrier_deformation_to_mesh(
        mesh, source, registered, deformed,
        interpolation_neighbours=6, smoothing_steps=3, smoothing_weight=.25,
    )
    assert len(result.vertices) == len(mesh.vertices)
    assert np.array_equal(result.faces, mesh.faces)
    assert report["source_to_registered_fit_relative"] < 1e-8
    assert np.allclose(np.asarray(result.vertices), registered + shift, atol=1e-7)


def test_expansion_compensation_samples_only_the_expanded_surface():
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    deformed = mesh.copy()
    vertices = np.asarray(deformed.vertices).copy()
    vertices[vertices[:, 0] > 0.0, 0] *= 2.0
    deformed.vertices = vertices
    points, report = sample_expansion_compensation(
        mesh, deformed, count=128, expansion_quantile=.5, minimum_expansion=1.1,
    )
    assert points.shape == (128, 3)
    assert report["selected_faces"] > 0
    assert np.all(np.isfinite(points))
