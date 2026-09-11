from src.depth_semantic_prompt import build_depth_semantic_prompt


def test_depth_semantic_prompt_locks_camera_mask_and_scale() -> None:
    prompt = build_depth_semantic_prompt(
        "a blue wheeled rubbish bin",
        structural_constraints=("Keep the two wheels parallel and attached to one axle.",),
    )
    for phrase in (
        "hard ControlNet-like spatial constraint",
        "camera viewpoint",
        "image-plane center",
        "apparent width and height",
        "foreground mask",
        "two wheels parallel",
    ):
        assert phrase in prompt


def test_depth_semantic_prompt_requires_object_description() -> None:
    try:
        build_depth_semantic_prompt("  ")
    except ValueError as error:
        assert "object_description" in str(error)
    else:
        raise AssertionError("empty object description must be rejected")


def test_random_crop_prompt_treats_missing_pixels_as_unknown() -> None:
    prompt = build_depth_semantic_prompt("chair", observation_mode="random_crop")
    for phrase in (
        "strong positive geometric evidence",
        "Unobserved pixels are unknown",
        "do not define the complete object's silhouette or bounding box",
        "recover all missing and cropped structures",
        "must not deform the object",
    ):
        assert phrase in prompt
    assert "apparent width and height" not in prompt
