"""Prompt contract for direct-GPT semantic completion from a depth raster."""

from __future__ import annotations


def build_depth_semantic_prompt(
    object_description: str,
    *,
    structural_constraints: tuple[str, ...] = (),
    observation_mode: str = "single_scan",
) -> str:
    """Build a category-independent, depth-conditioned instruction.

    The depth raster, rather than a language description, remains the source of
    camera, framing, silhouette, and visible geometry. Optional constraints
    describe genuine object structure, never a sample-specific image transform.
    """
    subject = object_description.strip()
    if not subject:
        raise ValueError("object_description must not be empty")
    if observation_mode not in {"single_scan", "random_crop"}:
        raise ValueError("observation_mode must be 'single_scan' or 'random_crop'")
    constraints = " ".join(item.strip() for item in structural_constraints if item.strip())
    if constraints:
        constraints = f" Additional structural constraints: {constraints}"
    if observation_mode == "random_crop":
        return (
            "Generate one complete, realistic RGB object image from the supplied random-crop depth map. "
            f"The object is {subject}. "
            "Treat the dominant spatially coherent non-background depth structures as strong positive "
            "geometric evidence at their observed image locations; tiny isolated components, boundary "
            "speckles, and depth outliers are soft evidence and must not deform the object. Preserve the "
            "camera perspective, orientation, foreshortening, depth ordering, principal extents, and robust "
            "observed part locations. Unobserved pixels are unknown: they are not confirmed background and "
            "do not define the complete object's silhouette or bounding box. "
            "Extend the object into unknown image regions wherever necessary to recover all missing and "
            "cropped structures, while connecting them continuously to the robust observed support in the "
            "same camera. Do not rotate, mirror, recenter, globally rescale, straighten, or canonicalize the "
            "observed object. The completed object must retain category-normal topology, proportions, and "
            "part thicknesses: never stretch, compress, twist, melt, or disconnect geometry merely to cover "
            "sparse points. Keep one coherent, fully completed object on a pure white background with sharp "
            "realistic boundaries and materials suitable for image-to-3D reconstruction. Do not leave the "
            "object partial or add text, logos, detached or duplicate parts, secondary objects, or cast shadows."
            f"{constraints}"
        )
    return (
        "Generate one complete, realistic RGB object image from the supplied incomplete depth map. "
        f"The object is {subject}. "
        "Treat every non-background depth pixel and its foreground mask as a hard ControlNet-like "
        "spatial constraint. Preserve the input camera viewpoint, perspective, image-plane center, "
        "apparent width and height, crop, orientation, visible silhouette, depth ordering, and all "
        "observed part locations. Do not rotate, mirror, recenter, rescale, widen, shorten, tilt, or "
        "redesign the observed object. Complete only genuinely missing or occluded regions, connect "
        "them naturally to the observed structure, and keep a single coherent object on a pure white "
        "background. Produce sharp boundaries and realistic materials suitable for image-to-3D "
        "reconstruction. Do not add text, logos, extra parts, secondary objects, or cast shadows that "
        f"change the foreground mask.{constraints}"
    )
