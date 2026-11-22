# r7：前端静态页可达 + 白盒边界（404 不被 StaticFiles 吞、不吞 API 路由）
# 断言三条最小集：200 + text/html + 非空 body；锚点断言（id="score-form"/POST /score 字面）
# 暂存至 r11 index.html 落盘后、r12 收口时补强。
from __future__ import annotations

from typing import Any


def _assert_error_body(resp: Any, code: int) -> None:
    """断言 status==code 且错误体恰为 {"error":{"code","message"}}、code/message 非空 str。"""
    assert resp.status_code == code, (resp.status_code, resp.text)
    d = resp.json()
    assert set(d.keys()) == {"error"}, sorted(d.keys())
    err = d["error"]
    assert set(err.keys()) == {"code", "message"}, sorted(err.keys())
    assert isinstance(err["code"], str) and err["code"], err
    assert isinstance(err["message"], str) and err["message"], err


def test_root_serves_html(client) -> None:
    """GET / → 200 + text/html + 非空 body（app.py FileResponse(index.html)）。"""
    r = client.get("/")
    assert r.status_code == 200, (r.status_code, r.text[:200])
    assert r.headers["content-type"].startswith("text/html"), r.headers["content-type"]
    assert len(r.text) > 0


def test_frontend_mount_serves_html(client) -> None:
    """GET /frontend → 200 + text/html + 非空 body（StaticFiles(html=True) 挂载）。"""
    r = client.get("/frontend")
    assert r.status_code == 200, (r.status_code, r.text[:200])
    assert r.headers["content-type"].startswith("text/html"), r.headers["content-type"]
    assert len(r.text) > 0


def test_unknown_route_404_not_swallowed(client) -> None:
    """白盒边界：GET /nope → 404 统一错误体——静态 mount 不吃 404、不吞 API 路由。"""
    r = client.get("/nope")
    _assert_error_body(r, 404)
    assert r.json()["error"]["code"] == "not_found"


def test_api_routes_survive_mount(client) -> None:
    """挂载后 API 路由不受影响：/health 仍 200（mount 顺序不吞路由）。"""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
