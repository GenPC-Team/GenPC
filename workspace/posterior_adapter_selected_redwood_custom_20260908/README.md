# Selected Redwood and Custom Results

This directory consolidates the selected from-scratch PosteriorAdapter runs
from `posterior_adapter_e2e_redwood_custom_20260908` into one sample-centric
layout. Files are hard-linked to the source run so the collection does not
duplicate the approximately 2.5 GB of artifacts.

## Layout

- `redwood/samples/<id>/final_100k.ply`: selected 100k-point completion.
- `custom/samples/<name>/final_100k.ply`: selected 100k-point completion.
- Each sample also keeps its partial input, saved camera/depth/semantic
  observation, generated Pixal prior, registration, Gaussian/Posterior output,
  and available diagnostics.
- Dataset-level `offline_metrics.{csv,json}` contain the post-hoc 16k metrics.
- `redwood/selection_manifest.json` records the selected source branch and
  rejected retries.

## Redwood selection

- `07136` uses the rerun selected from
  `redwood/view_retry_alt/07136` (`opposite_180`) plus its PosteriorAdapter
  output.
- `07306` uses the rerun selected from
  `redwood/view_retry/07306` (`opposite_180`) and its accepted Gaussian output.
- The other eight Redwood samples use their original fresh run from the same
  experiment root.

Ground truth was used only for the offline metric files and was not copied
into this collection.
