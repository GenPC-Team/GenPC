import numpy as np
from scipy import sparse

from src.refinement_evidence import candidate_audit, carrier_digest, residual_regions,observed_support_audit,semantic_part_evidence,discover_residual_windows
from src.multiview_partial_evidence import PoseProjector
from src.multiview_diagnostics import look_at_pose


def test_cumulative_strain_is_recorded_without_universal_rejection_ratio():
    rest = np.c_[np.arange(30.), np.zeros((30, 2))]
    graph = sparse.diags([np.ones(29), np.ones(29)], [-1, 1]).tocsr()
    current, candidate = rest*1.3, rest*1.3**2
    assert candidate_audit(rest, rest, current, graph)['passed']
    assert candidate_audit(current, current, candidate, graph)['passed']
    audit=candidate_audit(rest,current,candidate,graph)
    assert audit['passed']
    assert np.isclose(audit['cumulative_strain']['edge_stretch_p99'],1.69)
    assert candidate_audit(rest,rest,rest*.5,graph)['passed']
    assert audit['strain_policy']=='diagnostic_only_no_absolute_stretch_threshold'


def test_protection_compares_frozen_reference_not_previous_step():
    rest = np.c_[np.arange(30.), np.zeros((30, 2))]
    graph = sparse.diags([np.ones(29), np.ones(29)], [-1, 1]).tocsr()
    moved = rest+[0, .00001, 0]
    audit = candidate_audit(rest, moved, moved, graph, [0, 1])
    assert not audit['passed']
    assert not audit['protected_slots']['exactly_preserved']
    assert candidate_audit(rest, rest, rest, graph, [0, 1])['passed']


def test_repetition_key_uses_output_precision_and_preserves_slot_identity():
    points = np.random.default_rng(41).normal(size=(20, 3))
    assert carrier_digest(points) == carrier_digest(np.asfortranarray(points))
    assert carrier_digest(points) != carrier_digest(points[::-1])


def test_local_evidence_includes_regression_not_only_improvement():
    x, y = np.meshgrid(np.linspace(-1, 1, 40), np.linspace(-1, 1, 40))
    partial = np.c_[x.ravel(), y.ravel(), np.zeros(x.size)]
    before = partial+[0, 0, .05]
    after = partial.copy();after[:, 2] = np.where(partial[:, 0]<0, .01, .09)
    view = PoseProjector(look_at_pose(np.array([0.,0,4]), np.zeros(3), np.array([0.,1,0])), 38., 512)
    audit = residual_regions(partial, before, after, [view])
    assert audit['review_regions'][0]['mean_gain'] > 0
    assert audit['review_regions'][1]['mean_gain'] < 0


def test_regional_gate_allows_motion_but_rejects_hidden_local_regression():
    x,y=np.meshgrid(np.linspace(-1,1,40),np.linspace(-1,1,40))
    partial=np.c_[x.ravel(),y.ravel(),np.zeros(x.size)]
    reference=partial+[0,0,.1]
    view=PoseProjector(look_at_pose(np.array([0.,0,4]),np.zeros(3),np.array([0.,1,0])),38.,512)
    improved=partial+[0,0,.01]
    assert observed_support_audit(reference,improved,partial,view)['passed']
    # Better global fit must not conceal a newly worsened local observed region.
    regressed=improved.copy();regressed[partial[:,0]>.5,2]=.18
    audit=observed_support_audit(reference,regressed,partial,view)
    assert not audit['passed']
    assert audit['maximum_regression']>audit['maximum_allowed_regression']


def test_semantic_part_distance_does_not_match_neighbouring_surface():
    class Camera:
        image_shape = (512, 512)
        def project(self, points):
            return points[:, :2]*100+256, points[:, 2]+3
    x,y=np.meshgrid(np.linspace(0,.1,10),np.linspace(0,.1,10))
    partial=np.c_[x.ravel(),y.ravel(),np.zeros(x.size)]
    current=np.r_[partial+[.5,0,0],partial]  # Wrong part coincides with scan.
    candidate=current.copy();candidate[:len(partial)]-= [.5,0,0]
    def windows(lo,hi):
        return [{'view':v,'polygon':[[lo,49],[hi,49],[hi,54],[lo,54]]} for v in [0,1]]
    decision={'action':'DEFORM_REGION','part':'test part','windows':windows(59,63),
              'target_windows':windows(49,54)}
    result=semantic_part_evidence(partial,current,candidate,[Camera(),Camera()],decision)
    assert result['source_slots']==len(partial)
    assert result['mean_before']>.3
    assert result['mean_after']<1e-12
    assert len(result['review_regions'])==2


def test_autonomous_attention_finds_supported_error_without_part_labels():
    x,y=np.meshgrid(np.linspace(-1,1,40),np.linspace(-1,1,40))
    partial=np.c_[x.ravel(),y.ravel(),np.zeros(x.size)]
    current=partial.copy();current[:,2]=np.where(partial[:,0]>.5,.2,.001)
    camera=PoseProjector(look_at_pose(np.array([0.,0,4]),np.zeros(3),np.array([0.,1,0])),38.,512)
    result=discover_residual_windows(partial,current,[camera],maximum=3)
    assert result['regions'][0]['mean_before']>.1
    assert len(result['windows'])==1
    assert not result['semantic_part_labels']
    assert not result['ground_truth_used']
