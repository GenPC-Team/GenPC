# CompAgent Pixal3D-stage reproduction package

This directory is self-contained for the inference stages beginning with the
retained Pixal3D asset. It contains no GT and no metric-driven selection.

For each Redwood/Custom sample it retains:

- Camera-1 depth/semantic images, camera parameters, UV map and object mask;
- the partial observation;
- Pixal3D input, metadata, textured GLB, ordered 100k carrier and native MoGe cache;
- a portable four-view camera manifest (FOV plus four camera poses);
- the accepted registered prior as a numerical checkpoint;
- the final posterior and the before/after partial-complete overlays.

Running the optional final continuous measurement assimilation writes its
audit under `<dataset>/fusion_continuous/` and concise geometry/textured 100k
deliverables under `<dataset>/final_fused/<sample>/`. These reproducible
derived outputs preserve carrier ordering and are not inputs to registration
or PosteriorAdapter replay. The Custom Fox decoder starts from its explicitly
retained visual-best carrier.

Run from the GenPC repository root:

```bash
/opt/data/private/cr/miniconda3/envs/genpc/bin/python   scripts/reproduce_packaged_mainline.py   --bundle-root workspace/compagent_pixal_reproduction_20260925   --dataset redwood --samples 01184 --output-root /tmp/compagent_replay_01184
```

The replay first reconstructs Pixal--MoGe--partial registration from the
retained Pixal3D stage, then runs the frozen posterior solver with the saved
four cameras. `manifest.json` stores SHA-256 for every copied file. The Fox
visual-best result is explicitly recorded as the accepted residual-proximal
visual override; every other sample uses the shared posterior mainline.

`paper_assets/` contains the retained Fox paper visualizations and textured
overlay assets. They are not read by inference.
