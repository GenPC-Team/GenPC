import numpy as np
import pytest
from types import SimpleNamespace
from src.depth_prompting import DepthPrompting


def test_declared_camera_up_tracks_coordinate_convention():
    eye=np.array([1.,.5,2.])
    positive=DepthPrompting._up_for_viewpoint(eye)
    negative=DepthPrompting._up_for_viewpoint(eye,[0.,-1.,0.])
    np.testing.assert_allclose(negative,-positive,atol=1e-7)
    assert negative @ np.array([0.,-1.,0.])>0
    assert abs(negative @ eye)<1e-6


def test_camera_up_pole_is_nonparallel_for_any_declared_axis():
    for axis in np.eye(3):
        up=DepthPrompting._up_for_viewpoint(axis,axis)
        assert abs(up @ axis)<1e-6
        np.testing.assert_allclose(np.linalg.norm(up),1.,atol=1e-6)
    np.testing.assert_array_equal(DepthPrompting._up_for_viewpoint([0.,1.,0.]),[0.,0.,1.])


def test_camera_up_rejects_invalid_metadata():
    for invalid in [[0.,0.,0.],[float('nan'),1.,0.],[0.,1.]]:
        with pytest.raises(ValueError,match='world_up'):
            DepthPrompting._up_for_viewpoint([1.,0.,0.],invalid)


def test_observed_bound_camera_is_scale_translation_equivariant_and_external():
    points=np.array([[-1.,-2.,-3.],[1.,2.,3.]])
    editor=object.__new__(DepthPrompting)
    editor.cfg=SimpleNamespace(fovy=50.,distance=1.6,view_num=20)
    first=editor.frame_observed_bounds(points);eyes=editor._fibonacci_viewpoints()
    assert np.all(np.linalg.norm(eyes-np.array(first['target']),axis=1)>first['observed_bounding_radius'])
    shift=np.array([10.,-4.,2.]);editor.frame_observed_bounds(points*3+shift)
    np.testing.assert_allclose(editor._fibonacci_viewpoints(),eyes*3+shift,atol=2e-6)
