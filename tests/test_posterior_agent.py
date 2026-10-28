"""Decision contracts for the isolated posterior agent experiment."""

from src.posterior_agent import Observation, decide_next, verify_update


def observation(coverage, p90):
    return Observation(tuple(coverage), (.01,) * 4, p90, 1.5 * p90, p90 / 2)


def test_agent_stops_when_observation_plateaus():
    before = observation((.80, .80, .80, .80), .04)
    after = observation((.801, .801, .801, .801), .0398)
    assert decide_next(after, before, round_index=1, maximum_rounds=3).action == "ACCEPT"


def test_agent_uses_expansive_profile_for_supported_remaining_residual():
    before = observation((.70, .70, .70, .70), .05)
    after = observation((.75, .75, .75, .75), .04)
    decision = decide_next(after, before, round_index=1, maximum_rounds=3)
    assert (decision.action, decision.profile) == ("UPDATE_POSTERIOR", "EXPANSIVE")


def test_agent_rebuilds_correspondence_from_four_views_when_evidence_disagrees():
    current = observation((.60, .85, .82, .83), .045)
    decision = decide_next(current, None, round_index=0, maximum_rounds=3)
    assert (decision.action, decision.transport) == ("UPDATE_POSTERIOR", "ALL_ACTIVE_VIEWS")


def test_agent_routes_local_residual_tail_to_observation_field():
    prior = Observation((.9,) * 4, (.01,) * 4, .011, .018, .005)
    current = Observation((.92,) * 4, (.01,) * 4, .007, .037, .003)
    decision = decide_next(current, prior, round_index=2, maximum_rounds=3)
    assert (decision.action, decision.profile) == ("REFINE_OBSERVED", "OBSERVATION_FIELD")


def test_agent_keeps_full_transport_for_broad_residual():
    prior = Observation((.9,) * 4, (.01,) * 4, .011, .018, .005)
    current = Observation((.92,) * 4, (.01,) * 4, .007, .019, .003)
    assert decide_next(current, prior, round_index=2, maximum_rounds=3).action == "UPDATE_POSTERIOR"


def test_verifier_rejects_single_view_regression_and_carrier_breakage():
    before = observation((.80, .80, .80, .80), .04)
    unsafe_view = observation((.77, .90, .90, .90), .035)
    assert verify_update(before, unsafe_view, {"integrity": {"passed": True}}).action == "ROLLBACK"
    assert verify_update(before, observation((.85,) * 4, .035),
                         {"integrity": {"passed": False}}).action == "ROLLBACK"
    assert verify_update(before, observation((.85,) * 4, .035),
                         {"integrity": {"passed": True}},
                         reference_coverage=.88).reason == "reference_prior_coverage_regressed"


def test_verifier_accepts_supported_improvement():
    before = observation((.80,) * 4, .04)
    after = observation((.82,) * 4, .035)
    assert verify_update(before, after, {"integrity": {"passed": True}}).action == "ACCEPT_UPDATE"
