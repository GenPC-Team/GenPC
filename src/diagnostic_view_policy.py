"""Dataset-independent diagnostic extension; no object labels or GT inputs."""
import copy
import numpy as np
from src.multiview_diagnostics import look_at_pose,rotate_about_axis


def fixed_six_view_manifest(manifest):
    """Preserve four existing views and append fixed +/-35 degree elevations.

    The first camera's right axis defines elevation. All positions, centre,
    distance and intrinsics come from the existing manifest, never a part.
    """
    if len(manifest['views'])!=4:raise ValueError('four source diagnostic views required')
    result=copy.deepcopy(manifest);centre=np.asarray(manifest['centre'],float)
    first=np.asarray(manifest['views'][0]['camera_pose'],float)
    offset=first[:3,3]-centre;right=first[:3,0];up=first[:3,1]
    for angle in (-35.,35.):
        direction=rotate_about_axis(offset,right,angle)
        pose=look_at_pose(centre+direction,centre,rotate_about_axis(up,right,angle))
        result['views'].append({'name':f'fixed_elevation_{angle:+g}','camera_pose':pose.tolist(),'elevation_degrees_relative_to_reference':angle,'synthetic_diagnostic_only':True})
    result['diagnostic_view_policy']='preserve_four_plus_fixed_elevation_pair_v1'
    result['additional_observed_geometry']=False
    result['ground_truth_used']=False
    return result
