#!/usr/bin/env python3
"""Replay the opt-in sparse bridge on immutable archive inputs, without GT.

This isolates registration: it does not regenerate priors or run refinement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.pointcloud_io import load_points, write_points, write_compare
from src.ray_consistent_registration import apply_transform
from src.saved_camera import SavedCameraProjector, draw_projection_overlay
from src.sparse_observation_registration import fit_sparse_bridge, camera_bridge_rotation, refine_sparse_scale_translation, select_sparse_candidate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--datasets', nargs='+', default=['kitti', 'waymo'])
    parser.add_argument('--samples', nargs='+')
    args = parser.parse_args()
    source, output = args.archive_root.resolve(), args.output_root.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('audit output must be separate from the accepted archive')
    if output.exists():
        raise ValueError('use a fresh audit directory')
    output.mkdir(parents=True)
    rows = []
    for dataset in args.datasets:
        for case in sorted((source / dataset).iterdir()):
            if not case.is_dir() or (args.samples and case.name not in args.samples):
                continue
            sid = case.name
            p = case / 'inputs/partial' / f'{sid}.ply'
            if not p.exists():
                continue
            dest = output / dataset / sid
            dest.mkdir(parents=True)
            try:
                camera = case / 'inputs/camera' / sid
                native = case / 'registration/native'
                bridge = case / 'registration/bridge'
                q = case / 'inputs/pixal' / sid / 'pixal3d_sampled_100k.ply'
                m = native / 'pixal_native_moge_points.ply'
                ni = native / 'pixal_native_moge_info.json'
                matches_path = bridge / 'two_camera_pixal_moge_partial_to_native_moge_matches.npy'
                baseline_path = case / 'registration/final/camera1_amplified_registered_100k.ply'
                partial, prior, moge = load_points(p), load_points(q), load_points(m)
                uv = np.load(camera / 'point_uv.npy')
                projector = SavedCameraProjector.from_partial(partial, camera / 'camera.pth', padding=.15, image_shape=(512, 512), device='cpu')
                transform, report = fit_sparse_bridge(moge, partial, np.load(matches_path), uv, camera_bridge_rotation(projector))
                native_transform = np.asarray(json.loads(ni.read_text())['prior_to_native_moge'])
                total = transform @ native_transform
                result = apply_transform(prior, total)
                result, polish = refine_sparse_scale_translation(partial, result, uv, projector)
                report['positive_surface_fit'] = polish
                total = np.asarray(polish.get('transform', np.eye(4))) @ total
                baseline = load_points(baseline_path)
                candidate = result
                accept, selection = select_sparse_candidate(partial, baseline, candidate, uv)
                report['selection_guard'] = selection
                write_points(dest / 'sparse_candidate_100k.ply', candidate)
                np.save(dest / 'sparse_candidate_pixal_to_partial.npy', total)
                if not accept:
                    result = baseline
                report['selected_route'] = selection['selected']
                diagonal = float(np.linalg.norm(np.ptp(partial, axis=0)))
                def support(points):
                    distance = cKDTree(points).query(partial, workers=1)[0] / diagonal * 100
                    return {'mean_percent': float(distance.mean()), 'p95_percent': float(np.quantile(distance, .95))}
                report.update(sample=sid, dataset=dataset, status='complete', output_points=len(result),
                              baseline_observed_support=support(baseline), sparse_observed_support=support(result),
                              input_sha256={str(v): sha(v) for v in [p, q, m, ni, matches_path, camera/'camera.pth', camera/'point_uv.npy', baseline_path]},
                              warning='Observed support is not GT accuracy or semantic correctness. No refinement/fusion rerun.')
                write_points(dest / 'registered_100k.ply', result)
                write_compare(dest / 'sparse_partial_gray_prior_red.ply', partial, result)
                write_compare(dest / 'baseline_partial_gray_prior_red.ply', partial, baseline)
                draw_projection_overlay(dest/'sparse_projection.png', camera/'img.png', partial, result, projector)
                draw_projection_overlay(dest/'baseline_projection.png', camera/'img.png', partial, baseline, projector)
                # Candidate transform is explicit; the baseline's transform provenance
                # remains in the accepted registration stage, never mislabeled as ours.
                (dest/'report.json').write_text(json.dumps(report, indent=2))
                rows.append({k:report[k] for k in ['sample','dataset','status','unique_pixel_pairs','occupied_image_cells','rotation_fraction','camera_rotation_delta_degrees','baseline_observed_support','sparse_observed_support','selected_route']})
            except Exception as exc:
                rows.append({'sample':sid,'dataset':dataset,'status':'failed','error':str(exc)})
                (dest/'failure.json').write_text(json.dumps(rows[-1], indent=2))
            (output/'summary.json').write_text(json.dumps({'ground_truth_used':False,'cases':rows}, indent=2))
            print(json.dumps(rows[-1]), flush=True)
    if any(row['status'] != 'complete' for row in rows) or not rows:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
