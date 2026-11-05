import numpy as np
import torch

from src.saved_camera import SavedCameraProjector
from src.differentiable_registration import residual_sim3, refine_differentiable_sim3, DifferentiableRegistrationConfig
from src.differentiable_registration import positive_registration_objective


def test_pinhole_tensor_projection_matches_saved_pixels_and_has_gradients():
    projector = SavedCameraProjector(None,(0,0),1,padding=.15,image_shape=(320,480),
        pinhole_intrinsic=np.array([[400,0,320],[0,410,240],[0,0,1]]),
        pinhole_world_to_camera=np.eye(4),pinhole_image_shape=(480,640))
    points = torch.tensor([[.1,.2,2.],[-.3,.4,3.]],dtype=torch.float64,requires_grad=True)
    uv,depth = projector.project_tensor(points)
    ref_uv,ref_depth = projector.project(points.detach().numpy())
    np.testing.assert_allclose(uv.detach(),ref_uv,atol=1e-9)
    np.testing.assert_allclose(depth.detach(),ref_depth,atol=1e-9)
    assert torch.autograd.gradcheck(lambda p: projector.project_tensor(p)[0],points)


def test_normalized_tensor_projection_matches_existing_camera_contract():
    class Camera:
        def transform(self,p):
            return p*2 + p.new_tensor([.1,.2,1.])
    projector = SavedCameraProjector(Camera(),(.2,.3),2,padding=.15,image_shape=(128,128))
    points = torch.tensor([[.1,.2,2.],[-.3,.4,3.]],requires_grad=True)
    uv,depth = projector.project_tensor(points)
    ref_uv,ref_depth = projector.project(points.detach().numpy())
    np.testing.assert_allclose(uv.detach(),ref_uv,atol=1e-5)
    np.testing.assert_allclose(depth.detach(),ref_depth,atol=1e-5)
    uv.sum().backward()
    assert torch.isfinite(points.grad).all()
    assert torch.count_nonzero(points.grad) == 4


def test_similarity_has_finite_derivative_at_identity_and_no_shear():
    parameters=torch.zeros(7,dtype=torch.float64,requires_grad=True)
    centre=torch.tensor([1.,2.,3.],dtype=torch.float64)
    assert torch.autograd.gradcheck(lambda p: residual_sim3(p,centre,2.),parameters)
    linear,_=residual_sim3(parameters+parameters.new_tensor([.1,.2,.3,.1,.1,0,0]),centre,2.)
    product=linear.T@linear
    torch.testing.assert_close(product,torch.eye(3,dtype=torch.float64)*torch.exp(parameters.new_tensor(.2)))


def test_differentiable_residual_recovers_small_global_offset():
    rng=np.random.default_rng(5)
    prior=rng.normal(size=(256,3))
    prior=prior/np.linalg.norm(prior,axis=1,keepdims=True)*[.3,.2,.1]+[0,0,2.]
    partial=prior+[.02,-.01,.015]
    projector=SavedCameraProjector(None,(0,0),1,padding=.15,image_shape=(64,64),
        pinhole_intrinsic=np.array([[100,0,32],[0,100,32],[0,0,1]]),
        pinhole_world_to_camera=np.eye(4),pinhole_image_shape=(64,64))
    result,report=refine_differentiable_sim3(prior,partial,projector,device='cpu',
        config=DifferentiableRegistrationConfig(steps=60,prior_samples=256,partial_samples=256))
    assert report['accepted']
    assert report['after']['mean_distance'] < .5*report['before']['mean_distance']
    assert result.shape==prior.shape


def test_unobserved_complete_surface_does_not_count_as_registration_error():
    projection={'coverage':.95,'visible_depth_normalized':.01,'iou':.8,'leakage':.1}
    other={**projection,'iou':.3,'leakage':.7}
    assert positive_registration_objective(.01,projection)==positive_registration_objective(.01,other)
