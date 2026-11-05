"""Optional geometry tools must remain inside the four-stage data flow."""
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

from scripts import run_four_stage_pipeline as pipeline


@pytest.mark.parametrize("local_flag", ["--coherent-local-motion", "--planned-local-motion"])
def test_optional_geometry_flows_through_refinement_and_fusion(tmp_path, monkeypatch, local_flag):
    sample = "object"
    camera = tmp_path / "inputs/camera" / sample
    pixal = tmp_path / "inputs/pixal" / sample
    partial = tmp_path / "inputs/partial/object.ply"
    for path in (camera, pixal, partial.parent, tmp_path / "prior_agent"):
        path.mkdir(parents=True)
    Image.new("RGB", (2, 2), "white").save(camera / "img.png")
    Image.new("L", (2, 2), 100).save(camera / "depth.png")
    rgba = Image.new("RGBA", (2, 2), (255, 255, 255, 0))
    rgba.putpixel((0, 0), (20, 20, 20, 255))
    rgba.save(pixal / "gpt_image.png")
    (camera / "camera.pth").write_bytes(b"camera")
    partial.write_bytes(b"partial")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Complete the observed object.")
    prior = {"sample": sample, "accepted": {
        "source_image": str(camera / "img.png"), "prompt_file": str(prompt),
        "source_sha256": pipeline._sha256(camera / "img.png"),
        "installed_sha256": pipeline._sha256(camera / "img.png"),
        "pixal_input_sha256": pipeline._sha256(pixal / "gpt_image.png")}}
    (tmp_path / "prior_agent/prior_agent_manifest.json").write_text(json.dumps(prior))
    calls = {}
    states = []

    def capture(name, command, outputs, state, *args, **kwargs):
        calls[name] = command
        states.append(state)

    monkeypatch.setattr(pipeline, "_stage", capture)
    arguments = ["pipeline", "--output-root", str(tmp_path), "--dry-run",
                 local_flag, "--residual-registration"]
    monkeypatch.setattr(sys, "argv", arguments)
    pipeline.main()
    assert list(calls)[-2:] == ["refinement", "fusion"]
    refine = calls["refinement"]
    assert local_flag in refine
    assert "differentiable_residual" in refine[refine.index("--prior") + 1]
    assert refine[refine.index("--multiview-manifest") + 1] == calls["registration_residual"][
        calls["registration_residual"].index("--multiview-manifest") + 1]
    fusion = calls["fusion"]
    assert Path(fusion[fusion.index("--posterior") + 1]).name == "agent_selected_posterior_100k.ply"
    assert fusion[fusion.index("--mode") + 1] == "continuous"

    # A resume cannot silently mix a different geometry policy with cached outputs.
    (tmp_path / "four_stage_pipeline.json").write_text(json.dumps(states[0]))
    monkeypatch.setattr(sys, "argv", arguments[:-2])
    calls.clear()
    with pytest.raises(ValueError, match="options changed"):
        pipeline.main()
    assert not calls
