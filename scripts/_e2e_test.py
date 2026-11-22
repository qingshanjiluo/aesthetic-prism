# 商业化端到端测试（TestClient）：注册/登录/评分扣分/充值/购模型/扩容/算力
import io
import os
import pathlib
import sys

os.environ["AP_MODE"] = "mock"
os.environ["AP_AUTH_DB"] = "data/test_e2e.db"
sys.path.insert(0, "src")
for suffix in ("", "-wal", "-shm"):
    try:
        pathlib.Path("data/test_e2e.db" + suffix).unlink()
    except OSError:
        pass

from PIL import Image
from fastapi.testclient import TestClient
from aesthetic_prism.serve import app as app_mod


def png():
    b = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 40, 90)).save(b, format="PNG")
    return b.getvalue()


with TestClient(app_mod.app) as c:
    # 注册
    r = c.post("/api/auth/register", json={"username": "e2e", "password": "secret1"})
    assert r.status_code == 200, r.text
    print("REGISTER_OK bal", r.json()["user"]["balance"])

    # 登录
    r = c.post("/api/auth/login", json={"username": "e2e", "password": "secret1"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    h = {"Authorization": "Bearer " + token}
    print("LOGIN_OK token_len", len(token))

    # 评分扣 10 积分（初始 100 → 90）
    r = c.post("/score", files={"image": ("a.png", png(), "image/png")}, headers=h)
    assert r.status_code == 200, r.text
    w = c.get("/api/wallet", headers=h).json()
    print("SCORE_OK bal_after", w["balance"])
    assert w["balance"] == 90, "score should deduct 10"

    # 充值 500 → 590
    r = c.post("/api/wallet/recharge", json={"amount": 500}, headers=h)
    assert r.status_code == 200, r.text
    print("RECHARGE_OK bal", r.json()["balance"])

    # 购模型扣 500 → 90
    r = c.post("/api/models/buy", json={"model_id": "models/hapnet_teacher.onnx"}, headers=h)
    assert r.status_code == 200, r.text
    w = c.get("/api/wallet", headers=h).json()
    print("BUY_OK bal_after", w["balance"])

    # 空间扩容 1GB 扣 200（90 不足 → 402）
    r = c.post("/api/space/expand", json={"gb": 1}, headers=h)
    print("SPACE_EXPAND insufficient", r.status_code)
    assert r.status_code == 402, "balance 90 < 200 should 402"

    # 算力 T1 扣 10（90 够 → 80）
    r = c.post("/api/compute", json={"tier": 1}, headers=h)
    assert r.status_code == 200, r.text
    w = c.get("/api/wallet", headers=h).json()
    print("COMPUTE_OK bal_after", w["balance"])
    assert w["balance"] == 80

    # 无 token 评分（本地兼容放行不扣）
    r = c.post("/score", files={"image": ("b.png", png(), "image/png")})
    print("NO_TOKEN_SCORE", r.status_code)

    # 无 token 访问钱包 401
    r = c.get("/api/wallet")
    assert r.status_code == 401, r.status_code
    print("NO_TOKEN_WALLET_401", r.status_code)

    print("ALL_E2E_PASS")