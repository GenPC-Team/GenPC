from pathlib import Path
from types import SimpleNamespace
import json

import src.prior_generation_agent as prior_module

from src.prior_generation_agent import PriorGenerationAgent, compose_depth_edit_prompt


def test_codex_prior_retries_transient_error_event(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert "model_reasoning_effort=low" in command
        answer = Path(command[command.index("--output-last-message") + 1])
        answer.write_text('{"choice": "ok"}')
        events = [{"type": "thread.started", "thread_id": "test"}]
        if len(calls) == 1:
            events.append({"type": "item.completed", "item": {"type": "error"}})
        events.append({"type": "turn.completed"})
        return SimpleNamespace(returncode=0, stderr="", stdout="\n".join(map(json.dumps, events)))

    monkeypatch.setattr(prior_module.subprocess, "run", fake_run)
    monkeypatch.setattr(prior_module.time, "sleep", lambda _: None)
    agent = object.__new__(PriorGenerationAgent)
    agent.model = "test"
    result = agent._decide(
        {"required": ["choice"], "properties": {"choice": {"type": "string"}}},
        {}, [],
    )
    assert result["decision"] == {"choice": "ok"}
    assert len(calls) == 2


def test_fixed_camera_prompt_uses_approved_short_depth_sentence():
    prompt = compose_depth_edit_prompt(
        object_description="沙发",
        observed_geometry="A back runs diagonally up-left beside the seat.",
        completion_geometry="Continue the seat and back into one sofa.",
    )
    assert prompt == (
        "这是一个沙发扫描出来的深度图。用 Image Gen 将图1补全成一张完整的沙发图，"
        "遵循深度图可见部分的深度、轮廓约束，背景为纯白色。"
    )


def test_depth_relation_hint_adds_one_grounded_sentence_without_changing_base():
    base = compose_depth_edit_prompt(object_description="mirrorless camera")
    hint = "近端是机身背侧，镜头位于较远端；保持图1的斜视角。"
    assert compose_depth_edit_prompt(
        object_description="mirrorless camera", depth_relation_hint=hint,
    ) == base + " " + hint


def test_depth_relation_hint_removes_echoed_base_sentence():
    base = compose_depth_edit_prompt(object_description="wolf")
    hint = "保留俯视的头身朝向和自然连接的尾巴。"
    assert compose_depth_edit_prompt(
        object_description="wolf", depth_relation_hint=base + hint,
    ) == base + " " + hint


def test_review_rejects_incomplete_object_despite_scan_match(monkeypatch):
    agent = object.__new__(PriorGenerationAgent)
    candidate = {
        "action": "ACCEPT", "reason": "One end matches but the other is missing.",
        "next_prompt": "", "pose_and_orientation_match": True,
        "front_rear_axis_match": True, "image_plane_orientation_match": True,
        "orientation_evidence": "Supported landmark order agrees on the unchanged canvas.",
        "natural_construction": True, "visible_structure_match": True,
        "category_identity_match": True, "depth_order_match": True,
        "projected_envelope_match": True, "functional_form_match": True,
        "complete_object": False,
    }
    monkeypatch.setattr(agent, "_decide", lambda *args, **kwargs: {"decision": candidate})
    result = agent.review(
        depth=Path("depth.png"), candidate=Path("candidate.png"),
        audit_overlay=Path("overlay.png"),
        audit={"passed": True, "centre_offset_ratio": 0.0,
               "bbox_scale_xy": [1.0, 1.0], "depth_coverage": 1.0,
               "mask_iou": 1.0, "semantic_leakage": 0.0},
        prompt="Complete one sofa using the partial depth as reference.",
        object_description="sofa",
    )
    assert result["decision"]["action"] == "REVISE"
    assert "whole-object completeness" in result["decision"]["next_prompt"]


def test_review_rejects_reversed_front_rear_axis(monkeypatch):
    agent = object.__new__(PriorGenerationAgent)
    candidate = {
        "action": "ACCEPT", "reason": "Heads and tail have the right locations but face one another.",
        "next_prompt": "", "pose_and_orientation_match": True,
        "front_rear_axis_match": False, "image_plane_orientation_match": True,
        "orientation_evidence": "Image-plane order agrees; facing is reversed.",
        "natural_construction": True, "visible_structure_match": True,
        "category_identity_match": True, "depth_order_match": True,
        "projected_envelope_match": True, "functional_form_match": True,
        "complete_object": True,
    }
    monkeypatch.setattr(agent, "_decide", lambda *args, **kwargs: {"decision": candidate})
    result = agent.review(
        depth=Path("depth.png"), candidate=Path("candidate.png"),
        audit_overlay=Path("overlay.png"),
        audit={"passed": True, "centre_offset_ratio": 0.0,
               "bbox_scale_xy": [1.0, 1.0], "depth_coverage": 1.0,
               "mask_iou": 1.0, "semantic_leakage": 0.0},
        prompt="Complete the object from partial depth.",
        object_description="three-headed hydra",
    )
    assert result["decision"]["action"] == "REVISE"


def test_review_requires_pose_and_natural_construction(monkeypatch):
    agent = object.__new__(PriorGenerationAgent)
    candidate = {
        "action": "ACCEPT",
        "reason": "Visible support matches, but the chair base is implausible.",
        "next_prompt": "",
        "pose_and_orientation_match": True,
        "front_rear_axis_match": True, "image_plane_orientation_match": True,
        "orientation_evidence": "Supported landmark order agrees on the unchanged canvas.",
        "natural_construction": False,
        "visible_structure_match": True,
        "category_identity_match": True,
        "depth_order_match": True,
        "projected_envelope_match": True,
        "functional_form_match": True,
        "complete_object": True,
    }
    monkeypatch.setattr(agent, "_decide", lambda *args, **kwargs: {"decision": candidate})
    result = agent.review(
        depth=Path("depth.png"), candidate=Path("candidate.png"),
        audit_overlay=Path("overlay.png"),
        audit={"passed": True, "centre_offset_ratio": 0.0,
               "bbox_scale_xy": [1.0, 1.0], "depth_coverage": 1.0,
               "mask_iou": 1.0, "semantic_leakage": 0.0},
        prompt="Generate a realistic object from the observed depth.",
        object_description="office chair",
    )
    assert result["decision"]["action"] == "REVISE"
    assert "natural physical construction" in result["decision"]["next_prompt"]


def test_review_rejects_category_change_even_with_silhouette_coverage(monkeypatch):
    agent = object.__new__(PriorGenerationAgent)
    candidate = {
        "action": "ACCEPT", "reason": "Mask coverage passes, but the sofa became a chair.",
        "next_prompt": "", "pose_and_orientation_match": True,
        "front_rear_axis_match": True, "image_plane_orientation_match": True,
        "orientation_evidence": "Supported landmark order agrees on the unchanged canvas.",
        "natural_construction": True, "visible_structure_match": True,
        "category_identity_match": False, "depth_order_match": True,
        "projected_envelope_match": True, "functional_form_match": True,
        "complete_object": True,
    }
    monkeypatch.setattr(agent, "_decide", lambda *args, **kwargs: {"decision": candidate})
    result = agent.review(
        depth=Path("depth.png"), candidate=Path("candidate.png"),
        audit_overlay=Path("overlay.png"),
        audit={"passed": True, "centre_offset_ratio": 0.0,
               "bbox_scale_xy": [1.0, 1.0], "depth_coverage": 1.0,
               "mask_iou": 1.0, "semantic_leakage": 0.0},
        prompt="Generate a long sofa from the observed depth.",
        object_description="long sofa",
    )
    assert result["decision"]["action"] == "REVISE"
    assert "category identity" in result["decision"]["next_prompt"]


def test_review_rejects_catalog_view_expansion(monkeypatch):
    agent = object.__new__(PriorGenerationAgent)
    candidate = {
        "action": "ACCEPT", "reason": "A long sofa, but shown from a broad new view.",
        "next_prompt": "", "pose_and_orientation_match": True,
        "front_rear_axis_match": True, "image_plane_orientation_match": True,
        "orientation_evidence": "Supported landmark order agrees on the unchanged canvas.",
        "natural_construction": True, "visible_structure_match": True,
        "category_identity_match": True, "depth_order_match": True,
        "projected_envelope_match": False, "functional_form_match": True,
        "complete_object": True,
    }
    monkeypatch.setattr(agent, "_decide", lambda *args, **kwargs: {"decision": candidate})
    result = agent.review(
        depth=Path("depth.png"), candidate=Path("candidate.png"),
        audit_overlay=Path("overlay.png"),
        audit={"passed": True, "centre_offset_ratio": 0.0,
               "bbox_scale_xy": [1.17, 1.05], "depth_coverage": .999,
               "mask_iou": .75, "semantic_leakage": .25},
        prompt="Render the object in the same fixed view.",
        object_description="sofa",
    )
    assert result["decision"]["action"] == "REVISE"
    assert "projected contour" in result["decision"]["next_prompt"]


def test_review_rejects_upside_down_rgb_even_with_full_mask_overlap(monkeypatch):
    agent=object.__new__(PriorGenerationAgent)
    decision={key:True for key,value in prior_module.REVIEW_SCHEMA['properties'].items()
              if value['type']=='boolean'}
    decision.update(action='ACCEPT',reason='Mask overlaps but top and bottom parts are reversed.',
                    next_prompt='',image_plane_orientation_match=False,
                    orientation_evidence='Observed upper landmark appears below the lower landmark in RGB.')
    monkeypatch.setattr(agent,'_decide',lambda *a,**k:{'decision':decision})
    result=agent.review(depth=Path('depth.png'),candidate=Path('rgb.png'),audit_overlay=Path('overlay.png'),
        audit={'passed':True,'centre_offset_ratio':0.,'bbox_scale_xy':[1.,1.],
               'depth_coverage':1.,'mask_iou':1.,'semantic_leakage':0.},prompt='Complete the object.',object_description='object')
    assert result['decision']['action']=='REVISE'


def test_saved_prior_audit_cannot_keep_a_reversed_candidate(monkeypatch):
    agent=object.__new__(PriorGenerationAgent)
    decision={'action':'KEEP_PRIOR','selected_view':'view_1','current_view_suitable':True,
              'image_plane_orientation_match':False,'near_far_match':True,
              'natural_complete_object':True,'visible_part_layout_match':False}
    monkeypatch.setattr(agent,'_decide',lambda *a,**k:{'decision':decision})
    result=agent.audit_existing_prior(images=[],current_view='view_1',view_ids=['view_1','view_2'],object_description='object')
    assert result['decision']['action']=='REGENERATE'
    assert result['decision']['selected_view']=='view_1'


def test_machine_repair_context_is_not_human_feedback(monkeypatch):
    agent = object.__new__(PriorGenerationAgent)
    captured = {}
    def decide(schema, payload, images):
        captured.update(payload=payload, images=images)
        return {'decision': {}}
    monkeypatch.setattr(agent, '_decide', decide)
    evidence = {'repair_hint': 'Recheck the observed upper-right projection.',
                'uncertainty': 'Exact articulation is unknown.'}
    agent.interpret_depth(depth=Path('depth.png'), object_description='object',
                          review_context=evidence)
    assert captured['payload']['user_feedback'] == ''
    assert captured['payload']['same_view_machine_review'] == evidence
    assert captured['images'] == [Path('depth.png')]
