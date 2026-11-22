# 05 部署方案（DEPLOY · SERVE）

| 项 | 值 |
|---|---|
| 文档 ID | D-DEPLOY-05 |
| 归属 | SERVE 起草，lead 批准；服务/部署/benchmark 交付的实施依据 |
| 状态 | 草案（lead 批准后冻结，回改须 lead 批准） |
| 关联契约 | C-SERVE-01（docs/contracts/score_api_request_response.md）、C-EXPORT-01（docs/contracts/onnx_io_names.md） |
| 关联验收 | docs/08_ACCEPTANCE.md：S1-01~05、S4-03、S5-01~05、S8-01/02 |
| 实现文件归属 | `src/aesthetic_prism/serve/app.py`（路由/异常归一/OpenAPI schema）、`src/aesthetic_prism/serve/service.py`（ScoreService/常量/异常类） |

## 1. ONNX Runtime 推理接入（①）

### 1.1 模型路径与会话初始化

| 项 | 值 |
|---|---|
| 默认模型路径 | `models/hapnet_teacher.onnx`（段4 后可切 `models/hapnet_student_int8.onnx`） |
| 覆盖方式 | 环境变量 `AP_MODEL_PATH`（相对项目根），仅配置层读取，不进请求链路 |
| 会话创建 | 应用 lifespan 启动阶段创建一次 `onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider", "CUDAExecutionProvider"])`，进程级单例；禁止每请求新建 |
| 启动校验 | 按 C-EXPORT-01 §3 核对：输入名 `images`、shape `(None,3,224,224)` float32、输出恰为五名 `total/composition/light/creativity/story` 且 shape `(None,1)`、域 [0,100]；不符则启动 fail-fast（不降级），`/health` 进入 `ready=false` |
| 设备 | `AP_DEVICE=cpu|cuda`（默认 cpu）；cuda 不可用时回退 cpu 并在启动日志记 warn |
| 会话不可用时 | `/score` 按 C-SERVE-01 §4 E6 返 500 `internal_error`；`/health` 返 200 + `status="degraded"` |

### 1.2 预处理 / 后处理（对齐 score 契约 §3.2 与 C-EXPORT-01 §3）

预处理（`service.py::ScoreService.score_bytes` 内）：

1. 字节数 > `MAX_IMAGE_BYTES`(10,485,760) → `ImageTooLargeError` 413；
2. 魔数校验：JPEG `FFD8FF` / PNG `89504E47`，不符 → `UnsupportedMediaError` 415；
3. Pillow 解码（失败 → `InvalidImageError` 400），EXIF 转正，RGB 统一（灰度/CMYK 转 RGB，alpha 丢弃白底合成）；
4. 解码后宽/高 <16 或 >8192 → `InvalidImageError` 400；
5. resize 224×224（BILINEAR，服务层等价路径，见 01_ARCH §2）→ float32/255 → ImageNet 归一化 `mean=(0.485,0.456,0.406) std=(0.229,0.224,0.225)` → `(1,3,224,224)`，值域 [-2.1179, 2.6400]；
6. `session.run(None, {"images": x})`，超 5000 ms 或 ORT 异常 → `InferenceError` 500。

后处理（与 score 契约 §3.2 逐字对齐）：

- 五输出 (1,1) float32 → `clip(0,100)` → `round(x, 1)`（契约 §1 序列化规则：≤1 位小数）；
- 构造 dict 键集**恰为** `total, composition, light, creativity, story, model` 六字段（additionalProperties=false 语义，多键即违约）；`model` 取 ONNX metadata `model_version`（非请求输入）；
- 评分五键与 ONNX 输出五名**逐字同名**（裁决 A）；历史三键旧命名（裁决 A 废止键族）禁止出现在任何响应、字段与文档中，残留 0（检查见「## 验收标准」第 2 条）。

### 1.3 mock ↔ 真实两模式切换语义

| 项 | mock（段1） | onnx 真实（段4 起） |
|---|---|---|
| 开关 | `AP_MODE=mock`（默认） | `AP_MODE=onnx` 且模型文件存在 |
| 分数来源 | 图像字节 sha256 派生确定性伪分数（0–100，round 1 位），同图恒同分 | ONNX 会话真实推理 |
| `model` 字段值 | 含 `mock` 子串，如 `mock-sha256` | `hapnet-teacher-v1`（模型元数据） |
| 健康状态 | `ready=true`（mock 可服务） | 模型加载成功 `ready=true`，失败 `ready=false` |
| schema | 与真实模式**同一** ScoreResponse 六字段，仅数值与 model 标识不同 | 同左 |

切换判据：`AP_MODE` 显式优先；未显式时按「模型文件存在 → onnx，缺失 → mock」自动降级并记 warn（段1 无模型必须可跑，S1-03 断言 `model` 含 mock；S4-01 断言 `model` 不含 mock，两段互不破坏）。

## 2. API 契约引用表（②，逐字引 C-SERVE-01）

### 2.1 端点与实现文件归属

| 契约条目 | 逐字要点（原文出处） | 实现文件 |
|---|---|---|
| `GET /health` | 恒 200 + HealthResponse，不抛业务异常（§2 `get_health`） | `app.py`（路由）；字段计算在 `service.py` |
| `POST /score` | multipart/form-data，字段 `image`；成功 ScoreResponse；失败抛 ApiError 子类（§2 `post_score`） | `app.py`（路由/异常归一）；`service.py`（`score_bytes`） |
| 异常类谱系 | `ApiError` → `ImageTooLargeError`413 / `UnsupportedMediaError`415 / `InvalidImageError`400 / `TooManyRequestsError`429（CW-S1-01）/ `ModelNotReadyError`500 / `InferenceError`500（§2） | 类定义 `service.py`；exception handler 注册 `app.py` |
| 限制常量 | `MAX_IMAGE_BYTES=10_485_760`、`ALLOWED_MIME={"image/jpeg","image/png"}`、`SCORE_TIMEOUT_MS=5000`、`MAX_INFLIGHT=4`（CW-S1-01）（§2 常量表） | `service.py`（唯一事实源，测试共用） |
| 422 归一 | FastAPI multipart 解析失败 422 → override 400 `invalid_request`（§2.1） | `app.py`（RequestValidationError handler） |
| 端口 | 服务基址 `http://127.0.0.1:8000` | `app.py`（uvicorn 8000） |

### 2.2 `ScoreResponse`（200，六字段，additionalProperties=false）

逐字引 C-SERVE-01 §3.2：

| 字段 | 类型 | 取值范围 |
|---|---|---|
| `total` | number | 0 … 100，≤1 位小数 |
| `composition` | number | 0 … 100，≤1 位小数 |
| `light` | number | 0 … 100，≤1 位小数 |
| `creativity` | number | 0 … 100，≤1 位小数 |
| `story` | number | 0 … 100，≤1 位小数 |
| `model` | string | 非空，如 `"hapnet-teacher-v1"`；来自模型元数据，非请求输入 |

四维中文名 = 构图 / 光影 / 创意 / 故事性（composition / light / creativity / story，与 HAP-Net 四分支同名）。

### 2.3 `HealthResponse`（200，逐字 §3.3）

| 字段 | 类型 | 取值范围 |
|---|---|---|
| `status` | string | `"ok"` \| `"degraded"`（模型未就绪时 degraded） |
| `ready` | boolean | 模型可服务 = true |
| `model` | string \| null | 已加载模型名；未加载 = null |
| `device` | string | `"cpu"` \| `"cuda"` |
| `uptime_s` | number | ≥ 0，进程存活秒数，1 位小数 |

### 2.4 `ErrorResponse` 与状态码表（一切 4xx/5xx 统一，逐字 §3.4/§3.5；六档，429=CW-S1-01 扩档）

错误体恒为 `{"error":{"code","message"}}`（code 非空 snake_case；message 非空单行、无堆栈/路径泄露）。

| HTTP | `error.code` | 触发条件 | 调用方处理 |
|---|---|---|---|
| 400 | `invalid_request` | 缺 `image` 字段 / 图像解码失败 / 魔数与声明不符 / 解码后尺寸越界 / multipart 解析失败（含框架 422 归一） | 修复请求后重试；判为客户端错误不重投 |
| 404 | `not_found` | 未知路径或方法（含 `/score` 用 GET） | 检查路由拼写；同上 |
| 413 | `payload_too_large` | `image` > 10,485,760 字节 | 压缩图片后重试 |
| 415 | `unsupported_media_type` | mime ∉ {image/jpeg, image/png}，或请求体为 JSON 等非 multipart | 转码为 JPEG/PNG 后重试 |
| 429 | `too_many_requests` | 在途请求达 `MAX_INFLIGHT=4`（信号量满，E13） | 短退避 ≥100ms 重试 ≤3；客户端限速 |
| 500 | `internal_error` | 模型未加载 / 推理异常 / 推理超时 > 5000 ms | 指数退避重试 ≤2 次；仍失败则告警 |

健康检查失败不走错误体：`ready=false` 时仍返回 200 + `status="degraded"`。测试断言以 `code` 为准，不匹配 `message` 文案（§4 规则）。

## 3. 最小前端页交互（③）

页面 `frontend/index.html` + `frontend/app.js`（纯原生 JS，无构建步骤；段8 起由 `make demo` 托管）。交互流：

1. **选图**：`<input type="file" accept="image/jpeg,image/png">` + 拖拽区；前端预检大小 ≤10 MiB（超限直接提示 413 文案，不发请求）；
2. **提交**：`fetch("/score", {method:"POST", body: formData})`，formData 字段名逐字 `image`；
3. **成功展示**：`total` 大号数字（保留 1 位小数）+ 四条水平进度条 `composition`/`light`/`creativity`/`story`（宽度 = 分值%，标签含中文名与数值）+ `model` 角标；
4. **错误体展示**：非 2xx 时解析 `{"error":{"code","message"}}`，展示 `code`（徽标）+ `message`；解析失败展示 `http_<status>` 兜底；
5. **健康灯**：页面加载即刻 + 每 5 s 轮询 `GET /health`；`ready=true` → 绿灯（status/model），`ready=false` → 黄灯（degraded），请求失败/超时 → 红灯；灯旁显示 `device` 与 `uptime_s`。

契约引用：§2.2 六字段、§2.4 错误体、端口 8000；前端不自造字段、不静默吞错。

## 4. 延迟预算（④；以 00_PRD 为准）

> 默认预算（本档）：**P50 ≤ 150 ms、P95 ≤ 500 ms、QPS ≥ 5**。阈值冲突时**以 `docs/00_PRD.md` 为准**（G4：单图 CPU P95 ≤ 500 ms，batch=1，onnxruntime CPU）。

| 环节 | 预算（P95） | 说明 |
|---|---|---|
| 请求接收 + 读体 + 魔数/尺寸校验 | ≤ 30 ms | 10 MiB 上限内 |
| Pillow 解码 + EXIF + resize 224 + 归一化 | ≤ 60 ms | 短边缩放等价路径 |
| ORT 会话 run（教师 / 学生） | ≤ 300 / ≤ 80 ms | 00_PRD AC8：教师 ≤200 ms、学生 ≤80 ms 中位；预算取 P95 宽松值 |
| clip + round + 序列化 | ≤ 10 ms | 六字段 JSON |
| uvicorn/网络抖动 | ≤ 40 ms | 本地回环 |
| warmup | 首请求不计入统计 | benchmark 前预热 5 次（§7 报告含 warmup 字段） |

门禁映射：S6-02（bench P50/P95 落盘 `reports/`）、S8-02（locust QPS ≥5、错误率 0）→ 判定路径见第 7 节；压测报告不许伪造，一律取工具原始输出。

## 5. Docker / compose、日志、配置校验与错误处理（⑤）

### 5.1 Docker / compose（段5 交付，S5-01）

| 项 | 规划 |
|---|---|
| 基础镜像 | `python:3.13-slim`，非 root 用户，`pip install --no-cache-dir -r requirements.txt` |
| COPY 范围 | `src/ frontend/ configs/ docs/contracts/ requirements.txt`；`models/` 经 volume 只读挂载（工件不进镜像层） |
| 启动 | `uvicorn aesthetic_prism.serve.app:app --host 0.0.0.0 --port 8000`（容器内 0.0.0.0，对外仍 8000） |
| compose | 单服务 `api`：`ports 8000:8000`、`healthcheck: curl -f http://127.0.0.1:8000/health`、env 注入 `AP_MODE/AP_MODEL_PATH/AP_DEVICE`、`models/` 只读卷 |
| 判定路径 | `docker compose up --build -d` → 15 s 内 `/health` 200（S5-01）；`docker build -f docker/Dockerfile -t aesthetic-prism:ci .`（AC7） |

### 5.2 日志

- 应用侧 `logging` JSON 单行：`ts, level, event, request_id, path, status, latency_ms, mode, model`；每请求一行访问日志（含状态码与耗时）；5xx 记 error 级（异常类型进日志，**不进响应体**）。
- 启动日志必含：mode、device、model_path、契约版本；uvicorn 自带 access log 关闭（避免双写）。
- `make dev` 将输出重定向 `logs/serve.log`（`logs/` 入 .gitignore）；**不写 `qa/`**（裁决 C：QA 所有，实现方只读）。

### 5.3 配置校验（`configs/serve/serve.yaml` + pydantic Settings）

| 字段 | 校验规则（启动 fail-fast，非法即非 0 退出） |
|---|---|
| `port` | 必须 = 8000（契约端口，改动须 lead 批准） |
| `mode` | ∈ {mock, onnx} |
| `device` | ∈ {cpu, cuda} |
| `model_path` | onnx 模式下必须存在且过 C-EXPORT-01 §3 核对 |
| `max_image_bytes` | 必须 = 10485760（与 `service.py` 常量同源断言） |
| `score_timeout_ms` | 必须 = 5000 |
| `allowed_mime` | 必须 = {image/jpeg, image/png} |

### 5.4 错误处理（与契约 §4 E1–E9 逐条对齐）

- 全局 handler：`ApiError` → `JSONResponse {"error":{"code","message"}}` + 其 `status_code`；框架 422 → 归一 400 `invalid_request`；404/405 → `not_found`；非 multipart → 415 `unsupported_media_type`。
- 5xx 响应体只含 `code`+`message`，不含堆栈/绝对路径；测试断言只认 `code`。
- `/health` 恒 200：`ready=false` → `status="degraded"`，不走错误体。

## 6. Makefile 目标清单（⑥；Windows + GNU Make 4.4.1）

环境钉死：GNU Make 4.4.1（winget `ezwinports.make`）。PATH 别名 `C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links\make.exe`；个别进程不可见时用全路径 `C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\ezwinports.make_Microsoft.Winget.Source_8wekyb3d8bbwe\bin\make.exe`。

编写硬约束：

1. **命令体走 python/pwsh**：recipe 用单行简单命令（`python -m …`）或 `&&` 串联（cmd/sh 双兼容）；复杂逻辑落 `scripts/*.py`（或 `.ps1`，`pwsh -NoProfile -Command`）再调用。
2. **禁止 bash-only 语法**：不写 `[[ ]]`、`<(...)`、`declare -A`、`function(){}`、数组拼接；不依赖 `$()` 特性；路径分隔用 `/`。
3. **不默认 `.ONESHELL`**：每行 recipe 独立 shell；跨行逻辑一律进脚本文件，不在 Makefile 内联多行。
4. 门禁类命令（QA 执行）按裁决 D 走 Git `sh -c "…"`；Makefile 本身不绑定 sh 专有内建。
5. 目标声明 `.PHONY:`，Tab 缩进，无隐式规则依赖。

| 目标 | 命令体（要点） | 覆盖门禁 |
|---|---|---|
| `dev` | `python -m uvicorn aesthetic_prism.serve.app:app --host 127.0.0.1 --port 8000`（默认 mock 模式，前台阻塞） | S1-01/S1-02/S1-03 |
| `test` | `python -m pytest -q` | S1-04、S5-04 |
| `lint` | `ruff check src tests` | S5-02、S1-05 |
| `typecheck` | `mypy src` | S5-03 |
| `coverage` | `python -m pytest --cov=src --cov-report=term-missing -q`（TOTAL ≥80%） | S5-05 |
| `demo` | 一键起后端 + 打开前端页（FastAPI StaticFiles 挂 `frontend/`，`make dev` 同源复用，单命令全链路） | S8-01、S8-05 |
| `reproduce` | `python scripts/reproduce.py`（编排 数据→导出→评测复算 的接线壳，各段签名由对应组脚本提供，SERVE 只接线） | S7-04 |
| `bench`（附加） | `python -m src.bench --n 200 --out reports/latency.json` | S6-02 |
| `load`（附加） | `locust -f tests/load/locustfile.py --headless -u 8 -t 30s --csv reports/load` | S8-02 |
| `build`（附加） | `docker build -f docker/Dockerfile -t aesthetic-prism:ci .` | AC7 |

门禁 `make dev` 必须在 Windows + GNU Make 4.4.1 下可跑（S1-01：sh 后台拉起 20 s 存活）。

## 7. 压测方案（⑦）与门禁判定路径映射

### 7.1 推理延迟 benchmark（S6-02）

`python -m src.bench --n 200 --out reports/latency.json`：warmup 5 次不计入 → 计时 ≥200 次 `session.run` → 落盘 `{"n", "p50_ms", "p95_ms", "device", "model", "mode", "warmup", "cpu"}`；判定 `p50_ms≤150 && p95_ms≤500`（与 §4 延迟预算一致，以 00_PRD G4 为准）。**成绩必须来自实测输出，禁止手写/伪造。**

### 7.2 HTTP 压测（locust 2.47.0，S8-02 / AC8）

- 实现单场景模块 `tests/load/locustfile.py`（QA 判定路径）；`benchmarks/locustfile.py` 为薄壳 re-export 同一场景（满足 PRD AC8 双路径，Windows 无 symlink 用 `import` 转发，不复制逻辑）。
- 场景：multipart `POST /score`（固定样图 `docs/contracts/assets/example_sample.jpg`，混合 `assets/` 样图轮换）+ 少量 `GET /health`；HTTP 直连 127.0.0.1:8000。
- 门禁参数：`--headless -u 8 -t 30s`，断言 QPS(Requests/s) ≥5 且 Failure Count = 0。
- **报告必含字段**：QPS、P50(ms)、P95(ms)、错误率(%)、样本量(Request Count/失败数)、warmup 次数（前 5 次请求 `stats.clear()` 前完成、不入统计）、并发用户数、压测时长、CPU 型号/核数、模型与模式（mock/onnx）。落盘 `reports/load_report.{json,html}` + `--csv` 原始表。
- warmup 方案：locust `test_start` 事件先发 5 次单线程预热请求后 `environment.stats.clear()`，再进入正式统计窗口。
- 结果不许伪造：报告 JSON 由脚本从 locust stats API 读出生成，禁止手工编辑。

### 7.3 门禁判定路径 → 本文对应章节

| 条目 | 判定路径（08_ACCEPTANCE 原文摘要） | 本文章节 |
|---|---|---|
| S1-01 | `make dev` 后台拉起，20 s 后进程存活 | §6 `dev` |
| S1-02 | `GET /health` 200 且 `status=="ok"` | §2.1、§6 `dev` |
| S1-03 | `POST /score` mock 六字段 0–100、`model` 含 mock | §1.3、§2.2 |
| S1-04 | `pytest -q` 全绿 | §6 `test` |
| S1-05 | CI 含 lint + test 双门禁 | §8 |
| S4-03 | 非法路径/非图像/超大文件 → 4xx + `error.code/message` | §2.4、§5.4 |
| S5-01 | `docker compose up --build -d` + `/health` 200 | §5.1 |
| S5-02 | `make lint` 零告警 | §6 `lint` |
| S5-03 | `make typecheck` 零错误 | §6 `typecheck` |
| S5-04 | `make test` 全绿 | §6 `test` |
| S5-05 | `make coverage` TOTAL ≥80% | §6 `coverage` |
| S8-01 | `make demo` 单命令起全链路，`/score` 200 | §6 `demo`、§3 |
| S8-02 | locust QPS ≥5、失败 =0 | §7.2 |
| S6-02 | bench P50/P95 落盘 | §7.1 |
| S7-04 | `make reproduce` 退出码 0 | §6 `reproduce` |

## 8. CI 骨架（⑧；lint + test 双门禁）

`.github/workflows/ci.yml`：`on: [push, pull_request]`；两个并列 job（缺一即红）——

- `lint`：`make lint`（等效 `ruff check src tests`）；
- `test`：`make test`（等效 `python -m pytest -q`）；
- 矩阵：`ubuntu-latest` + Python 3.13.14（make 命令体为跨平台 python 调用，Linux runner 原生 make 可跑；Windows 本地同构验证由 §6 保证）；
- 注释行固定写明门禁清单原文 `pytest|make test` 与 `ruff|flake8|make lint` 两串字面（S1-05 的 grep 判定对 ERE 转义解释不敏感，两种解释均命中）；
- 段5 扩展位：`coverage`（上传 term 报告）、`docker build`（AC7），骨架先留 `workflow_dispatch` 手动入口。

## 9. 双端交付：扩展端点、绑定与桌面快捷方式（⑨）

> 本节登记 D-双端交付新增的三个端点与部署形态。**只登记本文，不进 `docs/08_ACCEPTANCE.md` 冻结表**（08 仅主控可改）；主契约 `/score` `/health` 与错误体语义逐字不变。

### 9.1 新增端点（错误体同走六档 `{"error":{"code","message"}}`，413/415/404/429 全链保持）

| 端点 | 方法/体 | 成功返回 | 失败档 |
|---|---|---|---|
| `/upload` | POST multipart，字段名逐字 `image` | 200 `{"path","filename","width","height","bytes","mime"}`，`path`=相对项目根 POSIX 路径（`data/uploads/<stem>-<uuid8>.<ext>`） | 非 multipart 415 / >10,485,760 413 / 空文件·魔数不符·尺寸越界 400/415（校验链与 `/score` 同源 `probe_image`）/ 重复 `image` 字段 400 |
| `/train` | POST，可选 JSON body `{"steps":N}`（默认 20，N∈[1,10000]） | 202 语义 200 JSON `{"job_id","state","steps","loss_log","status_url"}`，后台线程 `python -m src.train --steps N --loss-log data/uploads/train-<id>.json` | steps 越界/非整数 400 `invalid_request` |
| `/train/status` | GET | 200 `{"running","jobs_running","latest_job_id","state","steps","done","total","pct","last_loss","loss_log"}`——读 `loss.json` 计算进度（无作业时读根 `loss.json`） | 恒 200 |
| `/jobs/<id>` | GET | 200 job 详情（`job_id/kind/state/steps/created_at/pid/returncode/done/total/pct/last_loss`） | 未知 id → 404 `not_found`（统一错误体） |

实现归属：路由 `src/aesthetic_prism/serve/app.py`；`probe_image` 校验链 `src/aesthetic_prism/serve/service.py`。`/upload` 复用 `/score` 的 multipart 守卫（路径集 `{"/score","/upload"}`，415→413→400→重复字段顺序不变）。

### 9.2 服务绑定（局域网可达）

- 启动命令：`uvicorn aesthetic_prism.serve.app:app --host 0.0.0.0 --port 8000 --app-dir src`（容器内/宿主机同形，`--host 0.0.0.0` 使局域网任意设备可访问 `http://<lan-ip>:8000`）。
- 本机回环验收仍用 `http://127.0.0.1:8000`；契约端口 8000 不变。

### 9.3 桌面快捷方式

- `scripts/desktop_start.bat`：起 `uvicorn … 0.0.0.0:8000`（新窗口 detached/minimized）→ `timeout 3` → `start http://127.0.0.1:8000/` → 退出。
- `scripts/make_shortcut.ps1`：`WScript.Shell` COM 生成桌面 `Aesthetic Prism.lnk` → 指向 `desktop_start.bat`（WorkingDirectory=项目根，WindowStyle=7）。
- 「检查状态」不生成 .lnk：页面内 `检查状态` 按钮 `fetch /health`，JSON 徽标显示 运行中 / 降级 / 异常 / 离线，面板内嵌 `/health` 原始 JSON。

## 验收标准（本文档自检，sh -c 可执行）

```bash
# 1) 必需章节齐全 + 六字段五键逐字在位
sh -c "for s in '## 1. ONNX Runtime' '## 2. API 契约引用表' '## 3. 最小前端页交互' '## 4. 延迟预算' '## 5. Docker' '## 6. Makefile' '## 7. 压测方案' '## 8. CI 骨架' '## 验收标准'; do grep -q \"\$s\" docs/05_DEPLOY.md || exit 1; done && for k in total composition light creativity story model; do grep -q \"\$k\" docs/05_DEPLOY.md || exit 1; done && echo SECTIONS-OK"

# 2) 裁决 A 废止旧三键零命中（模式用字符类防自匹配）+ 六档状态码齐备（429=CW-S1-01 扩档）+ 错误体结构在位
sh -c "if grep -qiE 'col[o]r|lightin[g]|detai[l]' docs/05_DEPLOY.md; then exit 1; fi && for c in 400 404 413 415 429 500; do grep -q \"\$c\" docs/05_DEPLOY.md || exit 1; done && grep -q '{\"error\":{\"code\",\"message\"}}' docs/05_DEPLOY.md && grep -q '8000' docs/05_DEPLOY.md && echo CONTRACT-OK"

# 3) 门禁判定路径映射：S1-01~05 / S4-03 / S5-01~05 / S8-01/02 十三条全有对应章节行
sh -c "for id in S1-01 S1-02 S1-03 S1-04 S1-05 S4-03 S5-01 S5-02 S5-03 S5-04 S5-05 S8-01 S8-02; do grep -q \"\$id\" docs/05_DEPLOY.md || exit 1; done && echo GATE-MAP-OK"

# 4) Makefile 七目标 + Windows/GNU Make 4.4.1 约束 + 压测报告字段
sh -c "for t in dev test lint typecheck coverage demo reproduce; do grep -q \"\$t\" docs/05_DEPLOY.md || exit 1; done && grep -q 'GNU Make 4.4.1' docs/05_DEPLOY.md && grep -q 'ONESHELL' docs/05_DEPLOY.md && grep -q 'warmup' docs/05_DEPLOY.md && grep -q '样本量' docs/05_DEPLOY.md && echo MAKEFILE-OK"
```
