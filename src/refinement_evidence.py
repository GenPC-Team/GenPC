"""Category-independent evidence for iterative, ordered-carrier refinement.

Fixed slots and rest edges persist across rounds. Observation distances are
positive-support diagnostics, not semantic correspondences or completeness.
"""
import hashlib

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from src.deformation_graph import edge_strain
from src.zbuffer import zbuffer_depth_with_indices
from src.balanced_registration import BalancedRegistrationConfig,region_labels


def carrier_digest(points):
    """Use ordered float64 coordinates, matching the Open3D double PLY carrier."""
    return hashlib.sha256(np.asarray(points, dtype='<f8').tobytes()).hexdigest()


def rejection_evidence(geometry):
    """Retain numerical rejection criteria, omitting only bulky surface rows."""
    keys = {'operator', 'fraction', 'strain', 'hard_passed', 'gate_checks', 'criteria',
            'mean_before', 'mean_after', 'observation_mean_before', 'observation_mean_after',
            'connectivity', 'minimum_full_rank_jacobian_determinant', 'accepted', 'reason',
            'integrity_audit', 'current_regional_support', 'initial_regional_support',
            'solver_integrity_passed'}
    result = {key: ({k: v for k, v in value.items() if k != 'regions'}
                    if key.endswith('regional_support') else value)
              for key, value in geometry.items() if key in keys}
    failed = [key for key, passed in geometry.get('gate_checks', {}).items() if not passed]
    failed += [key for key in ['integrity_audit', 'current_regional_support', 'initial_regional_support']
               if geometry.get(key, {}).get('passed') is False]
    result['failed_checks'] = failed
    return result


def candidate_audit(rest, current, candidate, rest_graph, protected_ids=()):
    """Report cumulative strain; only finite data and explicit locks gate here.

    A generated prior can require substantial proportion changes. Edge-length
    percentiles are evidence for review, not universal geometric validity limits.
    """
    rest, current, candidate = (np.asarray(p) for p in (rest, current, candidate))
    if candidate.shape != rest.shape or current.shape != rest.shape:
        raise ValueError('ordered carrier slots must be preserved')
    ids = np.asarray(protected_ids, dtype=int)
    if ids.ndim != 1 or np.any(ids < 0) or np.any(ids >= len(rest)):
        raise ValueError('invalid protected slot indices')
    finite = bool(np.isfinite(candidate).all())
    exact = bool(np.array_equal(candidate[ids], rest[ids]))
    protection = {
        'count': int(len(ids)),
        'reference': 'frozen_loop_initial_carrier',
        'reference_coordinates_sha256': carrier_digest(rest[ids]),
        'candidate_coordinates_sha256': carrier_digest(candidate[ids]),
        'exactly_preserved': exact,
        'maximum_displacement': float(np.linalg.norm(candidate[ids]-rest[ids], axis=1).max()) if len(ids) else 0.,
    }
    strain = edge_strain(rest, candidate, rest_graph) if finite else None
    passed = finite and exact
    return {
        'carrier_slots': len(rest), 'finite': finite, 'protected_slots': protection,
        'cumulative_strain': strain,
        'strain_policy': 'diagnostic_only_no_absolute_stretch_threshold',
        'cumulative_reference': 'fixed edges and coordinates at start of this loop, not previous round',
        'maximum_step_displacement': float(np.linalg.norm(candidate-current, axis=1).max()),
        'passed': bool(passed),
    }


def observed_support_audit(reference, candidate, partial, camera):
    """Protect observed regional fit, without making any part immobile.

    Reuse the registration method's shared regional trust limits. The saved
    acquisition camera assigns fixed scan tiles; distances are measured in 3D.
    Unobserved complete surfaces are not penalized as missing scan data.
    """
    config = BalancedRegistrationConfig()
    uv, depth = camera.project(partial)
    _, _, index = zbuffer_depth_with_indices(uv, depth, camera.image_shape, 0)
    ids = np.unique(index[index >= 0])
    if len(ids) < 8:
        return {'passed': False, 'reason': 'insufficient saved-camera support'}
    labels = region_labels(uv[ids], config.grid_size)
    diagonal = max(float(np.linalg.norm(np.ptp(partial, axis=0))), 1e-12)
    before = cKDTree(reference).query(partial[ids])[0]/diagonal
    after = cKDTree(candidate).query(partial[ids])[0]/diagonal
    regions = []
    for label in np.unique(labels):
        use = labels == label
        if use.sum() < 8:
            continue
        regions.append({'tile': int(label), 'observations': int(use.sum()),
                        'mean_before': float(before[use].mean()),
                        'mean_after': float(after[use].mean()),
                        'regression': float((after[use]-before[use]).mean())})
    loss = np.array([r['regression'] for r in regions])
    fraction = float(np.mean(loss > config.regional_tolerance)) if len(loss) else 1.
    worst = float(loss.max()) if len(loss) else None
    passed = bool(len(loss) and fraction <= config.maximum_regressed_fraction
                  and worst <= 3*config.regional_tolerance)
    return {'passed': passed, 'normalization': 'partial_bbox_diagonal',
            'camera': 'saved_acquisition', 'regions': regions,
            'regressed_fraction': fraction, 'maximum_regression': worst,
            'regional_tolerance': config.regional_tolerance,
            'maximum_regressed_fraction': config.maximum_regressed_fraction,
            'maximum_allowed_regression': 3*config.regional_tolerance,
            'no_immobile_part_assumption': True}


def residual_regions(partial, current, candidate, views, grid_size=8):
    """Expose strongest measured gain AND regression on fixed observed tiles.

    The same physical scan is reprojected; tiles from different views are not
    independent observations. No category or generated part labels are used.
    """
    before = cKDTree(current).query(partial)[0]
    after = cKDTree(candidate).query(partial)[0]
    regions = []
    for vi, view in enumerate(views):
        uv, depth = view.project(partial)
        _, _, index = zbuffer_depth_with_indices(uv, depth, view.image_shape, 0)
        ids = np.unique(index[index >= 0])
        height, width = view.image_shape
        cell = np.clip((uv[ids]/[width, height]*grid_size).astype(int), 0, grid_size-1)
        labels = cell[:, 1]*grid_size+cell[:, 0]
        for label in np.unique(labels):
            selected = ids[labels == label]
            if len(selected) < 8:
                continue
            x, y = int(label % grid_size), int(label // grid_size)
            regions.append({
                'view': vi, 'tile': [x, y], 'observed_points': len(selected),
                'mean_before': float(before[selected].mean()),
                'mean_after': float(after[selected].mean()),
                'mean_gain': float((before[selected]-after[selected]).mean()),
                'box': [max(0, int((x-.5)*width/grid_size)), max(0, int((y-.5)*height/grid_size)),
                        min(width, int((x+1.5)*width/grid_size)), min(height, int((y+1.5)*height/grid_size))],
            })
    chosen = []
    if regions:
        best = max(regions, key=lambda r: r['mean_gain'])
        worst = min(regions, key=lambda r: r['mean_gain'])
        for role, region in [('largest_measured_gain', best), ('largest_regression_or_smallest_gain', worst)]:
            chosen.append({**region, 'role': role})
    return {
        'metric': 'observed-to-carrier nearest distance; not semantic correctness',
        'synthetic_views_are_not_independent_observations': True,
        'whole_scan_mean_before': float(before.mean()),
        'whole_scan_mean_after': float(after.mean()),
        'regions': regions, 'review_regions': chosen,
    }


def semantic_part_evidence(partial, current, candidate, views, decision):
    """Compare fixed corresponding part slots, excluding neighbouring surfaces.

    Paired windows are an MLLM hypothesis, not ground-truth segmentation.
    Keep their intersection and slot identity fixed for before/after distances.
    This prevents an unrelated nearby surface from supplying the apparent gain.
    Only observed-to-part distance is used: unseen completion is not penalized.
    """
    from matplotlib.path import Path as Polygon
    source_windows = decision.get('windows', [])
    target_windows = decision.get('target_windows', [])
    if decision.get('action') != 'DEFORM_REGION' or not source_windows or not target_windows:
        return None

    def selected(points, windows):
        use = np.ones(len(points), dtype=bool)
        for window in windows:
            view = views[window['view']]
            uv, depth = view.project(points)
            height, width = view.image_shape
            polygon = np.asarray(window['polygon'])/100*[width, height]
            use &= (depth > 0) & Polygon(polygon).contains_points(uv, radius=3)
        return use

    source = selected(current, source_windows)
    target = selected(partial, target_windows)
    report = {'part': decision.get('part'), 'source_slots': int(source.sum()),
              'observed_points': int(target.sum()),
              'metric': 'observed part to fixed corresponding prior slots, 3D distance',
              'semantic_identity_is_hypothesis': True,
              'synthetic_views_are_not_independent_observations': True,
              'review_regions': []}
    if not source.any() or not target.any():
        report['available'] = False
        return report
    before = cKDTree(current[source]).query(partial[target])[0]
    after = cKDTree(candidate[source]).query(partial[target])[0]
    report.update(available=True, mean_before=float(before.mean()), mean_after=float(after.mean()),
                  p90_before=float(np.quantile(before, .9)), p90_after=float(np.quantile(after, .9)))
    for window in source_windows:
        vi = window['view']; view = views[vi]; height, width = view.image_shape
        paired = next(w for w in target_windows if w['view'] == vi)
        points = np.r_[np.asarray(window['polygon'])/100*[width, height],
                       np.asarray(paired['polygon'])/100*[width, height],
                       view.project(candidate[source])[0]]
        low = np.maximum(0, np.floor(points.min(axis=0)-12)).astype(int)
        high = np.minimum([width, height], np.ceil(points.max(axis=0)+12)).astype(int)
        report['review_regions'].append({'view': vi, 'role': 'same_part_fixed_slots_3D',
                                        'box': [*low.tolist(), *high.tolist()],
                                        'mean_before': report['mean_before'],
                                        'mean_after': report['mean_after']})
    return report


def discover_residual_windows(partial, current, views, maximum=3, grid_size=8):
    """Choose inspection crops from observed errors, not human part hints.

    Greedy coverage discounts scan slots already represented by another crop.
    A crop is an attention cue only; semantic identity still comes from the MLLM.
    """
    distances = cKDTree(current).query(partial)[0]
    regions = residual_regions(partial, current, current, views, grid_size)['regions']
    memberships = {}
    for vi, view in enumerate(views):
        uv, depth = view.project(partial)
        _, _, index = zbuffer_depth_with_indices(uv, depth, view.image_shape, 0)
        ids = np.unique(index[index >= 0])
        height, width = view.image_shape
        cell = np.clip((uv[ids]/[width, height]*grid_size).astype(int), 0, grid_size-1)
        for region in (r for r in regions if r['view'] == vi):
            memberships[(vi, *region['tile'])] = ids[np.all(cell == region['tile'], axis=1)]
    covered = np.zeros(len(partial), dtype=bool)
    used_views = set(); chosen = []; windows = []
    for _ in range(maximum):
        eligible = [r for r in regions if r['view'] not in used_views]
        if not eligible:
            break
        def score(region):
            ids = memberships[(region['view'], *region['tile'])]
            return float(distances[ids[~covered[ids]]].sum()/len(ids))
        region = max(eligible, key=score)
        if score(region) <= 0:
            break
        chosen.append({**region, 'attention_score': score(region)})
        covered[memberships[(region['view'], *region['tile'])]] = True
        used_views.add(region['view'])
        height, width = views[region['view']].image_shape
        x0,y0,x1,y1 = np.asarray(region['box'])/[width,height,width,height]*100
        windows.append({'view': region['view'], 'polygon': [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]})
    return {'windows': windows, 'handles': [], 'regions': chosen,
            'source': 'partial_only_positive_support_residuals',
            'semantic_part_labels': False, 'ground_truth_used': False}


def render_residual_comparison(partial, current, candidate, views, regions, path):
    """Identical crops/scales, including regression, with observed points unchanged."""
    if not regions:
        return None
    side, row_height = 384, 430
    image = Image.new('RGB', (side*3, row_height*len(regions)), 'white')
    draw = ImageDraw.Draw(image)
    for row, region in enumerate(regions):
        view = views[region['view']]
        def mask(points):
            uv, depth = view.project(points)
            return zbuffer_depth_with_indices(uv, depth, view.image_shape, 1)[1]
        observed, old, new = mask(partial), mask(current), mask(candidate)
        for col, prior_mask in enumerate((None, old, new)):
            rgb = np.full((*observed.shape, 3), 250, dtype=np.uint8)
            rgb[observed] = [45, 105, 230]
            if prior_mask is not None:
                rgb[prior_mask & ~observed] = [230, 80, 80]
                rgb[prior_mask & observed] = [150, 70, 185]
            crop = Image.fromarray(rgb).crop(region['box'])
            scale = min(side/crop.width, side/crop.height)
            crop = crop.resize((round(scale*crop.width), round(scale*crop.height)), Image.Resampling.NEAREST)
            image.paste(crop, (col*side, row*row_height+40))
            draw.text((col*side+4, row*row_height+23), ('OBSERVED', 'BEFORE overlay', 'AFTER overlay')[col], fill='black')
        draw.text((4, row*row_height+4), f"View {region['view']}: {region['role']} | distance {region['mean_before']:.5f} -> {region['mean_after']:.5f}", fill='black')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path
