# Aesthetic Prism · 架构文档（ARCH）

| 项 | 值 |
|---|---|
| 文档 ID | D-ARCH-01 |
| 归属 | ARCH 定义结构与形状；MODEL/SERVE/DATA 在契约内实现；QA 验证 |
| 状态 | 草案（lead 批准后冻结，回改须 lead 批准） |
| 关联契约 | C-DATA-01 / C-SERVE-01 / C-EXPORT-01 / C-BRANCH-01（docs/contracts/model_branch_interfaces.md） |

## 1. 四层结构

```
┌─ 应用层  frontend/ + labeling/ ─── 前端 Demo、标注平台（浏览器）        段2/段4/段8
├─ 服务层  src/aesthetic_prism/serve ─ FastAPI /score /health + 模型会话   段1/段4/段5/段8
├─ 模型层  src/aesthetic_prism/model ─ HAP-Net 四分支+门控+双头；export/   段3/段4/段6
├─ 数据层  src/aesthetic_prism/data ── DatasetSample 读写、合成、标注导出   段2
└─ 横切    configs/ docker/ tests/ benchmarks/ qa/ ─ 配置/封装/门禁/验收
```

依赖方向（单向，禁止反向 import）：应用层 → 服务层 → 模型层 → 数据层；横切层被各层引用，不依赖任何一层。
数据层只认 C-DATA-01；服务层只认 C-SERVE-01；模型层对内实现 C-BRANCH-01、对外导出符合 C-EXPORT-01 的工件。

## 2. 输入张量形状约定

| 项 | 值（唯一事实源，训练/导出/服务三方一致） |
|---|---|
| 输入名 | `images`（ONNX/ORT 层面，裁决 B） |
| dtype | `float32`，CHW（导出/推理）；DataLoader 内部亦为 NCHW |
| shape | `(N, 3, 224, 224)`；训练 batch=64，推理 N=1（dynamic axis 仅 N） |
| 尺寸预处理 | 短边缩放 → 中心裁剪 224×224（Pillow BILINEAR）；服务层等价：直接 resize 224×224 |
| 归一化 | ImageNet：`x = (pixel/255 - mean)/std`，`mean=(0.485,0.456,0.406)`，`std=(0.229,0.224,0.225)` |
| 值域 | `[-2.1179, 2.6400]`（0/255 与 1 端点实算，见 C-EXPORT-01 §5） |
| 参考样例 | `docs/contracts/assets/example_input_224.npy`（1,3,224,224）实测 min=-1.351285 max=2.248908 |

颜色空间：RGB（Pillow `convert("RGB")`，EXIF 转正后）。灰度/CMYK 输入在服务层转 RGB；alpha 通道丢弃（白色底衬合成）。

## 3. HAP-Net 四分支与融合门控、双头输出

结构与 forward 签名以 C-BRANCH-01 为准，此处给数据流与形状摘要：

```
images (N,3,224,224)
  → stem: Conv3x3/s2 ×2 + BN + GELU → (N,32,56,56)
  → trunk: 深度可分离残差块 ×4 → (N,128,14,14)   [共享主干]
  ├→ branch_composition → GAP → feat (N,64) → z_c (N,1)
  ├→ branch_light        → GAP → feat (N,64) → z_l (N,1)
  ├→ branch_creativity   → GAP → feat (N,64) → z_r (N,1)
  └→ branch_story        → GAP → feat (N,64) → z_s (N,1)
       │
       ├─ score 头: F=(N,256)→g=softmax over 4 gate logits (N,4)；四子分 sub=100·σ(z) (N,4)
       │            total = clip(Σ gᵢ·subᵢ, 0, 100) (N,1)
       └─ ranking 头: Bradley-Terry 打分 r (N,1)，成对 loss=-log σ(r_a - r_b)  [仅训练，不进 ONNX]
```

双头输出（PyTorch eval 态 dict，六键：五键进 ONNX + ranking_logit 训练专用）：

| key | dtype | shape | 范围 | 进 ONNX？ |
|---|---|---|---|---|
| `total` | float32 | (N,1) | [0,100] | 是 |
| `composition` | float32 | (N,1) | [0,100] | 是 |
| `light` | float32 | (N,1) | [0,100] | 是 |
| `creativity` | float32 | (N,1) | [0,100] | 是 |
| `story` | float32 | (N,1) | [0,100] | 是 |
| `ranking_logit` | float32 | (N,1) | ℝ（未过 sigmoid） | 否（训练专用，导出剥离） |
| `gate` | float32 | (N,4) | 行和=1 | 内部（仅中间张量） |

## 4. 参数量预算

| 模型 | 说明 | 预算上限 | 门禁 |
|---|---|---|---|
| 教师 hapnet-teacher | 四分支全宽（分支宽度 64，与 C-BRANCH-01 §3.1 冻结 D=64 一致），rank+score 双头 | ≤ 25,000,000 | 段3 |
| 学生 hapnet-student | 蒸馏共享主干→窄分支（宽度 48）+ 深度剪枝 | **< 10,000,000**（硬） | 段6 |
| 学生 INT8 部署 | INT8 权重文件 | < 10,000,000 字节（=10 MB） | 段6 |
| 分支头/门控头单体 | GAP 投影 (64→1)×4 + gate (256→4) | < 2,000 | 段3 |

预算校验点：`sum(p.numel() for p in model.parameters())`，证据写 `reports/params.json`（字段：`{"teacher": int, "student": int, "student_int8_bytes": int}`），AC 见 00_PRD §5 AC4。

## 5. 目录结构（aesthetic-prism/ 树）

路径可微调（lead 裁决 C：`qa/` 为 QA 所有、实现方只读）：

```
aesthetic-prism/
├── README.md                     # 本树各路径可微调的说明（含 qa/ 权属）
├── GATE_LOG.md                   # 段0–8 门禁执行记录（append-only）
├── docs/
│   ├── 00_PRD.md  01_ARCH.md     # 本文件 06_RISK.md 07_PLAN.md
│   ├── 06_RISK.md 07_PLAN.md
│   └── contracts/
│       ├── dataset_DatasetSample.md          # C-DATA-01（DATA 实现依据）
│       ├── score_api_request_response.md     # C-SERVE-01（SERVE 实现依据）
│       ├── onnx_io_names.md                  # C-EXPORT-01（MODEL/SERVE 实现依据）
│       ├── model_branch_interfaces.md        # C-BRANCH-01（MODEL 实现依据）
│       └── assets/  example_sample.jpg · example_input_224.npy   # 契约示例资产（ARCH 所有）
├── qa/                           # 裁决 C：QA 所有，实现方只读
│   ├── evidence/S0..S8/      # S 格证据（报告/日志/截图，文件名见 07_PLAN）
│   └── reports/FINAL_ACCEPTANCE.md
├── configs/{data,model,train,serve}/ *.yaml
├── data/{raw,synthetic,exports,labeled,batch_00,checkpoints}/   # DATA 所有
├── labeling/                     # 标注平台（DATA）
├── src/aesthetic_prism/
│   ├── data/ model/ train/ export/ serve/ utils/
├── frontend/                     # Demo 前端（SERVE）
├── scripts/                      # make 门禁包装脚本（bash，经 sh -c 执行）
├── tests/{contract,unit,integration,perf}/
├── benchmarks/                   # locustfile.py + 吞吐基准（QA 执行，DATA/MODEL 提供）
├── docker/  .github/workflows/
├── models/                       # *.onnx 产物（不入库，段4 生成）
└── reports/                      # 指标与压测证据（append/覆盖规则见 07_PLAN）
```

权属：docs/contracts/assets = ARCH；docs/00–07 = ARCH（lead 批准后冻结）；qa/ = QA；data/ labeling/ = DATA；src/model|train|export = MODEL；src/serve frontend = SERVE；tests/ scripts/ 由 QA 出题、对应实现方落码；lint/CI 由 SERVE 接线。

## 6. 如何跑验收命令（唯一姿势：Git `sh -c`）

门禁命令一律 bash 风格，**统一经 Git 的 `sh -c "…"` 执行**（裁决 D）：

```bash
sh -c "python -m pytest -q tests/contract/test_onnx_io_contract.py::test_onnx_io_matches_contract"
sh -c "ruff check src tests && mypy src && pytest -q"
```

理由与规则：
1. 本机已验证 `sh` = `C:\Program Files\Git\bin\sh.exe`（Git for Windows 自带，PATH 可用）。
2. 在该 sh 内 `curl / grep / test / tee / wc / python / ruff / mypy / locust / docker` 均实测可用。
3. **不要**在 PowerShell 直接跑 `curl`/`tee`——pwsh 中二者是别名陷阱（`curl`→`Invoke-WebRequest`，参数语义不同），会假绿或报错。
4. 所有 Makefile 目标、QA 门禁脚本、07_PLAN 验收列，一律包 `sh -c "…"`；多命令用 `&&` 串联，任一失败即整条非零退出。
5. 退出码语义：0=过，非 0=不过；证据必须同时落 `qa/evidence/S<N>/`（07_PLAN 每行注明文件名），GATE_LOG.md 记一行时间戳+命令+退出码。

## 7. 依赖与版本基线（requirements 钉死）

```text
Python            == 3.13.14
GNU Make          == 4.4.1（门禁入口 make <target>，内部仍 sh -c）
onnx              == 1.23.2    (IR_VERSION 14, opset 17)
mypy              == 2.4.1
locust            == 2.47.0
onnxruntime       == 1.28.0
torch             == 2.12.0    torchvision == 0.27.0
fastapi           == 0.135.2   uvicorn == 0.42.0   pydantic == 2.13.4
pytest            == 9.0.3     ruff == 0.16.2
numpy             == 2.5.2     Pillow == 10.4.0    jsonschema == 4.26.0
```

平台：Windows 11/10 + Git for Windows（提供 `sh`）。Docker 门禁在 Linux CI 容器内执行（本地有 Docker 时可镜像）。

## 验收标准（可执行检查）

```bash
# 1) 四层结构与依赖方向小节齐全
sh -c "grep -q '^## 1. 四层结构' docs/01_ARCH.md && grep -q '^## 2. 输入张量形状约定' docs/01_ARCH.md && grep -q '^## 3. HAP-Net' docs/01_ARCH.md && grep -q '^## 4. 参数量预算' docs/01_ARCH.md"

# 2) 裁决 A/B/C/D 条款字面在位：五键、images/opset17、qa/ 目录、sh -c 执行
sh -c "for k in total composition light creativity story; do grep -q \"\`$k\`\" docs/01_ARCH.md || exit 1; done && grep -q '(N, 3, 224, 224)' docs/01_ARCH.md && grep -q 'qa/' docs/01_ARCH.md && grep -q 'sh -c' docs/01_ARCH.md && grep -q 'opset 17' docs/01_ARCH.md"

# 3) 版本基线四条硬性（onnx/mypy/locust/Python）+ Make
sh -c "grep -q 'onnx              == 1.23.2' docs/01_ARCH.md && grep -q 'mypy              == 2.4.1' docs/01_ARCH.md && grep -q 'locust            == 2.47.0' docs/01_ARCH.md && grep -q 'Python            == 3.13.14' docs/01_ARCH.md && grep -q 'GNU Make          == 4.4.1' docs/01_ARCH.md"

# 4) 双头输出表含 ranking 头"不进 ONNX"与学生 <10M 预算
sh -c "grep -q 'ranking_logit' docs/01_ARCH.md && grep -q '< 10,000,000' docs/01_ARCH.md"
```
