"""Region planning and cumulative shape guards for local refinement."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from src.deformation_graph import edge_strain, local_surface_graph
from src.zbuffer import zbuffer_depth_with_indices

POLICY_VERSION = "planned_local_v2_visible_regions_fixed_rest"
REGION_INSTRUCTIONS = (
    "You plan a bounded geometric refinement of an already registered complete object. "
    "Use only the supplied observations and images. Blue is the physically observed, "
    "incomplete partial scan; red is the complete generated prior. Red-only geometry is "
    "unknown, not evidence for deletion. Purple screen overlap alone does not establish "
    "3D correspondence. Each numbered candidate pairs an observed residual region with "
    "a proposed rigid prior core. Matching numbers are hypotheses, not proof of part identity. "
    "The overview locates those hypotheses in the whole object. Additional images show "
    "each candidate in four matched square crops, with near-light/far-dark depth shading. "
    "A numbered marker is placed only on visible points of that region; it may be absent "
    "in an occluded view. Do not interpret a hidden region as the surface in front of it. "
    "Determine whether the two regions plausibly belong to the same physical structure, "
    "whether the proposed motion follows observed depth and contour evidence, and whether "
    "moving the prior core would preserve its attachment and the object's construction. "
    "Choose TRY_REGION with one supplied candidate ID when a local rigid move is supported. "
    "A small but consistent correction is valid; avoid chasing isolated scan noise. "
    "Choose KEEP_CURRENT when correspondence is ambiguous or all moves risk damaging the "
    "complete object. The geometry tool has screened observation fit and cumulative rest "
    "strain, but scalar residual improvement does not prove semantic correspondence. "
    "Explain the observed structure, the corresponding prior structure, and the visible "
    "motion evidence. Do not invent numeric transforms, new parts, coordinates, or category "
    "templates. Previously accepted rigid cores must remain coherent. Use failed attempts "
    "as evidence to avoid repeating an unsupported association. Never access GT, CD or EMD."
)


class SquareCropProjector:
    """A fixed square pixel window, padded outside the original image."""
    def __init__(self, base, origin, side):
        self.base = base
        self.origin = np.asarray(origin, dtype=float)
        self.image_shape = (int(side), int(side))

    def project(self, points):
        uv, depth = self.base.project(points)
        return uv - self.origin, depth


def square_crop_projectors(views, focus):
    crops = []
    for view in views:
        uv, z = view.project(focus)
        uv = uv[np.isfinite(uv).all(axis=1) & np.isfinite(z) & (z > 0)]
        if not len(uv):
            raise ValueError("local region has no finite positive-depth projection")
        centre = .5 * (uv.min(axis=0) + uv.max(axis=0))
        side = max(64, int(np.ceil(1.4 * np.ptp(uv, axis=0).max())))
        crops.append(SquareCropProjector(view, np.floor(centre - side / 2), side))
    return crops


def annotate_region_handles(board: Path, output: Path, partial, carrier, views, candidates):
    """Locate numbered observed/prior pairs without rescaling either canvas."""
    image = Image.open(board).convert("RGB")
    draw = ImageDraw.Draw(image)
    size, header = 320, 58
    projections = {}
    for v, view in enumerate(views):
        for col, points in enumerate((partial, carrier)):
            uv, depth = view.project(points)
            _, _, index = zbuffer_depth_with_indices(uv, depth, view.image_shape, splat_radius=1)
            visible = np.zeros(len(points), dtype=bool)
            visible[index[index >= 0]] = True
            projections[v, col] = uv, visible
    for i, (_, record, weight) in enumerate(candidates):
        regions = (np.asarray(record['partial_ids']), np.flatnonzero(weight > .999999))
        record['handle_visibility'] = []
        for v, view in enumerate(views):
            visibility = []
            for col, ids in enumerate(regions):
                uv, visible = projections[v, col]
                visible_ids = ids[visible[ids]]
                visibility.append(float(len(visible_ids)/max(len(ids), 1)))
                if not len(visible_ids):
                    continue
                location = np.median(uv[visible_ids], axis=0)
                h, w = view.image_shape
                x = (v % 2) * 3 * size + col * size + location[0] * size / w
                y = (v // 2) * (size + header) + header + location[1] * size / h
                if not (0 <= location[0] < w and 0 <= location[1] < h):
                    continue
                draw.ellipse((x-11, y-11, x+11, y+11), fill='white', outline='black', width=2)
                draw.text((x-3, y-6), str(i), fill='black')
            record['handle_visibility'].append(visibility)
    image.save(output)
    return output


def plan_region(agent, candidates, *, overview, crops, history, rounds_left):
    allowed = list(range(len(candidates)))
    schema = {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'action': {'type': 'string', 'enum': ['TRY_REGION', 'KEEP_CURRENT']},
            'candidate_id': {'type': 'integer', 'enum': [-1, *allowed]},
            'correspondence_supported': {'type': 'boolean'},
            'evidence': {'type': 'array', 'items': {'type': 'string'}},
            **{key: {'type': 'string'} for key in (
                'observed_region', 'prior_region', 'motion_evidence', 'reason')},
        },
        'required': ['action', 'candidate_id', 'correspondence_supported',
                     'observed_region', 'prior_region', 'motion_evidence', 'reason', 'evidence'],
    }
    summaries = []
    for i, (_, record, _) in enumerate(candidates):
        summaries.append({'candidate_id': i, **{key: record[key] for key in (
            'core_points', 'translation', 'local_gain', 'local_strain',
            'mean_observation_gain', 'cumulative_integrity', 'handle_visibility') if key in record}})
    result = agent._request(
        schema=schema, name='local_region_plan', instructions=REGION_INSTRUCTIONS,
        payload={'task': 'choose_supported_local_region', 'policy': POLICY_VERSION,
                 'candidates': summaries, 'recent_attempts': history[-3:],
                 'rounds_left': rounds_left,
                 'images_order': ['numbered_whole_object'] + [f'region_{i}_before' for i in allowed]},
        images=[overview, *crops])
    choice = result['decision']
    result['region_prompt_version'] = POLICY_VERSION
    if choice['action'] == 'TRY_REGION' and choice['candidate_id'] not in allowed:
        raise ValueError('planner selected an unavailable region')
    if choice['action'] == 'TRY_REGION' and not choice['correspondence_supported']:
        result['model_decision'] = dict(choice)
        choice.update(action='KEEP_CURRENT', candidate_id=-1)
    return result


class CumulativeLocalGuard:
    """Keep one rest graph and protect accepted cores across all local steps."""
    def __init__(self, reference, partial):
        self.reference = np.asarray(reference, dtype=float)
        self.partial = np.asarray(partial, dtype=float)
        self.diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-12)
        self.graph, _, _ = local_surface_graph(self.reference, neighbours=12, edge_ratio=1.85)
        coo = self.graph.tocoo()
        keep = coo.row < coo.col
        self.edges = np.column_stack((coo.row[keep], coo.col[keep]))
        self.initial_distance = cKDTree(self.reference).query(partial, workers=-1)[0]
        self.cores = []

    def protect_core(self, points, ids):
        membership = np.zeros(len(points), dtype=bool)
        membership[ids] = True
        edges = self.edges[membership[self.edges].all(axis=1)]
        length = np.linalg.norm(points[edges[:, 0]]-points[edges[:, 1]], axis=1)
        valid = length > 1e-8*self.diagonal
        self.cores.append((edges[valid], length[valid]))

    def check(self, candidate):
        if candidate.shape != self.reference.shape or not np.isfinite(candidate).all():
            return {'passed': False, 'reason': 'invalid_carrier'}
        displacement = np.linalg.norm(candidate-self.reference, axis=1)/self.diagonal
        active = displacement > 1e-10
        edges = self.graph.multiply(active[:, None]).maximum(self.graph.multiply(active[None, :]))
        strain = edge_strain(self.reference, candidate, edges)
        distance = cKDTree(candidate).query(self.partial, workers=-1)[0]
        stable = self.initial_distance <= .005*self.diagonal
        stable_loss = (float(np.quantile(distance[stable]-self.initial_distance[stable], .9))/self.diagonal
                       if stable.any() else 0.)
        core_distortion = 0.
        for core_edges, initial_length in self.cores:
            if len(core_edges):
                length = np.linalg.norm(candidate[core_edges[:, 0]]-candidate[core_edges[:, 1]], axis=1)
                core_distortion = max(core_distortion, float(np.max(np.abs(length/initial_length-1))))
        reason = 'passed'
        if displacement.max() > .12:
            reason = 'cumulative_motion_limit'
        elif strain['edge_stretch_p01'] < .75 or strain['edge_stretch_p99'] > 1.33:
            reason = 'cumulative_rest_strain'
        elif stable_loss > .002:
            reason = 'original_stable_support_regressed'
        elif distance.mean() > self.initial_distance.mean()*1.01:
            reason = 'original_observation_fit_regressed'
        elif core_distortion > .02:
            reason = 'previous_rigid_core_deformed'
        return {'passed': reason == 'passed', 'reason': reason, 'rest_strain': strain,
                'maximum_displacement_ratio': float(displacement.max()),
                'stable_support_loss_p90': stable_loss,
                'previous_core_maximum_relative_distortion': core_distortion}
