import numpy as np
import pytest
from src.semantic_handle_refinement import lift,local_arap_candidate
from src.saved_camera import SavedCameraProjector


def view():
    return SavedCameraProjector(None,(0,0),1,padding=.15,image_shape=(512,512),
        pinhole_intrinsic=np.array([[200,0,256],[0,200,256],[0,0,1]]),
        pinhole_world_to_camera=np.eye(4),pinhole_image_shape=(512,512))


def test_lifting_uses_front_visible_surface():
    points=np.array([[0,0,2.],[0,0,3.],[.1,0,2.]])
    index,error=lift({'view':0,'xy':[50,50]},points,[view()])
    assert index==0 and error==0


def test_lifting_rejects_background_and_invalid_view():
    p=np.array([[0,0,2.]])
    with pytest.raises(ValueError):lift({'view':0,'xy':[1,1]},p,[view()])
    with pytest.raises(ValueError):lift({'view':1,'xy':[50,50]},p,[view()])


def test_deformation_requires_independent_windows():
    p=np.random.default_rng(4).normal(size=(100,3))
    decision={'windows':[{'view':0,'polygon':[[0,0],[100,0],[100,100]]}]*2,'handles':[]}
    with pytest.raises(ValueError,match='independent'):
        local_arap_candidate(p,p,[view()],decision)


def test_arap_preserves_unselected_points_and_moves_handles():
    xy=np.stack(np.meshgrid(np.linspace(-.5,.5,25),np.linspace(-.5,.5,25)),axis=-1).reshape(-1,2)
    p=np.c_[xy,np.full(len(xy),2.)];target=p.copy()
    target[:,1]+=np.clip((p[:,0]-.2)/.3,0,1)*.025
    views=[view(),view()];handles=[]
    for x,y in [( .25,-.25),(.375,0),(.5,.25)]:
        index=np.argmin(np.linalg.norm(p[:,:2]-[x,y],axis=1))
        source_uv=views[0].project(p[index:index+1])[0][0]/512*100
        target_uv=views[0].project(target[index:index+1])[0][0]/512*100
        handles.append({'name':'surface','source':{'view':0,'xy':source_uv.tolist()},'target':{'view':0,'xy':target_uv.tolist()}})
    decision={'windows':[{'view':i,'polygon':[[54.2,39],[61,39],[61,61],[54.2,61]]} for i in [0,1]],'handles':handles}
    result,report,mask=local_arap_candidate(p,target,views,decision)
    np.testing.assert_array_equal(result[~mask],p[~mask])
    assert np.mean(report['handle_error_after']) < np.mean(report['handle_error_before'])
    assert result.shape==p.shape and np.isfinite(result).all()


def test_semantic_rigid_core_does_not_form_landmark_spikes():
    from src.semantic_handle_refinement import coherent_semantic_candidate
    xy=np.stack(np.meshgrid(np.linspace(-.5,.5,25),np.linspace(-.5,.5,25)),axis=-1).reshape(-1,2)
    p=np.c_[xy,np.full(len(xy),2.)];target=p+[.01,.01,0]
    v=view();handles=[]
    for x,y in [(.25,-.25),(.375,0),(.5,.25)]:
        i=np.argmin(np.linalg.norm(p[:,:2]-[x,y],axis=1))
        handles.append({'name':'surface','source':{'view':0,'xy':(v.project(p[i:i+1])[0][0]/512*100).tolist()},'target':{'view':0,'xy':(v.project(target[i:i+1])[0][0]/512*100).tolist()}})
    d={'windows':[{'view':i,'polygon':[[54.2,39],[61,39],[61,61],[54.2,61]]} for i in [0,1]],'handles':handles}
    r,report,active=coherent_semantic_candidate(p,target,[v,v],d,.5)
    ids=report['source_ids']
    np.testing.assert_allclose(np.linalg.norm(r[ids[1:]]-r[ids[0]],axis=1),np.linalg.norm(p[ids[1:]]-p[ids[0]],axis=1),atol=1e-10)
    np.testing.assert_array_equal(r[~active],p[~active])

def test_smooth_field_preserves_unselected_points_and_improves_handles():
    from src.semantic_handle_refinement import smooth_semantic_candidate
    xy=np.stack(np.meshgrid(np.linspace(-.5,.5,25),np.linspace(-.5,.5,25)),axis=-1).reshape(-1,2)
    p=np.c_[xy,np.full(len(xy),2.)];target=p.copy()
    target[:,1]+=np.clip((p[:,0]-.2)/.3,0,1)*.025
    views=[view(),view()];handles=[]
    for x,y in [( .25,-.25),(.375,0),(.5,.25)]:
        index=np.argmin(np.linalg.norm(p[:,:2]-[x,y],axis=1))
        source_uv=views[0].project(p[index:index+1])[0][0]/512*100
        target_uv=views[0].project(target[index:index+1])[0][0]/512*100
        handles.append({'name':'surface','source':{'view':0,'xy':source_uv.tolist()},'target':{'view':0,'xy':target_uv.tolist()}})
    decision={'windows':[{'view':i,'polygon':[[54.2,39],[61,39],[61,61],[54.2,61]]} for i in [0,1]],'handles':handles}
    result,report,mask=smooth_semantic_candidate(p,target,views,decision)
    np.testing.assert_array_equal(result[~mask],p[~mask])
    assert np.mean(report['handle_error_after']) < np.mean(report['handle_error_before'])
    assert result.shape==p.shape and np.isfinite(result).all()



def test_protected_region_is_exact_and_transition_is_bounded():
    from scipy import sparse
    from src.semantic_handle_refinement import protect_displacement
    p=np.c_[np.arange(10,dtype=float),np.zeros((10,2))]
    metric=sparse.diags([np.ones(9),np.ones(9)],[-1,1],shape=(10,10)).tocsr()
    candidate=p+[0,1,0]
    result=protect_displacement(p,candidate,metric,[0,1],4.)
    np.testing.assert_array_equal(result[:2],p[:2])
    assert np.all(np.diff(result[:,1])>=0)
    np.testing.assert_array_equal(result[5:],candidate[5:])


def test_cross_view_validation_rejects_target_on_different_part(tmp_path):
    from PIL import Image
    from src.semantic_handle_refinement import validate_semantic_plan
    xy=np.stack(np.meshgrid(np.linspace(-.5,.5,25),np.linspace(-.5,.5,25)),axis=-1).reshape(-1,2)
    points=np.c_[xy,np.full(len(xy),2.)];views=[view(),view()]
    source={'view':0,'xy':[57.5,50.]}
    decision={'windows':[{'view':i,'polygon':[[54.2,39],[61,39],[61,61],[54.2,61]]} for i in (0,1)],
              'target_windows':[{'view':i,'polygon':[[39,39],[45.8,39],[45.8,61],[39,61]]} for i in (0,1)],
              'handles':[{'name':'same physical surface','source':source,'target':source}]}
    paths=[]
    for i in range(2):
        path=tmp_path/f'view_{i}.png';Image.new('RGB',(1024,548),'white').save(path);paths.append(path)
    result,_=validate_semantic_plan(points,points,views,decision,paths,tmp_path/'check',require_target_windows=True)
    assert not result['valid']
    assert all(p['inside_source_window'] for p in result['handles'][0]['projections'])
    assert any('OUTSIDE the observed part window' in issue for issue in result['issues'])


@pytest.mark.parametrize('name', ['coherent_semantic_candidate', 'smooth_semantic_candidate'])
def test_large_component_is_not_rejected_by_point_fraction(name):
    from src import semantic_handle_refinement as module
    xy=np.stack(np.meshgrid(np.linspace(-.5,.5,25),np.linspace(-.5,.5,25)),axis=-1).reshape(-1,2)
    points=np.c_[xy,np.full(len(xy),2.)];target=points+[.01,.01,0]
    v=view();handles=[]
    for x,y in [(0,-.25),(.25,.2),(.5,0)]:
        i=np.argmin(np.linalg.norm(points[:,:2]-[x,y],axis=1))
        handles.append({'name':'surface','source':{'view':0,'xy':(v.project(points[i:i+1])[0][0]/512*100).tolist()},
                        'target':{'view':0,'xy':(v.project(target[i:i+1])[0][0]/512*100).tolist()}})
    d={'windows':[{'view':i,'polygon':[[45,39],[61,39],[61,61],[45,61]]} for i in [0,1]],'handles':handles}
    result,report,_=getattr(module,name)(points,target,[v,v],d)
    assert report['part_points']>.5*len(points)
    assert report['affected_points']>.45*len(points)
    assert np.isfinite(result).all()
    assert np.mean(report['handle_error_after'])<np.mean(report['handle_error_before'])
