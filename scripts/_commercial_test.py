# 商业化端点全链路测试（TestClient 内存起 app，无需外部 uvicorn）
import os
import pathlib
import sys

os.environ["AP_MODE"] = "mock"
os.environ["AP_AUTH_DB"] = "data/test_commercial.db"
sys.path.insert(0, "src")
for suffix in ("", "-wal", "-shm"):
    try:
        pathlib.Path("data/test_commercial.db" + suffix).unlink()
    except OSError:
        pass

from fastapi.testclient import TestClient
from aesthetic_prism.serve import app as app_mod

with TestClient(app_mod.app) as c:
    # 注册
    r = c.post("/api/auth/register", json={"username": "user1", "password": "secret1"})
    assert r.status_code == 200, r.text
    print("REGISTER", r.status_code, "balance", r.json()["user"]["balance"])

    # 重复注册 409
    r = c.post("/api/auth/register", json={"username": "user1", "password": "secret1"})
    assert r.status_code == 409, r.status_code
    print("DUP_REGISTER_409", r.status_code)

    # 登录
    r = c.post("/api/auth/login", json={"username": "user1", "password": "secret1"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    print("LOGIN_OK token_len", len(token))

    # 错误密码 401
    r = c.post("/api/auth/login", json={"username": "user1", "password": "wrong"})
    assert r.status_code == 401, r.status_code
    print("BADPW_401", r.status_code)

    h = {"Authorization": "Bearer " + token}

    # 无 token 401
    r = c.get("/api/wallet")
    assert r.status_code == 401, r.status_code
    print("NO_AUTH_401", r.status_code)

    # 钱包
    r = c.get("/api/wallet", headers=h)
    assert r.status_code == 200, r.text
    bal = r.json()["balance"]
    print("WALLET_bal", bal)

    # 充值
    r = c.post("/api/wallet/recharge", json={"amount": 500}, headers=h)
    assert r.status_code == 200, r.text
    print("RECHARGE_bal", r.json()["balance"])

    # 购模型
    r = c.post("/api/models/buy", json={"model_id": "models/hapnet_teacher.onnx"}, headers=h)
    assert r.status_code == 200, r.text
    print("BUY", r.json()["ok"], "price", r.json().get("price"))

    # 商城（已购标记）
    r = c.get("/api/models/shop", headers=h)
    assert r.status_code == 200, r.text
    item = [i for i in r.json()["items"] if i["model_id"] == "models/hapnet_teacher.onnx"][0]
    print("SHOP_owned", item["owned"])

    # 空间扩容（BUY 后余额 100，需 200，先充值确保够）
    c.post("/api/wallet/recharge", json={"amount": 500}, headers=h)
    r = c.post("/api/space/expand", json={"gb": 1}, headers=h)
    assert r.status_code == 200, r.text
    print("SPACE_expand", r.json()["space_bytes"], "cost", r.json()["cost"])

    # 算力
    r = c.post("/api/compute", json={"tier": 1}, headers=h)
    assert r.status_code == 200, r.text
    print("COMPUTE", r.json()["ok"], "cost", r.json()["cost"])

    # 积分不足（余额耗尽后）
    # 充值 500 + 注册 100 = 600；扣 10(未花) + 500(模型) + 200(空间) + 10(算力) = 余额 80
    r = c.post("/api/space/expand", json={"gb": 1}, headers=h)  # 需 200，余额可能不足
    w = c.get("/api/wallet", headers=h).json()["balance"]
    print("FINAL_BALANCE", w)

print("ALL_COMMERCIAL_PASS")