# auth 核心冒烟：注册/登录/计费/购买/校验 token
import os
import sys

os.environ["AP_AUTH_DB"] = "data/test_auth_smoke.db"
sys.path.insert(0, "src")

import pathlib

for p in ("data/test_auth_smoke.db", "data/test_auth_smoke.db-wal", "data/test_auth_smoke.db-shm"):
    try:
        pathlib.Path(p).unlink()
    except OSError:
        pass

from aesthetic_prism.serve import auth

auth.init_db()

r = auth.register("alice", "pw123456")
assert r is not None, "register failed"
uid = r["id"]
print("REGISTER_OK balance=", r["balance"])

lg = auth.login("alice", "pw123456")
assert lg is not None, "login failed"
print("LOGIN_OK balance=", lg["balance"])

# 重复注册
assert auth.register("alice", "x") is None, "dup register should fail"
print("DUP_REJECT_OK")

# 错误密码
assert auth.login("alice", "wrong") is None, "bad password should fail"
print("BADPW_REJECT_OK")

# 计费
assert auth.charge(uid, 10, "消费", "评分") is True
w = auth.get_wallet(uid)
print("CHARGE_OK balance=", w["balance"])

# 余额不足
assert auth.charge(uid, 999999, "消费", "超额") is False
print("INSUFFICIENT_OK")

# 购买模型
buy = auth.buy_model(uid, "models/hapnet_teacher.onnx")
assert buy is not None and not buy["already"]
print("BUY_OK price=", buy["price"], "owned=", auth.owned_models(uid))

# 重复购买返回 already
buy2 = auth.buy_model(uid, "models/hapnet_teacher.onnx")
assert buy2 is not None and buy2["already"]
print("BUY_ALREADY_OK")

# token 校验
tok = lg["token"]
v = auth.verify_token(tok)
assert v is not None and v["id"] == uid
print("TOKEN_VERIFY_OK uid=", v["id"])

# 无效 token
assert auth.verify_token("garbage") is None
print("BAD_TOKEN_OK")

print("ALL_AUTH_SMOKE_PASS")