import copy
import numpy as np
from scipy.spatial.transform import Rotation
from src.diagnostic_view_policy import fixed_six_view_manifest
from src.multiview_diagnostics import look_at_pose
from src.gpt_refine_agent import render_diagnostic_board
from src.multiview_partial_evidence import PoseProjector
from PIL import Image


def manifest():
    centre=np.array([.1,.2,.3]);eyes=[[0,0,3],[3,0,0],[0,0,-3],[-3,0,0]]
    return {'centre':centre.tolist(),'field_of_view_degrees':38.,'views':[{'camera_pose':look_at_pose(centre+e,centre,np.array([0,1.,0])).tolist()} for e in np.array(eyes)]}


def test_six_views_preserve_inputs_and_distance():
    source=manifest();saved=copy.deepcopy(source);new=fixed_six_view_manifest(source)
    assert source==saved and new['views'][:4]==source['views']
    assert len(new['views'])==6 and not new['additional_observed_geometry']
    for v in new['views']:
        p=np.array(v['camera_pose']);np.testing.assert_allclose(p[:3,:3].T@p[:3,:3],np.eye(3),atol=1e-10)
        assert abs(np.linalg.norm(p[:3,3]-new['centre'])-3)<1e-9


def test_rule_is_equivariant_to_world_pose_and_scale():
    a=manifest();r=Rotation.from_rotvec([.3,-.1,.2]).as_matrix();shift=np.array([2,-3,1]);scale=2.3
    b=copy.deepcopy(a);b['centre']=(scale*r@np.array(a['centre'])+shift).tolist()
    for v in b['views']:
        p=np.array(v['camera_pose']);p[:3,:3]=r@p[:3,:3];p[:3,3]=scale*r@p[:3,3]+shift;v['camera_pose']=p.tolist()
    aa,bb=fixed_six_view_manifest(a),fixed_six_view_manifest(b)
    for va,vb in zip(aa['views'],bb['views']):
        pa,pb=np.array(va['camera_pose']),np.array(vb['camera_pose'])
        np.testing.assert_allclose(pb[:3,3],scale*r@pa[:3,3]+shift,atol=1e-10)
        np.testing.assert_allclose(pb[:3,:3],r@pa[:3,:3],atol=1e-10)


def test_six_view_board_has_all_rows(tmp_path):
    m=fixed_six_view_manifest(manifest());views=[PoseProjector(np.array(v['camera_pose']),38.,64) for v in m['views']]
    points=np.array([[.1,.2,.3],[.2,.3,.4],[.0,.1,.2]])
    path=render_diagnostic_board(points,points,views,tmp_path/'six.png')
    assert Image.open(path).size==(1920,1160)
