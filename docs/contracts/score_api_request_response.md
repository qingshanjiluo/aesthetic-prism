# 契约 C-SERVE-01：POST /score 与 GET /health（FastAPI HTTP 接口）

| 项 | 值 |
|---|---|
| 契约 ID | C-SERVE-01 |
| 归属 | ARCH 定义签名与 schema；SERVE 实现；QA 验证 |
| 批准状态 | 已冻结 @2026-11-08 03:30（lead 批准，回改须 lead 批准） |
| 修订留痕 | CW-S1-01 @2026-11-08 10:15（lead 批准·W3/W4：§4 补 E10 空文件 400 / E11 重复 image 400 / E12 Content-Length 先查后读 413 / E13 信号量 MAX_INFLIGHT=4→429 扩档 / E14 threadpool 约束；§2 加 TooManyRequestsError、§2.1 加 MAX_INFLIGHT、§3.5 扩 429 六档） |
| 已并入裁决 | 裁决 A：成功响应体六字段（`total`+四子分+`model`），四子分与全链路同名；错误体统一 `{"error":{"code","message"}}` |
| 四要素索引 | ① 函数签名=§2 ② JSON 结构=§3 ③ 错误语义=§4 ④ 最小示例=§5 |

## 1. 用途与适用范围

- 服务层（FastAPI）对外仅暴露两个端点：`GET /health`（存活/就绪探针）、`POST /score`（单图审美评分）。
- 所有成功响应 `Content-Type: application/json; charset=utf-8`；所有失败响应走同一错误体结构 + 4xx/5xx（裁决 A）。
- 分数序列化规则：五个分数字段输出前统一 `round(x, 1)`，故 JSON 中最多 1 位小数，范围 0–100（含端点）。
- 前端 Demo、压测脚本（locust）、QA 契约测试全部以本文档为唯一依据。

## 2. ① 函数签名（参数名 / 类型 / 返回类型 / 异常类型）

实现文件归属：`src/aesthetic_prism/serve/app.py` 与 `service.py`（SERVE 实现，签名不得改动）。

```python
from __future__ import annotations
from pathlib import Path
from typing import Any, Literal
from fastapi import UploadFile

class ApiError(Exception):
    """HTTP 层统一错误。属性: status_code: int; code: str; message: str。"""

class ImageTooLargeError(ApiError): ...     # → 413 payload_too_large
class UnsupportedMediaError(ApiError): ...  # → 415 unsupported_media_type
class InvalidImageError(ApiError): ...      # → 400 invalid_request
class ModelNotReadyError(ApiError): ...     # → 500 internal_error
class InferenceError(ApiError): ...         # → 500 internal_error
class TooManyRequestsError(ApiError): ...   # → 429 too_many_requests（在途满，W3/CW-S1-01 扩档）

class ScoreService:
    def __init__(self, model_path: Path, device: Literal["cpu", "cuda"] = "cpu") -> None: ...
    def score_bytes(self, data: bytes, mime: str) -> dict[str, float]:
        """返回键恰为 total/composition/light/creativity/story 的 dict，值 0–100。"""

async def get_health(service: ScoreService) -> dict[str, Any]:
    """GET /health 处理器。恒返回 200 + HealthResponse dict，不抛业务异常。"""

async def post_score(service: ScoreService, image: UploadFile) -> dict[str, Any]:
    """POST /score 处理器。成功返回 ScoreResponse dict；失败抛 ApiError 子类。"""
```

### 2.1 参数与返回明细

| 函数 / 方法 | 参数名 | 参数类型 | 返回类型 | 抛出异常类型 |
|---|---|---|---|---|
| `ScoreService.__init__` | `model_path` | `pathlib.Path` | `ScoreService` | `ModelNotReadyError`（ONNX 文件缺失/损坏） |
| `ScoreService.__init__` | `device` | `Literal["cpu","cuda"]` | 同上 | `ValueError`（编程错误，直接修复） |
| `ScoreService.score_bytes` | `data` | `bytes` | `dict[str, float]`（5 键） | `ImageTooLargeError`, `UnsupportedMediaError`, `InvalidImageError`, `ModelNotReadyError`, `InferenceError` |
| `ScoreService.score_bytes` | `mime` | `str` | 同上 | 同上 |
| `get_health` | `service` | `ScoreService` | `dict[str, Any]` | 无 |
| `post_score` | `service` | `ScoreService` | `dict[str, Any]` | `ApiError` 子类（见 §4） |
| `post_score` | `image` | `fastapi.UploadFile` | 同上 | 同上；FastAPI 解析 multipart 失败时由框架抛 422 → 须被 override 成 400 `invalid_request` 错误体 |

限制常量（服务层唯一事实源，实现与测试共用）：

| 常量 | 值 | 含义 |
|---|---|---|
| `MAX_IMAGE_BYTES` | `10_485_760`（10 MiB） | 超过 → 413 |
| `ALLOWED_MIME` | `{"image/jpeg", "image/png"}` | mime 或魔数不符 → 415 |
| `SCORE_TIMEOUT_MS` | `5000` | 单次推理超时 → 500 `internal_error` |
| `MAX_INFLIGHT` | `4` | 在途请求上限（信号量），满 → 429 `too_many_requests`（W3/CW-S1-01） |

## 3. ② JSON 数据结构（字段名 / 类型 / 取值范围）

### 3.1 `POST /score` 请求（multipart/form-data）

| 字段 | 位置 | 类型 | 约束 |
|---|---|---|---|
| `image` | form file | binary | 必填；魔数须为 JPEG(`FFD8FF`) 或 PNG(`89504E47`)；≤ 10 MiB；解码后宽高 ≥ 16 且 ≤ 8192 |

（无 JSON body 请求形式；`application/json` 请求体 → 415。）

### 3.2 `ScoreResponse`（200，六字段：5 分数键+model；四子分与全链路同名，无额外键）

| 字段 | 类型 | 取值范围 |
|---|---|---|
| `total` | number | 0 … 100，≤1 位小数 |
| `composition` | number | 0 … 100，≤1 位小数 |
| `light` | number | 0 … 100，≤1 位小数 |
| `creativity` | number | 0 … 100，≤1 位小数 |
| `story` | number | 0 … 100，≤1 位小数 |
| `model` | string | 非空，如 `"hapnet-teacher-v1"`；来自模型元数据，非请求输入 |

```json
{
  "total": 73.0, "composition": 78.4, "light": 71.2,
  "creativity": 65.9, "story": 74.6, "model": "hapnet-teacher-v1"
}
```

（示意结构；真实往返示例见 §5。`additionalProperties` 语义 = false，多键即违约。）

### 3.3 `HealthResponse`（200）

| 字段 | 类型 | 取值范围 |
|---|---|---|
| `status` | string | `"ok"` \| `"degraded"`（模型未就绪时 degraded） |
| `ready` | boolean | 模型可服务 = true |
| `model` | string \| null | 已加载模型名；未加载 = null |
| `device` | string | `"cpu"` \| `"cuda"` |
| `uptime_s` | number | ≥ 0，进程存活秒数，1 位小数 |

```json
{"status": "ok", "ready": true, "model": "hapnet-teacher-v1", "device": "cpu", "uptime_s": 12.4}
```

### 3.4 `ErrorResponse`（一切 4xx/5xx，统一）

| 字段 | 类型 | 约束 |
|---|---|---|
| `error.code` | string | 非空，snake_case，取值见 §3.5 |
| `error.message` | string | 非空，单行人类可读，不含堆栈/路径泄露 |

### 3.5 状态码表（六档：400/404/413/415/429/500；429=CW-S1-01 扩档，lead 已批）

| HTTP | `error.code` | 触发条件 | 调用方处理 |
|---|---|---|---|
| 400 | `invalid_request` | 缺 `image` 字段 / 图像解码失败 / 魔数与声明不符 / 解码后尺寸越界 / multipart 解析失败（含框架 422 归一） | 修复请求后重试；判为客户端错误不重投 |
| 404 | `not_found` | 未知路径或方法（含 `/score` 用 GET） | 检查路由拼写；同上 |
| 413 | `payload_too_large` | `image` > 10,485,760 字节 | 压缩图片后重试 |
| 415 | `unsupported_media_type` | mime ∉ {image/jpeg, image/png}，或请求体为 JSON 等非 multipart | 转码为 JPEG/PNG 后重试 |
| 500 | `internal_error` | 模型未加载 / 推理异常 / 推理超时 > 5000 ms | 指数退避重试 ≤2 次；仍失败则告警 |
| 429 | `too_many_requests` | 在途请求达 `MAX_INFLIGHT=4`（信号量满，E13） | 短退避 ≥100ms 重试 ≤3；客户端限速 |

429 档为 CW-S1-01 扩档（W3，lead 已批）；400/404/413/415/500 原有档位零改动，429 为第六档。

健康检查失败不走错误体：`ready=false` 时仍返回 200 + `status="degraded"`（负载均衡探针读 `ready` 字段）。

## 4. ③ 错误语义（什么情况抛什么错 / 调用方如何处理）

| # | 条件 | 服务层抛出 | HTTP | 错误体（真实消息示例） | 调用方处理 |
|---|---|---|---|---|---|
| E1 | `image` 字段缺失 | `InvalidImageError` | 400 | `{"error":{"code":"invalid_request","message":"missing form field 'image'"}}` | 补齐字段，不重试 |
| E2 | 字节非 JPEG/PNG（魔数不符） | `UnsupportedMediaError` | 415 | `{"error":{"code":"unsupported_media_type","message":"content is not image/jpeg or image/png"}}` | 转码后重试 |
| E3 | 魔数合法但解码器报错（截断） | `InvalidImageError` | 400 | `{"error":{"code":"invalid_request","message":"image decode failed: truncated jpeg"}}` | 判坏文件，不重试 |
| E4 | 文件 10,485,761 字节 | `ImageTooLargeError` | 413 | `{"error":{"code":"payload_too_large","message":"image is 10485761 bytes, limit 10485760"}}` | 压缩后重试 |
| E5 | 解码后 width=8 | `InvalidImageError` | 400 | `{"error":{"code":"invalid_request","message":"image too small: 8x8, min 16x16"}}` | 拒收，不重试 |
| E6 | 模型文件缺失启动即捕获；请求时 | `ModelNotReadyError` | 500 | `{"error":{"code":"internal_error","message":"model not ready: session unavailable"}}` | 退避重试 ≤2 次；仍失败告警 |
| E7 | 推理抛 onnxruntime 异常 / 超 5000 ms | `InferenceError` | 500 | `{"error":{"code":"internal_error","message":"inference failed: timeout after 5000ms"}}` | 同 E6 |
| E8 | 未知路径 `GET /nope` | 框架 404 被 exception handler 归一 | 404 | `{"error":{"code":"not_found","message":"no route for GET /nope"}}` | 检查路径，不重试 |
| E9 | 请求体非 multipart（如 `application/json`） | 路由守卫 | 415 | `{"error":{"code":"unsupported_media_type","message":"expected multipart/form-data"}}` | 换编码后重试 |
| E10 | 空文件：Content-Length=0，或 image 解码 0 字节（W4） | `InvalidImageError` | 400 | `{"error":{"code":"invalid_request","message":"empty image: decoded 0 bytes"}}` | 修请求补齐文件，不重试 |
| E11 | 重复同名 `image` 字段：multipart 同名字段数 >1（W4） | `InvalidImageError` | 400 | `{"error":{"code":"invalid_request","message":"duplicate form field 'image': 2 parts"}}` | 客户端 bug/构造请求；修请求后重试 |
| E12 | Content-Length > 10,485,760（W4）：**读 body 前**查请求头，先查后读，禁止读满再判；无 Content-Length 时边读边累计、达 10,485,761 立即中断 | `ImageTooLargeError` | 413 | `{"error":{"code":"payload_too_large","message":"content-length 10485761 exceeds 10485760"}}` | 压缩后重试 |
| E13 | 在途请求达 `MAX_INFLIGHT=4`（`asyncio.Semaphore` 满，W3） | `TooManyRequestsError` | 429 | `{"error":{"code":"too_many_requests","message":"inflight limit 4 reached, retry after 100ms"}}` | 短退避 ≥100ms 重试 ≤3；SDK 限速 |
| E14 | `score_bytes` 为阻塞 ORT `session.run`（≤5000 ms），不得在事件循环直调（W3） | —（实现约束非异常；超时归 E7 → 500） | — | 约束：必须经 `anyio.to_thread` / `run_in_executor` 专用线程池执行，Semaphore 在进池前取 | 框架层约束，SERVE 实现验收；`/health` 恒可探、不得被推理饿死 |

规则：5xx 错误体不得包含堆栈、绝对路径、模型内部名以外的实现细节；`code` 决定重试策略，`message` 只供日志/人读。测试断言以 `code` 为准，不匹配 `message` 文案。

## 5. ④ 最小示例（真实值，非伪代码）

示例资产 `docs/contracts/assets/example_sample.jpg`（48×48，666 字节，JPEG `FFD8FF`）。
推理取值与 DatasetSample §5 同源（total 由四子分门控加权 72.98 → round 73.0）。

### 5.1 GET /health

```bash
sh -c 'curl -s http://127.0.0.1:8000/health'
```

请求头：无。响应：

```json
HTTP/1.1 200 OK
content-type: application/json; charset=utf-8

{"status":"ok","ready":true,"model":"hapnet-teacher-v1","device":"cpu","uptime_s":12.4}
```

### 5.2 POST /score（成功 200）

```bash
sh -c 'curl -s -X POST http://127.0.0.1:8000/score -F "image=@docs/contracts/assets/example_sample.jpg" -w "\n%{http_code}"'
```

请求头：`content-type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW`（框架生成）。
响应：

```json
HTTP/1.1 200 OK
content-type: application/json; charset=utf-8

{"total":73.0,"composition":78.4,"light":71.2,"creativity":65.9,"story":74.6,"model":"hapnet-teacher-v1"}
```

### 5.3 失败示例（真实 415）

```bash
sh -c 'curl -s -X POST http://127.0.0.1:8000/score -H "content-type: application/json" -d "{\"x\":1}" -w "\n%{http_code}"'
```

```json
HTTP/1.1 415 Unsupported Media Type
content-type: application/json; charset=utf-8

{"error":{"code":"unsupported_media_type","message":"expected multipart/form-data"}}
```

### 5.4 调用方伪代码级判定（真实逻辑值）

```python
>>> body, status = post_score_request(image_bytes=open("docs/contracts/assets/example_sample.jpg","rb").read())
>>> status, sorted(body.keys())
(200, ['composition', 'creativity', 'light', 'model', 'story', 'total'])
>>> all(0 <= body[k] <= 100 for k in ['total','composition','light','creativity','story']), body['total']
(True, 73.0)
```

## 6. 验收标准（可执行检查）

```bash
# 1) 四要素小节齐全
sh -c "grep -q '## 2. ① 函数签名' docs/contracts/score_api_request_response.md && grep -q '## 3. ② JSON 数据结构' docs/contracts/score_api_request_response.md && grep -q '## 4. ③ 错误语义' docs/contracts/score_api_request_response.md && grep -q '## 5. ④ 最小示例' docs/contracts/score_api_request_response.md"

# 2) 裁决 A 六字段 + 统一错误体结构在位
sh -c "for k in total composition light creativity story model error code message; do grep -q \"\\\"$k\\\"\" docs/contracts/score_api_request_response.md || exit 1; done"

# 3) 六档状态码齐备（400/404/413/415/429/500；429=CW-S1-01 扩档）
sh -c "for c in 400 404 413 415 429 500; do grep -q \"| $c |\" docs/contracts/score_api_request_response.md || exit 1; done"

# 4) OpenAPI/schema 与本文档一致（SERVE 段5 交付后生效）
sh -c "python -m pytest -q tests/contract/test_score_api_contract.py::test_score_response_schema"
```
