# r4：GET /health — C-SERVE-01 §3.3 HealthResponse 五字段（S1-02 冒烟）
from __future__ import annotations


def test_health_200_and_fields(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    d = r.json()
    # 五字段恰在（HealthResponse §3.3）
    assert set(d.keys()) == {"status", "ready", "model", "device", "uptime_s"}
    assert d["status"] in ("ok", "degraded")
    assert isinstance(d["ready"], bool)
    assert d["ready"] is True  # mock 模式可服务
    assert d["status"] == "ok"
    assert isinstance(d["model"], str) and "mock" in d["model"]
    assert d["device"] in ("cpu", "cuda")
    assert isinstance(d["uptime_s"], (int, float)) and d["uptime_s"] >= 0
