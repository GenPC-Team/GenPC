from pathlib import Path

from src.prior_generation_agent import PriorGenerationAgent, compose_depth_edit_prompt


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


def test_review_rejects_incomplete_object_despite_scan_match(monkeypatch):
    agent = object.__new__(PriorGenerationAgent)
    candidate = {
        "action": "ACCEPT", "reason": "One end matches but the other is missing.",
        "next_prompt": "", "pose_and_orientation_match": True,
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


def test_review_requires_pose_and_natural_construction(monkeypatch):
    agent = object.__new__(PriorGenerationAgent)
    candidate = {
        "action": "ACCEPT",
        "reason": "Visible support matches, but the chair base is implausible.",
        "next_prompt": "",
        "pose_and_orientation_match": True,
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
