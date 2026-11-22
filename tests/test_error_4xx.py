# r6a：六档之 4xx 四档 — 400 空文件(E10) / 400 重复 image(E11) / 404 未知路由 / 415 非图字节
# 口径：状态码∈{400,404,415}、body 顶层 {"error":{"code","message"}}、code/message 非空 str；断言以 code 为准
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


def test_400_empty_file(client) -> None:
    """E10 空文件：0 字节 image → 400 invalid_request。"""
    r = client.post("/score", files={"image": ("empty.png", b"", "image/png")})
    _assert_error_body(r, 400)
    assert r.json()["error"]["code"] == "invalid_request"


def test_400_duplicate_image_field(client, tmp_sample_png) -> None:
    """E11 重复同名 image 字段：multipart 同名字段数 2 → 400 invalid_request。"""
    data = tmp_sample_png.read_bytes()
    r = client.post(
        "/score",
        files=[
            ("image", ("a.png", data, "image/png")),
            ("image", ("b.png", data, "image/png")),
        ],
    )
    _assert_error_body(r, 400)
    assert r.json()["error"]["code"] == "invalid_request"


def test_404_unknown_route(client) -> None:
    """E8 未知路由 GET /nope → 404 not_found 统一错误体。"""
    r = client.get("/nope")
    _assert_error_body(r, 404)
    assert r.json()["error"]["code"] == "not_found"


def test_415_non_image_bytes(client) -> None:
    """E2 .png 后缀但内容为纯文本字节（魔数不符）→ 415 unsupported_media_type。"""
    r = client.post("/score", files={"image": ("fake.png", b"hello, not an image", "image/png")})
    _assert_error_body(r, 415)
    assert r.json()["error"]["code"] == "unsupported_media_type"
