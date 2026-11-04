#!/usr/bin/env python3
"""Copy an Image Gen result into a prior-agent run with exact prompt provenance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path,
                        help="Defaults to the current prior-agent prompt")
    parser.add_argument("--reference-image", type=Path, action="append", default=[],
                        help="Additional input image used for an Image Gen edit; repeat as needed")
    args = parser.parse_args()
    root = args.output_root.resolve()
    source = args.image.resolve()
    state = json.loads((root / "prior_agent/prior_agent_manifest.json").read_text())
    if state["accepted"] is not None:
        raise ValueError("a prior image is already accepted in this run")
    prompt_file = (args.prompt_file or Path(state["current_prompt_file"])).resolve()
    if not source.is_file() or not prompt_file.is_file():
        raise FileNotFoundError("generated image or prompt is missing")
    destination = root / "semantic.png"
    shutil.copy2(source, destination)
    depth = Path(state["selected_depth"]).resolve()
    references = [path.resolve(strict=True) for path in args.reference_image]
    from PIL import Image
    with Image.open(destination) as image:
        size = f"{image.width}x{image.height}"
    record = {
        "sample": state["sample"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Codex Image Gen tool",
        "model": "UNKNOWN", "model_path": "UNKNOWN",
        "checkpoint_path": "UNKNOWN", "transformer_path": "UNKNOWN",
        "input_depth": str(depth), "input_depth_sha256": sha256(depth),
        "input_references": [{"path": str(depth), "sha256": sha256(depth),
                              "role": "depth"}] +
                            [{"path": str(path), "sha256": sha256(path),
                              "role": "edit_reference"} for path in references],
        "source_image": str(source), "semantic_image": str(destination),
        "semantic_sha256": sha256(destination),
        "prompt_file": str(prompt_file),
        "prompt": prompt_file.read_text(encoding="utf-8").strip(),
        "negative_prompt": "NONE",
        "generation_parameters": {
            "resolution": size,
            "resize_policy": "Image Gen provider UNKNOWN; no pre-resize before generation",
            "seed": "UNKNOWN", "steps": "UNKNOWN", "cfg": "UNKNOWN",
            "scheduler": "UNKNOWN",
            "backend": "Codex Image Gen tool; exact model UNKNOWN",
        },
        "postprocessing": "None before prior review; later steps pending.",
        "approval": "Pending prior agent review; user has not approved this candidate.",
        "exactly_reproducible": False,
    }
    (root / "generation.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    archive = root / "prior_agent" / "generations"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / f"{record['semantic_sha256']}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(json.dumps({"image": str(destination), "prompt": str(prompt_file),
                      "sha256": record["semantic_sha256"]}))


if __name__ == "__main__":
    main()
