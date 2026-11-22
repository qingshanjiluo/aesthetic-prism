# auth 极简验证（强制内置 hmac 哈希，快速）
import os
import pathlib
import sys

os.environ["AP_AUTH_DB"] = "data/test_auth_probe.db"
sys.path.insert(0, "src")
for p in ("data/test_auth_probe.db", "data/test_auth_probe.db-wal", "data/test_auth_probe.db-shm"):
    try:
        pathlib.Path(p).unlink()
    except OSError:
        pass

from aesthetic_prism.serve import auth

auth._HAS_PASSLIB = False  # 走内置 pbkdf2，快
auth.init_db()

r = auth.register("carol", "pw1")
print("REG", r is not None, r["balance"])
lg = auth.login("carol", "pw1")
print("LOGIN", lg is not None)
print("BADPW", auth.login("carol", "x") is None)
print("DUP", auth.register("carol", "y") is None)
print("CHARGE", auth.charge(r["id"], 10, "消费", "评分"))
print("BAL", auth.get_wallet(r["id"])["balance"])
print("BUY", auth.buy_model(r["id"], "models/hapnet_teacher.onnx"))
print("OWN", auth.owned_models(r["id"]))
print("VERIFY", auth.verify_token(lg["token"]))
print("PROBE_DONE")