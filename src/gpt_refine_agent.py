"""Vision-language decisions for the isolated, no-GT posterior experiment.

GPT sees saved-camera evidence and chooses from a finite action set. Geometry,
correspondences, and non-negotiable integrity checks remain deterministic.
"""

from __future__ import annotations

import base64
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.posterior_agent import Decision, Observation
from src.zbuffer import zbuffer_depth_with_indices


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["UPDATE_POSTERIOR", "REFINE_OBSERVED", "ACCEPT"]},
        "profile": {"type": "string", "enum": ["CONSERVATIVE", "BALANCED", "EXPANSIVE"]},
        "transport": {"type": "string", "enum": ["CAMERA1", "ALL_ACTIVE_VIEWS"]},
        "view_strategy": {"type": "string", "enum": ["SAVED_FOUR", "ADAPTIVE_ORBIT"]},
        "reason": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["action", "profile", "transport", "view_strategy", "reason", "evidence"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["ACCEPT_UPDATE", "TRY_NEXT_CANDIDATE", "STOP_KEEP_CURRENT"]},
        "reason": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["action", "reason", "evidence"],
    "additionalProperties": False,
}

PROMPT_VERSION = "v7_evidence_driven_stop"

PLATEAU_PATIENCE = 2


def next_plateau_streak(before: Observation, after: Observation, streak: int) -> int:
    """Count accepted steps with negligible view, bulk, and local-tail gains."""
    coverage_gain = after.mean_coverage - before.mean_coverage
    relative_p90_gain = (before.partial_to_carrier_p90 - after.partial_to_carrier_p90) / max(
        before.partial_to_carrier_p90, 1e-9,
    )
    relative_p99_gain = (before.partial_to_carrier_p99 - after.partial_to_carrier_p99) / max(
        before.partial_to_carrier_p99, 1e-9,
    )
    return streak + 1 if (coverage_gain < .005 and relative_p90_gain < .03
                          and relative_p99_gain < .03) else 0

INSTRUCTIONS = (
    "You decide which deterministic geometry tool to run in a test-time partial-to-complete refinement loop. "
    "The input is an already registered complete prior, not ground truth. "
    "Every view has THREE columns rendered with the SAME camera: "
    "A is ONLY the physically OBSERVED PARTIAL point cloud in BLUE; it is incomplete. "
    "B is ONLY the generated COMPLETE PRIOR point cloud in RED; it must remain complete. "
    "C overlays them: BLUE-ONLY is positive observed geometry missing from the prior, "
    "RED-ONLY is prior geometry without an observation (unknown, not evidence for deletion), "
    "and PURPLE is screen-space overlap, which alone does not prove 3D depth agreement. "
    "First identify which column is the physical observation and which is the prior. "
    "Then use all four view rows and their numeric coverage, depth and 3D residual evidence. "
    "A coherent blue-only extent across views is stronger than isolated noisy blue pixels. "
    "Choose only the specified discrete action, profile, and correspondence route. "
    "UPDATE_POSTERIOR runs structure-preserving Partial OT and PosteriorAdapter. "
    "REFINE_OBSERVED runs a narrow local observation field only when most of the prior "
    "is already aligned and the remaining 3D residual is small with a heavy outlier tail. "
    "STRUCTURED_DEFORMATION, when available, builds an aggressive observation-fit proposal "
    "from the ORIGINAL registered complete prior and projects its reliable visible motion "
    "through an embedded surface graph onto a complete carrier. It is a bounded geometric "
    "candidate for persistent coherent local mismatch that survives ordinary updates, "
    "not a license to delete unobserved geometry. The proposal still undergoes hard "
    "integrity checks and a before/after review. "
    "A substantial p90 distance or coherent local or object-extent discrepancy calls "
    "for UPDATE_POSTERIOR, which can move low-frequency structure. "
    "ACCEPT stops without changing the current carrier. The maximum round count is a "
    "safety ceiling, not a target: stop as soon as the observed geometry is adequately "
    "explained or further movement is more likely to damage the complete prior. "
    "Do not stop merely because one small local step had little gain while a coherent "
    "blue-only structure still remains; first consider a different available route. "
    "Conversely, do not run extra rounds just to exhaust the budget. Two consecutive "
    "accepted steps with negligible multiview coverage and relative 3D residual gains "
    "will trigger an independent deterministic plateau stop. "
    "CAMERA1 is the actual saved acquisition camera with the calibrated physical depth "
    "and scale relation. The other orbit views are synthetic diagnostic projections and "
    "may use different framing; they provide evidence for local assimilation but are not "
    "automatically reliable as additional global OT cameras. For broad structural or "
    "extent mismatch, prefer CAMERA1 transport and use auxiliary views to audit and "
    "assimilate the result. Choose ALL_ACTIVE_VIEWS for OT only if the supplied evidence "
    "clearly supports their calibration for this purpose; do not equate more views with "
    "better correspondence by default. "
    "CONSERVATIVE, BALANCED, and EXPANSIVE are preset strengths, not free parameters. "
    "SAVED_FOUR uses exactly the four supplied cameras; ADAPTIVE_ORBIT adds up to six "
    "same-orbit views selected by visible positive partial evidence. Compare the two "
    "view options' measured unique visible partial fractions when choosing; a meaningful "
    "gain in physical partial visibility supports ADAPTIVE_ORBIT, while negligible gain "
    "favors the simpler saved four. More cameras are not automatically better. "
    "The goal is both observed fit and a complete, coherent shape: neither ignoring a "
    "real observed part nor collapsing hidden prior geometry is acceptable. "
    "If an accepted UPDATE_POSTERIOR leaves the same coherent blue-only region in multiple "
    "views, do not blindly repeat the same profile and transport; consider the structured "
    "route when it is available. Choose it only from positive observation, not a guessed category. "
    "Do not predict transforms, coordinates, thresholds, or semantic part labels. "
    "Prefer preserving coherent prior structure over fitting a few noisy partial points. "
    "Never claim access to GT, CD, or EMD. Keep reasons short and evidence-specific."
)


def _mask(points: np.ndarray, projector) -> np.ndarray:
    uv, depth = projector.project(points)
    _, mask, _ = zbuffer_depth_with_indices(
        uv, depth, projector.image_shape, splat_radius=1,
    )
    return mask


def visible_partial_fraction(partial: np.ndarray, projectors, *, resolution: int = 256) -> float:
    """Fraction of physical partial samples visible in at least one candidate view."""
    visible = np.zeros(len(partial), dtype=bool)
    for projector in projectors:
        uv, depth = projector.project(partial)
        height, width = projector.image_shape
        scaled = np.asarray(uv, dtype=np.float64) * np.array(
            [resolution / width, resolution / height], dtype=np.float64,
        )
        _, mask, indices = zbuffer_depth_with_indices(
            scaled, depth, (resolution, resolution), splat_radius=1,
        )
        visible[np.unique(indices[mask])] = True
    return float(visible.mean()) if len(visible) else 0.0


def render_diagnostic_board(
    partial: np.ndarray, carrier: np.ndarray, projectors, path: Path,
    *, focus_points: np.ndarray | None = None,
    depth_reference_points: np.ndarray | None = None,
) -> Path:
    """Show partial, complete prior, and overlay separately under identical cameras."""
    if len(projectors) not in (4, 6):
        raise ValueError("a GPT diagnostic board requires four or six cameras")
    rows = (len(projectors) + 1) // 2
    size = 320
    header = 58
    footer = 26
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, 17) if Path(font_path).is_file() else ImageFont.load_default()
    small_font = ImageFont.truetype(font_path, 14) if Path(font_path).is_file() else ImageFont.load_default()
    board = Image.new("RGB", (size * 6, (size + header) * rows + footer), "white")
    draw = ImageDraw.Draw(board)
    for view, projector in enumerate(projectors, start=1):
        observed = _mask(partial, projector)
        predicted = _mask(carrier, projector)
        separate = []
        for mask, color in ((observed, (38, 103, 224)), (predicted, (224, 51, 47))):
            pixels = np.full((*projector.image_shape, 3), 248, dtype=np.uint8)
            pixels[mask] = color
            if depth_reference_points is not None:
                _, reference_depth = projector.project(depth_reference_points)
                valid = reference_depth[np.isfinite(reference_depth) & (reference_depth > 0)]
                if len(valid):
                    low,high = np.quantile(valid,[.01,.99])
                    uv,z = projector.project(partial if len(separate)==0 else carrier)
                    zbuffer,valid_mask,_ = zbuffer_depth_with_indices(uv,z,projector.image_shape,splat_radius=1)
                    shade = np.clip((zbuffer[valid_mask]-low)/max(high-low,1e-9),0,1)
                    # Shared before/after near-light, far-dark depth shading.
                    base = np.asarray(color,dtype=float)
                    pixels[valid_mask] = (base[None,:]*(.45+.55*shade[:,None])
                                         + 230.*(.55-.55*shade[:,None])).astype(np.uint8)
            separate.append(pixels)
        overlay = separate[1].copy()
        overlay[observed] = (38, 103, 224)
        overlay[observed & predicted] = (133, 68, 155)
        base_x = ((view - 1) % 2) * 3 * size
        base_y = ((view - 1) // 2) * (size + header)
        draw.text((base_x + 8, base_y + 3),
                  "REFERENCE VIEW (0)" if view == 1 else f"AUXILIARY VIEW {view - 1}",
                  font=font, fill=(20, 20, 20))
        for col, (pixels, label) in enumerate(zip(
            (*separate, overlay),
            ("A  OBSERVED PARTIAL (blue)", "B  COMPLETE PRIOR (red)", "C  OVERLAY / MISMATCH"),
        )):
            x = base_x + col * size
            draw.text((x + 8, base_y + 30), label, font=small_font, fill=(20, 20, 20))
            tile = Image.fromarray(pixels)
            if focus_points is not None:
                uv, _ = projector.project(focus_points)
                uv = uv[np.isfinite(uv).all(axis=1)]
                if len(uv):
                    centre = .5*(uv.min(axis=0)+uv.max(axis=0))
                    radius = max(32., .7*float(np.ptp(uv, axis=0).max()))
                    height, width = projector.image_shape
                    box = (max(0, int(centre[0]-radius)), max(0, int(centre[1]-radius)),
                           min(width, int(centre[0]+radius)+1), min(height, int(centre[1]+radius)+1))
                    if box[2] > box[0] and box[3] > box[1]:
                        tile = tile.crop(box)
            tile = tile.resize((size, size), Image.Resampling.NEAREST)
            board.paste(tile, (x, base_y + header))
    draw.text((10, (size + header) * rows + 4),
              "Blue only: observed   |   Red only: unknown   |   Purple: 2D overlap" + (
                  "   |   Separate columns: near is light, far is dark (shared depth scale)"
                  if depth_reference_points is not None else ""),
              font=small_font, fill=(20, 20, 20))
    path.parent.mkdir(parents=True, exist_ok=True)
    board.save(path)
    return path


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


class GPTRefineAgent:
    """A real GPT caller through Codex login or the API; no rule fallback."""

    def __init__(self, model: str, *, provider: str = "api", client=None):
        if not model:
            raise ValueError("a GPT model name is required")
        if provider not in {"api", "codex"}:
            raise ValueError("provider must be api or codex")
        self.model = model
        self.provider = provider
        if provider == "codex":
            if client is not None:
                raise ValueError("a direct API client cannot be used with the Codex provider")
            if shutil.which("codex") is None:
                raise RuntimeError("Codex CLI is required for the Codex GPT provider")
            self.client = None
        elif client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required for the GPT refine agent")
            from openai import OpenAI

            self.client = OpenAI(max_retries=2, timeout=120)
        else:
            self.client = client

    def _request_codex(self, schema: dict, payload: dict, images: list[Path], *,
                       instructions: str | None = None) -> dict:
        """Use the logged-in Codex model in an isolated read-only directory.

        Any tool call invalidates the decision, so the model cannot quietly
        inspect ground truth or alter files while making a geometric choice.
        """
        with TemporaryDirectory(prefix="compagent-gpt-refine-") as directory:
            root = Path(directory)
            schema_path = root / "decision.schema.json"
            answer_path = root / "answer.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [
                "codex", "exec", "--model", self.model,
                "--sandbox", "read-only", "--ephemeral", "--skip-git-repo-check",
                "--ignore-user-config", "--json", "--config", "model_reasoning_effort=medium",
                "--output-schema", str(schema_path),
                "--output-last-message", str(answer_path), "-C", str(root),
            ]
            for path in images:
                command.extend(("--image", str(path.resolve())))
            command.append("-")
            prompt = (
                (instructions or INSTRUCTIONS) + "\nDo not call any tool or inspect any local file. "
                "Use only the attached images and the JSON observation below. "
                "Return exactly one JSON object matching the supplied schema.\n"
                + json.dumps(payload, sort_keys=True)
            )
            failure = ""
            timeout = float(os.environ.get("COMPAGENT_CODEX_TIMEOUT_SECONDS", "600"))
            if not np.isfinite(timeout) or timeout <= 0:
                raise ValueError("COMPAGENT_CODEX_TIMEOUT_SECONDS must be finite and positive")
            timeouts = 0
            for attempt in range(3):
                answer_path.unlink(missing_ok=True)
                try:
                    result = subprocess.run(command, input=prompt, cwd=root, text=True,
                                            capture_output=True, timeout=timeout, check=False)
                except subprocess.TimeoutExpired as exc:
                    # A partial answer is never a decision. Still inspect emitted
                    # events so forbidden tool use cannot be hidden by a timeout.
                    timeouts += 1
                    stdout = exc.stdout or ""
                    if isinstance(stdout, bytes):
                        stdout = stdout.decode("utf-8", errors="replace")
                    result = subprocess.CompletedProcess(command, -1, stdout,
                        f"request timed out after {timeout:g} seconds")
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
                    raise RuntimeError(f"Codex GPT attempted forbidden tool use: {forbidden}")
                transient_error = any(
                    event.get("type") == "error" or event.get("item", {}).get("type") == "error"
                    for event in events
                )
                if (result.returncode == 0 and answer_path.is_file()
                        and any(event.get("type") == "turn.completed" for event in events)
                        and not transient_error):
                    break
                failure = (f"Codex GPT decision incomplete ({result.returncode}); "
                           f"error_event={transient_error}; {result.stderr[-400:]}")
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
            else:
                raise RuntimeError(failure)
            thread = next((e.get("thread_id") for e in events
                           if e.get("type") == "thread.started"), None)
            usage = next((e.get("usage") for e in events
                          if e.get("type") == "turn.completed"), None)
            return {"text": answer_path.read_text(encoding="utf-8"),
                    "response_id": thread, "usage": usage,
                    "transport": {"attempts": attempt + 1, "timeouts": timeouts,
                                  "timeout_seconds": timeout}}

    def _request(self, *, schema: dict, name: str, payload: dict, images: list[Path],
                 instructions: str | None = None) -> dict:
        if self.provider == "codex":
            raw = (self._request_codex(schema, payload, images, instructions=instructions)
                   if instructions is not None else self._request_codex(schema, payload, images))
        else:
            content = [{"type": "input_text", "text": json.dumps(payload, sort_keys=True)}]
            content.extend({"type": "input_image", "image_url": _data_uri(path), "detail": "high"}
                           for path in images)
            response = self.client.responses.create(
                model=self.model,
                reasoning={"effort": "medium"},
                instructions=instructions or INSTRUCTIONS,
                input=[{"role": "user", "content": content}],
                text={"format": {"type": "json_schema", "name": name,
                                 "strict": True, "schema": schema}},
            )
            if getattr(response, "status", None) != "completed" or not response.output_text:
                raise RuntimeError(f"GPT returned no completed structured decision: {getattr(response, 'status', None)}")
            raw = {"text": response.output_text,
                   "response_id": getattr(response, "id", None),
                   "usage": None}
        decision = json.loads(raw["text"])
        if set(decision) != set(schema["required"]):
            raise ValueError("GPT decision did not match the required fields")
        for key, field in schema["properties"].items():
            if "enum" in field and decision[key] not in field["enum"]:
                raise ValueError(f"GPT returned invalid {key}: {decision[key]}")
        if not isinstance(decision["evidence"], list) or any(
            not isinstance(item, str) for item in decision["evidence"]
        ):
            raise ValueError("GPT evidence must be a list of strings")
        return {"decision": decision, "response_id": raw["response_id"],
                "model": self.model, "reasoning_effort": "medium", "provider": self.provider, "usage": raw["usage"],
                "transport": raw.get("transport"),
                "prompt_version": PROMPT_VERSION}

    def plan(self, current: Observation, previous: Observation | None,
             *, round_index: int, maximum_rounds: int, board: Path,
             recent_trace: list[dict], view_options: dict | None = None,
             structural_available: bool = False,
             plateau_streak: int = 0) -> tuple[Decision, dict]:
        last = recent_trace[-1] if recent_trace else {}
        recent = {
            "round": last.get("round"),
            "decision": last.get("decision"),
            "accepted": last.get("accepted"),
            "candidate_results": [
                {"profile": item.get("profile"), "transport": item.get("transport"),
                 "hard_verdict": item.get("verdict", {}).get("reason"),
                 "gpt_review": (item.get("gpt_review") or {}).get("decision")}
                for item in last.get("candidates", [])
            ],
        }
        actions = ["UPDATE_POSTERIOR", "REFINE_OBSERVED", "ACCEPT"]
        if structural_available and not any(
            item.get("accepted") and item.get("decision", {}).get("action") == "STRUCTURED_DEFORMATION"
            for item in recent_trace
        ):
            actions.insert(2, "STRUCTURED_DEFORMATION")
        schema = {**PLAN_SCHEMA, "properties": {
            **PLAN_SCHEMA["properties"], "action": {"type": "string", "enum": actions},
        }}
        record = self._request(
            schema=schema, name="posterior_refine_plan",
            payload={"task": "plan_next_action", "round": round_index + 1,
                     "maximum_rounds": maximum_rounds,
                     "remaining_rounds_including_this_one": maximum_rounds - round_index,
                     "plateau_streak": plateau_streak,
                     "plateau_patience": PLATEAU_PATIENCE,
                     "image_columns": {
                         "A": "observed physical partial point cloud, blue, incomplete",
                         "B": "generated complete prior point cloud, red, preserve unobserved geometry",
                         "C": "same-camera overlay: blue-only is missing observed support; red-only is unknown",
                     },
                     "available_actions": actions,
                     "current_observation": asdict(current),
                     "view_options": view_options,
                     "previous_observation": asdict(previous) if previous else None,
                     "previous_round": recent if last else None},
            images=[board],
        )
        choice = record["decision"]
        decision = Decision(choice["action"], choice["profile"], choice["reason"],
                            choice["transport"])
        return decision, record

    def review(self, before: Observation, after: Observation, *,
               before_board: Path, after_board: Path, profile: str,
               transport: str, integrity: dict,
               remaining_candidates: int = 0,
               previous_candidate_results: list[dict] | None = None,
               local_boards: tuple[Path, Path] | None = None,
               local_diagnostics: dict | None = None) -> dict:
        if remaining_candidates < 0:
            raise ValueError("remaining_candidates must be nonnegative")
        allowed_actions = ["ACCEPT_UPDATE", "STOP_KEEP_CURRENT"]
        if remaining_candidates:
            allowed_actions.insert(1, "TRY_NEXT_CANDIDATE")
        schema = {
            **REVIEW_SCHEMA,
            "properties": {
                **REVIEW_SCHEMA["properties"],
                "action": {"type": "string", "enum": allowed_actions},
            },
        }
        if local_boards is not None:
            fields = {key:{"type":"boolean"} for key in (
                "correspondence_supported", "core_shape_preserved",
                "attachment_preserved", "unaffected_parts_preserved")}
            fields.update({key:{"type":"string"} for key in (
                "observed_region_description", "prior_region_description",
                "motion_direction_evidence", "uncertainty")})
            schema = {**schema, "properties": {**schema["properties"],
                "local_structure": {"type":"object", "properties":fields,
                                    "required":list(fields), "additionalProperties":False}},
                "required":[*schema["required"],"local_structure"]}
        local_payload = ({
            "local_geometry": local_diagnostics,
            "local_review_contract": (
                "This is a local rigid translation candidate: its core retains exact shape; "
                "a geodesic transition connects it to the unchanged complete carrier. "
                "Two extra boards show the SAME cropped camera window before/after. "
                "Separate columns use a shared depth scale: nearer is lighter. "
                "Describe the observed and prior structures visually rather than guessing "
                "segmentation labels. State the supported direction of movement. "
                "Check that moved prior geometry is the SAME physical part supported by "
                "the blue scan, that attachment and overall structure remain natural, "
                "and that nearby parts are not dragged along. A nearest-neighbour residual "
                "reduction alone does not establish part identity. Reject invented bumps, "
                "stretched attachments or a surface patch moved to explain a different part. "
                "Use the full boards to check the complete structure and the crops for detail."
            ),
        } if local_boards is not None else {})
        result = self._request(
            schema=schema, name="posterior_refine_review",
            payload={"task": "review_solver_proposal",
                     "allowed_review_actions": {
                         "ACCEPT_UPDATE": "keep the proposal and continue the bounded loop",
                         "STOP_KEEP_CURRENT": "reject it and terminate without changing the carrier",
                         **({"TRY_NEXT_CANDIDATE": "reject it and test the next preset route"}
                            if remaining_candidates else {}),
                     },
                     "remaining_candidates": remaining_candidates,
                     "previous_candidate_results": previous_candidate_results or [],
                     "before_observation": asdict(before),
                     "after_observation": asdict(after),
                     "profile": profile, "transport": transport,
                     "hard_integrity_passed": bool(integrity.get("passed", False)),
                     "images_order": ["before", "proposal"] + (
                         ["local_before", "local_proposal"] if local_boards else []),
                     **local_payload},
            images=[before_board, after_board] + (list(local_boards) if local_boards else []),
        )
        if local_boards is not None and result["decision"]["action"] == "ACCEPT_UPDATE":
            checks = result["decision"]["local_structure"]
            if not all(checks[key] for key in ("correspondence_supported", "core_shape_preserved",
                                              "attachment_preserved", "unaffected_parts_preserved")):
                result["model_decision"] = dict(result["decision"])
                result["decision"] = {**result["decision"],
                    "action":"TRY_NEXT_CANDIDATE" if remaining_candidates else "STOP_KEEP_CURRENT",
                    "reason":"local_structure_check_failed"}
        return result
