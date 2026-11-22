# tests/conftest.py : src layout sys.path injection + env pin + shared fixtures
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

# 0) env pin must run before any aesthetic_prism module is imported.
#    conftest is loaded first at collection time.
os.environ["AP_MODE"] = "mock"
os.environ.setdefault("PYTHONUTF8", "1")

# 1) sys.path injection: locate project root via pathlib, do not assume cwd.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest
from PIL import Image, ImageDraw


@pytest.fixture()
def tmp_sample_png(tmp_path: Path) -> Path:
    "Build a 256x256 gradient PNG with geometric shapes in tmp_path."
    w = h = 256
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = y / (h - 1)
            u = x / (w - 1)
            px[x, y] = (int(40 + 180 * t), int(60 + 120 * (1 - t)), int(150 + 90 * u))
    d = ImageDraw.Draw(img)
    d.ellipse((64, 64, 192, 192), outline=(255, 255, 255), width=6)
    d.rectangle((16, 16, 64, 64), fill=(250, 220, 80))
    d.line((0, 0, 255, 255), fill=(20, 20, 20), width=3)
    out = tmp_path / "sample.png"
    img.save(out, format="PNG")
    return out


@pytest.fixture()
def app():
    "FastAPI app instance; lifespan is triggered by client."
    from aesthetic_prism.serve.app import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client(app) -> Iterator[object]:
    "TestClient in with-form so lifespan runs and app.state.service is ready."
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c

