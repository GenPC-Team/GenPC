"""The GPT controller must actually call a vision model and obey its schema."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

import src.gpt_refine_agent as refine_module

from src.gpt_refine_agent import (
    GPTRefineAgent, next_plateau_streak, render_diagnostic_board,
    visible_partial_fraction,
)
from src.posterior_agent import Observation


def test_codex_refinement_retries_transient_error_event(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert "model_reasoning_effort=low" in command
        answer = Path(command[command.index("--output-last-message") + 1])
        answer.write_text('{"action": "STOP"}')
        events = [{"type": "thread.started", "thread_id": "test"}]
        if len(calls) == 1:
            events.append({"type": "item.completed", "item": {"type": "error"}})
        events.append({"type": "turn.completed"})
        return SimpleNamespace(returncode=0, stderr="", stdout="\n".join(map(json.dumps, events)))

    monkeypatch.setattr(refine_module.subprocess, "run", fake_run)
    monkeypatch.setattr(refine_module.time, "sleep", lambda _: None)
    agent = object.__new__(GPTRefineAgent)
    agent.model = "test"
    result = agent._request_codex({}, {}, [])
    assert json.loads(result["text"]) == {"action": "STOP"}
    assert len(calls) == 2


def test_codex_timeout_discards_partial_answer_and_retries(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(kwargs)
        answer = Path(command[command.index("--output-last-message") + 1])
        assert not answer.exists(), "a stale partial answer must not survive retry"
        if len(calls) == 1:
            answer.write_text('{"action": "UNFINISHED"}')
            raise refine_module.subprocess.TimeoutExpired(command, kwargs['timeout'],
                                                          output=b'{"type":"thread.started"}\n')
        answer.write_text('{"action": "STOP"}')
        return SimpleNamespace(returncode=0, stderr='', stdout='{"type":"turn.completed"}\n')

    monkeypatch.setenv('COMPAGENT_CODEX_TIMEOUT_SECONDS', '610')
    monkeypatch.setattr(refine_module.subprocess, 'run', fake_run)
    monkeypatch.setattr(refine_module.time, 'sleep', lambda _: None)
    agent = object.__new__(GPTRefineAgent); agent.model = 'test'
    result = agent._request_codex({}, {}, [])
    assert json.loads(result['text']) == {'action': 'STOP'}
    assert result['transport'] == {'attempts': 2, 'timeouts': 1, 'timeout_seconds': 610}
    assert calls[0]['input'] == calls[1]['input']


def test_codex_timeouts_are_bounded_and_never_accept_partial_answer(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[command.index('--output-last-message') + 1]).write_text('{"action":"STOP"}')
        raise refine_module.subprocess.TimeoutExpired(command, kwargs['timeout'])

    monkeypatch.setattr(refine_module.subprocess, 'run', fake_run)
    monkeypatch.setattr(refine_module.time, 'sleep', lambda _: None)
    agent = object.__new__(GPTRefineAgent); agent.model = 'test'
    with pytest.raises(RuntimeError, match='timed out'):
        agent._request_codex({}, {}, [])
    assert len(calls) == 3


class FakeProjector:
    image_shape = (32, 32)

    def project(self, points):
        return points[:, :2] * 20 + 8, np.ones(len(points), dtype=np.float64)


class FakeResponses:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(status="completed", output_text=json.dumps(next(self.answers)),
                               id=f"mock-{len(self.calls)}", model=kwargs["model"])


def test_local_review_cannot_accept_an_unverified_attachment(tmp_path):
    path=tmp_path/'board.png'
    Image.new('RGB',(64,64),'white').save(path)
    responses=FakeResponses([{'action':'ACCEPT_UPDATE','reason':'fit improved','evidence':[],
        'local_structure':{'correspondence_supported':True,'core_shape_preserved':True,
            'attachment_preserved':False,'unaffected_parts_preserved':True,
            'observed_region_description':'thin observed extension',
            'prior_region_description':'nearby thin extension',
            'motion_direction_evidence':'toward blue support','uncertainty':'attachment unclear'}}])
    agent=GPTRefineAgent('test',client=SimpleNamespace(responses=responses))
    result=agent.review(_observation(),_observation(),before_board=path,after_board=path,
        profile='LOCAL_RIGID_TRANSLATION',transport='COHERENT_PARTIAL_RESIDUAL',
        integrity={'passed':True},local_boards=(path,path),local_diagnostics={})
    assert result['decision']['action']=='STOP_KEEP_CURRENT'
    assert result['model_decision']['action']=='ACCEPT_UPDATE'


def _observation():
    return Observation((.8, .75, .7, .78), (.03, .04, .05, .02), .025, .055, .004)


def test_evidence_driven_plateau_requires_two_weak_accepted_steps():
    first = Observation((.90,) * 4, (.03,) * 4, .0100, .025, .003)
    weak_one = Observation((.902,) * 4, (.03,) * 4, .0098, .0245, .003)
    weak_two = Observation((.904,) * 4, (.03,) * 4, .0096, .0240, .003)
    strong = Observation((.910,) * 4, (.03,) * 4, .0080, .020, .002)
    tail_gain = Observation((.905,) * 4, (.03,) * 4, .0095, .0220, .003)
    assert next_plateau_streak(first, weak_one, 0) == 1
    assert next_plateau_streak(weak_one, weak_two, 1) == 2
    assert next_plateau_streak(weak_two, strong, 2) == 0
    assert next_plateau_streak(weak_two, tail_gain, 2) == 0


def test_gpt_plan_and_review_use_images_and_structured_outputs(tmp_path):
    points = np.array([[.1, .2, .3], [.5, .6, .7], [.8, .4, .2]])
    board = render_diagnostic_board(points, points + .03,
                                    [FakeProjector()] * 4, tmp_path / "board.png")
    assert board.is_file()
    pixels = np.asarray(Image.open(board))
    assert pixels.shape[1] == 1920
    assert np.any(np.all(pixels[58:378, 0:320] == (38, 103, 224), axis=2))
    assert np.any(np.all(pixels[58:378, 320:640] == (224, 51, 47), axis=2))
    assert not np.any(np.all(pixels[58:378, 0:320] == (224, 51, 47), axis=2))
    assert visible_partial_fraction(points, [FakeProjector()] * 4) == 1.0
    responses = FakeResponses([
        {"action": "UPDATE_POSTERIOR", "profile": "BALANCED",
         "transport": "ALL_ACTIVE_VIEWS", "view_strategy": "ADAPTIVE_ORBIT",
         "reason": "coherent offset in two views",
         "evidence": ["blue-only band in two views"]},
        {"action": "ACCEPT_UPDATE", "reason": "coverage improves without a broken silhouette",
         "evidence": ["four-view overlap increased"]},
    ])
    agent = GPTRefineAgent("test-gpt-model", client=SimpleNamespace(responses=responses))
    decision, plan = agent.plan(_observation(), None, round_index=0,
                                maximum_rounds=3, board=board, recent_trace=[],
                                view_options={"SAVED_FOUR": {"unique_visible_partial_fraction": .8},
                                              "ADAPTIVE_ORBIT": {"unique_visible_partial_fraction": .9}})
    review = agent.review(_observation(), _observation(), before_board=board,
                          after_board=board, profile="BALANCED",
                          transport="ALL_ACTIVE_VIEWS", integrity={"passed": True})
    assert decision.action == "UPDATE_POSTERIOR"
    assert decision.transport == "ALL_ACTIVE_VIEWS"
    assert plan["decision"]["view_strategy"] == "ADAPTIVE_ORBIT"
    assert plan["response_id"] == "mock-1"
    assert review["decision"]["action"] == "ACCEPT_UPDATE"
    assert len(responses.calls) == 2
    assert responses.calls[0]["text"]["format"]["type"] == "json_schema"
    assert responses.calls[0]["input"][0]["content"][1]["image_url"].startswith(
        "data:image/png;base64,"
    )
    assert len(responses.calls[1]["input"][0]["content"]) == 3
    assert "ground_truth" not in str(responses.calls[0]["input"])
    assert '"unique_visible_partial_fraction": 0.9' in responses.calls[0]["input"][0]["content"][0]["text"]
    assert '"A": "observed physical partial point cloud' in responses.calls[0]["input"][0]["content"][0]["text"]


def test_structured_route_is_only_offered_when_enabled(tmp_path):
    board = tmp_path / "board.png"
    board.write_bytes(b"mock-image")
    choice = {"action": "STRUCTURED_DEFORMATION", "profile": "BALANCED",
              "transport": "CAMERA1", "view_strategy": "SAVED_FOUR",
              "reason": "coherent residual remains", "evidence": ["blue-only extent in two views"]}
    responses = FakeResponses([choice, choice])
    agent = GPTRefineAgent("test-gpt-model", client=SimpleNamespace(responses=responses))
    with pytest.raises(ValueError, match="invalid action"):
        agent.plan(_observation(), None, round_index=0, maximum_rounds=3,
                   board=board, recent_trace=[], structural_available=False)
    decision, _ = agent.plan(_observation(), None, round_index=0, maximum_rounds=3,
                             board=board, recent_trace=[], structural_available=True)
    assert decision.action == "STRUCTURED_DEFORMATION"
    assert "STRUCTURED_DEFORMATION" in responses.calls[1]["text"]["format"]["schema"]["properties"]["action"]["enum"]


def test_gpt_backend_requires_credentials_and_rejects_invalid_action(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        GPTRefineAgent("test-gpt-model")
    board = tmp_path / "board.png"
    board.write_bytes(b"not-a-real-image-but-sufficient-for-a-mocked-request")
    responses = FakeResponses([{"action": "DELETE_POINTS", "profile": "BALANCED",
                                "transport": "CAMERA1", "view_strategy": "SAVED_FOUR",
                                "reason": "invalid", "evidence": []}])
    agent = GPTRefineAgent("test-gpt-model", client=SimpleNamespace(responses=responses))
    with pytest.raises(ValueError, match="invalid action"):
        agent.plan(_observation(), None, round_index=0,
                   maximum_rounds=3, board=board, recent_trace=[])


def test_last_candidate_review_cannot_request_unavailable_next_route(tmp_path):
    board = tmp_path / "board.png"
    board.write_bytes(b"mock-image")
    responses = FakeResponses([
        {"action": "TRY_NEXT_CANDIDATE", "reason": "try another route", "evidence": []},
    ])
    agent = GPTRefineAgent("test-gpt-model", client=SimpleNamespace(responses=responses))
    with pytest.raises(ValueError, match="invalid action"):
        agent.review(_observation(), _observation(), before_board=board,
                     after_board=board, profile="OBSERVATION_FIELD",
                     transport="ALL_ACTIVE_VIEWS", integrity={"passed": True},
                     remaining_candidates=0,
                     previous_candidate_results=[{"profile": "BALANCED",
                                                  "hard_verdict": "carrier_integrity_failed"}])
    call = responses.calls[0]
    assert call["text"]["format"]["schema"]["properties"]["action"]["enum"] == [
        "ACCEPT_UPDATE", "STOP_KEEP_CURRENT"]
    prompt = call["input"][0]["content"][0]["text"]
    assert '"remaining_candidates": 0' in prompt
    assert "carrier_integrity_failed" in prompt


def test_review_can_request_next_route_when_one_remains(tmp_path):
    board = tmp_path / "board.png"
    board.write_bytes(b"mock-image")
    responses = FakeResponses([
        {"action": "TRY_NEXT_CANDIDATE", "reason": "next route is available", "evidence": []},
    ])
    agent = GPTRefineAgent("test-gpt-model", client=SimpleNamespace(responses=responses))
    review = agent.review(_observation(), _observation(), before_board=board,
                          after_board=board, profile="BALANCED", transport="CAMERA1",
                          integrity={"passed": True}, remaining_candidates=1)
    assert review["decision"]["action"] == "TRY_NEXT_CANDIDATE"
    assert "TRY_NEXT_CANDIDATE" in responses.calls[0]["text"]["format"]["schema"]["properties"]["action"]["enum"]


def test_codex_provider_uses_logged_in_model_and_rejects_tool_use(monkeypatch, tmp_path):
    image = tmp_path / "board.png"
    image.write_bytes(b"mock-image")
    answer = {"action": "UPDATE_POSTERIOR", "profile": "BALANCED",
              "transport": "CAMERA1", "view_strategy": "SAVED_FOUR",
              "reason": "observed mismatch", "evidence": ["four-view residual"]}
    events = [
        {"type": "thread.started", "thread_id": "mock-codex-thread"},
        {"type": "item.completed", "item": {"type": "agent_message"}},
        {"type": "turn.completed", "usage": {"input_tokens": 10}},
    ]
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(answer))
        return SimpleNamespace(returncode=0, stdout="\n".join(json.dumps(e) for e in events),
                               stderr="")

    monkeypatch.setattr("src.gpt_refine_agent.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr("src.gpt_refine_agent.subprocess.run", fake_run)
    agent = GPTRefineAgent("gpt-6-sol", provider="codex")
    decision, record = agent.plan(_observation(), None, round_index=0,
                                  maximum_rounds=3, board=image, recent_trace=[])
    assert decision.transport == "CAMERA1"
    assert record["response_id"] == "mock-codex-thread"
    assert calls[0][0][calls[0][0].index("--model") + 1] == "gpt-6-sol"
    assert "--sandbox" in calls[0][0] and "read-only" in calls[0][0]
    assert "ground_truth" not in calls[0][1]["input"]

    events.insert(1, {"type": "item.completed", "item": {"type": "function_call"}})
    with pytest.raises(RuntimeError, match="forbidden tool use"):
        agent.plan(_observation(), None, round_index=0,
                   maximum_rounds=3, board=image, recent_trace=[])
