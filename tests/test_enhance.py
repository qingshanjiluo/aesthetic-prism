# 增强端点测试（ENHANCE）：/assets /models /samples/generate /score-batch /assets/meta /assets/delete
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from aesthetic_prism.serve import app as app_mod


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app_mod.app) as c:  # AP_MODE=mock 由 conftest 提供
        yield c


def _png_bytes(w: int = 32, h: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 50, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _upload_sample(client: TestClient, name: str = "enh.png") -> dict:
    r = client.post(
        "/upload",
        files={"image": (name, _png_bytes(), "image/png")},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---- /assets：素材库列表 ----
def test_assets_lists_uploads(client: TestClient) -> None:
    up = _upload_sample(client, "assets-list.png")
    r = client.get("/assets?limit=50")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(it["path"] == up["path"] for it in data["items"])


def test_assets_search_filters(client: TestClient) -> None:
    _upload_sample(client, "uniquetag-xyz.png")
    r = client.get("/assets?q=uniquetag&limit=100")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert all("uniquetag" in it["filename"] for it in data["items"])


# ---- /assets/meta + /assets/delete ----
def test_assets_meta_update_and_delete(client: TestClient) -> None:
    up = _upload_sample(client, "meta-del.png")
    r = client.post(
        "/assets/meta",
        json={"path": up["path"], "tags": ["t1", "t2"], "note": "hi"},
    )
    assert r.status_code == 200
    assert set(r.json()["tags"]) == {"t1", "t2"}
    # 删除
    rd = client.post("/assets/delete", json={"paths": [up["path"]]})
    assert rd.status_code == 200
    assert rd.json()["deleted"] == 1
    # 删除后 /assets/exists 判不存在
    re = client.post("/assets/exists", json={"paths": [up["path"]]})
    assert re.status_code == 200
    assert re.json()["items"][0]["exists"] is False


# ---- /models：模型列表与元数据 ----
def test_models_lists_onnx(client: TestClient) -> None:
    r = client.get("/models")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert "active_model" in data
    assert all(it["suffix"] in (".onnx", ".pt", ".pth") for it in data["items"])


def test_models_meta_update(client: TestClient) -> None:
    # 先取第一个模型
    m = client.get("/models").json()
    target = m["items"][0]["path"]
    r = client.post("/models/meta", json={"path": target, "category": "测试类"})
    assert r.status_code == 200
    assert r.json()["category"] == "测试类"
    # 回读确认
    m2 = client.get("/models").json()
    it = next(x for x in m2["items"] if x["path"] == target)
    assert it["category"] == "测试类"


# ---- /score-batch ----
def test_score_batch_returns_sorted(client: TestClient) -> None:
    p1 = _upload_sample(client, "sb1.png")
    p2 = _upload_sample(client, "sb2.png")
    r = client.post("/score-batch", json={"paths": [p1["path"], p2["path"]]})
    assert r.status_code == 200
    data = r.json()
    assert data["scored"] == 2
    assert len(data["items"]) == 2
    # 按 total 降序
    totals = [it.get("total", -1) for it in data["items"]]
    assert totals == sorted(totals, reverse=True)


# ---- /samples/generate ----
def test_samples_generate(client: TestClient) -> None:
    # 输出目录必须位于项目根内（synthetic.generate 强制 ROOT-relative）
    r = client.post("/samples/generate", json={"n": 3, "out": "data/tmp_test_gen"})
    assert r.status_code == 200
    data = r.json()
    assert data["generated"] == 3
    out_dir = Path("data/tmp_test_gen")
    pngs = list(out_dir.glob("*.png"))
    assert len(pngs) >= 3
    assert (out_dir / "index.json").is_file()


def test_samples_generate_n_bounds(client: TestClient) -> None:
    r = client.post("/samples/generate", json={"n": 0})
    assert r.status_code in (400, 422)