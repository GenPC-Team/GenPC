import numpy as np
from scipy.spatial.transform import Rotation
from src.balanced_registration import weighted_similarity, region_weights, refine_balanced_sim3
from src.saved_camera import SavedCameraProjector


def projector():
    return SavedCameraProjector(None,(0,0),1,padding=.15,image_shape=(256,256),
        pinhole_intrinsic=np.array([[180,0,128],[0,180,128],[0,0,1]]),
        pinhole_world_to_camera=np.eye(4),pinhole_image_shape=(256,256))


def cloud():
    rng=np.random.default_rng(12)
    xy=rng.uniform(-.7,.7,(2000,2))
    return np.c_[xy,2+.15*np.sin(xy[:,0]*4)+.1*xy[:,1]**2]


def test_weighted_similarity_recovers_scale_rotation_translation():
    x=cloud();r=Rotation.from_rotvec([.01,.03,-.02]).as_matrix()
    y=1.02*x@r.T+[.02,-.03,.01]
    t=weighted_similarity(x,y,np.ones(len(x)))
    np.testing.assert_allclose(x@t[:3,:3].T+t[:3,3],y,atol=1e-10)
    np.testing.assert_allclose(t[:3,:3].T@t[:3,:3],np.eye(3)*1.02**2,atol=1e-10)
    assert np.linalg.det(t[:3,:3])>0


def test_equal_region_mass_despite_density_imbalance():
    labels=np.r_[np.zeros(1000,int),np.ones(10,int)]
    w=region_weights(labels,np.ones(1010)*.01)
    np.testing.assert_allclose([w[:1000].sum(),w[1000:].sum()],[.5,.5])


def test_collinear_correspondences_rejected():
    import pytest
    x=np.c_[np.arange(20),np.zeros((20,2))]
    with pytest.raises(ValueError,match='degenerate'):
        weighted_similarity(x,x+.1,np.ones(20))


def test_identity_and_hidden_geometry_are_preserved():
    x=cloud();hidden=x+[0,0,2]
    q=np.r_[x,hidden]
    result,report=refine_balanced_sim3(q,x,projector())
    assert not report['accepted']
    np.testing.assert_array_equal(result,q)


def test_recovers_small_global_offset_without_changing_shape():
    x=cloud();target=x+[.012,-.008,.01]
    result,report=refine_balanced_sim3(x,target,projector())
    assert report['accepted']
    assert report['after']['balanced_mean']<report['before']['balanced_mean']*.4
    assert result.shape==x.shape
