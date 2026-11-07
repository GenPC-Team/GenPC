"""Bounded GPT-6 Astra decisions for image-conditioned prior generation.

Image Gen is an interactive Codex tool. This module records its exact prompt
and reviews saved candidates; geometry and framing gates stay deterministic.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time


PROMPT_VERSION = "prior_mining_v25_complete_structure"


def compose_depth_edit_prompt(*, object_description: str,
                              observed_geometry: str = "",
                              completion_geometry: str = "",
                              revision_feedback: str = "",
                              depth_relation_hint: str = "") -> str:
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
    hint = depth_relation_hint.strip()
    # The model occasionally echoes the supplied base sentence in its hint.
    # Preserve one copy of the validated sentence and keep only the new cue.
    if hint.startswith(prompt):
        hint = hint[len(prompt):].strip()
    if hint:
        prompt += " " + hint
    if revision_feedback.strip():
        prompt += "\n请修正上一轮的具体问题：" + revision_feedback.strip()
    return prompt


DEPTH_INTERPRETATION_SCHEMA = {
    "type": "object",
    "properties": {
        "observed_geometry": {"type": "string"},
        "near_far_relation": {"type": "string"},
        "front_rear_orientation": {"type": "string"},
        "image_plane_orientation": {"type": "string"},
        "facing_visual_cue": {"type": "string"},
        "semantic_structure": {"type": "string"},
        "part_identity_and_count": {"type": "string"},
        "count_guard": {"type": "string"},
        "visible_part_layout": {"type": "string"},
        "part_connections": {"type": "string"},
        "part_axis_directions": {"type": "string"},
        "terminal_part_directions": {"type": "string"},
        "uncertainty": {"type": "string"},
        "imagegen_hint": {"type": "string"},
    },
    "required": ["observed_geometry", "near_far_relation",
                 "front_rear_orientation", "image_plane_orientation", "facing_visual_cue",
                 "semantic_structure",
                 "part_identity_and_count", "count_guard", "visible_part_layout",
                 "part_connections",
                 "part_axis_directions", "terminal_part_directions",
                 "uncertainty",
                 "imagegen_hint"],
    "additionalProperties": False,
}

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
        "image_plane_orientation_match": {"type": "boolean"},
        "orientation_evidence": {"type": "string"},
        "front_rear_axis_match": {"type": "boolean"},
        "natural_construction": {"type": "boolean"},
        "visible_structure_match": {"type": "boolean"},
        "category_identity_match": {"type": "boolean"},
        "depth_order_match": {"type": "boolean"},
        "projected_envelope_match": {"type": "boolean"},
        "functional_form_match": {"type": "boolean"},
        "complete_object": {"type": "boolean"},
    },
    "required": ["action", "reason", "next_prompt", "pose_and_orientation_match",
                 "front_rear_axis_match", "image_plane_orientation_match", "orientation_evidence",
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
    "Inspect image-plane orientation explicitly: canvas x increases rightward "
    "and y downward. Identify two or more supported semantic landmarks and "
    "describe their top/bottom and left/right ordering in the DEPTH image, "
    "before inspecting their ordering in RGB. A natural upright catalog image "
    "is wrong if the supplied depth depicts the object tilted or inverted. "
    "Do not mentally rotate, vertically flip or mirror either image to match. "
    "Distinguish actual camera roll from top/bottom part reversal. If supported "
    "landmarks cannot establish the sign, report uncertainty rather than "
    "inventing gravity from the image edge. A stored world-up axis may help "
    "only when its convention is documented. For unknown-camera selection, "
    "prefer an informative exterior view with clear supported part order and "
    "limited foreshortening over an ambiguous axial/underside view, while "
    "retaining coverage. A front view is not always the most informative. "
    "For depth interpretation before generation, read only the supplied depth "
    "and category, plus saved camera orientation when supplied. Brighter valid pixels are nearer and darker valid pixels "
    "are farther; black is unobserved. First map the whole object's image-plane "
    "axis and near/far order. Then inspect every visible category-defining "
    "part on the 512-pixel canvas: its identity and count, approximate location, "
    "where it joins the body, the axis from base to end, and the separate "
    "direction of the tip (up/down/left/right and near/far). A limb can extend "
    "horizontally while its terminal claws point down; do not conflate these. "
    "Describe semantic front versus rear separately from part locations: "
    "where a head/face, lens, nose, or tool bit points relative to the "
    "tail/back/handle and relative to the camera. A head at the far end "
    "can still face the camera; do not mistake location for facing direction. "
    "If the category has no meaningful front/rear, say so. In "
    "facing_visual_cue, translate a confident facing relation into one short "
    "observable cue for Image Gen: whether the viewer sees a rear surface "
    "or a face/front opening. For example, a head facing away should show "
    "the back of the head rather than eyes or an open mouth facing camera. "
    "Leave this field empty if facing is uncertain. "
    "Trace long or thin appendages from base to tip, including "
    "tails, claws, wings, legs, tools, lenses, rotors, and supports when present. "
    "State these in part_identity_and_count, visible_part_layout, "
    "part_connections, part_axis_directions and terminal_part_directions "
    "before writing imagegen_hint. Use the ordinary count of category-defining "
    "parts unless the visible scan clearly supports an exception. Do not "
    "duplicate a head, limb, wheel or other part by misreading a wing, shadow, "
    "scan gap or distal silhouette. If there is a salient duplication risk, "
    "write one short explicit count/identity clause in count_guard; otherwise "
    "return an empty string there. "
    "Check that the hint preserves each confidently visible terminal direction "
    "and connection, as well as category-defining structure. Explicitly state "
    "any confident image-plane tilt or inverted part order in the short hint; "
    "image_plane_orientation must record the supporting landmark order. "
    "the count of salient parts in the hint when it prevents a plausible "
    "identity error (such as one head versus several heads). "
    "Use a supplied camera-above/below relation to identify whether the visible "
    "surface is an upper or lower side; never infer this from image brightness "
    "alone. The saved camera does not reveal unseen part geometry. "
    "Use user feedback when given. Do not infer hidden material, color, or "
    "details from black pixels. If a relation is ambiguous, state uncertainty "
    "and omit that claim from the image-generation hint. Write one concise "
    "hint that preserves visible geometry and near/far ordering while adding "
    "only category semantics needed for natural physical construction. "
    "The imagegen_hint field must contain only the added cue: never repeat "
    "the supplied base_imagegen_prompt. Keep that validated sentence intact "
    "and add the hint after it; "
    "do not turn the partial mask into a complete-object boundary. "
    "For review, use supplied depth interpretation and human feedback as "
    "part-identification context. If a grayscale shape could have multiple "
    "semantic readings, do not reverse a user-confirmed part identity or "
    "near/far relation without clear contradictory visible evidence. "
    "The candidate's generation prompt is provenance, not ground truth: "
    "when a retry prompt assigns a specific identity to a feature that the "
    "saved depth interpretation marked uncertain, review against the depth "
    "and confident interpretation instead of enforcing that prompt claim. "
    "If the depth interpretation explicitly marks a small protrusion's "
    "identity or direction as uncertain, do not require the candidate to "
    "render that protrusion as a specific wing, fin, or other part; judge the "
    "confidently observed main structure and positive support instead. "
    "Independently verify front/rear facing direction, especially head gaze "
    "against the tail/back axis; set front_rear_axis_match false when the "
    "candidate reverses it even if the head and tail locations match. "
    "Also set image_plane_orientation_match false for an upside-down, mirrored "
    "or materially rotated RGB relative to the depth. In orientation_evidence, "
    "name corresponding landmarks and their image positions in each image; "
    "mask overlap alone cannot establish orientation. Do not penalize small "
    "pose offsets or plausible unobserved completion. "
    "The three supplied images use the same full-frame pixel canvas: "
    "the generated RGB was resized to the saved depth dimensions without crop "
    "or translation before comparison. Compare corresponding pixel locations. "
    "If next_prompt needs a position, express it as a percentage of the full "
    "image width or height, never as a raw pixel coordinate: the Image Gen "
    "native output size can differ from this comparison canvas. "
    "Non-black depth pixels are positive but incomplete observations. Brighter "
    "depth pixels are nearer the acquisition camera. Black pixels are unknown, "
    "so a natural completed object may extend outside the observed mask. "
    "Small isolated black voids inside a visible surface are missing scan "
    "samples, not evidence of drilled holes; require continuous natural "
    "material there unless the category itself supports such openings. "
    "For sparse or noisy point scans, require a finished object surface: "
    "do not preserve scattered points, ragged scan holes or depth-speckle "
    "texture as if they were the object's material. "
    "For a sparse human scan, a broad lower-body patch may be clothing or "
    "overlapping limbs; do not infer an exact hip or torso boundary unless "
    "the scan clearly separates those parts. A natural anatomical split is "
    "acceptable when positive support, overall pose, and visible limb "
    "directions still agree. "
    "Likewise, scattered lower-body points on a sparse vehicle scan do not "
    "fix an exact wheel center unless a distinct wheel or arch is visible. "
    "Check that each confidently observed wheel region is approximately "
    "supported, while allowing a natural completed vehicle to place an "
    "uncertain wheel at a plausible location within that lower region. "
    "Judge whether the visible parts approximately match in silhouette, size, "
    "pose, orientation, front/back side, part junctions, and near-to-far order. "
    "Allow modest scan gaps, edge noise, and small offsets; do not demand "
    "pixel-perfect contour identity. An inferred tip or wing may extend into "
    "unobserved pixels when the observed structure remains supported and the "
    "whole object is physically plausible; do not treat the partial scan's "
    "bounding box as a complete-object boundary or reject solely for that "
    "extension. For a sparse scan that samples only the central body, a "
    "complete vehicle or person can plausibly extend 15–25% beyond the "
    "observed bounding box. Set projected_envelope_match true when the "
    "observed positive support, visible part scale, and pose align and the "
    "extra extent is natural unobserved completion. Reject oversizing only "
    "when a confidently observed part itself is too large or misplaced. "
    "Foreground coverage and monocular depth "
    "statistics are supporting diagnostics, not proof of correct geometry. "
    "Do not reject depth order solely because a monocular-depth statistic is "
    "low; identify a visible part, occlusion or shape cue that contradicts "
    "the observed near/far relation before setting depth_order_match false. "
    "Independently judge whether the result is a complete, naturally built "
    "object of the requested category: coherent materials, connected parts, "
    "functional proportions, and plausible repeated supports or wheels. "
    "The depth is a partial scan, not a depiction of the whole object: "
    "complete missing but functionally necessary structure in unobserved areas. "
    "For repeated structural parts, account for each support implied by the "
    "object's construction and the confident depth interpretation in this "
    "view. Check attachment, direction and plausible endpoint; a stretcher, "
    "trim strip or image-plane overlap cannot substitute for a missing leg. "
    "An occluded support need not be visible, but its hidden placement must "
    "be geometrically plausible and the completed object must remain stable. "
    "Set natural_construction and complete_object false if a needed support "
    "is absent, disconnected or too short, even when the observed pixels fit. "
    "Reject a generated object that changes the observed viewpoint or visible "
    "part structure, or has missing/impossible construction, even if its "
    "foreground covers the depth mask. Do not use GT, CD, EMD, or sample-specific "
    "rules. Do not call tools or read files."
)

class PriorGenerationAgent:
    def __init__(self, model: str = "gpt-6-astra", *, reasoning_effort: str = "low") -> None:
        if shutil.which("codex") is None:
            raise RuntimeError("the logged-in Codex CLI is required")
        self.model = model
        self.reasoning_effort = reasoning_effort

    def _decide(self, schema: dict, payload: dict, images: list[Path]) -> dict:
        with TemporaryDirectory(prefix="compagent-prior-agent-") as directory:
            root = Path(directory)
            schema_path = root / "answer.schema.json"
            answer_path = root / "answer.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [
                "codex", "exec", "--model", self.model, "--sandbox", "read-only",
                "--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
                "--json", "--config", f"model_reasoning_effort={getattr(self, 'reasoning_effort', 'low')}",
                "--output-schema", str(schema_path),
                "--output-last-message", str(answer_path), "-C", str(root),
            ]
            for path in images:
                command.extend(("--image", str(path.resolve())))
            command.append("-")
            failure = ""
            timeout = float(os.environ.get('COMPAGENT_CODEX_TIMEOUT_SECONDS', '600'))
            if not math.isfinite(timeout) or timeout <= 0:
                raise ValueError('COMPAGENT_CODEX_TIMEOUT_SECONDS must be finite and positive')
            timeouts = 0
            for attempt in range(3):
                answer_path.unlink(missing_ok=True)
                try:
                    result = subprocess.run(
                        command,
                        input=INSTRUCTIONS + "\nReturn one JSON object matching the schema.\n"
                              + json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        text=True, capture_output=True, cwd=root, timeout=timeout, check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    timeouts += 1
                    stdout = exc.stdout or ''
                    if isinstance(stdout, bytes):
                        stdout = stdout.decode('utf-8', errors='replace')
                    result = subprocess.CompletedProcess(command, -1, stdout,
                              f'request timed out after {timeout:g} seconds')
                events = []
                for line in result.stdout.splitlines():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                forbidden = [event.get("item", {}).get("type") for event in events
                             if event.get("type") in {"item.started", "item.completed"}
                             and event.get("item", {}).get("type") not in
                             {"agent_message", "reasoning", "error"}]
                if forbidden:
                    raise RuntimeError(f"Codex prior agent attempted tool use: {forbidden}")
                transient_error = any(
                    event.get("type") == "error" or event.get("item", {}).get("type") == "error"
                    for event in events
                )
                if (result.returncode == 0 and answer_path.is_file()
                        and any(event.get("type") == "turn.completed" for event in events)
                        and not transient_error):
                    break
                failure = (f"Codex prior decision incomplete ({result.returncode}); "
                           f"error_event={transient_error}; {result.stderr[-400:]}")
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
            else:
                raise RuntimeError(failure)
            decision = json.loads(answer_path.read_text(encoding="utf-8"))
            if set(decision) != set(schema["required"]):
                raise ValueError("prior decision has unexpected fields")
            for name, spec in schema["properties"].items():
                expected = bool if spec["type"] == "boolean" else str
                if not isinstance(decision[name], expected) or ("enum" in spec and decision[name] not in spec["enum"]):
                    raise ValueError(f"invalid prior decision field: {name}")
            thread = next((e.get("thread_id") for e in events
                           if e.get("type") == "thread.started"), None)
            usage = next((e.get("usage") for e in events
                          if e.get("type") == "turn.completed"), None)
            return {"decision": decision, "model": self.model,
                    "reasoning_effort": getattr(self, 'reasoning_effort', 'low'),
                    "provider": "codex", "thread_id": thread,
                    "usage": usage,
                    "transport": {"attempts": attempt + 1, "timeouts": timeouts,
                                  "timeout_seconds": timeout},
                    "prompt_version": PROMPT_VERSION}

    def select_view(self, *, board: Path | list[Path], view_ids: list[str],
                    object_description: str, base_prompt: str = "",
                    camera_geometry: dict | None = None,
                    previous_attempt_feedback: str = "") -> dict:
        schema = {**VIEW_SCHEMA, "properties": {**VIEW_SCHEMA["properties"],
                  "view_id": {"type": "string", "enum": view_ids}}}
        result = self._decide(schema, {
            "task": "select_front_side_partial_depth_view",
            "view_ids": view_ids,
            "object_description": object_description,
            "candidate_camera_geometry": camera_geometry or {},
            "previous_attempt_feedback": previous_attempt_feedback,
            "selection_policy": (
                "The views were already ranked by partial-only visible point count "
                "and separated angularly. Choose the depth view whose visible "
                "part layout most resembles the known object category, with a "
                "plausible exterior/front orientation and informative part "
                "connections. Avoid reversed, back-inside or misleading views. "
                "When a physical up axis is explicitly documented, use each camera's "
                "signed elevation to distinguish upper surfaces from undersides. "
                "Prefer an informative natural exterior view over an ambiguous underside "
                "even if the latter has more observed points. Elevation alone does not "
                "determine quality: explain the visible part and occlusion evidence. "
                "An unknown world-up is not evidence of physical gravity."
            ),
        }, [board] if isinstance(board, Path) else board)
        return result

    def audit_existing_prior(self, *, images: list[Path], current_view: str,
                             view_ids: list[str], object_description: str) -> dict:
        """Reassess an archived prior without trusting its historical approval."""
        properties = {
            'action': {'type':'string','enum':['KEEP_PRIOR','REGENERATE','RESELECT_VIEW','UNCERTAIN']},
            'selected_view': {'type':'string','enum':view_ids},
            **{key:{'type':'boolean'} for key in ['current_view_suitable',
                'image_plane_orientation_match','near_far_match','natural_complete_object',
                'visible_part_layout_match']},
            **{key:{'type':'string'} for key in ['depth_landmark_order','rgb_landmark_order',
                'view_quality_evidence','near_far_evidence','reason','repair_hint','uncertainty']},
        }
        schema = {'type':'object','properties':properties,'required':list(properties),
                  'additionalProperties':False}
        payload = {'task':'independent_saved_prior_view_and_orientation_audit',
                   'object_description':object_description,'current_view':current_view,
                   'available_view_ids':view_ids,
                   'image_order':['current_depth','current_semantic_same_canvas','same_canvas_overlay',
                                  'remaining images: labeled saved candidate depth boards'],
                   'policy': 'First read the current depth and record supported top/bottom and left/right landmark order. '
                             'Then compare the RGB in exactly the same canvas; do not rotate either mentally. '
                             'Audit visible near/far ordering, natural full structure and current view ambiguity. '
                             'Inspect the alternative depth boards independently of the current generated RGB. '
                             'KEEP_PRIOR only if current view and RGB are suitable. REGENERATE if current view '
                             'is suitable but RGB disagrees. RESELECT_VIEW only for concrete poor view evidence '
                             'and a clearer saved alternative; do not churn an adequate view just for variety. '
                             'UNCERTAIN for insufficient evidence. selected_view stays current except RESELECT_VIEW. '
                             'Describe a short grounded correction in repair_hint, not invented unseen anatomy. '
                             'Historical acceptance, image beauty and coverage alone are not correctness evidence.'}
        result = self._decide(schema, payload, images)
        decision = result['decision']
        checks = ['current_view_suitable','image_plane_orientation_match','near_far_match',
                  'natural_complete_object','visible_part_layout_match']
        if decision['action']=='KEEP_PRIOR' and not all(decision[k] for k in checks):
            decision['action'] = 'REGENERATE' if decision['current_view_suitable'] else 'UNCERTAIN'
        if decision['action']!='RESELECT_VIEW' and decision['selected_view']!=current_view:
            raise ValueError('only RESELECT_VIEW may change the selected camera')
        if decision['action']=='RESELECT_VIEW' and decision['selected_view']==current_view:
            raise ValueError('reselection must identify a different saved view')
        result['audit_payload'] = payload
        return result

    def interpret_depth(self, *, depth: Path, object_description: str,
                        feedback: str = "", camera_context: str = "",
                        review_context: dict | None = None) -> dict:
        """Extract one grounded near/far instruction before Image Gen."""
        return self._decide(DEPTH_INTERPRETATION_SCHEMA, {
            "task": "interpret_fixed_partial_depth_before_image_generation",
            "object_description": object_description,
            "user_feedback": feedback,
            "same_view_machine_review": review_context or {},
            "saved_camera_context": camera_context,
            "base_imagegen_prompt": compose_depth_edit_prompt(
                object_description=object_description,
            ),
            "image_order": ["saved_partial_depth"],
            "hint_policy": (
                "Write imagegen_hint as one or two COMPLETE concise Chinese sentences, "
                "at most 180 Chinese characters. Keep count_guard and facing_visual_cue "
                "concise Chinese too. Cover supported whole-object "
                "pose, near/far order, semantic front/rear facing direction, "
                "part identity/count, axis directions, "
                "If same_view_machine_review is present, recheck its suspected "
                "mismatch against this depth and include a concrete correction "
                "only where visible evidence supports it. This is fallible "
                "model feedback, not a human instruction or ground truth. "
                "separate terminal-part directions and attachments. Do not repeat "
                "the base sentence, change camera, add arbitrary parts, or "
                "treat the partial mask as a rigid complete boundary."
            ),
        }, [depth])

    def review(self, *, depth: Path, candidate: Path, audit_overlay: Path,
               audit: dict, prompt: str, object_description: str,
               depth_audit: dict | None = None,
               depth_interpretation: dict | None = None,
               human_feedback: str = "", candidate_feedback: str = "") -> dict:
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
            "prior_depth_interpretation": depth_interpretation or {},
            "human_part_feedback": human_feedback,
            "human_candidate_feedback": candidate_feedback,
            "image_order": ["comparison_depth", "generated_image_same_canvas", "layout_audit_overlay_same_canvas"],
        }, [depth, candidate, audit_overlay])
        decision = result["decision"]
        if decision["action"] == "ACCEPT" and not (
            decision["pose_and_orientation_match"] and decision["front_rear_axis_match"]
            and decision["image_plane_orientation_match"]
            and decision["natural_construction"]
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
        if decision["action"] == "REVISE" and not decision["next_prompt"].strip():
            raise ValueError("revision needs a concrete correction")
        return result
