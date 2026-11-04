from pathlib import Path

import numpy as np

from scripts.materialize_scan_datasets import extract_kitti_frame


def test_kitti_extraction_uses_annotated_class_and_3d_box(tmp_path: Path):
    for name in ("label_2", "calib", "velodyne"):
        (tmp_path / name).mkdir()
    (tmp_path / "label_2" / "000001.txt").write_text(
        "Car 0 0 0 0 0 1 1 2 2 4 0 0 5 0\n"
        "Pedestrian 0 0 0 0 0 1 1 2 1 1 3 0 5 0\n"
    )
    (tmp_path / "calib" / "000001.txt").write_text(
        "Tr_velo_to_cam: 1 0 0 0 0 1 0 0 0 0 1 0\n"
        "R0_rect: 1 0 0 0 1 0 0 0 1\n"
    )
    np.asarray([[0, -1, 5, 1], [0.5, -1, 6, 1], [2, -1, 5, 1],
                [3, -1, 5, 1], [3, 1, 5, 1]], dtype="<f4").tofile(
        tmp_path / "velodyne" / "000001.bin"
    )
    rows = extract_kitti_frame(tmp_path / "label_2" / "000001.txt", tmp_path)
    assert [(category, count) for category, _, count, _, _ in rows] == [
        ("car", 2), ("pedestrian", 1)
    ]
    np.testing.assert_allclose(rows[0][3][0], [0, -1, 0])
    np.testing.assert_allclose(rows[1][3][0], [0, -1, 0])
