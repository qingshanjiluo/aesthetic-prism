# Aesthetic Prism 商业化路由（COMMERCIAL.md）：认证 / 钱包 / 商城 / 空间 / 算力 / 计费
# 独立 router，app.py include_router 挂载。计费依赖 get_current_user。
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException

from aesthetic_prism.serve import auth

router = APIRouter(prefix="/api", tags=["commercial"])


# ---- 鉴权依赖：Authorization: Bearer <token> → user ----
def get_current_user(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization[7:].strip()
    user = auth.verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return user


def _require_balance(user: dict[str, Any], cost: int, kind: str, item: str) -> None:
    """扣积分；余额不足 402。"""
    if not auth.charge(user["id"], cost, kind, item):
        raise HTTPException(status_code=402, detail=f"积分不足，需要 {cost} 积分")


# ---- 认证 ----
@router.post("/auth/register")
async def register_route(body: dict[str, Any]) -> dict[str, Any]:
    username = str((body or {}).get("username", "")).strip()
    password = str((body or {}).get("password", ""))
    if not username or len(username) < 3 or len(password) < 6:
        raise HTTPException(status_code=400, detail="用户名≥3字符，密码≥6字符")
    r = auth.register(username, password)
    if r is None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    return {"ok": True, "user": r}


@router.post("/auth/login")
async def login_route(body: dict[str, Any]) -> dict[str, Any]:
    username = str((body or {}).get("username", "")).strip()
    password = str((body or {}).get("password", ""))
    r = auth.login(username, password)
    if r is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"ok": True, "token": r["token"], "user": {"id": r["id"], "username": r["username"], "balance": r["balance"], "space_bytes": r["space_bytes"]}}


@router.get("/me")
async def me_route(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    w = auth.get_wallet(user["id"])
    return {"id": user["id"], "username": user["username"], "balance": w["balance"], "space_bytes": w["space_bytes"]}


# ---- 钱包 / 积分 ----
@router.get("/wallet")
async def wallet_route(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    w = auth.get_wallet(user["id"])
    return {"balance": w["balance"], "space_bytes": w["space_bytes"]}


@router.get("/wallet/ledger")
async def ledger_route(limit: int = 50, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"items": auth.ledger_list(user["id"], limit)}


@router.post("/wallet/recharge")
async def recharge_route(body: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """模拟充值：amount 积分到账（生产接支付回调）。"""
    amount = int((body or {}).get("amount", 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount 必须>0")
    auth.credit(user["id"], amount, "充值", "模拟充值")
    w = auth.get_wallet(user["id"])
    return {"ok": True, "balance": w["balance"], "recharged": amount}


# ---- 模型商城 ----
@router.get("/models/shop")
async def shop_route(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    owned = set(auth.owned_models(user["id"]))
    items = [{"model_id": m, "price": p, "owned": m in owned} for m, p in auth.MODEL_PRICES.items()]
    return {"items": items}


@router.post("/models/buy")
async def buy_route(body: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    model_id = str((body or {}).get("model_id", ""))
    if model_id not in auth.MODEL_PRICES:
        raise HTTPException(status_code=404, detail="模型不存在")
    if model_id in auth.owned_models(user["id"]):
        return {"ok": True, "already": True, "model_id": model_id}
    _require_balance(user, auth.MODEL_PRICES[model_id], "消费", f"购买模型{model_id}")
    r = auth.buy_model(user["id"], model_id)
    return {"ok": True, "already": False, "model_id": model_id, "price": auth.MODEL_PRICES[model_id]}


# ---- 云端空间 ----
@router.post("/space/expand")
async def space_expand_route(body: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    gb = int((body or {}).get("gb", 1))
    if gb < 1 or gb > 100:
        raise HTTPException(status_code=400, detail="gb 须在 1-100")
    cost = auth.PLAN["space_1gb"] * gb
    _require_balance(user, cost, "消费", f"空间扩容{gb}GB")
    if not auth.expand_space(user["id"], gb):
        raise HTTPException(status_code=402, detail="空间扩容失败")
    w = auth.get_wallet(user["id"])
    return {"ok": True, "space_bytes": w["space_bytes"], "cost": cost}


# ---- 云端算力 API ----
@router.post("/compute")
async def compute_route(body: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """云端算力：按档扣积分（demo 档 1/2/3 = 10/20/50）。"""
    tier = int((body or {}).get("tier", 1))
    if tier not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="tier 须为 1/2/3")
    cost = {1: 10, 2: 20, 3: 50}[tier]
    _require_balance(user, cost, "消费", f"云端算力T{tier}")
    return {"ok": True, "tier": tier, "cost": cost, "job_id": f"compute-{user['id']}-{tier}"}