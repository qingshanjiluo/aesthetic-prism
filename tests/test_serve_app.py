"""serve/app.py + serve/service.py 真实 TestClient 测试（mock 服务 + conftest fixture 语义一致）。"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from aesthetic_prism.serve import app as app_mod
from aesthetic_prism.serve.service import (
    MAX_IMAGE_BYTES,
    ScoreService,
    probe_image,
)


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app_mod.app) as c:  # lifespan 触发 build_service（AP_MODE=mock 由 Makefile 提供）
        yield c


def _png_bytes(w: int = 64, h: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (100, 120, 140)).save(buf, format="PNG")
    return buf.getvalue()


# ---- service 层单元：probe_image 校验链 ----
def test_probe_ok() -> None:
    meta = probe_image(_png_bytes(), "image/png")
    assert meta["width"] == 64 and meta["mime"] == "image/png"


def test_probe_too_large() -> None:
    with pytest.raises(Exception) as ei:
        probe_image(b"\x89PNG" + b"0" * (MAX_IMAGE_BYTES + 1), "image/png")
    assert getattr(ei.value, "status_code", None) == 413


def test_probe_empty() -> None:
    with pytest.raises(Exception) as ei:
        probe_image(b"", "image/png")
    assert ei.value.status_code == 400


def test_probe_bad_mime() -> None:
    with pytest.raises(Exception) as ei:
        probe_image(_png_bytes(), "image/gif")
    assert ei.value.status_code == 415


def test_probe_bad_magic() -> None:
    with pytest.raises(Exception) as ei:
        probe_image(b"JUNKJUNKJUNK" * 10, "image/png")
    assert ei.value.status_code == 415


def test_probe_undecodable() -> None:
    with pytest.raises(Exception) as ei:
        probe_image(b"\x89PNG\r\n\x1a\nGARBAGE", "image/png")
    assert ei.value.status_code == 400


def test_probe_too_small() -> None:
    with pytest.raises(Exception) as ei:
        probe_image(_png_bytes(8, 8), "image/png")
    assert ei.value.status_code == 400


def test_mock_score_bytes_keys() -> None:
    svc = ScoreService(model_path=Path("unused.onnx"), device="cpu")  # auto→mock（文件缺失）
    out = svc.score_bytes(_png_bytes(), "image/png")
    assert set(out) == {"total", "composition", "light", "creativity", "story"}
    assert all(0.0 <= v <= 100.0 for v in out.values())


# ---- app 层 TestClient：真实 HTTP 语义 ----
def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok" and "mock" in d["model"]


def test_score_ok(client: TestClient) -> None:
    r = client.post("/score", files={"image": ("t.png", _png_bytes(), "image/png")})
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"total", "composition", "light", "creativity", "story", "model"}
    assert "mock" in d["model"]


def test_score_not_multipart(client: TestClient) -> None:
    r = client.post("/score", json={"a": 1})
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_media_type"


def test_score_validation_error_maps_400(client: TestClient) -> None:
    r = client.post("/score", files={"wrong": ("t.png", _png_bytes(), "image/png")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"


def test_unknown_route_404(client: TestClient) -> None:
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_upload_ok(client: TestClient) -> None:
    r = client.post("/upload", files={"image": ("my pic.png", _png_bytes(), "image/png")})
    assert r.status_code == 200
    d = r.json()
    assert d["width"] == 64 and d["mime"] == "image/png"
    # 落盘校验：文件确实存在于 data/uploads/
    assert (app_mod._ROOT / d["path"]).is_file()


def test_train_and_status_and_job(client: TestClient) -> None:
    # 训练会拉起真实子进程（可能很慢）——只验证登记/路由/查询语义，不等待训练结束
    r = client.post("/train", json={"steps": 1})
    assert r.status_code == 200
    d = r.json()
    assert d["state"] == "running"
    jid = d["job_id"]
    s = client.get("/train/status").json()
    assert s["latest_job_id"] == jid
    j = client.get(f"/jobs/{jid}").json()
    assert j["job_id"] == jid
    assert j["steps"] == 1
    assert {"done", "total", "pct", "last_loss"} <= set(j)


def test_job_unknown_404(client: TestClient) -> None:
    r = client.get("/jobs/deadbeef0000")
    assert r.status_code == 404


def test_train_steps_validation(client: TestClient) -> None:
    assert client.post("/train", json={"steps": 0}).status_code == 400
    assert client.post("/train", json={"steps": True}).status_code == 400
    assert client.post("/train", json={"steps": 10_001}).status_code == 400


def test_score_duplicate_field_rejected(client: TestClient) -> None:
    r = client.post(
        "/score",
        files=[
            ("image", ("a.png", _png_bytes(), "image/png")),
            ("image", ("b.png", _png_bytes(), "image/png")),
        ],
    )
    assert r.status_code == 400
    assert "duplicate" in r.json()["error"]["message"]


def test_mock_score_deterministic() -> None:
    svc = ScoreService(model_path=Path("unused.onnx"), device="cpu")
    a = svc.score_bytes(_png_bytes(), "image/png")
    b = svc.score_bytes(_png_bytes(), "image/png")
    assert a == b


def test_jpeg_probe_ok() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(buf, format="JPEG")
    meta = probe_image(buf.getvalue(), "image/jpeg")
    assert meta["width"] == 32 and meta["bytes"] > 0


def test_openapi_available(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/score" in r.json()["paths"]
