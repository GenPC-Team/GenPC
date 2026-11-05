import numpy as np
from scipy import sparse
from scipy.spatial.distance import pdist
from scipy.spatial.transform import Rotation

from src.coherent_local_refinement import fit_rigid, geodesic_rigid_warp, local_rigid_candidates


def test_rigid_fit_recovers_rotation_translation_without_scaling():
    source = np.random.default_rng(7).normal(size=(30,3))
    rotation = Rotation.from_rotvec([.1,-.2,.05]).as_matrix()
    target = source@rotation.T + [1.,2.,3.]
    r,t = fit_rigid(source,target)
    np.testing.assert_allclose(source@r.T+t, target, atol=1e-10)
    assert np.linalg.det(r) > .999999


def test_geodesic_warp_preserves_core_and_does_not_move_nearby_disconnected_surface():
    # Two spatially adjacent chains are separate surfaces in the rest graph.
    a = np.column_stack([np.arange(10)*.1, np.zeros(10), np.zeros(10)])
    points = np.r_[a,a+[0,.01,0]]
    rows = np.r_[np.arange(9),np.arange(10,19)]
    cols = rows+1
    graph = sparse.coo_matrix((np.full(len(rows)*2,.1),
        (np.r_[rows,cols],np.r_[cols,rows])),shape=(20,20)).tocsr()
    rotation = Rotation.from_rotvec([0,0,.3]).as_matrix()
    result, weight = geodesic_rigid_warp(points,graph,np.arange(4),rotation,
                                        np.array([.02,.03,0]),.25)
    np.testing.assert_allclose(pdist(result[:4]),pdist(points[:4]),atol=1e-12)
    np.testing.assert_array_equal(result[10:],points[10:])
    assert weight[6] == 0
    assert 0 < weight[4] < 1


def test_aligned_partial_produces_no_candidate():
    points = np.random.default_rng(3).normal(size=(500,3))
    candidates, report = local_rigid_candidates(points,points[::3])
    assert not candidates
    assert report['reason'] == 'insufficient_residual_support'


def test_displaced_small_part_moves_whole_while_body_stays_fixed():
    rng = np.random.default_rng(12)
    body = rng.normal(size=(1000,3))*.08
    rod = np.column_stack([np.linspace(-.12,.12,120),
                           .45 + rng.normal(size=120)*.003,
                           rng.normal(size=120)*.003])
    carrier = np.r_[body,rod]
    partial = np.r_[body[::10],rod[::5]+[0,.04,0]]
    candidates, _ = local_rigid_candidates(carrier,partial)
    assert candidates
    points, record, _ = max(candidates,key=lambda c:c[1]['mean_observation_gain'])
    assert record['local_gain'] > .5
    np.testing.assert_array_equal(points[:1000],body)
    np.testing.assert_allclose(pdist(points[1000:]),pdist(rod),atol=1e-12)


def test_candidate_policy_is_invariant_to_world_units_and_origin():
    rng=np.random.default_rng(12)
    body=rng.normal(size=(1000,3))*.08
    rod=np.column_stack([np.linspace(-.12,.12,120),
                         .45+rng.normal(size=120)*.003,rng.normal(size=120)*.003])
    carrier=np.r_[body,rod]
    partial=np.r_[body[::10],rod[::5]+[0,.04,0]]
    a,_=local_rigid_candidates(carrier,partial)
    offset=np.array([4.,-2.,3.])
    b,_=local_rigid_candidates(carrier*7+offset,partial*7+offset)
    assert len(a)==len(b)>0
    for (pa,_,_),(pb,_,_) in zip(a,b):
        np.testing.assert_allclose(pa*7+offset,pb,atol=1e-10)


def test_connectivity_guard_detects_a_severed_component():
    from src.local_refinement_stage import connectivity_audit
    x,y=np.meshgrid(np.linspace(0,1,20),np.linspace(0,.2,6))
    reference=np.column_stack([x.ravel(),y.ravel(),np.zeros(x.size)])
    candidate=reference.copy()
    candidate[candidate[:,0]>.5,0]+=2.
    result=connectivity_audit(reference,candidate)
    assert not result['passed']
    assert result['broken_components']==1
