from src.semantic_refinement_policy import planning_contract


def test_autonomous_contract_requires_inventory_and_conditioned_alignment():
    prompt, schema = planning_contract(observation_field=True, posterior=True, autonomous=True)
    assert 'mismatch_inventory' in schema['required']
    assert 'stopping_assessment' in schema['required']
    assert set(schema['properties']['action']['enum']) == {
        'DEFORM_REGION', 'REFINE_ALIGNMENT', 'KEEP_CURRENT', 'REFINE_OBSERVED', 'UPDATE_POSTERIOR'}
    assert 'spatially distinct parts' in prompt
    assert 'no human circles' in prompt
    assert 'Ground truth and offline metrics are unavailable' in prompt


def test_assisted_contract_does_not_mutate_later_autonomous_schema():
    _, assisted = planning_contract()
    _, autonomous = planning_contract(posterior=True, autonomous=True)
    assert 'mismatch_inventory' not in assisted['required']
    assert 'UPDATE_POSTERIOR' not in assisted['properties']['action']['enum']
    assert 'mismatch_inventory' in autonomous['required']
