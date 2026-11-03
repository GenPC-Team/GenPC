"""Bounded GPT-6 Sol decisions for image-conditioned prior generation.

Image Gen is an interactive Codex tool. This module records its exact prompt
and reviews saved candidates; geometry and framing gates stay deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory


PROMPT_VERSION = "prior_mining_v9_simple_depth_sentence_and_aligned_review"


def compose_depth_edit_prompt(*, object_description: str,
                              observed_geometry: str = "",
                              completion_geometry: str = "",
                              revision_feedback: str = "") -> str:
    """Use the short sentence validated on the ten Redwood depth images.

    The agent selects the camera and reviews the result. Its detailed geometric
    observations are review evidence, not extra generation prose.
    """
    label = object_description.strip()
    if not label:
        raise ValueError("object description is required")
    prompt = (
        f"这是一个{label}扫描出来的深度图。用 Image Gen 将图1补全成一张完整的{label}图，"
        "遵循深度图可见部分的深度、轮廓约束，背景为纯白色。"
    )
    if revision_feedback.strip():
        prompt += "\n请修正上一轮的具体问题：" + revision_feedback.strip()
    return prompt

VIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "view_id": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["view_id", "reason"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["ACCEPT", "REVISE"]},
        "reason": {"type": "string"},
        "next_prompt": {"type": "string"},
        "pose_and_orientation_match": {"type": "boolean"},
        "natural_construction": {"type": "boolean"},
        "visible_structure_match": {"type": "boolean"},
        "category_identity_match": {"type": "boolean"},
        "depth_order_match": {"type": "boolean"},
        "projected_envelope_match": {"type": "boolean"},
        "functional_form_match": {"type": "boolean"},
        "complete_object": {"type": "boolean"},
    },
    "required": ["action", "reason", "next_prompt", "pose_and_orientation_match",
                 "natural_construction", "visible_structure_match",
                 "category_identity_match", "depth_order_match",
                 "projected_envelope_match", "functional_form_match", "complete_object"],
    "additionalProperties": False,
}

INSTRUCTIONS = (
    "You are the Prior Generation Agent for a partial point-cloud completion pipeline. "
    "You may receive a board of candidate depth views for view selection, or "
    "a depth image, generated semantic image, and overlay for review. "
    "For view selection, choose the acquisition-side/front or exterior view "
    "that best reveals the observed object's parts and their layout; avoid "
    "the reversed back or inside of a hollow object. Do not choose a new view "
    "when the camera is fixed. "
    "For review, the three supplied images use the same full-frame pixel canvas: "
    "the generated RGB was resized to the saved depth dimensions without crop "
    "or translation before comparison. Compare corresponding pixel locations. "
    "Non-black depth pixels are positive but incomplete observations. Brighter "
    "depth pixels are nearer the acquisition camera. Black pixels are unknown, "
    "so a natural completed object may extend outside the observed mask. "
    "Judge whether the visible parts approximately match in silhouette, size, "
    "pose, orientation, front/back side, part junctions, and near-to-far order. "
    "Allow modest scan gaps, edge noise, and small offsets; do not demand "
    "pixel-perfect contour identity. Foreground coverage and monocular depth "
    "statistics are supporting diagnostics, not proof of correct geometry. "
    "Independently judge whether the result is a complete, naturally built "
    "object of the requested category: coherent materials, connected parts, "
    "functional proportions, and plausible repeated supports or wheels. "
    "Reject a generated object that changes the observed viewpoint or visible "
    "part structure, or has missing/impossible construction, even if its "
    "foreground covers the depth mask. Do not use GT, CD, EMD, or sample-specific "
    "rules. Do not call tools or read files."
)

class PriorGenerationAgent:
    def __init__(self, model: str = "gpt-6-sol") -> None:
        if shutil.which("codex") is None:
            raise RuntimeError("the logged-in Codex CLI is required")
        self.model = model

    def _decide(self, schema: dict, payload: dict, images: list[Path]) -> dict:
        with TemporaryDirectory(prefix="compagent-prior-agent-") as directory:
            root = Path(directory)
            schema_path = root / "answer.schema.json"
            answer_path = root / "answer.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [
                "codex", "exec", "--model", self.model, "--sandbox", "read-only",
                "--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
                "--json", "--config", "model_reasoning_effort=medium",
                "--output-schema", str(schema_path),
                "--output-last-message", str(answer_path), "-C", str(root),
            ]
            for path in images:
                command.extend(("--image", str(path.resolve())))
            command.append("-")
            result = subprocess.run(
                command,
                input=INSTRUCTIONS + "\nReturn one JSON object matching the schema.\n"
                      + json.dumps(payload, ensure_ascii=False, sort_keys=True),
                text=True, capture_output=True, cwd=root, timeout=300, check=False,
            )
            if result.returncode != 0 or not answer_path.is_file():
                raise RuntimeError(
                    f"Codex prior decision failed ({result.returncode}): {result.stderr[-800:]}"
                )
            events = []
            for line in result.stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if not any(event.get("type") == "turn.completed" for event in events):
                raise RuntimeError("Codex prior turn did not complete")
            forbidden = [event.get("item", {}).get("type") for event in events
                         if event.get("type") in {"item.started", "item.completed"}
                         and event.get("item", {}).get("type") not in {"agent_message", "reasoning"}]
            if forbidden:
                raise RuntimeError(f"Codex prior agent attempted tool use: {forbidden}")
            decision = json.loads(answer_path.read_text(encoding="utf-8"))
            if set(decision) != set(schema["required"]):
                raise ValueError("prior decision has unexpected fields")
            for name, spec in schema["properties"].items():
                expected = bool if spec["type"] == "boolean" else str
                if not isinstance(decision[name], expected) or ("enum" in spec and decision[name] not in spec["enum"]):
                    raise ValueError(f"invalid prior decision field: {name}")
            thread = next((e.get("thread_id") for e in events
                           if e.get("type") == "thread.started"), None)
            return {"decision": decision, "model": self.model,
                    "provider": "codex", "thread_id": thread,
                    "prompt_version": PROMPT_VERSION}

    def select_view(self, *, board: Path, view_ids: list[str],
                    object_description: str, base_prompt: str = "") -> dict:
        schema = {**VIEW_SCHEMA, "properties": {**VIEW_SCHEMA["properties"],
                  "view_id": {"type": "string", "enum": view_ids}}}
        result = self._decide(schema, {
            "task": "select_front_side_partial_depth_view",
            "view_ids": view_ids,
            "object_description": object_description,
            "selection_policy": "prefer the acquisition-side/front/exterior view that best separates visible parts and preserves enough positive partial support",
        }, [board])
        return result

    def review(self, *, depth: Path, candidate: Path, audit_overlay: Path,
               audit: dict, prompt: str, object_description: str,
               depth_audit: dict | None = None) -> dict:
        result = self._decide(REVIEW_SCHEMA, {
            "task": "review_imagegen_prior_candidate",
            "object_description": object_description,
            "prompt": prompt,
            "numeric_layout_audit": {
                "passed": audit["passed"],
                "verification_mode": audit.get("verification_mode", "strict_framing"),
                "canvas_mapping": audit.get("canvas_mapping", {}),
                "centre_offset_ratio": audit["centre_offset_ratio"],
                "bbox_scale_xy": audit["bbox_scale_xy"],
                "depth_coverage": audit["depth_coverage"],
                "mask_iou": audit["mask_iou"],
                "semantic_leakage": audit["semantic_leakage"],
            },
            "ordinal_depth_audit": depth_audit or {},
            "image_order": ["comparison_depth", "generated_image_same_canvas", "layout_audit_overlay_same_canvas"],
        }, [depth, candidate, audit_overlay])
        decision = result["decision"]
        if decision["action"] == "ACCEPT" and not (
            decision["pose_and_orientation_match"] and decision["natural_construction"]
            and decision["visible_structure_match"]
            and decision["category_identity_match"]
            and decision["depth_order_match"]
            and decision["projected_envelope_match"]
            and decision["functional_form_match"]
            and decision["complete_object"]
        ):
            decision["action"] = "REVISE"
            if len(decision["next_prompt"].strip()) < 80:
                decision["next_prompt"] = (
                    prompt.strip() + "\n\nCorrect the candidate's observed pose, "
                    "orientation, visible depth and part structure, category identity, "
                    "projected contour, ordinary functional form, and natural "
                    "physical construction and whole-object completeness before review."
                )
        if decision["action"] == "REVISE" and len(decision["next_prompt"].strip()) < 80:
            raise ValueError("revision needs a complete next Image Gen prompt")
        return result
