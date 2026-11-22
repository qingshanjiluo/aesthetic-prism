# Aesthetic Prism · 图片审美评分系统 — PRD（产品需求文档）

| 项 | 值 |
|---|---|
| 文档 ID | D-PRD-00 |
| 归属 | ARCH 起草，lead 批准；全队唯一需求事实源 |
| 状态 | 已冻结 @2026-11-08 03:35（lead 批准，回改须 lead 批准）；修订 CW-S0-01/02 已并入 2026-11-08 03:35+08:00 |
| 关联契约 | C-DATA-01 / C-SERVE-01 / C-EXPORT-01 / C-BRANCH-01（docs/contracts/）；验收条目 = docs/08_ACCEPTANCE.md（S-条目唯一执行源） |

## 1. 目标（Goals）

G1 输入任意 JPEG/PNG 图片，输出 `total` 总分与四维子分 `composition`（构图）/ `light`（光影）/ `creativity`（创意）/ `story`（故事性），0–100；五个评分键全链路同名（裁决 A），成功响应共六字段（5 分数键 + `model`）。
G2 从空仓库推进到 200%：按裁决表 E 九段推进（0/25/50/75/100/125/150/175/200）——架构契约 → 骨架 → 数据标注闭环 → 模型与训练 → 功能全通 → 工程化 → 性能达标 → 实验可视化 → 生产级。
G3 双目标可测：排序质量 pairwise accuracy ≥ 0.68、相关性 Pearson r ≥ 0.70、四子分 MAE ≤ 5.0（0–100 量表）。
G4 服务性能：单图 CPU P50 ≤ 150 ms（目标线）、P95 ≤ 500 ms（硬线）；`/health` 恒 200 可探。
G5 学生模型参数量硬上限 10,000,000（INT8 权重 < 10 MB），教师 ≤ 25,000,000；教师单图 ≤ 200 ms、学生 ≤ 80 ms。

## 2. 非目标（Non-Goals）

N1 不做人脸识别、身份判定、NSFW 检测等合规敏感功能。
N2 不做视频/文本多模态评分；只处理单张位图。
N3 不做在线学习/自动重训练；模型更新走离线重训 + 重导出流程。
N4 不追求开放世界美学理论完备；四维划分即需求边界，不加第五维。
N5 Demo 阶段接口无鉴权（仅限内部部署），不做多租户计费配额体系。
N6 不输出"好看/难看"价值判断，只输出统计一致的评分。

## 3. 用户故事（User Stories）

| ID | 角色 | 故事 | 验收指向 |
|---|---|---|---|
| US1 | 前端用户 | 拖入一张图片，秒级看到五维雷达图与总分 | G1，段4 最小页 / 段8 Demo |
| US2 | API 调用方 | `POST /score` multipart 上传，拿到稳定六字段 JSON（5 分数键 + model）；错误统一 `{"error":{"code","message"}}` | C-SERVE-01；08 S1-03 / S4-01 |
| US3 | 运维 | `GET /health` 返回 `ready/status/model/device/uptime_s`，探针直接可用 | C-SERVE-01 §3.3；08 S1-02 |
| US4 | 数据工程师 | 合成生成器与标注导出共用 DatasetSample，split 由 `split_of(id)` 确定性推导 | C-DATA-01；08 S2-01 / S2-03 |
| US5 | 标注员 | 标注平台四维打分 + 成对偏好，导出即含 `rater_count` | 段2 最小闭环 / 段4 完整功能 |
| US6 | 算法工程师 | 四分支/融合/双头 forward 签名与张量形状有唯一契约，训练与导出不各写各的 | C-BRANCH-01；08 S3-02 |
| US7 | 平台工程师 | `onnx.load` 得输入名 `images`、五输出 `(N,1)`、opset 17，换模型文件不改服务代码 | C-EXPORT-01；08 S4-02 |
| US8 | QA | 每段门禁为 08_ACCEPTANCE 的 S-条目，证据落 `qa/evidence/S<N>/` 可追溯 | 07_PLAN / 08_ACCEPTANCE |

## 契约索引

| 契约 ID | 文件全路径 | 主责实现方 |
|---|---|---|
| C-DATA-01 | docs/contracts/dataset_DatasetSample.md | DATA |
| C-SERVE-01 | docs/contracts/score_api_request_response.md | SERVE |
| C-EXPORT-01 | docs/contracts/onnx_io_names.md | MODEL/SERVE |
| C-BRANCH-01 | docs/contracts/model_branch_interfaces.md | MODEL |

说明：08_ACCEPTANCE S0-03 以本节正则抽 `docs/[\w\-/]+\.md` 全路径校验前三份强制契约四要素（C-BRANCH-01 登记备查）。

## 4. 九个里程碑（0% → 200%，裁决表 E）

| 里程碑 | 段 | 进度 | 内容（完成定义） | 证据产物 |
|---|---|---|---|---|
| M0 | 段0 | 0% | 架构与契约（本文档 + 01/06/07 + contracts 四契约 + 08_ACCEPTANCE），lead 批准 | qa/evidence/S0/ |
| M1 | 段1 | 25% | 骨架：目录、依赖、配置、最小 FastAPI（/health、/score mock）、最小前端页、Makefile、CI 骨架、pytest 冒烟、make dev 起服务 | qa/evidence/S1/ |
| M2 | 段2 | 50% | 数据与标注闭环：合成生成器 ≥200 条、Dataset 类、标注平台最小闭环（成对/四维/黄金题/导出）、JSON 过 schema、dataloader 可读 | qa/evidence/S2/ |
| M3 | 段3 | 75% | 模型与训练闭环：基元层、四分支、融合门控、双头、三阶段训练脚本；门禁 = 前向/反向 + 形状、20 step loss 下降、checkpoint 存取、四维 0–100 | qa/evidence/S3/ |
| M4 | 段4 | 100% | 功能全通：评分头映射完整、单图推理 CLI/API、标注平台完整功能、ONNX 导出、端到端脚本、README 一键复现 | qa/evidence/S4/ |
| M5 | 段5 | 125% | 工程化：Docker+compose、Makefile 全目标、pytest/lint/typecheck、日志、配置校验、错误处理、API 文档、覆盖率报告 | qa/evidence/S5/ |
| M6 | 段6 | 150% | 性能达标：教师→学生蒸馏、通道剪枝、INT8 量化、ONNX Runtime benchmark P50/P95 实测落盘、学生 <10M、pairwise accuracy+Pearson 测试集报告（未达标写原因不许伪造） | qa/evidence/S6/ |
| M7 | 段7 | 175% | 实验与可视化：训练曲线、错误分析、构图热力图、光影直方图、模型卡、数据卡、复现实验配置 | qa/evidence/S7/ |
| M8 | 段8 | 200% | 生产级：一键启动 make demo、API+前端 Demo、压测报告（QPS/延迟/错误率）、主动学习采样脚本、版本管理、QA 验收报告 + FINAL_ACCEPTANCE、已知限制 ≥5 条 + 路线 | qa/evidence/S8/ |

进度语义：M4 = 100% 即功能全通可交付；M5–M7 为工程化/性能/可视化超额推进；M8 = 200% 生产级收口（含主动学习采样脚本、版本管理、已知限制 ≥5 条与后续路线）。

## 5. 可测验收标准（Acceptance Criteria；AC1–AC6 命令路径以 docs/08_ACCEPTANCE.md 条目为唯一执行源）

AC1（数据·段2）合成与标注导出全过 `data/annotations/schema.json` 校验（08 S2-03 同源命令）；DatasetSample 结构由 08 S3-01（`tests/test_data.py::test_dataloader_shape`）与 C-DATA-01 §6 自检覆盖：

```bash
sh -c "python -c \"import json,glob,jsonschema as js;sch=json.load(open('data/annotations/schema.json'));fs=sorted(glob.glob('data/annotations/export_*.json'));assert len(fs)>=1,fs;[js.validate(json.load(open(f)),sch) for f in fs];print('validated',len(fs))\""
```

AC2（模型形状·段3，08 S3-02 路径）四分支池化特征 (N,64)、门控 (N,4) 行和=1、四子分输出 (N,4)、四分支梯度非 None 且 finite；输出域 0–100 = 08 S3-05；键集 = C-BRANCH-01：

```bash
sh -c "pytest -q tests/test_model.py::test_forward_backward_shapes"
```

AC3（训练指标·段6）pairwise accuracy ≥0.68、Pearson r ≥0.70、四子分 MAE ≤5.0（08 S6-03 + S6-06 同源断言）；20-step loss 下降与 checkpoint 存取 = 08 S3-03 / S3-04（段3 门禁）：

```bash
sh -c "python -c \"import json,sys;m=json.load(open('reports/metrics.json'));pa=m['pairwise_accuracy'];pe=m['pearson'];mae=max(float(v) for v in (m.get('mae_per_dim') or m['mae']).values());print('pa',pa,'pe',pe,'mae',mae);sys.exit(0 if pa>=0.68 and pe>=0.70 and mae<=5.0 else 1)\""
```

AC4（蒸馏/量化·段6，08 S6-01 同源命令）学生参数量 <10,000,000；INT8 权重 <10 MB（`reports/params.json` 字段 `student_int8_bytes`）；学生四子分 MAE ≤ 教师 +0.5；复算一致 = 08 S6-04：

```bash
sh -c "python -c \"import onnx,math;m=onnx.load('artifacts/student.onnx');n=sum(math.prod(p.dims) for p in m.graph.initializer if p.dims);print('params=',n);assert n<10_000_000,n\""
```

AC5（导出·段4）输入名 `images`、五输出 `total/composition/light/creativity/story`、opset 17、动态轴仅 N；与 PyTorch 误差 <1e-3 = 08 S4-02；域 0–100 图内映射 + ranking 头不进图 = C-EXPORT-01 裁决 B：

```bash
sh -c "python -c \"import onnx;m=onnx.load('artifacts/model.onnx');ins=[i.name for i in m.graph.input];outs=[o.name for o in m.graph.output];assert ins==['images'],ins;assert m.opset_import[0].version==17;assert outs==['total','composition','light','creativity','story'],outs;print('io-ok',outs)\""
```

AC6（服务·段4/段1 分界）成功体**六字段**（5 分数键 + `model`，`model` 非 mock）全 0–100；错误六档 400/404/413/415/429/500 统一 `{"error":{"code","message"}}` = 08 S4-03 + C-SERVE-01 §3.5；`/health` 200 = 08 S1-02；mock 冒烟 = 08 S1-03：

```bash
sh -c "curl -s -X POST -F image=@assets/sample.png http://127.0.0.1:8000/score | python -c \"import json,sys;d=json.load(sys.stdin);ks=('total','composition','light','creativity','story');assert all(isinstance(d.get(k),(int,float)) and 0<=d[k]<=100 for k in ks),d;assert isinstance(d.get('model'),str) and d['model'] and 'mock' not in d['model'].lower(),d;assert len(d)==6,d;print('ok',d['total'])\""
```

AC7（设施·段5）lint/typecheck/test 零告警零失败（08 S5-02/03/04，Makefile 封装 ruff 0.16.2 / mypy 2.4.1 / pytest 9.0.3）；覆盖率 TOTAL ≥80% = 08 S5-05；compose 一键起服务 = 08 S5-01：

```bash
sh -c "make lint && make typecheck && make test"
```

AC8（性能与压测·段6/段8）locust（2.47.0）QPS ≥5 且失败 =0；P50≤150 ms / P95≤500 ms 与教师 ≤200 ms / 学生 ≤80 ms = 08 S6-02 + 微基准实测落 `reports/`：

```bash
sh -c "locust -f tests/load/locustfile.py --headless -u 8 -t 30s --csv reports/locust && python -c \"import csv,sys;r=list(csv.DictReader(open('reports/locust_stats.csv')))[-1];q=float(r['Requests/s']);f=int(r['Failure Count']);print('qps',q,'fail',f);sys.exit(0 if q>=5 and f==0 else 1)\""
```

AC9（验收·段8）FINAL_ACCEPTANCE 存在且三小节 + 已知限制 ≥5 条 = 08 S8-03/S8-04；端到端人验 = 08 S8-05；lead 签字：

```bash
sh -c "test -f qa/reports/FINAL_ACCEPTANCE.md && grep -q '## 验收结论' qa/reports/FINAL_ACCEPTANCE.md && grep -q '## 已知限制' qa/reports/FINAL_ACCEPTANCE.md"
```

## 错误语义（Error Semantics，需求面）
PRD 级约束（实现细节归 C-SERVE-01 §4，冲突以契约为准）：① 一切 4xx/5xx 响应体必须为 `{"error": {"code": "<非空>", "message": "<非空>"}}`；② 六档状态码 400/404/413/415/429/500 各自触发条件与调用方处理见 C-SERVE-01 §3.5/§4；③ 服务内部异常（模型未就绪/推理失败）归一 500，不得外泄堆栈；④ `/health` 恒 200、以 status 字段表达 degraded，不走错误体。

## 验收标准（本文档自身的可执行检查）

```bash
# 1) 九行里程碑段号与百分比逐字 = 裁决表 E（0/25/50/75/100/125/150/175/200）
sh -c "grep -qE '^\| M0 \| 段0 \| 0% \|' docs/00_PRD.md && grep -qE '^\| M1 \| 段1 \| 25% \|' docs/00_PRD.md && grep -qE '^\| M2 \| 段2 \| 50% \|' docs/00_PRD.md && grep -qE '^\| M3 \| 段3 \| 75% \|' docs/00_PRD.md && grep -qE '^\| M4 \| 段4 \| 100% \|' docs/00_PRD.md && grep -qE '^\| M5 \| 段5 \| 125% \|' docs/00_PRD.md && grep -qE '^\| M6 \| 段6 \| 150% \|' docs/00_PRD.md && grep -qE '^\| M7 \| 段7 \| 175% \|' docs/00_PRD.md && grep -qE '^\| M8 \| 段8 \| 200% \|' docs/00_PRD.md"

# 2) AC1–AC9 九条且每条含 sh -c 可执行命令
sh -c "test $(grep -cE '^AC[1-9]' docs/00_PRD.md) -eq 9 && test $(grep -c 'sh -c \"' docs/00_PRD.md) -ge 9"

# 3) 裁决 A 六字段口径 + 阈值（P50/P95/pairwise/Pearson/MAE）+ M8 补件（主动学习/版本管理/已知限制）
sh -c "grep -q '六字段' docs/00_PRD.md && grep -q 'P50 ≤ 150 ms' docs/00_PRD.md && grep -q 'P95 ≤ 500 ms' docs/00_PRD.md && grep -q 'Pearson r ≥ 0.70' docs/00_PRD.md && grep -q '主动学习采样脚本' docs/00_PRD.md && grep -q '版本管理' docs/00_PRD.md && grep -q '已知限制 ≥5 条' docs/00_PRD.md && grep -q 'US5.*段2' docs/00_PRD.md"

# 4) 残留清零：旧计数口径（正则七.{0}键，防自匹配）= 0、seg<N> = 0、证据目录全为 qa/evidence/S<N>/
sh -c "! grep -qE '七.{0}键' docs/00_PRD.md && ! grep -qE 'seg[0-9]' docs/00_PRD.md && test $(grep -c 'qa/evidence/S[0-8]/' docs/00_PRD.md) -ge 9"
```

