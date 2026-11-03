from PIL import Image, ImageDraw
import pytest

from scripts.install_depth_conditioned_semantic import match_full_canvas
from scripts.run_prior_generation_agent import verify_review_canvas


def test_full_canvas_resize_aligns_depth_and_generated_image():
    semantic = Image.new("RGB", (1254, 1254), "white")
    ImageDraw.Draw(semantic).rectangle((313, 313, 941, 941), fill="black")
    depth = Image.new("L", (512, 512), 0)
    aligned_semantic, aligned_depth, mapping = match_full_canvas(semantic, depth, 512)
    assert aligned_semantic.size == aligned_depth.size == (512, 512)
    assert aligned_semantic.getpixel((256, 256)) == (0, 0, 0)
    assert aligned_semantic.getpixel((64, 64)) == (255, 255, 255)
    assert mapping["source_semantic_size"] == [1254, 1254]
    assert mapping["source_depth_size"] == [512, 512]
    assert mapping["mapping"] == "full_canvas_resize_no_crop_no_translation"


def test_mismatched_aspect_ratio_requires_camera_mapping():
    with pytest.raises(ValueError, match="aspect ratios differ"):
        match_full_canvas(Image.new("RGB", (1254, 1024)), Image.new("L", (512, 512)), 512)


def test_review_requires_all_images_on_recorded_canvas(tmp_path):
    audit = {"canvas_mapping": {"comparison_size": [512, 512]}}
    for name in ("comparison_depth.png", "img.png", "semantic_depth_audit.png"):
        Image.new("RGB", (512, 512)).save(tmp_path / name)
    assert verify_review_canvas(tmp_path, audit) == (512, 512)
    Image.new("RGB", (1254, 1254)).save(tmp_path / "img.png")
    with pytest.raises(ValueError, match="cannot compare contours"):
        verify_review_canvas(tmp_path, audit)
