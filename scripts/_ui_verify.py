# 前端重构验证：TestClient 读首页 HTML 验证新视觉 + 登录 + 各视图
import os
import pathlib
import sys

os.environ["AP_MODE"] = "mock"
os.environ["AP_AUTH_DB"] = "data/test_ui_verify.db"
sys.path.insert(0, "src")
for s in ("", "-wal", "-shm"):
    try:
        pathlib.Path("data/test_ui_verify.db" + s).unlink()
    except OSError:
        pass

from fastapi.testclient import TestClient
from aesthetic_prism.serve import app as m

with TestClient(m.app) as c:
    r = c.get("/")
    assert r.status_code == 200, r.status_code
    html = r.text
    print("PAGE", r.status_code)
    print("NEW_ACCENT", "4f9cf5" in html, "(去AI紫)")
    print("LOGIN_VIEW", "login-view" in html)
    print("VIEWS", html.count('id="view-'))
    print("TABS", html.count("data-view="))

    # 登录流
    r = c.post("/api/auth/register", json={"username": "uiv", "password": "pass123"})
    assert r.status_code == 200, r.text
    r = c.post("/api/auth/login", json={"username": "uiv", "password": "pass123"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    h = {"Authorization": "Bearer " + tok}
    print("LOGIN_OK", len(tok))

    # 钱包/商城/空间/算力视图 API
    w = c.get("/api/wallet", headers=h)
    assert w.status_code == 200, w.text
    print("WALLET", w.json()["balance"])
    s = c.get("/api/models/shop", headers=h)
    print("SHOP", len(s.json()["items"]))

print("UI_VERIFY_PASS")