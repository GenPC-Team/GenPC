from types import SimpleNamespace
import json

import numpy as np
import pytest
from PIL import Image

from src.planned_local_refinement import (
    CumulativeLocalGuard, annotate_region_handles, plan_region, square_crop_projectors,
)
from src.gpt_refine_agent import GPTRefineAgent


class LinearCamera:
    image_shape = (100, 200)

    def project(self, points):
        return np.asarray(points)[:, :2], np.asarray(points)[:, 2]


def test_edge_crop_keeps_square_geometry_and_pads_instead_of_stretching():
    points = np.array([[-5., 2., 1.], [10., 12., 1.]])
    crop = square_crop_projectors([LinearCamera()], points)[0]
    assert crop.image_shape[0] == crop.image_shape[1]
    assert crop.origin[0] < 0 and crop.origin[1] < 0
    before, _ = crop.project(points)
    after, _ = crop.project(points + [3., 4., 0.])
    np.testing.assert_allclose(after-before, [[3., 4.], [3., 4.]])


def test_hidden_region_is_not_labelled_as_the_front_surface(tmp_path):
    points = np.array([[40., 40., 1.], [40., 40., 2.]])
    source = tmp_path/'before.png'
    Image.new('RGB', (1920, 782), 'white').save(source)
    hidden = (None, {'partial_ids': [1]}, np.array([0., 1.]))
    visible = (None, {'partial_ids': [0]}, np.array([1., 0.]))
    annotate_region_handles(source, tmp_path/'labels.png', points, points,
                            [LinearCamera()]*4, [hidden, visible])
    assert hidden[1]['handle_visibility'] == [[0., 0.]]*4
    assert visible[1]['handle_visibility'] == [[1., 1.]]*4


def _supported_rod():
    rng = np.random.default_rng(12)
    body = rng.normal(size=(1000, 3))*.08
    rod = np.column_stack([np.linspace(-.12, .12, 120),
                           .45+rng.normal(size=120)*.003,
                           rng.normal(size=120)*.003])
    carrier = np.r_[body, rod]
    partial = np.r_[body[::10], rod[::5]+[0., .04, 0.]]
    return carrier, partial


def test_accepted_core_can_move_rigidly_but_cannot_be_stretched_in_later_round():
    carrier, partial = _supported_rod()
    guard = CumulativeLocalGuard(carrier, partial)
    accepted = carrier.copy()
    accepted[1000:, 1] += .04
    assert guard.check(accepted)['passed']
    guard.protect_core(accepted, np.arange(1000, 1120))
    rigid_next = accepted.copy()
    rigid_next[1000:, 1] += .001
    assert guard.check(rigid_next)['passed']
    stretched = accepted.copy()
    stretched[1000:, 0] *= 1.04
    result = guard.check(stretched)
    assert not result['passed']
    assert result['reason'] == 'previous_rigid_core_deformed'


def test_cumulative_motion_is_measured_against_original_not_last_round():
    carrier, partial = _supported_rod()
    guard = CumulativeLocalGuard(carrier, partial)
    cumulative = carrier.copy()
    cumulative[1000:, 1] += .13*guard.diagonal
    assert guard.check(cumulative)['reason'] == 'cumulative_motion_limit'


@pytest.mark.parametrize('candidate_id', [0, 5])
def test_region_planner_cannot_authorize_unsupported_or_unknown_correspondence(candidate_id):
    def request(**kwargs):
        assert kwargs['instructions']
        assert kwargs['payload']['candidates'][0]['candidate_id'] == 0
        return {'decision': {'action': 'TRY_REGION', 'candidate_id': candidate_id,
                             'correspondence_supported': False}}
    agent = SimpleNamespace(_request=request)
    call = lambda: plan_region(agent, [(None, {}, None)], overview='full.png',
                                crops=['crop.png'], history=[], rounds_left=3)
    if candidate_id:
        with pytest.raises(ValueError, match='unavailable'):
            call()
    else:
        result = call()
        assert result['decision']['action'] == 'KEEP_CURRENT'
        assert result['model_decision']['action'] == 'TRY_REGION'


def test_region_schema_and_custom_instructions_work_through_shared_gpt_transport(tmp_path):
    image = tmp_path/'board.png'
    image.write_bytes(b'fake image bytes')

    def create(**kwargs):
        assert 'numbered candidate' in kwargs['instructions']
        fields = kwargs['text']['format']['schema']['required']
        decision = {key: 'visible supported region' for key in fields}
        decision.update(action='TRY_REGION', candidate_id=0, correspondence_supported=True,
                        evidence=['the observed edge and prior core agree in depth'])
        return SimpleNamespace(status='completed', output_text=json.dumps(decision), id='test')

    agent = GPTRefineAgent('test', client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    result = plan_region(agent, [(None, {}, None)], overview=image, crops=[image],
                         history=[], rounds_left=3)
    assert result['decision']['action'] == 'TRY_REGION'
