"""Bounded camera-aware 2D+3D residual Sim(3) after the MoGe bridge.

Visibility and nearest-neighbour identities are refreshed without gradients;
the residual proper similarity and the exact saved-camera projection are
differentiable. Only positive partial observations contribute data terms.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import numpy as np
from scipy.spatial import cKDTree
import torch
from torch.nn import functional as F

from src.bidirectional_cycle_registration import prepare_visible_target, visible_score
from src.zbuffer import zbuffer_depth_with_indices


@dataclass(frozen=True)
class DifferentiableRegistrationConfig:
    steps: int = 120
    learning_rate: float = .005
    prior_samples: int = 16000
    partial_samples: int = 2048
    maximum_rotation_degrees: float = 15.
    maximum_log_scale: float = .15
    maximum_translation_ratio: float = .12
    screen_weight: float = .25
    minimum_relative_gain: float = .01


def residual_sim3(parameters, centre, diagonal):
    """A proper isotropic similarity, differentiable also at zero rotation."""
    x,y,z = parameters[:3].unbind()
    zero = x*0.
    skew = torch.stack((zero,-z,y,z,zero,-x,-y,x,zero)).reshape(3,3)
    linear = torch.exp(parameters[3])*torch.matrix_exp(skew)
    translation = centre-linear@centre+diagonal*parameters[4:]
    return linear,translation


def positive_registration_objective(mean_distance: float, projection: dict) -> float:
    """Missing scan pixels are unknown, so IoU/leakage are not penalties."""
    return (float(mean_distance) + .10*(1.-projection['coverage'])
            + .25*min(projection['visible_depth_normalized'], .20))


def refine_differentiable_sim3(prior, partial, projector, *, device='cuda', config=None):
    config = config or DifferentiableRegistrationConfig()
    prior,partial = (np.asarray(x,dtype=np.float64) for x in (prior,partial))
    if min(len(prior),len(partial)) < 8 or not np.isfinite(prior).all() or not np.isfinite(partial).all():
        raise ValueError('finite nontrivial point clouds are required')
    diagonal = max(float(np.linalg.norm(np.ptp(partial,axis=0))),1e-12)
    qids = np.linspace(0,len(prior)-1,min(len(prior),config.prior_samples),dtype=int)
    pids = np.linspace(0,len(partial)-1,min(len(partial),config.partial_samples),dtype=int)
    q = torch.as_tensor(prior[qids],device=device,dtype=torch.float32)
    p = torch.as_tensor(partial[pids],device=device,dtype=torch.float32)
    centre = q.mean(dim=0)
    parameters = torch.zeros(7,device=device,requires_grad=True)
    optimizer = torch.optim.Adam([parameters],lr=config.learning_rate)
    screen_scale = p.new_tensor([projector.image_shape[1]-1,projector.image_shape[0]-1])
    p_uv,_ = projector.project_tensor(p)
    p_uv = p_uv.detach()/screen_scale
    best_loss = float('inf')
    best = parameters.detach().clone()
    history = []
    for step in range(config.steps):
        linear,translation = residual_sim3(parameters,centre,diagonal)
        current = q@linear.T+translation
        if step % 5 == 0:
            uv,depth = projector.project(current.detach().cpu().numpy())
            _,_,index = zbuffer_depth_with_indices(uv,depth,projector.image_shape,splat_radius=1)
            visible = np.unique(index[index>=0])
            if len(visible) < 8:
                break
            visible_ids = torch.as_tensor(visible,device=device,dtype=torch.long)
        visible_points = current[visible_ids]
        current_uv,_ = projector.project_tensor(visible_points)
        current_uv = current_uv/screen_scale
        # Assignment is piecewise constant; differentiating only selected
        # distances avoids retaining a large cdist backward matrix.
        with torch.no_grad():
            nn3 = torch.cdist(p/diagonal,visible_points/diagonal).argmin(dim=1)
            nn2 = torch.cdist(p_uv,current_uv).argmin(dim=1)
        d3 = torch.linalg.vector_norm((p-visible_points[nn3])/diagonal,dim=1)
        d2 = torch.linalg.vector_norm(p_uv-current_uv[nn2],dim=1)
        loss3 = F.smooth_l1_loss(d3,torch.zeros_like(d3),beta=.02,reduction='none')
        loss2 = F.smooth_l1_loss(d2,torch.zeros_like(d2),beta=.02,reduction='none')
        keep = max(8,int(.9*len(p)))
        data = loss3.sort().values[:keep].mean()+config.screen_weight*loss2.sort().values[:keep].mean()
        loss = data + .001*parameters.square().sum()
        value = float(data.detach())
        if np.isfinite(value) and value < best_loss:
            best_loss = value
            best = parameters.detach().clone()
        if step % 10 == 0:
            history.append({'step':step,'data_loss':value,'visible_prior_points':len(visible)})
        optimizer.zero_grad()
        loss.backward()
        if not torch.isfinite(parameters.grad).all():
            break
        optimizer.step()
        with torch.no_grad():
            angle = parameters[:3].norm().clamp_min(1e-12)
            parameters[:3] *= torch.clamp(math.radians(config.maximum_rotation_degrees)/angle,max=1.)
            parameters[3].clamp_(-config.maximum_log_scale,config.maximum_log_scale)
            length = parameters[4:].norm().clamp_min(1e-12)
            parameters[4:] *= torch.clamp(config.maximum_translation_ratio/length,max=1.)
    linear,translation = residual_sim3(best,centre,diagonal)
    transform = np.eye(4)
    transform[:3,:3] = linear.detach().cpu().numpy()
    transform[:3,3] = translation.detach().cpu().numpy()
    candidate = prior@transform[:3,:3].T+transform[:3,3]
    cache = prepare_visible_target(partial,projector)
    before = visible_score(partial,prior,projector,diagonal,target_cache=cache)
    after = visible_score(partial,candidate,projector,diagonal,target_cache=cache)
    old_distance = cKDTree(prior).query(partial,workers=-1)[0]/diagonal
    new_distance = cKDTree(candidate).query(partial,workers=-1)[0]/diagonal
    before_positive=positive_registration_objective(old_distance.mean(),before['projection'])
    after_positive=positive_registration_objective(new_distance.mean(),after['projection'])
    accepted = bool(
        after_positive < before_positive*(1-config.minimum_relative_gain)
        and new_distance.mean() < old_distance.mean()*(1-config.minimum_relative_gain)
        and np.quantile(new_distance,.9) <= np.quantile(old_distance,.9)*1.01
        and after['projection']['coverage'] >= before['projection']['coverage']-.02)
    report = {'method':'bounded_differentiable_positive_2d_3d_sim3',
              'ground_truth_used':False,'config':asdict(config),'accepted':accepted,
              'history':history,'candidate_transform':transform.tolist(),
              'before':{'visible_objective':float(before['objective']),
                        'positive_objective':before_positive,
                        'visible_depth':float(before['projection']['visible_depth_normalized']),
                        'mean_distance':float(old_distance.mean()),'p90':float(np.quantile(old_distance,.9)),
                        'coverage':float(before['projection']['coverage'])},
              'after':{'visible_objective':float(after['objective']),
                       'positive_objective':after_positive,
                       'visible_depth':float(after['projection']['visible_depth_normalized']),
                       'mean_distance':float(new_distance.mean()),'p90':float(np.quantile(new_distance,.9)),
                       'coverage':float(after['projection']['coverage'])}}
    return (candidate if accepted else prior.copy()),report
