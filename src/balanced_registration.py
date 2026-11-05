"""Experimental region-balanced, visibility-aware proper Sim(3) continuation.

No semantic labels or GT are used. Camera tiles balance positive observations;
they are not asserted to be semantic parts. Missing scan pixels stay unknown.
"""
from dataclasses import dataclass, asdict
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from src.zbuffer import zbuffer_depth_with_indices
from src.ray_consistent_registration import apply_transform


@dataclass(frozen=True)
class BalancedRegistrationConfig:
    iterations: int = 20
    grid_size: int = 8
    maximum_samples: int = 16000
    screen_weight: float = .25
    correspondence_distance: float = .08
    maximum_rotation_degrees: float = 5.
    maximum_log_scale: float = .05
    maximum_motion_ratio: float = .05
    regional_tolerance: float = .002
    maximum_regressed_fraction: float = .20


def weighted_similarity(source, target, weights):
    """Weighted Umeyama; reject insufficient spatial support instead of guessing."""
    w = np.asarray(weights, float); w = w/w.sum()
    a, b = w @ source, w @ target
    x, y = source-a, target-b
    u, s, vt = np.linalg.svd((y*w[:, None]).T @ x)
    if s[1] < max(s[0], 1e-15)*1e-6:
        raise ValueError('degenerate correspondence support')
    sign = np.ones(3); sign[-1] = np.sign(np.linalg.det(u @ vt))
    rot = (u*sign) @ vt
    scale = (s @ sign) / np.sum(w*np.sum(x*x, axis=1))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('invalid similarity')
    transform = np.eye(4); transform[:3, :3] = scale*rot
    transform[:3, 3] = b-scale*rot@a
    return transform


def visible_ids(points, projector, maximum):
    uv, depth = projector.project(points)
    _, _, index = zbuffer_depth_with_indices(uv, depth, projector.image_shape, splat_radius=0)
    ids = np.unique(index[index >= 0])
    if len(ids) > maximum:
        ids = ids[np.linspace(0, len(ids)-1, maximum, dtype=int)]
    return ids, uv


def region_labels(uv, size):
    low = uv.min(axis=0); span = np.maximum(np.ptp(uv, axis=0), 1.)
    cell = np.clip(((uv-low)/span*size).astype(int), 0, size-1)
    return cell[:, 1]*size+cell[:, 0]


def region_weights(labels, residual):
    """Unit mass per supported tile, with within-tile robust confidence."""
    w = np.zeros(len(labels))
    for label in np.unique(labels):
        ids = labels == label
        scale = max(float(np.median(residual[ids])), 1e-4)
        confidence = 1./(1.+(residual[ids]/scale)**2)
        w[ids] = confidence/confidence.sum()
    return w/w.sum()


def refine_balanced_sim3(prior, partial, projector, *, config=None,
                          reciprocal=True, balanced=True):
    config = config or BalancedRegistrationConfig()
    prior, partial = np.asarray(prior, float), np.asarray(partial, float)
    if any(x.ndim != 2 or x.shape[1] != 3 or len(x) < 8 or not np.isfinite(x).all()
           for x in (prior, partial)):
        raise ValueError('finite Nx3 clouds with at least eight points required')
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-12)
    ids, uv = visible_ids(partial, projector, config.maximum_samples)
    if len(ids) < 8:
        return prior.copy(), {'accepted':False, 'reason':'insufficient_visible_observations'}
    target = partial[ids]; pixels = uv[ids]
    labels = region_labels(pixels, config.grid_size)
    regions = np.unique(labels)
    screen = np.array([projector.image_shape[1], projector.image_shape[0]])
    features = np.c_[target/diagonal, config.screen_weight*pixels/screen]
    target_tree = cKDTree(features)
    def audit(points):
        vi, _ = visible_ids(points, projector, config.maximum_samples)
        if len(vi) < 8:
            return None
        d = cKDTree(points[vi]).query(target)[0]/diagonal
        means = np.array([d[labels == label].mean() for label in regions])
        return {'region_mean':means.tolist(), 'balanced_mean':float(means.mean()),
                'mean':float(d.mean()), 'p90':float(np.quantile(d,.9)),
                'worst_region':float(means.max())}
    before = audit(prior)
    if before is None:
        return prior.copy(), {'accepted':False, 'reason':'insufficient_visible_prior'}
    current = prior.copy(); transform = np.eye(4); history = []
    for iteration in range(config.iterations):
        qi, quv = visible_ids(current, projector, config.maximum_samples)
        q = current[qi]
        qfeatures = np.c_[q/diagonal, config.screen_weight*quv[qi]/screen]
        _, match = cKDTree(qfeatures).query(features)
        residual = np.linalg.norm(q[match]-target, axis=1)/diagonal
        valid = residual < config.correspondence_distance
        if reciprocal:
            reverse = target_tree.query(qfeatures)[1]
            valid &= reverse[match] == np.arange(len(target))
        ix = np.flatnonzero(valid)
        if len(ix) < 12 or len(np.unique(labels[ix])) < 3:
            history.append({'iteration':iteration,'stop':'insufficient_distributed_correspondences'});break
        weights = (region_weights(labels[ix], residual[ix]) if balanced
                   else 1./(1.+(residual[ix]/max(np.median(residual[ix]),1e-4))**2))
        try:
            step = weighted_similarity(q[match[ix]], target[ix], weights)
        except ValueError:
            history.append({'iteration':iteration,'stop':'degenerate_correspondences'});break
        scale = np.cbrt(np.linalg.det(step[:3,:3]))
        rotvec = Rotation.from_matrix(step[:3,:3]/scale).as_rotvec()
        centre = np.average(q[match[ix]], axis=0, weights=weights)
        shift = apply_transform(centre[None], step)[0]-centre
        previous = audit(current); trials=[]; accepted=False
        for fraction in (1., .5, .25, .125):
            delta=np.eye(4); delta[:3,:3]=np.exp(fraction*np.log(scale))*Rotation.from_rotvec(fraction*rotvec).as_matrix()
            delta[:3,3]=centre+fraction*shift-delta[:3,:3]@centre
            total=delta@transform
            s=np.cbrt(np.linalg.det(total[:3,:3])); angle=np.rad2deg(Rotation.from_matrix(total[:3,:3]/s).magnitude())
            candidate=apply_transform(prior,total)
            motion=float(np.linalg.norm(candidate-prior,axis=1).max()/diagonal)
            if angle>config.maximum_rotation_degrees or abs(np.log(s))>config.maximum_log_scale or motion>config.maximum_motion_ratio:
                trials.append({'fraction':fraction,'rejected':'total_trust_region'});continue
            score=audit(candidate)
            if score is None:continue
            losses=np.array(score['region_mean'])-np.array(before['region_mean'])
            regressed=float(np.mean(losses>config.regional_tolerance))
            ok=(score['balanced_mean'] < previous['balanced_mean']-1e-6
                and score['mean']<=before['mean']*1.01+1e-6
                and score['p90']<=before['p90']*1.01+1e-6
                and regressed<=config.maximum_regressed_fraction
                and losses.max()<=3*config.regional_tolerance)
            trials.append({'fraction':fraction,'accepted':bool(ok),'score':score,'regressed_fraction':regressed})
            if ok:
                current,transform=candidate,total;accepted=True;break
        history.append({'iteration':iteration,'pairs':len(ix),'regions':len(np.unique(labels[ix])), 'trials':trials})
        if not accepted:break
    after=audit(current)
    report={'method':'visible_reciprocal_region_balanced_sim3_v1','ground_truth_used':False,
            'config':asdict(config),'reciprocal':reciprocal,'balanced':balanced,
            'accepted':bool(not np.allclose(transform,np.eye(4),atol=1e-12)),
            'transform':transform.tolist(),'region_ids':regions.tolist(),
            'before':before,'after':after,'history':history}
    return current,report
