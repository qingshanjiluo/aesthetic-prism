"""score.py 单元测试：图像加载与评分路径（mock 会话，不依赖真实模型文件）。"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from aesthetic_prism.score import _load_image, score_images


@pytest.fixture()
def png(tmp_path: Path) -> Path:
    from PIL import Image

    p = tmp_path / "t.png"
    Image.new("RGB", (64, 64), (128, 90, 40)).save(p)
    return p


def test_load_image_shape_and_norm(png: Path) -> None:
    arr = _load_image(png)
    assert arr.shape == (3, 224, 224)
    assert arr.dtype == np.float32
    assert np.isfinite(arr).all()


def test_load_image_missing(png: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _load_image(png.parent / "absent.png")


def test_score_images_with_stub_session(png: Path) -> None:
    stub = {name: np.array([[0.5]]) for name in
            ("total", "composition", "light", "creativity", "story")}
    with mock.patch("aesthetic_prism.score.load_session", return_value=object()), \
         mock.patch("aesthetic_prism.score.run_session", return_value=stub):
        out = score_images([png], Path("stub.onnx"))
    assert out[0]["model"] == "stub.onnx"
    assert out[0]["total"] == 0.5
    assert set(out[0]) == {"total", "composition", "light", "creativity", "story", "model"}
