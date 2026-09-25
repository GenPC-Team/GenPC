#!/usr/bin/env python3
"""Combine an ordered deformed carrier and a partial cloud for inspection.

The deformed carrier inherits per-point RGB values from the corresponding
ordered source carrier.  Partial points receive one uniform display colour.
No geometry is changed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement


def _vertices(path: Path) -> np.ndarray:
    vertices = PlyData.read(str(path))["vertex"].data
    return np.stack([vertices[axis] for axis in ("x", "y", "z")], axis=1).astype(np.float32)


def _colours(path: Path) -> np.ndarray:
    vertices = PlyData.read(str(path))["vertex"].data
    names = set(vertices.dtype.names or ())
    if not {"red", "green", "blue"}.issubset(names):
        raise ValueError(f"texture source has no RGB properties: {path}")
    return np.stack([vertices[channel] for channel in ("red", "green", "blue")], axis=1).astype(np.uint8)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--carrier", type=Path, required=True)
    parser.add_argument("--texture-source", type=Path, required=True)
    parser.add_argument("--partial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partial-colour", type=int, nargs=3, default=(5, 61, 235))
    args = parser.parse_args()

    carrier = _vertices(args.carrier)
    colours = _colours(args.texture_source)
    partial = _vertices(args.partial)
    if len(carrier) != len(colours):
        raise ValueError(
            "ordered carrier and texture source must have equal point counts: "
            f"{len(carrier)} != {len(colours)}"
        )

    partial_colour_values = np.asarray(args.partial_colour, dtype=np.int64)
    if np.any(partial_colour_values < 0) or np.any(partial_colour_values > 255):
        raise ValueError("partial colour values must be in [0, 255]")
    partial_colour = partial_colour_values.astype(np.uint8)
    xyz = np.concatenate([carrier, partial], axis=0)
    rgb = np.concatenate(
        [colours, np.broadcast_to(partial_colour, (len(partial), 3))], axis=0,
    )
    output = np.empty(
        len(xyz),
        dtype=[
            ("x", "f4"), ("y", "f4"), ("z", "f4"),
            ("red", "u1"), ("green", "u1"), ("blue", "u1"),
        ],
    )
    output["x"], output["y"], output["z"] = xyz.T
    output["red"], output["green"], output["blue"] = rgb.T
    args.output.parent.mkdir(parents=True, exist_ok=True)
    PlyData([PlyElement.describe(output, "vertex")], text=False).write(str(args.output))
    print(args.output.resolve())


if __name__ == "__main__":
    main()
