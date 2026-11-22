# Aesthetic Prism · 任务计划与门禁映射（PLAN）

| 项 | 值 |
|---|---|
| 文档 ID | D-PLAN-07 |
| 归属 | ARCH 起草，lead 批准；主责子智能体按行执行，QA 按 08 条目验收 |
| 状态 | 已冻结 @2026-11-08 04:35（lead 批准，CW-S0-04 整表重写已并入，回改须 lead 批准） |
| 关联 | 00_PRD §4 裁决表 E（M0–M8 百分比）、docs/08_ACCEPTANCE.md（S-条目唯一执行源）、06_RISK、C-BRANCH-01 |

## 0. 执行约定

- 任务表七列：任务ID / 依赖 / 主责子智能体 / 产出 / 验收命令 / 证据产物 / 预估工时。
- **验收命令列规则**：一律 `（S-条目ID）sh -c "…"` 式——S-条目 ID 指向 docs/08_ACCEPTANCE.md 原文（QA 按其通用约定执行，含双引号/`$()`/反引号的原文走落盘法），列内 `sh -c` 只放等价简写断言（无管道、无 `$()`，避免破坏表格列）。**每段全部 S-条目 ID 必须被该段任务行逐条覆盖**；无对应 S-条目的行标 `manifest 附加`，不得替代 S-条目。
- 证据产物：全部落 `qa/evidence/S<N>/`（S 编号唯一执行源，QA 所有、实现方只读）；同一段的 S 条目证据文件名沿用 08 条目定义。
- 段义/百分比 = 00_PRD §4 裁决表 E：M0 段0 0% / M1 段1 25% / M2 段2 50% / M3 段3 75% / M4 段4 100% / M5 段5 125% / M6 段6 150% / M7 段7 175% / M8 段8 200%。
- 执行环境：Git `sh -c "…"`（裁决 D，见 01_ARCH §6）；GNU Make 4.4.1 门禁入口；Windows + Python 3.13.14。

S-条目覆盖矩阵（段 → 引用的条目 → 承载任务行）：

| 段 | 08 条目 | 承载行 |
|---|---|---|
| 段0 | S0-01/S0-02/S0-03/S0-04/S0-05 | T-0-01（前三）/ T-0-02（后二） |
| 段1 | S1-01..S1-05 | T-1-02(T-1-03 mock)/T-1-04/T-1-05/T-1-06 + T-1-02 |
| 段2 | S2-01..S2-05 + S2-07/S2-08（W15 承载）+ S3-01（形状引到段2，lead 批准） | T-2-01/T-2-02/T-2-03/T-2-04/T-2-05/T-2-06 |
| 段3 | S3-02..S3-05（S3-01 已引段2） | T-3-01/T-3-02/T-3-03 |
| 段4 | S4-01..S4-04 | T-4-01/T-4-02/T-4-03/T-4-05 |
| 段5 | S5-01..S5-05 | T-5-01/T-5-03/T-5-04 |
| 段6 | S6-01..S6-06 | T-6-01/T-6-03/T-6-04/T-6-05 |
| 段7 | S7-01..S7-04 | T-7-01/T-7-03/T-7-04/T-7-05/T-7-06/T-7-07 |
| 段8 | S8-01..S8-05 | T-8-01/T-8-02/T-8-05 |

### 段0 · M0 · 0%：架构与契约（门禁 S0-01 ~ S0-05）

| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |
|---|---|---|---|---|---|---|
| T-0-01 | 无 | ARCH | docs/ 9 份文档 + contracts/ 4 契约齐套（含 C-BRANCH-01），每份含 `## 验收标准` | （S0-01/S0-02/S0-03）sh -c "test -f docs/00_PRD.md && test -f docs/01_ARCH.md && test -f docs/02_DATA.md && test -f docs/03_TRAINING.md && test -f docs/04_LABELING.md && test -f docs/05_DEPLOY.md && test -f docs/06_RISK.md && test -f docs/07_PLAN.md && test -f docs/08_ACCEPTANCE.md && grep -q '## 验收标准' docs/00_PRD.md && grep -q '## 验收标准' docs/07_PLAN.md && test -f docs/contracts/dataset_DatasetSample.md && test -f docs/contracts/score_api_request_response.md && test -f docs/contracts/onnx_io_names.md && test -f docs/contracts/model_branch_interfaces.md" | qa/evidence/S0/S0-01.log | 6 h |
| T-0-02 | T-0-01 | QA | docs/08_ACCEPTANCE.md 44 条（路径=docs/，QA 所有、实现方只读） | （S0-04/S0-05）sh -c "ls docs/08_ACCEPTANCE.md && grep -qE '^. S0-01 .' docs/08_ACCEPTANCE.md && grep -qE '^. S8-05 .' docs/08_ACCEPTANCE.md" | qa/evidence/S0/S0-04.log | 4 h |

### 段1 · M1 · 25%：骨架（门禁 S1-01 ~ S1-05）

| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |
|---|---|---|---|---|---|---|
| T-1-01 | T-0-01 | ARCH | 目录树 + 依赖清单 + configs/ 配置 schema（输入 = 01_ARCH §5/§7；落地执行归 SERVE） | manifest 附加：sh -c "test -d configs/serve" | qa/evidence/S1/S1-00.manifest.log | 4 h |
| T-1-02 | T-1-01 | SERVE | 最小 FastAPI：GET /health + POST /score mock（六字段 schema = C-SERVE-01，model 标识含 mock） | （S1-02/S1-03）sh -c "curl -s http://127.0.0.1:8000/health" | qa/evidence/S1/S1-02.log | 8 h |
| T-1-03 | T-1-02 | SERVE | 最小前端页 frontend/index.html（调 /score mock 渲染五维+总分骨架） | manifest 附加：sh -c "test -f frontend/index.html" | qa/evidence/S1/S1-00.frontend.log | 6 h |
| T-1-04 | T-1-02 | SERVE | Makefile 含 dev 目标：make dev 一键起服务（契约端口 8000） | （S1-01）sh -c "grep -q '^dev:' Makefile" | qa/evidence/S1/dev.log | 4 h |
| T-1-05 | T-1-04 | SERVE | CI 骨架 .github/workflows/（pytest + ruff lint 双门禁） | （S1-05）sh -c "grep -q pytest .github/workflows/ci.yml && grep -q ruff .github/workflows/ci.yml" | qa/evidence/S1/S1-05.log | 4 h |
| T-1-06 | T-1-04 | SERVE + QA | pytest 冒烟套件全绿；QA 黑盒复跑 S1-01 ~ S1-05 | （S1-04）sh -c "pytest -q" | qa/evidence/S1/S1-04.log | 4 h |

### 段2 · M2 · 50%：数据与标注闭环（门禁 S2-01 ~ S2-05 + S2-07/S2-08 + S3-01 形状引到本段）

| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |
|---|---|---|---|---|---|---|
| T-2-01 | T-0-01 | DATA | 合成生成器 + DatasetSample 导出 data/synthetic/index.json + data/annotations/*.json（≥200 条硬门禁；目标量 ≥5000） | （S2-01/S2-04）sh -c "python -c "import json;d=json.load(open('data/synthetic/index.json'));n=len(d['samples']);print('samples=',n);assert n>=200,n"" | qa/evidence/S2/S2-01.log | 14 h |
| T-2-02 | T-2-01 | DATA | Dataset 类 + DataLoader（C-DATA-01 读入，x=(B,3,224,224) float32、label=(B,4) ∈[0,100]） | （S3-01·引到本段）sh -c "pytest -q tests/test_data.py::test_dataloader_shape" | qa/evidence/S3/S3-01.log | 8 h |
| T-2-03 | T-2-01 | DATA | 标注平台最小闭环 labeling/：四维打分 + 成对偏好 + 黄金题 + 导出（累计条目 ≥10、导出文件 ≥1） | （S2-02/S2-05）sh -c "python -c 'import glob;print(len(glob.glob(\"data/annotations/export_*.json\")))'" | qa/evidence/S2/S2-02.log | 16 h |
| T-2-04 | T-2-03 | DATA | data/raw/SOURCES.csv 版权白名单 + reports/data_bias.json 分布报告（R5/R1 门禁，06_RISK 缓解·事前） | （S2-07）sh -c "test -f data/raw/SOURCES.csv && test -f reports/data_bias.json" | qa/evidence/S2/S2-07.log | 4 h |
| T-2-05 | T-2-02, T-2-03 | QA | 每次导出过 data/annotations/schema.json 校验；抽样 10 条四维标注复核 | （S2-03）sh -c "python -c "import json,glob,jsonschema as js;sch=json.load(open('data/annotations/schema.json'));fs=sorted(glob.glob('data/annotations/export_*.json'));assert len(fs)>=1,fs;[js.validate(json.load(open(f)),sch) for f in fs];print('validated',len(fs))"" | qa/evidence/S2/S2-03.log | 4 h |
| T-2-06 | T-2-03 | DATA | 标注复标质量报告 reports/label_quality.json（复标一致率 ≥0.70、含样本量 n；R3 门禁，06_RISK 缓解·事前③承载） | （S2-08）sh -c "test -f reports/label_quality.json" | qa/evidence/S2/S2-08.log | 2 h |

### 段3 · M3 · 75%：模型与训练闭环（门禁 S3-02 ~ S3-05；S3-01 已引段2）

| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |
|---|---|---|---|---|---|---|
| T-3-01 | T-0-01 | MODEL | 基元层 + 四分支 + 融合门控 + 双头 forward（C-BRANCH-01 实现：六键 dict、门控 softmax 行和=1、四维 0–100） | （S3-02/S3-05）sh -c "pytest -q tests/test_model.py::test_forward_backward_shapes" | qa/evidence/S3/S3-02.log | 16 h |
| T-3-02 | T-3-01 | MODEL | 三阶段训练脚本 docs/03_TRAINING.md + scripts/train.py：ranking(BT) → score → 联合；20 step loss 下降 + checkpoint 存取 | （S3-03/S3-04）sh -c "python -m src.train --steps 20" | qa/evidence/S3/S3-03.log | 14 h |
| T-3-03 | T-3-02 | QA | 形状/收敛独立复测：S3-02/S3-03/S3-04/S3-05 + 过拟合 gap（06_RISK R2 触发信号） | （S3-04）sh -c "pytest -q tests/test_model.py::test_checkpoint_roundtrip && pytest -q tests/test_model.py::test_output_range" | qa/evidence/S3/S3-04.log | 6 h |

### 段4 · M4 · 100%：功能全通（门禁 S4-01 ~ S4-04）

| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |
|---|---|---|---|---|---|---|
| T-4-01 | T-3-02 | MODEL | 评分头映射完整 + 单图推理 CLI scripts/score.py + 全量三阶段训练至收敛出 checkpoint + README 一键复现 | （S4-01）sh -c "python scripts/score.py docs/contracts/assets/example_sample.jpg" | qa/evidence/S4/S4-01.json | 14 h |
| T-4-02 | T-4-01 | MODEL | ONNX 导出 artifacts/model.onnx（opset17、动态轴仅 N、ranking 头不进图 = 裁决 B，C-EXPORT-01）；导出后复制 artifacts/model.onnx → models/hapnet_teacher.onnx（W12 搬运步，make export 内含） | （S4-02）sh -c "python -m src.export.compare --onnx artifacts/model.onnx --tol 1e-3" | qa/evidence/S4/S4-02.log | 8 h |
| T-4-03 | T-4-02 | SERVE | POST /score 接真实 ONNX（六字段、model 非 mock）+ 错误语义六档 400/404/413/415/429/500 统一错误体 | （S4-03）sh -c "curl -s -X POST -F image=@assets/sample.png http://127.0.0.1:8000/score" | qa/evidence/S4/S4-03.log | 10 h |
| T-4-04 | T-2-03, T-4-01 | DATA | 标注平台完整功能（四维 + 成对 + 黄金题 + 批量导出可直接训练）+ 端到端脚本 scripts/e2e.sh | manifest 附加：sh -c "test -f scripts/e2e.sh" | qa/evidence/S4/S4-00.e2e.log | 10 h |
| T-4-05 | T-4-03, T-4-04 | QA | 端到端人验（分数合理性 6 图抽查）+ 段2 回归复跑（S2 全绿 = 回归）+ 错误六档黑盒 | （S4-04·人工复核，命令引 S4-01 复跑）sh -c "grep -q composition qa/evidence/S4/S4-01.json" | qa/evidence/S4/S4-04.md | 4 h |

### 段5 · M5 · 125%：工程化（门禁 S5-01 ~ S5-05）

| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |
|---|---|---|---|---|---|---|
| T-5-01 | T-4-03 | SERVE | docker/Dockerfile + docker-compose.yml（一键构建起服务，/health 200） | （S5-01）sh -c "docker compose up --build -d" | qa/evidence/S5/S5-01.log | 8 h |
| T-5-02 | T-4-03 | SERVE | 日志（结构化 + 请求 ID）+ 配置校验（configs/schema，坏配置拒绝启动）+ 错误处理（C-SERVE-01 §4 归一）+ API 文档（/docs OpenAPI 可访问） | manifest 附加：sh -c "grep -q openapi src/aesthetic_prism/serve/app.py" | qa/evidence/S5/S5-00.docs.log | 8 h |
| T-5-03 | T-5-01 | SERVE | Makefile 全目标接线 lint/typecheck/test/coverage/demo/reproduce + CI 完整；make lint 零告警、make typecheck 零错误 | （S5-02/S5-03）sh -c "make lint && make typecheck" | qa/evidence/S5/S5-02.log | 6 h |
| T-5-04 | T-5-03 | QA | make test 全绿 + 覆盖率 TOTAL 达 08 S5-05 阈值 + 段1-4 回归复跑 | （S5-04/S5-05）sh -c "make test" | qa/evidence/S5/S5-04.log | 4 h |

### 段6 · M6 · 150%：性能达标（门禁 S6-01 ~ S6-06）

| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |
|---|---|---|---|---|---|---|
| T-6-01 | T-4-01 | MODEL | 教师→学生蒸馏 + 通道剪枝（share 主干→窄分支）→ artifacts/student.onnx，参数 <10,000,000 | （S6-01）sh -c "python -c "import onnx,math;m=onnx.load('artifacts/student.onnx');n=sum(math.prod(p.dims) for p in m.graph.initializer if p.dims);print('params=',n);assert n<10_000_000,n"" | qa/evidence/S6/S6-01.log | 14 h |
| T-6-02 | T-6-01 | MODEL | INT8 量化（<10 MB）+ reports/params.json 字段 student_int8_bytes + 量化校准报告 | manifest 附加：sh -c "python -c 'import json;print(json.load(open(\"reports/params.json\"))[\"student_int8_bytes\"])'" | qa/evidence/S6/S6-00.int8.log | 8 h |
| T-6-03 | T-6-01 | SERVE | ONNX Runtime benchmark 实测 P50≤150ms / P95≤500ms 落盘 latency.json（报告写样本量/数据来源/置信限制；未达标写原因不许伪造 = 06_RISK R4） | （S6-02）sh -c "python -m src.bench --n 200 --out qa/evidence/S6/latency.json" | qa/evidence/S6/S6-02.log | 6 h |
| T-6-04 | T-6-03 | QA | 指标复算 pairwise≥0.68 + Pearson≥0.70 + MAE≤5.0（复算值与报告逐键一致 1e-6） | （S6-03/S6-04）sh -c "python -m src.eval --recheck --against reports/metrics.json" | qa/evidence/S6/S6-03.log | 6 h |
| T-6-05 | T-6-04 | QA | 环境记录完整（CPU/GPU 型号、并发数、warmup、数据切分 4 项）+ 四子分 MAE 复算 | （S6-05 人工复核 + S6-06 命令）sh -c "grep -q mae_per_dim reports/metrics.json" | qa/evidence/S6/S6-05.md | 3 h |

### 段7 · M7 · 175%：实验与可视化（门禁 S7-01 ~ S7-04）

| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |
|---|---|---|---|---|---|---|
| T-7-01 | T-6-03 | MODEL | 训练曲线 + 指标对比图（reports/figs/*.png，合计 ≥4 张且每张 >10KB，与下列图共用配额） | （S7-01）sh -c "test -d reports/figs" | qa/evidence/S7/S7-01.log | 4 h |
| T-7-02 | T-7-01 | MODEL | 错误分析报告（低分样本 / 高分歧样本归因，reports/ERROR_ANALYSIS.md） | manifest 附加：sh -c "test -f reports/ERROR_ANALYSIS.md" | qa/evidence/S7/S7-00.error.log | 6 h |
| T-7-03 | T-7-01 | MODEL | 构图热力图（composition 分支归因，2 张 PNG） | （S7-01 计数含本行）sh -c "grep -q composition reports/ERROR_ANALYSIS.md" | qa/evidence/S7/S7-01.log | 4 h |
| T-7-04 | T-7-01 | MODEL | 光影直方图（light 分支，2 张 PNG） | （S7-01 计数含本行）sh -c "grep -q light reports/ERROR_ANALYSIS.md" | qa/evidence/S7/S7-01.log | 4 h |
| T-7-05 | T-6-04 | MODEL | reports/MODEL_CARD.md（用途/训练或数据/指标/局限/复现 ≥4 必要小节） | （S7-02）sh -c "grep -q 用途 reports/MODEL_CARD.md && grep -q 局限 reports/MODEL_CARD.md" | qa/evidence/S7/S7-02.log | 4 h |
| T-7-06 | T-2-05 | DATA | reports/DATA_CARD.md（来源/构成/标注流程/局限 ≥4 必要小节） | （S7-03）sh -c "grep -q 来源 reports/DATA_CARD.md && grep -q 局限 reports/DATA_CARD.md" | qa/evidence/S7/S7-03.log | 4 h |
| T-7-07 | T-7-05, T-7-06 | SERVE + QA | 复现实验配置 configs/repro/ + make reproduce 可复跑且复算与报告一致 1e-6；QA 核对全部七件 | （S7-04）sh -c "make reproduce" | qa/evidence/S7/S7-04.log | 6 h |

### 段8 · M8 · 200%：生产级（门禁 S8-01 ~ S8-05）

| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |
|---|---|---|---|---|---|---|
| T-8-01 | T-5-07, T-7-07 | SERVE | make demo 一键拉起前后端全链路（起服务→/score 200→页可用） | （S8-01）sh -c "grep -q '^demo:' Makefile" | qa/evidence/S8/S8-01.log | 6 h |
| T-8-02 | T-8-01 | SERVE + QA | API+前端 Demo 联调 + locust 2.47 压测报告：QPS≥5、延迟 P50/P95、错误率、样本量、warmup 全列 | （S8-02）sh -c "locust -f tests/load/locustfile.py --headless -u 8 -t 30s --csv qa/evidence/S8/qps" | qa/evidence/S8/S8-02.log | 8 h |
| T-8-03 | T-6-04 | DATA | 主动学习采样脚本 scripts/active_learning.py（按四维方差 + 成对不确定度采样，输出待标清单 data/annotations/active_queue.json，方案原文交付物） | manifest 附加：sh -c "test -f scripts/active_learning.py" | qa/evidence/S8/S8-00.active.log | 6 h |
| T-8-04 | T-8-01 | lead + MODEL | 版本管理：git tag 分段打点（v0.1.0 段0 … v1.0.0 段8）+ 模型/checkpoint 版本登记 reports/versioning.md（方案原文交付物） | manifest 附加：sh -c "test -f reports/versioning.md" | qa/evidence/S8/S8-00.version.log | 4 h |
| T-8-05 | T-8-02, T-8-04 | QA + lead | FINAL_ACCEPTANCE 逐条对照 00_PRD（三小节齐）+ 已知限制 ≥5 条 + 端到端人验 + 项目报告终审 | （S8-03/S8-04/S8-05）sh -c "test -f qa/reports/FINAL_ACCEPTANCE.md" | qa/evidence/S8/S8-03.log | 8 h |

工时合计：**297 h**（段0 10 + 段1 30 + 段2 48 + 段3 36 + 段4 46 + 段5 26 + 段6 37 + 段7 32 + 段8 32）。
串并行：段1→段2→段3 串行；段4 MODEL(4-01/4-02) 与 SERVE(4-03) 并行、DATA(4-04) 与之并行；段5 依赖段4-03；段6 串行（蒸馏→量化→bench→复算→记录）；段7 依赖段6-03/04；段8 依赖段5/段7。QA 各行与其对应实现行串行（先有产物后验收）。

## 验收标准（本文档自身的可执行检查）

```bash
# 1) 九段段标题与百分比行头逐字锚定（0%/25%/50%/75%/100%/125%/150%/175%/200%）
sh -c "grep -q '^### 段0 · M0 · 0%' docs/07_PLAN.md && grep -q '^### 段1 · M1 · 25%' docs/07_PLAN.md && grep -q '^### 段2 · M2 · 50%' docs/07_PLAN.md && grep -q '^### 段3 · M3 · 75%' docs/07_PLAN.md && grep -q '^### 段4 · M4 · 100%' docs/07_PLAN.md && grep -q '^### 段5 · M5 · 125%' docs/07_PLAN.md && grep -q '^### 段6 · M6 · 150%' docs/07_PLAN.md && grep -q '^### 段7 · M7 · 175%' docs/07_PLAN.md && grep -q '^### 段8 · M8 · 200%' docs/07_PLAN.md"

# 2) 七列行头计数 = 9（段0–段8 每段一张任务表）
sh -c "test $(grep -c '^| 任务ID | 依赖 | 主责子智能体 | 产出 | 验收命令 | 证据产物 | 预估工时 |' docs/07_PLAN.md) -eq 9"

# 3) 任务行 ≥25 且每行验收命令列都含 sh -c（行首锚定，不误计本节）
sh -c "test $(grep -cE '^\| T-[0-8]-[0-9]{2} \|' docs/07_PLAN.md) -ge 25 && test $(grep -cE '^\| T-[0-8]-[0-9]{2} .*sh -c' docs/07_PLAN.md) -eq $(grep -cE '^\| T-[0-8]-[0-9]{2} \|' docs/07_PLAN.md)"

# 4) 工时列格式（每任务行 N h 结尾）≥25 + 合计行 = 297 h（防自匹配：行内合计另锚定）
sh -c "test $(grep -cE '^\| T-[0-8]-[0-9]{2} .*[0-9]+ h \|$' docs/07_PLAN.md) -ge 25 && grep -q '工时合计：297 h' docs/07_PLAN.md"
```




