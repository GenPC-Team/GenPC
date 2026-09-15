# Agent decision packet: 07136

You are the high-level planner for a bounded zero-shot completion agent.
Read the current state and diagnostic board, then select exactly one permitted
discrete action. Do **not** supply pose, translation, scale, thresholds, or
continuous optimization parameters; deterministic geometry tools own them.
Do **not** use ground truth, CD, or EMD.

- State: `/opt/data/private/cr/lab/GenPC/.codex-worktrees/agentic-01184-probe/workspace/posterior_adapter_e2e_redwood_custom_20260908/redwood/view_retry_alt/07136/agent_state.json`
- Diagnostic board: `/opt/data/private/cr/lab/GenPC/.codex-worktrees/agentic-01184-probe/workspace/posterior_adapter_e2e_redwood_custom_20260908/redwood/view_retry_alt/07136/diagnostics/step_05_adaptation_diagnosis/diagnostic_board.png`
- Allowed next actions: `REPLAN_VIEW, RESTORE_ATTEMPT, ADAPT_AXIS_SCALE, ADAPT_LOCAL, ACCEPT`
- Remaining tool budget: `9`
- No-GT diagnostic recommendation (may be overridden only with evidence from this state):
  `{"source": "fixed_no_gt_diagnostic_policy", "must_be_verified_by": "state-bound MLLM or human planner", "ground_truth_cd_emd_used": false, "action": "ADAPT_AXIS_SCALE", "arguments": {}, "hypothesis": "The observed Camera-1 surface supports a relative-axis extent correction; apply its coherent whole-carrier initialization before the fixed local Gaussian edit.", "camera_axis_evidence": {"pixel_pairs": 23209, "within_metric_limit": 19498, "collision_free_pairs": 19498, "max_residual": 0.06623144441569649, "residual_median": 0.0072269026154915435, "residual_p90": 0.023481209574079936, "active": true, "controls": 19498, "trimmed_controls": 14623, "principal_axes": [[0.829128623008728, -5.253213419820213e-10, -0.5590579509735107], [0.010961920954287052, 0.9998077750205994, 0.016257423907518387], [0.5589504241943359, -0.019607843831181526, 0.8289691805839539]], "visible_scale": [1.0016384031882772, 1.0042638417872314, 1.0687974176751], "relative_scale": [0.9777464266264563, 0.9803092409118148, 1.0433035041319028], "applied_scale": [0.9777464266264563, 0.9803092409118148, 1.0433035041319028], "retain_isotropic_component": false, "isotropic_scale_removed": 1.0244357595294478, "anisotropy_log": 0.04239212518633096, "isotropic_error": 0.007059226165901817, "anisotropic_error": 0.00514821405029719, "axis_supported": [true, true, true], "source_axis_spread": [0.10925002175372543, 0.12661117356564242, 0.09206616507859228], "target_axis_spread": [0.10942901733768609, 0.127151023578222, 0.0984000794912489], "minimum_axis_spread_ratio": 0.08, "axis_frame": "saved_camera", "residual_reduction": 0.2707112749603334, "max_log_stretch": 0.16, "minimum_anisotropy": 0.025, "minimum_residual_reduction": 0.03, "singular_values": [18.57222211570619, 12.174489326438158, 6.304577679103591], "trace": [{"kept": 14623, "raw_scale": [1.0002916767593153, 1.0055621655018883, 1.0749992674732616], "clipped_scale": [1.0002916767593153, 1.0055621655018883, 1.0749992674732616], "residual_median": 0.0069431462820080695, "residual_trim_limit": 0.01226921134052977}, {"kept": 14623, "raw_scale": [1.0008082949821084, 1.0036998288859336, 1.0690981348612638], "clipped_scale": [1.0008082949821084, 1.0036998288859336, 1.0690981348612638], "residual_median": 0.006424206200434837, "residual_trim_limit": 0.012177365042214658}, {"kept": 14623, "raw_scale": [1.001356074875984, 1.0040495860447152, 1.0681136372254472], "clipped_scale": [1.001356074875984, 1.0040495860447152, 1.0681136372254472], "residual_median": 0.006320910526777842, "residual_trim_limit": 0.012229856590530257}], "field": "camera1_supported_relative_axis_scale_carrier"}}`

Return JSON in this exact form:

```json
{
  "state_sha256": "31ce41a08decf78b69fe724589f735eb24b28d50f92e37e25f4826aa50e87b44",
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
