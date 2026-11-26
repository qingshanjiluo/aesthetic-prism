# C-SERVE-01 HTTP 层：GET /health + POST /score（六档错误，CW-S1-01 全并入；r7 三修）
# 双端扩展：POST /upload、POST /train、GET /train/status、GET /jobs/<id>（登记 docs/05_DEPLOY §9，不入 08 冻结表）
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import re
import sys
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from aesthetic_prism.serve.service import (
    MAX_IMAGE_BYTES,
    MAX_INFLIGHT,
    ApiError,
    InvalidImageError,
    ModelNotReadyError,
    ScoreService,
    TooManyRequestsError,
    probe_image,
)
from aesthetic_prism.serve import auth  # 商业化：认证 + 积分

log = logging.getLogger("aesthetic_prism.serve")


def _maybe_charge(request: Request, cost: int, kind: str, item: str) -> None:
    """计费：带 token 则扣积分，不足 402；无 token 本地放行。"""
    ok, _uid = auth.charge_if_authed(request.headers.get("authorization"), cost, kind, item)
    if not ok:
        raise _err(402, "insufficient_points", f"积分不足，需要 {cost} 积分")

# ---- 段5 T-5-02：结构化 JSON 日志（stdout 一行一条 JSON）+ X-Request-ID ----


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": _dt.datetime.now(_dt.UTC).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            },
            ensure_ascii=False,
        )


def setup_json_logging() -> None:
    """幂等：给 aesthetic_prism 根 logger 挂 stdout JSON handler。"""
    root = logging.getLogger("aesthetic_prism")
    if getattr(root, "_ap_json_ready", False):
        return
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(_JsonFormatter())
    root.addHandler(h)
    root.setLevel(logging.INFO)
    root._ap_json_ready = True  # type: ignore[attr-defined]


setup_json_logging()

_ROOT = Path(__file__).resolve().parents[3]  # aesthetic-prism/
_FRONTEND = _ROOT / "frontend"
_UPLOAD_DIR = _ROOT / "data" / "uploads"
_LOSS_LOG = _ROOT / "loss.json"  # GET /train/status 进度读取点（--loss-log 默认位置）
_START = time.time()
_sem = asyncio.Semaphore(MAX_INFLIGHT)  # E13：在途上限，进池前取（CW-S1-01）

# ---- /train 作业注册表（进程内；job id = uuid4 hex 前 12 位）----
_jobs: dict[str, dict[str, Any]] = {}
_MAX_TRAIN_STEPS = 10_000
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def build_service() -> ScoreService:
    """配置来自环境（configs/serve/serve.yaml 由调用方注入环境或段5 接 pydantic Settings）。"""
    mode = os.environ.get("AP_MODE", "auto")
    model_path = Path(os.environ.get("AP_MODEL_PATH", "models/hapnet_teacher.onnx"))
    device = os.environ.get("AP_DEVICE", "cpu")
    if mode == "onnx" and not model_path.is_file():
        raise ModelNotReadyError(f"model not ready: file not found: {model_path.name}")
    return ScoreService(model_path=model_path, device=device)  # type: ignore[arg-type]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.service = build_service()
    auth.init_db()
    log.info("serve up mode=%s device=%s", app.state.service.mode, app.state.service.device)
    yield


app = FastAPI(
    title="Aesthetic Prism",
    version="1.0.0",
    lifespan=_lifespan,
    description="图片审美评分 C-SERVE-01：GET /health + POST /score",
)
from aesthetic_prism.serve.commercial_routes import router as commercial_router

app.include_router(commercial_router)


@app.get("/health")
async def get_health() -> dict[str, Any]:
    """GET /health 处理器。恒返回 200 + HealthResponse dict，不抛业务异常。"""
    svc: ScoreService = app.state.service
    ready = svc.ready
    return {
        "status": "ok" if ready else "degraded",
        "ready": ready,
        "model": svc.model_name,
        "device": svc.device,
        "uptime_s": round(time.time() - _START, 1),
    }


async def post_score(service: ScoreService, image: UploadFile) -> dict[str, Any]:
    """POST /score 处理器。成功返回 ScoreResponse dict；失败抛 ApiError 子类。"""
    data = await image.read()
    mime = image.content_type or ""
    # E13：满即 429 立即返回、绝不排队；进池前取（非阻塞 locked 快速失败）
    if _sem.locked():
        raise TooManyRequestsError()  # E13: full => 429 immediately, never queue
    await _sem.acquire()
    try:
        # E14：score_bytes 为阻塞调用，必须经 threadpool 执行，不得在事件循环直调
        scores = await anyio.to_thread.run_sync(service.score_bytes, data, mime)
    finally:
        _sem.release()
    payload: dict[str, Any] = dict(scores)
    payload["model"] = service.model_name
    return payload


@app.post("/score")
async def score_route(
    request: Request, image: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    _maybe_charge(request, 10, "消费", "评分")
    # defensive fallback (main pre-check in guard)
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_IMAGE_BYTES:
        from aesthetic_prism.serve.service import ImageTooLargeError

        raise ImageTooLargeError(f"content-length {cl} exceeds {MAX_IMAGE_BYTES}")
    svc: ScoreService = request.app.state.service
    try:
        return await post_score(svc, image)
    except ApiError:
        raise
    except TimeoutError:  # E7 超时归 500
        raise ModelNotReadyError("inference failed: timeout") from None
    except Exception as exc:
        log.exception("score failed: %s", type(exc).__name__)
        raise ModelNotReadyError("model not ready: session unavailable") from None


# ---- 双端扩展端点：/upload /train /train/status /jobs/<id>（错误体同走六档 ApiError 映射）----
def _job_view(job: dict[str, Any]) -> dict[str, Any]:
    """job 注册表条目 → 对外 JSON（只读拷贝，不含 stdout/stderr 全文）。"""
    return {
        "job_id": job["id"],
        "kind": job["kind"],
        "state": job["state"],
        "steps": job["steps"],
        "created_at": job["created_at"],
        "pid": job["pid"],
        "returncode": job["returncode"],
    }


def _train_progress(job: dict[str, Any]) -> dict[str, Any]:
    """读 loss.json 计算进度：记录数/steps、最近 loss、完成度百分比。"""
    loss_path = _ROOT / job["loss_log"]
    done = 0
    last: float | None = None
    if loss_path.is_file():
        try:
            data = json.loads(loss_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                done = len(data)
                if data and isinstance(data[-1], (int, float)):
                    last = round(float(data[-1]), 6)
        except (OSError, ValueError):
            done = 0
    total = int(job["steps"])
    return {
        "done": done,
        "total": total,
        "pct": round(100.0 * min(done, total) / total, 1) if total else 0.0,
        "last_loss": last,
        "loss_log": job["loss_log"],
    }


def _run_train_job(job: dict[str, Any]) -> None:
    """后台线程：python -m src.train --steps N --loss-log <path>，捕获 rc 归档输出尾部。"""
    import subprocess

    loss_abs = str(_ROOT / job["loss_log"])
    cmd = [sys.executable, "-m", "src.train", "--steps", str(job["steps"]), "--loss-log", loss_abs]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            timeout=job["timeout_s"],
            check=False,
        )
        job["returncode"] = int(proc.returncode)
        job["stdout_tail"] = (proc.stdout or "")[-2000:]
        job["stderr_tail"] = (proc.stderr or "")[-2000:]
        job["state"] = "succeeded" if proc.returncode == 0 else "failed"
    except Exception as exc:
        job["returncode"] = -1
        job["stderr_tail"] = f"{type(exc).__name__}: {exc}"[:2000]
        job["state"] = "failed"
    finally:
        job["finished_at"] = time.time()
        log.info("train job %s end state=%s rc=%s", job["id"], job["state"], job["returncode"])


@app.post("/upload")
async def upload_route(
    request: Request, image: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    """POST /upload：multipart 收图 → 校验（probe_image 同 /score 链）→ 存 data/uploads/ → 返回相对路径+尺寸。"""
    _maybe_charge(request, 2, "消费", "上传素材")
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_IMAGE_BYTES:
        from aesthetic_prism.serve.service import ImageTooLargeError

        raise ImageTooLargeError(f"content-length {cl} exceeds {MAX_IMAGE_BYTES}")
    data = await image.read()
    mime = image.content_type or ""
    meta = probe_image(data, mime)  # 413/415/400 校验链与 /score 同源
    ext = ".jpg" if mime == "image/jpeg" else ".png"
    original = Path(image.filename or f"upload{ext}").name  # 丢弃任何目录成分
    stem = _SAFE_NAME.sub("_", Path(original).stem).strip("._") or "upload"
    target = _UPLOAD_DIR / f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "path": str(target.relative_to(_ROOT)).replace("\\", "/"),
        "filename": original,
        "width": meta["width"],
        "height": meta["height"],
        "bytes": meta["bytes"],
        "mime": meta["mime"],
    }


@app.post("/train")
async def train_route(request: Request) -> dict[str, Any]:
    """POST /train：触发 python -m src.train --steps N 后台执行，202 + job id（默认 steps=20）。"""
    _maybe_charge(request, 100, "消费", "训练")
    steps = 20
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
        except Exception:
            raise InvalidImageError("train: request body is not valid JSON") from None
        if isinstance(body, dict) and "steps" in body:
            raw = body["steps"]
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1 or raw > _MAX_TRAIN_STEPS:
                raise InvalidImageError(f"train: steps must be int in [1, {_MAX_TRAIN_STEPS}]")
            steps = raw
    job_id = uuid.uuid4().hex[:12]
    loss_rel = f"data/uploads/train-{job_id}.json"
    job: dict[str, Any] = {
        "id": job_id,
        "kind": "train",
        "state": "running",
        "steps": steps,
        "created_at": time.time(),
        "finished_at": None,
        "pid": None,
        "returncode": None,
        "loss_log": loss_rel,
        "timeout_s": max(600, steps * 30),  # 30s/step 宽松上限，超时归 failed
        "stdout_tail": "",
        "stderr_tail": "",
    }
    _jobs[job_id] = job
    import threading

    threading.Thread(target=_run_train_job, args=(job,), daemon=True, name=f"train-{job_id}").start()
    log.info("train job %s start steps=%d", job_id, steps)
    return {"job_id": job_id, "state": "running", "steps": steps, "loss_log": loss_rel, "status_url": f"/jobs/{job_id}"}


@app.get("/train/status")
async def train_status_route() -> dict[str, Any]:
    """GET /train/status：读 loss.json 进度 + 最近一次训练作业状态。"""
    running = [j for j in _jobs.values() if j["kind"] == "train" and j["state"] == "running"]
    latest = max(_jobs.values(), key=lambda j: j["created_at"]) if _jobs else None
    view: dict[str, Any] = {
        "running": bool(running),
        "jobs_running": len(running),
        "latest_job_id": latest["id"] if latest else None,
        "state": latest["state"] if latest else "idle",
        "steps": latest["steps"] if latest else 0,
        "loss_log": _LOSS_LOG.name if latest is None else latest["loss_log"],
    }
    if latest is not None:
        view.update(_train_progress(latest))
    else:
        # 无人触发过训练时也读根 loss.json（S3-03/手动训练的 --loss-log 落点）
        view.update(_train_progress({"steps": 0, "loss_log": _LOSS_LOG.name}) | {"total": 0, "pct": 0.0})
        loss_path = _LOSS_LOG
        if loss_path.is_file():
            try:
                data = json.loads(loss_path.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    last_v = data[-1]
                    if isinstance(last_v, (int, float)):
                        view["last_loss"] = round(float(last_v), 6)
                    view["records"] = len(data)
            except (OSError, ValueError):
                pass
    return view


@app.get("/jobs/{job_id}")
async def job_route(job_id: str) -> dict[str, Any]:
    """GET /jobs/<id>：作业详情（训练作业附 loss.json 进度）。未知 id → 404 not_found。"""
    job = _jobs.get(job_id)
    if job is None:
        from starlette.exceptions import HTTPException

        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")  # 走 _not_found 归一
    out = _job_view(job)
    out.update(_train_progress(job))
    return out


# ===== 增强端点（ENHANCE_PLAN.md A1-A8）：素材库 / 批量 / 文件夹评分 =====

# 素材元数据登记（进程内；键=相对路径，值={tags,note,created}）。持久化于 data/assets_meta.json
_ASSETS_META = _ROOT / "data" / "assets_meta.json"
_meta: dict[str, dict[str, Any]] = {}


def _load_meta() -> None:
    if _meta or not _ASSETS_META.is_file():
        return
    try:
        _meta.update(json.loads(_ASSETS_META.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass


_META_LOCK = __import__("threading").Lock()

def _save_meta() -> None:
    _ASSETS_META.parent.mkdir(parents=True, exist_ok=True)
    with _META_LOCK:
        tmp = _ASSETS_META.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_ASSETS_META)


def _is_image_path(p: Path) -> bool:
    return p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _rel_list(paths: list[str]) -> list[Path]:
    """把请求里的路径归一到 data/ 下的相对 Path，剔除越界/非图片。"""
    out: list[Path] = []
    for s in paths:
        p = (Path(s) if Path(s).is_absolute() else _ROOT / Path(s)).resolve()
        try:
            p.relative_to(_ROOT.resolve())
        except ValueError:
            continue
        if _is_image_path(p) and p.is_file():
            out.append(p)
    return out


def _asset_view(p: Path) -> dict[str, Any]:
    st = p.stat()
    rel = str(p.relative_to(_ROOT)).replace("\\", "/")
    m = _meta.get(rel, {})
    return {
        "path": rel,
        "filename": p.name,
        "width": m.get("width"),
        "height": m.get("height"),
        "bytes": st.st_size,
        "mtime": round(st.st_mtime, 3),
        "mime": ("image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"),
        "tags": m.get("tags", []),
        "note": m.get("note", ""),
    }


@app.get("/assets")
async def assets_route(
    offset: int = 0,
    limit: int = 100,
    sort: str = "mtime",
    order: str = "desc",
    tag: str = "",
    q: str = "",
) -> dict[str, Any]:
    """GET /assets：素材库列表。offset/limit 分页；sort=filename|mtime|bytes|total；order=asc|desc；tag/q 过滤。"""
    _load_meta()
    items = []
    for p in _UPLOAD_DIR.glob("*"):
        if not _is_image_path(p) or not p.is_file():
            continue
        v = _asset_view(p)
        items.append(v)
    if tag:
        items = [v for v in items if tag in v["tags"]]
    if q:
        ql = q.lower()
        items = [v for v in items if ql in v["filename"].lower() or ql in (v["note"] or "").lower()]
    key = {"filename": lambda v: v["filename"].lower(), "mtime": lambda v: v["mtime"], "bytes": lambda v: v["bytes"], "total": lambda v: v.get("total") or 0}.get(sort, lambda v: v["mtime"])
    items.sort(key=key, reverse=(order == "desc"))
    total = len(items)
    page = items[offset:offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "items": page}


@app.post("/assets/delete")
async def assets_delete_route(request: Request) -> dict[str, Any]:
    """POST /assets/delete：json {paths:[...]} 批量删除。返回删除数；越界/不存在跳过。"""
    body = await request.json()
    paths = body.get("paths") if isinstance(body, dict) else None
    if not isinstance(paths, list):
        raise InvalidImageError("assets/delete: paths must be a list")
    targets = _rel_list([str(x) for x in paths])
    for p in targets:
        try:
            p.unlink()
        except OSError:
            pass
        rel = str(p.relative_to(_ROOT)).replace("\\", "/")
        _meta.pop(rel, None)
    _save_meta()
    return {"deleted": len(targets), "requested": len(paths)}


@app.post("/assets/rename")
async def assets_rename_route(request: Request) -> dict[str, Any]:
    """POST /assets/rename：json {path, new_name} 重命名（只改文件名，保留目录）。"""
    body = await request.json()
    src = str(body.get("path", "")) if isinstance(body, dict) else ""
    new = str(body.get("new_name", "")) if isinstance(body, dict) else ""
    if not src or not new:
        raise InvalidImageError("assets/rename: path and new_name required")
    p = (Path(src) if Path(src).is_absolute() else _ROOT / Path(src)).resolve()
    try:
        p.relative_to(_ROOT.resolve())
    except ValueError:
        raise InvalidImageError("assets/rename: path out of root") from None
    if not p.is_file():
        raise InvalidImageError(f"assets/rename: not found {src}")
    safe_new = _SAFE_NAME.sub("_", Path(new).name).strip("._") or "asset"
    dst = p.with_name(safe_new)
    if dst.exists():
        raise InvalidImageError(f"assets/rename: target exists {dst.name}")
    p.rename(dst)
    old_rel = str(p.relative_to(_ROOT)).replace("\\", "/")
    new_rel = str(dst.relative_to(_ROOT)).replace("\\", "/")
    if old_rel in _meta:
        _meta[new_rel] = _meta.pop(old_rel)
        _save_meta()
    return {"from": old_rel, "to": new_rel}


@app.post("/assets/meta")
async def assets_meta_route(request: Request) -> dict[str, Any]:
    """POST /assets/meta：json {path, tags?, note?} 更新单素材元数据。"""
    body = await request.json()
    src = str(body.get("path", "")) if isinstance(body, dict) else ""
    p = (Path(src) if Path(src).is_absolute() else _ROOT / Path(src)).resolve()
    try:
        p.relative_to(_ROOT.resolve())
    except ValueError:
        raise InvalidImageError("assets/meta: path out of root") from None
    rel = str(p.relative_to(_ROOT)).replace("\\", "/")
    _load_meta()
    m = _meta.get(rel, {})
    if isinstance(body, dict):
        if "tags" in body and isinstance(body["tags"], list):
            m["tags"] = [str(t) for t in body["tags"]]
        if "note" in body:
            m["note"] = str(body["note"])
    _meta[rel] = m
    _save_meta()
    return {"path": rel, "tags": m.get("tags", []), "note": m.get("note", "")}


@app.post("/assets/upload-batch")
async def assets_upload_batch_route(request: Request, files: Annotated[list[UploadFile], File()]) -> dict[str, Any]:
    """POST /assets/upload-batch：multipart 多文件（字段名 files）。逐文件校验/保存，返回结果+失败原因。"""
    results = []
    ok = fail = 0
    for f in files:
        data = await f.read()
        try:
            meta = probe_image(data, f.content_type or "")
        except ApiError as e:
            results.append({"filename": f.filename, "ok": False, "code": e.code, "message": e.message})
            fail += 1
            continue
        ext = ".jpg" if f.content_type == "image/jpeg" else ".png"
        original = Path(f.filename or f"upload{ext}").name
        stem = _SAFE_NAME.sub("_", Path(original).stem).strip("._") or "upload"
        target = _UPLOAD_DIR / f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
        _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        results.append({
            "filename": original, "path": str(target.relative_to(_ROOT)).replace("\\", "/"),
            "ok": True, "width": meta["width"], "height": meta["height"], "bytes": meta["bytes"],
        })
        ok += 1
    return {"ok": ok, "fail": fail, "total": len(files), "results": results}


@app.post("/score-batch")
async def score_batch_route(request: Request) -> dict[str, Any]:
    """POST /score-batch：json {paths:[...]} 批量评分。逐图走 /score 同链，返回按 total 降序 + 平均分。"""
    body = await request.json()
    paths = body.get("paths") if isinstance(body, dict) else None
    if not isinstance(paths, list) or not paths:
        raise InvalidImageError("score-batch: paths must be a non-empty list")
    targets = _rel_list([str(x) for x in paths])
    if not targets:
        raise InvalidImageError("score-batch: no valid image paths")
    _maybe_charge(request, len(targets) * 5, "消费", "批量评分")
    svc: ScoreService = request.app.state.service
    scored = []
    for p in targets:
        data = p.read_bytes()
        if _sem.locked():
            scored.append({"path": str(p.relative_to(_ROOT)).replace("\\", "/"), "error": "busy"})
            continue
        await _sem.acquire()
        try:
            s = await anyio.to_thread.run_sync(svc.score_bytes, data, "image/png" if p.suffix.lower() == ".png" else "image/jpeg")
        except ApiError as e:
            scored.append({"path": str(p.relative_to(_ROOT)).replace("\\", "/"), "error": e.code})
            continue
        finally:
            _sem.release()
        scored.append({"path": str(p.relative_to(_ROOT)).replace("\\", "/"), "total": round(float(s["total"]), 2), "composition": round(float(s["composition"]), 2), "light": round(float(s["light"]), 2), "creativity": round(float(s["creativity"]), 2), "story": round(float(s["story"]), 2)})
    scored.sort(key=lambda x: x.get("total", -1), reverse=True)
    vals = [x["total"] for x in scored if "total" in x]
    return {"scored": len(scored), "avg_total": round(sum(vals) / len(vals), 2) if vals else None, "items": scored}


@app.post("/train/batch")
async def train_batch_route(request: Request) -> dict[str, Any]:
    """POST /train/batch：json {steps, paths?} 批量训练。paths 省略=整库；返回 job id（沿用 /train 注册表）。"""
    body = await request.json()
    steps = 20
    paths = None
    if isinstance(body, dict):
        if "steps" in body:
            raw = body["steps"]
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1 or raw > _MAX_TRAIN_STEPS:
                raise InvalidImageError(f"train/batch: steps must be int in [1, {_MAX_TRAIN_STEPS}]")
            steps = raw
        if "paths" in body and body["paths"] is not None:
            paths = [str(x) for x in body["paths"]]
    job_id = uuid.uuid4().hex[:12]
    loss_rel = f"data/uploads/train-{job_id}.json"
    job: dict[str, Any] = {
        "id": job_id, "kind": "train_batch", "state": "running", "steps": steps,
        "created_at": time.time(), "finished_at": None, "pid": None, "returncode": None,
        "loss_log": loss_rel, "timeout_s": max(600, steps * 30), "stdout_tail": "", "stderr_tail": "",
        "paths": paths,
    }
    _jobs[job_id] = job
    import threading
    threading.Thread(target=_run_train_job, args=(job,), daemon=True, name=f"train-{job_id}").start()
    return {"job_id": job_id, "state": "running", "steps": steps, "paths_count": len(paths) if paths else None, "status_url": f"/jobs/{job_id}"}


@app.post("/assets/exists")
async def assets_exists_route(request: Request) -> dict[str, Any]:
    """POST /assets/exists：json {paths:[...]} 批量探测素材存在性。"""
    body = await request.json()
    paths = body.get("paths") if isinstance(body, dict) else None
    if not isinstance(paths, list):
        raise InvalidImageError("assets/exists: paths must be a list")
    out = []
    for s in paths:
        p = (Path(str(s)) if Path(str(s)).is_absolute() else _ROOT / Path(str(s))).resolve()
        out.append({"path": str(s), "exists": p.is_file()})
    return {"items": out}


# ===== 模型管理（ENHANCE：多模型命名/分类/标记）=====
_MODELS_META = _ROOT / "configs" / "models_meta.json"
_model_meta: dict[str, dict[str, Any]] = {}


def _load_model_meta() -> None:
    if _model_meta or not _MODELS_META.is_file():
        return
    try:
        _model_meta.update(json.loads(_MODELS_META.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass


def _save_model_meta() -> None:
    _MODELS_META.parent.mkdir(parents=True, exist_ok=True)
    with _META_LOCK:
        tmp = _MODELS_META.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_model_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_MODELS_META)


def _scan_models() -> list[Path]:
    """扫描 models/ 与 artifacts/ 下的 .onnx/.pt 模型文件。"""
    out: list[Path] = []
    for d in ("models", "artifacts"):
        dd = _ROOT / d
        if not dd.is_dir():
            continue
        for p in sorted(dd.glob("*")):
            if p.is_file() and p.suffix.lower() in (".onnx", ".pt", ".pth"):
                out.append(p)
    return out


@app.get("/models")
async def models_route() -> dict[str, Any]:
    """GET /models：列出全部模型文件 + 元数据（name/category/tags/note）。"""
    _load_model_meta()
    current = Path(os.environ.get("AP_MODEL_PATH", "models/hapnet_teacher.onnx"))
    items = []
    for p in _scan_models():
        rel = str(p.relative_to(_ROOT)).replace("\\", "/")
        m = _model_meta.get(rel, {})
        items.append({
            "path": rel,
            "filename": p.name,
            "bytes": p.stat().st_size,
            "suffix": p.suffix,
            "name": m.get("name", p.stem),
            "category": m.get("category", ""),
            "tags": m.get("tags", []),
            "note": m.get("note", ""),
            "active": (rel == str(current).replace("\\", "/")),
        })
    return {"total": len(items), "items": items, "active_model": str(current).replace("\\", "/")}


@app.post("/models/meta")
async def models_meta_route(request: Request) -> dict[str, Any]:
    """POST /models/meta：json {path, name?, category?, tags?, note?} 更新模型元数据。"""
    body = await request.json()
    src = str(body.get("path", "")) if isinstance(body, dict) else ""
    if not src:
        raise InvalidImageError("models/meta: path required")
    p = (Path(src) if Path(src).is_absolute() else _ROOT / Path(src)).resolve()
    try:
        p.relative_to(_ROOT.resolve())
    except ValueError:
        raise InvalidImageError("models/meta: path out of root") from None
    if not p.is_file():
        raise InvalidImageError(f"models/meta: not found {src}")
    rel = str(p.relative_to(_ROOT)).replace("\\", "/")
    _load_model_meta()
    m = _model_meta.get(rel, {})
    if isinstance(body, dict):
        if "name" in body:
            m["name"] = str(body["name"])
        if "category" in body:
            m["category"] = str(body["category"])
        if "tags" in body and isinstance(body["tags"], list):
            m["tags"] = [str(t) for t in body["tags"]]
        if "note" in body:
            m["note"] = str(body["note"])
    _model_meta[rel] = m
    _save_model_meta()
    return {"path": rel, "name": m.get("name", p.stem), "category": m.get("category", ""), "tags": m.get("tags", []), "note": m.get("note", "")}


@app.post("/samples/generate")
async def samples_generate_route(request: Request) -> dict[str, Any]:
    """POST /samples/generate：json {n?, out?} 自动生成合成训练样本（走 data/synthetic.py）。

    默认 n=20、out=data/synthetic；生成后返回数量与目录。n 上限 500。
    """
    n = 20
    out = None
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
        except Exception:
            raise InvalidImageError("samples/generate: body not valid JSON") from None
        if isinstance(body, dict):
            if "n" in body:
                raw = body["n"]
                if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1 or raw > 500:
                    raise InvalidImageError("samples/generate: n must be int in [1, 500]")
                n = raw
            if "out" in body:
                out = str(body["out"])
    _maybe_charge(request, n * 3, "消费", f"生成{n}张样本")
    from aesthetic_prism.data import synthetic as _syn

    try:
        samples = []
        out_dir = Path(out) if out else _syn.OUT_DIR
        if not out_dir.is_absolute():
            out_dir = _ROOT / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        # 从 index.json 读已生成的 id 集合，避免覆盖
        existing: set[str] = set()
        idx_file = out_dir / "index.json"
        if idx_file.is_file():
            try:
                idx = json.loads(idx_file.read_text(encoding="utf-8"))
                for s in idx.get("samples", []):
                    existing.add(s["id"])
            except (OSError, ValueError):
                pass
        nxt = 1
        while len(samples) < n and nxt <= 200000:
            sid = f"syn_{nxt:06d}"
            nxt += 1
            if sid in existing:
                continue
            samples.append(_syn.generate(_syn.SEED, sid, out_dir))
        # 合并进 index.json
        if idx_file.is_file():
            try:
                idx = json.loads(idx_file.read_text(encoding="utf-8"))
                idx["samples"] = idx.get("samples", []) + samples
                idx["meta"]["n"] = len(idx["samples"])
            except (OSError, ValueError):
                idx = {"meta": {"n": len(samples), "seed": _syn.SEED, "gen_version": "rw-s2-03", "labels": list(_syn.KEYS)}, "samples": samples}
        else:
            idx = {"meta": {"n": len(samples), "seed": _syn.SEED, "gen_version": "rw-s2-03", "labels": list(_syn.KEYS)}, "samples": samples}
        idx_file.write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return {"generated": len(samples), "total": idx["meta"]["n"], "dir": str(out_dir.relative_to(_ROOT)).replace("\\", "/")}
    except Exception as exc:
        log.exception("samples generate failed")
        raise InvalidImageError(f"samples/generate failed: {type(exc).__name__}") from None


# ---- 六档错误映射（ApiError 子类 → 400/404/413/415/429/500 统一 {"error":{code,message}}）----
@app.exception_handler(ApiError)
async def _api_error(_r: Request, exc: ApiError) -> JSONResponse:
    return _err(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def _validation(_r: Request, exc: RequestValidationError) -> JSONResponse:
    # multipart 解析失败 422 → 400 invalid_request（契约 §2.1）
    return _err(400, "invalid_request", "multipart parse failed: invalid request")


@app.exception_handler(404)
async def _not_found(request: Request, exc: Any) -> JSONResponse:
    return _err(404, "not_found", f"no route for {request.method} {request.url.path}")


@app.exception_handler(405)
async def _method_not_allowed(request: Request, exc: Any) -> JSONResponse:
    return _err(404, "not_found", f"no route for {request.method} {request.url.path}")


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled: %s", type(exc).__name__)
    if isinstance(exc, ApiError):
        return _err(exc.status_code, exc.code, exc.message)
    return _err(500, "internal_error", "inference failed")


# 请求守卫（E9→E12→E11，中间件在 ExceptionMiddleware 外层，一律 return 错误体、不 raise）
@app.middleware("http")
async def multipart_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.method == "POST" and request.url.path in ("/score", "/upload"):
        # 第1步 E9：非 multipart → 415（/upload 与 /score 同一守卫链）
        ctype = request.headers.get("content-type", "")
        if "multipart/form-data" not in ctype:
            return _err(415, "unsupported_media_type", "expected multipart/form-data")
        # 第2步 E12：读 body 前先查 Content-Length → 413（先查后读，禁止读满再判）
        cl = request.headers.get("content-length", "")
        if cl.isdigit() and int(cl) > MAX_IMAGE_BYTES:
            return _err(413, "payload_too_large", f"content-length {cl} exceeds {MAX_IMAGE_BYTES} bytes")
        try:
            # 第3步 先 body() 缓存 _body：下游经 _CachedRequest.wrapped_receive 回放全量
            #（form() 直接消费 stream 会使下游只收到空体；base.py 分支：_body 优先）
            await request.body()
            # 第4步 解析一次（starlette _form 缓存，FastAPI 依赖复用不二次解析；
            # max_part_size 对齐契约 §3.1 的 10 MiB，非 starlette 默认 1 MiB）
            form = await request.form(max_part_size=MAX_IMAGE_BYTES)
        except Exception:
            return _err(400, "invalid_request", "multipart parse failed: invalid request")
        # 第5步 E11：同名 image 字段数 > 1 → 400
        n = len(form.getlist("image"))
        if n > 1:
            return _err(400, "invalid_request", f"duplicate form field 'image': {n} parts")
    return await call_next(request)


# 前端静态页（同源 :8000，无跨域）：/ 与 /frontend 均可访问
if _FRONTEND.is_dir():
    app.mount("/frontend", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(_FRONTEND / "index.html")

# 素材静态访问（ENHANCE：素材缩略图/比对图走 /data/uploads/...）
_DATA_DIR = _ROOT / "data"
if _DATA_DIR.is_dir():
    app.mount("/data", StaticFiles(directory=str(_DATA_DIR)), name="data")


# ============================================================
# 数据标注 annotations API
# ============================================================
import csv as _csv
import io as _io
import threading as _threading

_ANNOTATIONS_DB = _ROOT / "data" / "annotations.db"


def _ann_connect():
    _ANNOTATIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3 as _s3
    conn = _s3.connect(str(_ANNOTATIONS_DB), check_same_thread=False, timeout=10)
    conn.row_factory = _s3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ann_init():
    conn = _ann_connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS annotations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL DEFAULT 0,
        path        TEXT NOT NULL,
        composition REAL DEFAULT 0,
        light       REAL DEFAULT 0,
        creativity  REAL DEFAULT 0,
        story       REAL DEFAULT 0,
        total       REAL DEFAULT 0,
        quality     TEXT DEFAULT '',
        note        TEXT DEFAULT '',
        annotator   TEXT DEFAULT '',
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_ann_user_path ON annotations(user_id, path);
    CREATE INDEX IF NOT EXISTS idx_ann_user ON annotations(user_id);
    CREATE TABLE IF NOT EXISTS ann_export_log (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        fmt      TEXT NOT NULL,
        count    INTEGER,
        created_at TEXT NOT NULL
    );
    """)
    # 旧库迁移：加 user_id 列（已有单列 UNIQUE(path) 的库）
    try:
        conn.execute("ALTER TABLE annotations ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ann_user_path ON annotations(user_id, path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ann_user ON annotations(user_id)")
        # 旧 UNIQUE(path) 索引若存在则保留（user_id=0 单机数据不冲突）
        conn.commit()
    except Exception:
        pass
    conn.commit()
    conn.close()


def _ann_user_id(request: Request) -> int:
    """从 Bearer token 解析 user_id；无 token / 无效 = 0（单机模式）。"""
    h = request.headers.get("authorization", "")
    if h.startswith("Bearer "):
        u = auth.verify_token(h[7:].strip())
        if u:
            return u["id"]
    return 0


_ANN_LOCK = _threading.Lock()
_ann_init()


@app.get("/annotations")
async def annotations_list(
    request: Request,
    q: str = "",
    quality: str = "",
    min_total: float = 0,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """GET /annotations 标注列表；按 token 用户隔离（无 token=单机全量）；q=path 子串；quality/min_total/offset/limit。"""
    uid = _ann_user_id(request)
    with _ANN_LOCK:
        conn = _ann_connect()
        where = ["user_id = ?"]
        args: list[Any] = [uid]
        if q:
            where.append("path LIKE ?")
            args.append(f"%{q}%")
        if quality:
            where.append("quality = ?")
            args.append(quality)
        if min_total > 0:
            where.append("total >= ?")
            args.append(min_total)
        w = " WHERE " + " AND ".join(where)
        total = conn.execute(f"SELECT COUNT(*) c FROM annotations{w}", args).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM annotations{w} ORDER BY total DESC LIMIT ? OFFSET ?",
            args + [limit, offset],
        ).fetchall()
        items = [dict(r) for r in rows]
        conn.close()
    return {"total": total, "limit": limit, "offset": offset, "user_id": uid, "items": items}


@app.post("/annotations")
async def annotations_upsert(request: Request) -> dict[str, Any]:
    """POST /annotations 写入/更新单条标注（按用户隔离）。计费 1 积分（带 token 时）。"""
    _maybe_charge(request, 1, "消费", "标注保存")
    uid = _ann_user_id(request)
    body = await request.json()
    path = str(body.get("path", "")).strip()
    if not path:
        return _err(400, "invalid_request", "path is required")
    c = float(body.get("composition", 0) or 0)
    l = float(body.get("light", 0) or 0)
    cr = float(body.get("creativity", 0) or 0)
    st = float(body.get("story", 0) or 0)
    total = float(body.get("total", 0) or ((c + l + cr + st) / 4))
    quality = str(body.get("quality", "")).strip()
    note = str(body.get("note", "")).strip()
    annotator = str(body.get("annotator", "local")).strip()
    now = _dt.datetime.now(_dt.UTC).isoformat()
    with _ANN_LOCK:
        conn = _ann_connect()
        conn.execute(
            """
            INSERT INTO annotations (user_id, path, composition, light, creativity, story, total, quality, note, annotator, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, path) DO UPDATE SET
                composition=excluded.composition, light=excluded.light,
                creativity=excluded.creativity, story=excluded.story,
                total=excluded.total, quality=excluded.quality,
                note=excluded.note, annotator=excluded.annotator,
                updated_at=excluded.updated_at
            """,
            (uid, path, c, l, cr, st, total, quality, note, annotator, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM annotations WHERE user_id=? AND path=?", (uid, path)).fetchone()
        conn.close()
    return dict(row)


@app.delete("/annotations")
async def annotations_delete(request: Request, path: str = "") -> dict[str, Any]:
    """DELETE /annotations?path= 删除单条（按用户隔离）。"""
    if not path:
        return _err(400, "invalid_request", "path query param required")
    uid = _ann_user_id(request)
    with _ANN_LOCK:
        conn = _ann_connect()
        cur = conn.execute("DELETE FROM annotations WHERE user_id=? AND path=?", (uid, path))
        conn.commit()
        deleted = cur.rowcount
        conn.close()
    return {"deleted": deleted}


@app.get("/annotations/export")
async def annotations_export(request: Request, fmt: str = "jsonl", quality: str = "", min_total: float = 0) -> dict[str, Any]:
    """GET /annotations/export?fmt=jsonl|csv 导出（按用户隔离）。计费 2 积分（带 token 时）。"""
    _maybe_charge(request, 2, "消费", "标注导出")
    uid = _ann_user_id(request)
    with _ANN_LOCK:
        conn = _ann_connect()
        where = ["user_id = ?"]
        args: list[Any] = [uid]
        if quality:
            where.append("quality = ?")
            args.append(quality)
        if min_total > 0:
            where.append("total >= ?")
            args.append(min_total)
        w = " WHERE " + " AND ".join(where)
        rows = conn.execute(f"SELECT * FROM annotations{w} ORDER BY total DESC", args).fetchall()
        conn.close()
        import json as _json
        items = [dict(r) for r in rows]
        if fmt == "csv":
            buf = _io.StringIO()
            fields = ["user_id", "path", "composition", "light", "creativity", "story", "total", "quality", "note", "annotator", "created_at", "updated_at"]
            wr = _csv.DictWriter(buf, fieldnames=fields)
            wr.writeheader()
            for r in items:
                wr.writerow({k: r.get(k, "") for k in fields})
            return {"count": len(items), "user_id": uid, "text": buf.getvalue()}
        lines = [_json.dumps(r, ensure_ascii=False) for r in items]
        return {"count": len(items), "user_id": uid, "lines": lines}

