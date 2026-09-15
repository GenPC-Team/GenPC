# Agent decision packet: 07306

You are the high-level planner for a bounded zero-shot completion agent.
Read the current state and diagnostic board, then select exactly one permitted
discrete action. Do **not** supply pose, translation, scale, thresholds, or
continuous optimization parameters; deterministic geometry tools own them.
Do **not** use ground truth, CD, or EMD.

- State: `/opt/data/private/cr/lab/GenPC/.codex-worktrees/agentic-01184-probe/workspace/posterior_adapter_e2e_redwood_custom_20260908/redwood/view_retry/07306/agent_state.json`
- Diagnostic board: `/opt/data/private/cr/lab/GenPC/.codex-worktrees/agentic-01184-probe/workspace/posterior_adapter_e2e_redwood_custom_20260908/redwood/view_retry/07306/diagnostics/step_07_accepted/diagnostic_board.png`
- Allowed next actions: `none`
- Remaining tool budget: `7`
- No-GT diagnostic recommendation (may be overridden only with evidence from this state):
  `{"source": "fixed_no_gt_diagnostic_policy", "must_be_verified_by": "state-bound MLLM or human planner", "ground_truth_cd_emd_used": false, "action": "ACCEPT", "arguments": {}, "hypothesis": "No further bounded tool is valid for this state."}`

Return JSON in this exact form:

```json
{
  "state_sha256": "cfc3259ea9619c057e4af1807bfefedce83192a6a51e3a3c904b4eed91682856",
  "action": {"name": "ONE_ALLOWED_ACTION", "arguments": {}},
  "rationale": "Evidence from the current diagnostic board and verifier.",
  "planner": "MLLM model identifier",
  "ground_truth_used": false
}
```

Argument contract:

- `SELECT_VIEW` and `REPLAN_VIEW`: `{"candidate": "<one name from candidate_manifest.json>"}`
- `RESCUE_GLOBAL`, `RESTORE_ATTEMPT`, `GENERATE_PRIOR`, `ALIGN_GLOBAL`, `REFINE_ALIGNMENT`, `ADAPT_LOCAL`, and `ADAPT_AXIS_SCALE`:
  `{}`.
- `ACCEPT`: `{}`, or `{"candidate": "rescue"}` / `{"candidate":
  "registered"}` / `{"candidate": "baseline"}` / `{"candidate":
  "adapted"}` / `{"candidate": "axis"}` when the fresh verifier finds
  that a later tool result is weaker than the bounded rescue / pre-edit
  registered candidate / replayed initial candidate / ordinary Gaussian
  candidate / camera-axis candidate.
- `COMPLETE_SEMANTIC`: `{"strategy": "qwen"}`
- `REFINE_SEMANTIC`: `{"source": "/absolute/path/to/pose_locked_external_clarity.png"}`.
  The supplied image is recorded and checked against the Camera-1 semantic
  observation before it becomes a candidate prior-conditioning image.
- `SELECT_CONDITIONING_IMAGE`: `{"source": "qwen" | "clarity"}`.
  The selected image is copied to the fixed Pixal input slot; no geometry is
  changed by this action.
