# Aesthetic Prism 商业化认证 + 积分核心（COMMERCIAL.md 二/三/四）
# SQLite 单机：users / wallets / ledger / purchases；JWT 鉴权；计费引擎。
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any

# ---- 依赖：可选（PyJWT + passlib；缺则降级 hmac-sha256 内置哈希，不阻断）----
try:
    import jwt as _jwt
    _HAS_JWT = True
except Exception:  # pragma: no cover
    _HAS_JWT = False

try:
    from passlib.hash import pbkdf2_sha256 as _pwd
    _HAS_PASSLIB = True
except Exception:  # pragma: no cover
    _HAS_PASSLIB = False

_AUTH_DB = Path(os.environ.get("AP_AUTH_DB", "auth.db")).resolve()
_SECRET = os.environ.get("AP_AUTH_SECRET", "aesthetic-prism-dev-secret-change-me-2026-0000")
_TOKEN_TTL = 60 * 60 * 24 * 7  # 7 天

_lock = threading.RLock()

# 初始积分与免费额度
SIGNUP_BONUS = 100
DEFAULT_SPACE = 256 * 1024 * 1024  # 256MB
PLAN = {
    "score": 10,
    "score_batch": 5,
    "upload": 2,
    "upload_batch": 2,
    "train": 100,
    "generate": 3,
    "space_1gb": 200,
}
MODEL_PRICES = {
    "models/hapnet_teacher.onnx": 500,
    "models/_smoke_teacher.onnx": 500,
    "artifacts/student.onnx": 1000,
    "artifacts/student_int8.onnx": 800,
    "artifacts/_smoke_student.onnx": 800,
}


def _connect() -> sqlite3.Connection:
    _AUTH_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_AUTH_DB), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db() -> None:
    with _connect() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wallets(
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                space_bytes INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ledger(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                kind TEXT NOT NULL,
                item TEXT DEFAULT '',
                ts TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS purchases(
                user_id INTEGER NOT NULL,
                model_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                PRIMARY KEY(user_id, model_id)
            );
            """
        )


def _hash_password(pw: str) -> str:
    if _HAS_PASSLIB:
        return _pwd.hash(pw)
    salt = secrets.token_hex(16)
    return f"hmac${salt}${hashlib.pbkdf2_hmac('sha256', pw.encode(), bytes.fromhex(salt), 100_000).hex()}"


def _verify_password(pw: str, stored: str) -> bool:
    if stored.startswith("hmac$"):
        _, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 100_000).hex()
        return hmac.compare_digest(calc, h)
    try:
        return _pwd.verify(pw, stored)
    except Exception:  # pragma: no cover
        return False


def _make_token(user_id: int, username: str) -> str:
    payload = {"sub": str(user_id), "name": username, "exp": _dt.datetime.now(_dt.UTC) + _dt.timedelta(seconds=_TOKEN_TTL)}
    if _HAS_JWT:
        return _jwt.encode(payload, _SECRET, algorithm="HS256")
    payload["nbf"] = int(_dt.datetime.now(_dt.UTC).timestamp())
    b64 = os.urandom(16).hex()
    return "simple." + b64 + "." + json.dumps(payload)


def register(username: str, password: str) -> dict[str, Any]:
    """注册：建用户 + 钱包（赠送 SIGNUP_BONUS 积分 + 默认空间）。重复用户名 → None。"""
    with _lock, _connect() as c:
        if c.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            return None  # type: ignore[return-value]
        now = _dt.datetime.now(_dt.UTC).isoformat()
        cur = c.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)", (username, _hash_password(password), now))
        uid = cur.lastrowid
        c.execute("INSERT INTO wallets(user_id,balance,space_bytes,updated_at) VALUES(?,?,?,?)", (uid, SIGNUP_BONUS, DEFAULT_SPACE, now))
        c.execute("INSERT INTO ledger(user_id,amount,kind,item,ts) VALUES(?,?,?,?,?)", (uid, SIGNUP_BONUS, "赠送", "新用户注册", now))
        return {"id": uid, "username": username, "balance": SIGNUP_BONUS, "space_bytes": DEFAULT_SPACE}


def login(username: str, password: str) -> dict[str, Any] | None:
    """登录：校验密码 → 返回 token + 用户。失败 → None。"""
    with _connect() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row or not _verify_password(password, row["password_hash"]):
            return None
        uid = row["id"]
        w = c.execute("SELECT * FROM wallets WHERE user_id=?", (uid,)).fetchone()
        token = _make_token(uid, username)
        return {"token": token, "id": uid, "username": username, "balance": w["balance"] if w else 0, "space_bytes": w["space_bytes"] if w else 0}


def get_wallet(user_id: int) -> dict[str, Any]:
    with _connect() as c:
        w = c.execute("SELECT * FROM wallets WHERE user_id=?", (user_id,)).fetchone()
        return {"balance": w["balance"] if w else 0, "space_bytes": w["space_bytes"] if w else 0}


def charge(user_id: int, amount: int, kind: str, item: str = "") -> bool:
    """扣积分（amount>0 消费）。余额不足返回 False；成功写 ledger。"""
    if amount <= 0:
        return True
    with _lock, _connect() as c:
        row = c.execute("SELECT balance FROM wallets WHERE user_id=?", (user_id,)).fetchone()
        bal = row["balance"] if row else 0
        if bal < amount:
            return False
        now = _dt.datetime.now(_dt.UTC).isoformat()
        c.execute("UPDATE wallets SET balance=?, updated_at=? WHERE user_id=?", (bal - amount, now, user_id))
        c.execute("INSERT INTO ledger(user_id,amount,kind,item,ts) VALUES(?,?,?,?,?)", (user_id, -amount, kind, item, now))
        return True


def credit(user_id: int, amount: int, kind: str, item: str = "") -> None:
    """加积分（充值/退款）。"""
    if amount <= 0:
        return
    with _lock, _connect() as c:
        now = _dt.datetime.now(_dt.UTC).isoformat()
        c.execute("UPDATE wallets SET balance=balance+?, updated_at=? WHERE user_id=?", (amount, now, user_id))
        c.execute("INSERT INTO ledger(user_id,amount,kind,item,ts) VALUES(?,?,?,?,?)", (user_id, amount, kind, item, now))


def expand_space(user_id: int, gb: int) -> bool:
    """空间扩容 1GB=PLAN['space_1gb'] 积分。成功返回 True 并加空间。"""
    cost = PLAN["space_1gb"] * gb
    if not charge(user_id, cost, "消费", f"空间扩容{gb}GB"):
        return False
    with _lock, _connect() as c:
        c.execute("UPDATE wallets SET space_bytes=space_bytes+?, updated_at=? WHERE user_id=?", (gb * 1024 * 1024 * 1024, _dt.datetime.now(_dt.UTC).isoformat(), user_id))
    return True


def ledger_list(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as c:
        rows = c.execute("SELECT amount,kind,item,ts FROM ledger WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def buy_model(user_id: int, model_id: str) -> dict[str, Any] | None:
    """购买模型（积分）。返回购买信息；余额不足/无此模型 → None。"""
    if model_id not in MODEL_PRICES:
        return None
    price = MODEL_PRICES[model_id]
    with _lock, _connect() as c:
        if c.execute("SELECT 1 FROM purchases WHERE user_id=? AND model_id=?", (user_id, model_id)).fetchone():
            return {"already": True, "model_id": model_id}
        if not charge(user_id, price, "消费", f"购买模型{model_id}"):
            return None
        c.execute("INSERT INTO purchases(user_id,model_id,ts) VALUES(?,?,?)", (user_id, model_id, _dt.datetime.now(_dt.UTC).isoformat()))
        return {"already": False, "model_id": model_id, "price": price}


def owned_models(user_id: int) -> list[str]:
    with _connect() as c:
        rows = c.execute("SELECT model_id FROM purchases WHERE user_id=?", (user_id,)).fetchall()
        return [r["model_id"] for r in rows]


def verify_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        if token.startswith("simple."):
            _h, b64, payload_s = token.split(".", 2)
            payload = json.loads(payload_s)
        elif _HAS_JWT:
            payload = _jwt.decode(token, _SECRET, algorithms=["HS256"])
        else:
            return None
        if "sub" not in payload:
            return None
        return {"id": int(payload["sub"]), "username": payload.get("name", "")}
    except Exception:  # pragma: no cover
        return None


def charge_if_authed(auth_header: str | None, cost: int, kind: str, item: str) -> tuple[bool, int | None]:
    """计费兼容：带有效 Bearer token 则扣积分（余额不足返回 (False, uid)）；
    无 token 视为本地模式放行（返回 (True, None)）。"""
    if not auth_header or not auth_header.startswith("Bearer "):
        return True, None
    user = verify_token(auth_header[7:].strip())
    if not user:
        return True, None
    uid = user["id"]
    if not charge(uid, cost, kind, item):
        return False, uid
    return True, uid


def user_by_id(user_id: int) -> dict[str, Any] | None:
    with _connect() as c:
        u = c.execute("SELECT id,username FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(u) if u else None