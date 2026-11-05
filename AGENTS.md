# Workspace Notes

## Research Engineering Scope
- This repository supports an academic paper/research project. Prefer methods
  that are simple, explainable, reproducible, and easy to ablate.
- Avoid over-engineering, model stacking, broad framework rewrites, or
  sample-specific hacks unless the user explicitly asks for a focused
  diagnostic experiment.

## Default Python Environment
- This project defaults to the conda environment `genpc`.
- Do not assume `python` or `pip` from `PATH` points to that environment.
- On this machine, use
  `/home/chenrui/miniconda3/envs/genpc/bin/python`; verify the path on other
  machines before running. Use `python -m pip` through that interpreter.

## Command Convention
- Install packages into `genpc`, not `base`.
- Run project scripts with the explicit `genpc` interpreter above.
- If a command needs `pip`, use that interpreter with `-m pip`.
- Current object pipeline: `scripts/run_prior_generation_agent.py prepare`,
  interactive Image Gen, `scripts/run_prior_generation_agent.py review`, then
  `CUDA_VISIBLE_DEVICES=0 .../genpc/bin/python scripts/run_four_stage_pipeline.py`.
  See `README.md` for exact arguments.
- Keep the prompt, selected depth/camera, same-canvas audit, transparent Pixal
  input, Pixal/MoGe assets, registration, diagnostics, refinement, fusion,
  manifests and logs together for paper experiments. The accepted ten-case
  archive is `workspace/redwood10_final/`; no other workspace directory is
  currently retained.
- Current Qwen ControlNet/Nunchaku test pins are `diffusers==0.36.0` and
  `transformers==4.57.6`.

## Experiment State Recording
- Maintain `PLAN.md` as the active refactor/task plan. Before making pipeline,
  registration, Qwen, MoGe, Hunyuan, FreeReg, or cleanup changes, read `PLAN.md`
  and check which stage the work belongs to.
- Treat `docs/core_registration_pipeline.md` as the canonical description of
  the project's core registration method. Before changing partial-to-image,
  MoGe, Hunyuan, FreeReg, DepthPro, or complete-to-partial composition logic,
  read that document and update it if the method changes.
- After completing or changing a planned stage, update `PLAN.md` with status,
  output paths, and any new risks or decisions.
- Do not mark a planned stage complete unless the relevant outputs exist and
  have been verified.
- Maintain `PROJECT_STATE.md` as the canonical record for good outputs,
  accepted experiments, and fragile parameter choices.
- When the user says an output is good, correct, should be kept, or uses similar
  language such as "效果很好", "这个是对的", "保留这个", immediately append or
  update an entry in `PROJECT_STATE.md` before continuing with more experiments.
- Each accepted-result entry must include:
  - timestamp and sample id;
  - exact output file path(s);
  - input file path(s);
  - model name/path and checkpoint/transformer path;
  - full prompt and negative prompt, copied verbatim;
  - generation parameters such as resolution, resize policy, seed, steps,
    CFG/guidance scale if used, and any scheduler/backend choices;
  - postprocessing steps such as RMBG, resize, masks, MoGe, Hunyuan, FreeReg,
    ICP, or coordinate flips;
  - what the user approved and what should not be changed without asking.
- If any of those fields are unknown because they were not recorded at the time,
  write `UNKNOWN` explicitly and mark the result as not exactly reproducible.
  Do not later present guesses as facts.
- Before changing prompts, model paths, generation resolution, seeds, or
  registration parameters, check `PROJECT_STATE.md` for accepted baselines and
  preserve or copy them instead of overwriting.
- For one-off experiments, save the prompt next to the output using a descriptive
  `*_prompt.txt` file. For scripted/main-flow experiments, keep prompt builders
  in code and add tests for prompt text when feasible.

## Model Download Notes
- New MLLM runs use `gpt-6-astra` with reasoning effort `medium` (user
  preference, 2026-11-05). This applies to prior interpretation/review and
  refinement planning/review. Preserve historical GPT-6 Sol run metadata.
- The current validated route is saved-camera depth → Codex Image Gen semantic
  completion → GPT-6 Sol prior review → RMBG transparent Pixal3D input →
  fixed Pixal--MoGe--partial registration → GPT-6 Sol geometric refinement →
  continuous observation fusion. Ground truth is used only for offline metrics.
- Qwen-Image-Edit-2511 and Nunchaku are an optional local backup, not a
  dependency of the accepted Redwood10 route. If used, their paths are
  `models/Qwen-Image-Edit-2511` and
  `models/nunchaku-qwen-image-edit/nunchaku_qwen_image_2511_balance_int4.safetensors`.
- Pixal3D source must be available at `models/Pixal3D` or via
  `PIXAL3D_SOURCE`; the tested source commit and its supplementary TRELLIS.2
  dependencies are recorded in `docs/models.md`. Its model files live under
  `models/Pixal3D-weights`; DINOv3 lives under
  `models/dinov3-vitl16-pretrain-lvd1689m`.
- Native Pixal--MoGe registration uses `models/moge-2-vitl/model.pt` and
  RMBG-2.0 under `models/RMBG-2.0`. The source image, saved MoGe cache, and
  Pixal camera metadata must all describe the same preprocessed Pixal input.
- Model weights are external assets: use the current links and licence notes in
  `docs/models.md`, rather than adding checkpoint binaries to the repository.
