# r6b：六档之余 413 预检（header 注入不真传 11MB）+ 429 非阻塞立即返回（E12/E13）
from __future__ import annotations

import threading
import time
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


def test_413_content_length_precheck(client, tmp_sample_png) -> None:
    """E12：读 body 前按 Content-Length>10MiB 拦截 → 413（header 注入，不真传 11MB）。"""
    data = tmp_sample_png.read_bytes()  # 真实体远小于 10MiB
    r = client.post(
        "/score",
        files={"image": (tmp_sample_png.name, data, "image/png")},
        headers={"content-length": str(11 * 1024 * 1024)},
    )
    _assert_error_body(r, 413)
    assert r.json()["error"]["code"] == "payload_too_large"


def test_429_nonblocking_immediate(client, app, monkeypatch) -> None:
    """E13：信号量满 → 429 立即返回绝不排队（locked 快速失败分支，真 HTTP 断言）。

    路数：monkeypatch 模块 _sem=Semaphore(1)（等价 MAX_INFLIGHT=1）→ 线程1 发第 1 个请求
    并在推理步（score_bytes，threadpool 内）卡住占住唯一许可 → 主线程发第 2 个请求断言
    立即 429 且 elapsed<1s（若排队则会等 hold 释放 → 200 且 ≥ hold 时长，即判"回潮排队"）。
    """
    from aesthetic_prism.serve import app as appmod

    monkeypatch.setattr(appmod, "_sem", __import__("asyncio").Semaphore(1))

    svc = app.state.service
    orig = svc.score_bytes
    entered = threading.Event()
    release = threading.Event()

    def slow(data: bytes, mime: str) -> dict[str, float]:
        entered.set()  # 已进入推理（许可已被本请求持有）
        release.wait(timeout=2.0)  # 卡住 worker 线程占住许可；超时兜底防死锁
        return orig(data, mime)

    monkeypatch.setattr(svc, "score_bytes", slow)

    import io as _io

    from PIL import Image

    buf = _io.BytesIO()
    Image.new("RGB", (64, 64), (30, 90, 200)).save(buf, format="PNG")
    img_bytes = buf.getvalue()

    results: list[Any] = []

    def first() -> None:
        results.append(client.post("/score", files={"image": ("a.png", img_bytes, "image/png")}))

    t1 = threading.Thread(target=first, daemon=True)
    t1.start()
    assert entered.wait(timeout=5.0), "first request never reached inference"

    t0 = time.perf_counter()
    r2 = client.post("/score", files={"image": ("b.png", img_bytes, "image/png")})
    elapsed = time.perf_counter() - t0

    _assert_error_body(r2, 429)
    assert r2.json()["error"]["code"] == "too_many_requests"
    assert elapsed < 1.0, f"429 must be immediate (queued {elapsed:.3f}s)"

    release.set()
    t1.join(timeout=5.0)
    assert results and results[0].status_code == 200, getattr(results[0], "text", "no first response")  # 许可已释放回池


def test_toomanyrequests_mapping() -> None:
    """映射函数单测：TooManyRequestsError → 429 + too_many_requests（六档之一）。"""
    from aesthetic_prism.serve.service import TooManyRequestsError

    e = TooManyRequestsError()
    assert e.status_code == 429 and e.code == "too_many_requests" and e.message
