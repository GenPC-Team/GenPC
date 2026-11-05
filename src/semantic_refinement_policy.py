"""Shared planning contract for semantic refinement, independent of category."""
from src.semantic_handle_refinement import INSTRUCTIONS, schema

COMPLETION_SCHEMA = {
    'type': 'object', 'properties': {
        'action': {'type': 'string', 'enum': ['STOP', 'REASSESS']},
        'reason': {'type': 'string'},
        'evidence': {'type': 'array', 'items': {'type': 'string'}},
    }, 'required': ['action', 'reason', 'evidence'], 'additionalProperties': False,
}

COMPLETION_INSTRUCTIONS = '''Audit a proposed end to geometric refinement.
Independently inspect the entire current object across the paired views and
automatic residual crops. The planning inventory is a hypothesis, not authority.
Find any confidently corresponding part still needing meaningful correction;
distinguish missing scan data, noise and genuine pose/shape errors. Use REASSESS
if a supported actionable discrepancy or an untried appropriate route remains,
and identify the part and views concretely. Use STOP for adequate fit or only
genuinely uncertain/exhausted residuals, stating the limitation. Check natural
complete structure and attachments. Do not demand matching unobserved surfaces
to partial holes, invent fixed strain ratios, or use GT/offline metrics.'''


def planning_contract(*, observation_field=False, posterior=False, autonomous=False):
    contract = schema()
    instructions = INSTRUCTIONS + '''
Available local solvers are coherent rigid part motion and low-frequency RBF
bending/proportion correction, with smooth intrinsic attachment transitions.
Missing scan connections are unknown; visible distal surfaces can still support
a correction while an unseen connection stays complete and plausible.

For DEFORM_REGION, provide separate prior windows and observed target_windows
for the SAME physical part in the SAME TWO views. Source and target landmarks
are reprojected into both windows before solving. Never match a neighbouring
limb or opposite surface just because it is close. Use fresh grid coordinates;
zoom labels retain the original panel percentages. Include the part's attachment
boundary and exclude unrelated parts. For other actions windows may be empty.

REFINE_ALIGNMENT is a conditional tool for a shared global pose/scale offset
supported by several reliable, spatially distinct parts. A single differently
posed part should not move the whole object. The front-end registration already
provides a common frame. Do not select alignment merely to exercise the tool;
explicitly describe the common offset if it is needed.

Each proposal is checked against current and fixed initial regional observation
support, geometry integrity and whole-object structural review. Approval means
a comparison baseline, not frozen coordinates. Only explicitly listed protected
slots are immobile; zero protected slots means every part may improve.
Edge strain is descriptive, not a universal material limit. Do not invent a
1.5 expansion, 0.6 compression or other strain-ratio acceptance cutoff.

After a rejection, use its exact evidence to revise correspondence, step or
tool. Do not repeat exhausted deterministic updates at unchanged geometry.
KEEP_CURRENT requires either adequate supported fit or concrete exhaustion of
appropriate alternatives; uncertainty alone should first prompt inspection of
another supplied view or region. Semantic identity, natural complete structure,
attachments and observed depth must agree, not just projected overlap or a
global nearest-distance score. Ground truth and offline metrics are unavailable.
'''
    if observation_field:
        contract['properties']['action']['enum'].append('REFINE_OBSERVED')
        instructions += '''
REFINE_OBSERVED uses the existing narrow continuous observation field for small
distributed surface residuals when part poses are reasonable. It is a candidate
requiring the same review, not an automatic acceptance or part-correspondence
guarantee. Full, half and quarter steps are tested.
'''
    if posterior:
        contract['properties']['action']['enum'].append('UPDATE_POSTERIOR')
        instructions += '''
UPDATE_POSTERIOR uses the existing coarse-to-fine partial transport and
PosteriorAdapter with the saved acquisition camera. Consider it for broad
distributed mismatch. It is an alternative to semantic part correction and
fine observation updates, not mandatory. Do not use it to collapse unseen
complete structure into missing scan data. All proposals receive the same
fixed-reference checks and review.
'''
    if autonomous:
        issue = {'type': 'object', 'properties': {
            'part': {'type': 'string'},
            'kind': {'type': 'string', 'enum': ['global_pose', 'local_pose', 'local_shape', 'distributed_surface', 'uncertain']},
            'views': {'type': 'array', 'items': {'type': 'integer'}},
            'evidence': {'type': 'string'},
            'status': {'type': 'string', 'enum': ['actionable', 'uncertain', 'resolved']},
        }, 'required': ['part', 'kind', 'views', 'evidence', 'status'], 'additionalProperties': False}
        contract['properties']['mismatch_inventory'] = {'type': 'array', 'items': issue}
        contract['properties']['stopping_assessment'] = {'type': 'string'}
        contract['required'] += ['mismatch_inventory', 'stopping_assessment']
        instructions += '''
This run is autonomous: no human circles, part hints, previous plans or accepted
intermediate shapes are supplied. Inspect all views and build a fresh whole-object
mismatch_inventory each round, ordered by meaningful actionable discrepancy.
Track the SAME physical parts across views: repeated projections are not separate
parts. Inspect extremities, supports, terminal directions and attachment transitions
as well as the main body. Do not assume that correcting one region fixes another.
Record uncertain identity explicitly rather than inventing correspondence.

Additional automatically selected residual crops highlight positive observed
support errors. They are attention cues, NOT semantic labels or independent
measurements. Inspect the full views too: the largest geometric residual may
not be the largest semantic mismatch. A correct hidden completion is not an error
because the scan lacks it. Discover windows and surface landmarks yourself.

Choose a tool from the diagnosed error type. If a localized corresponding part
is wrong, prioritize that part and its attachment over small distributed score
gains. If multiple parts share an offset, consider alignment; if errors are
distributed with plausible part poses, consider posterior or observation updates.
After each accepted update, inspect the entire object again for remaining or new
issues. KEEP_CURRENT with no actionable inventory entries ends the run; explain
adequate fit versus exhausted/uncertain residuals in stopping_assessment. Do not
claim completeness when uncertainty remains or the iteration budget is exhausted.
'''
    else:
        instructions += '''
Optional user feedback images are correspondence hints. Infer coordinates from
the current paired grids, not from an annotated board with a different layout.
Focus on the indicated mismatch while checking the entire object for regression.
'''
    return instructions, contract
