# MODEL CARD — aesthetic-prism student（HAPNet KD student, ONNX）

## 用途

- 对单张图像输出美学评分：总分 `total` 与四个子维度 `composition / light / creativity / story`（0-100）。
- 服务形态：FastAPI `POST /score`（multipart 上传），ONNX Runtime CPU 推理；输入 1×3×224×224 float32（ImageNet MEAN/STD 归一化）。
- 定位：轻量评分器（147k 参数、FP32 271KB / INT8 275KB 文件），面向延迟敏感场景；**不是通用美学裁判**（见局限）。

## 数据或训练

- 训练数据：`data/synthetic` 200 张程序合成图 + 合成标签（`data/synthetic/index.json`，sha256 去重），split 按 sha256 前 8 hex 确定性切分（train 160 / val 20 / test 20）。
- 教师：HAPNet teacher（377k 参数，`models/hapnet_teacher.onnx`，opset 17，ir_version 14，5 输出）。
- 学生管线：剪枝（stem 20 / trunk 77 / branch_feat_dim 39 / gate_hidden 77 / ranking_hidden 77）→ 三阶段 KD（pairwise → regression+joint → KD finetune），冻结常量 steps=3000、KD_LR 1e-4→1e-5、KD_BATCH=32、TAU=10.0、ALPHA=0.3、joint_from=4200、seed=42。
- 产物：`artifacts/student.onnx`（FP32，575,538 B，sha256_1MB=8fb5c6da…）；`artifacts/student_int8.onnx`（INT8 动态量化，274,625 B，sha256_1MB=4acde982…）。

## 指标

> **⚠️ 2026-11-19 修订：下表数字作废，勿引用。** `bench/metric_recheck.py` 当时按「id 排序序号」切 split，与训练侧契约口径 `C-DATA-01 §2.2 split_of(sha256(id)[:8]%20)` 不同源；旧口径 test 20 个样本在契约口径下 **20/20 全属 train**，故下表是在训练集上测出的。已修脚本。

| 指标 | val (n=20) | test (n=20) | 门限 | 判定 |
|---|---|---|---|---|
| ~~pairwise (total)~~ | ~~0.8158~~ | ~~0.9101~~ | ≥0.68 | **作废** |
| ~~Pearson (total)~~ | ~~0.8564~~ | ~~0.9564~~ | ≥0.70 | **作废** |
| ~~mae4~~ | ~~10.092~~ | ~~8.196~~ | ≤5.0 | **作废** |

**契约口径真实指标**（`reports/contract_split_metrics.json`）：

| 指标 | val (n=19) | test (n=16) | 门限 | 判定 |
|---|---|---|---|---|
| pairwise (total) | **0.5497** | **0.4622** | ≥0.68 | **FAIL** |
| Pearson (total) | **0.1551** | **0.0062** | ≥0.70 | **FAIL** |
| mae4 | **14.2705** | **14.7202** | ≤5.0 | **FAIL** |

教师 `models/hapnet_teacher.onnx` 同口径：val mae4 14.2059 / pair 0.6199 / pearson 0.3793；test 14.7156 / 0.5042 / 0.1240 —— 教师自身也未达标。详见 `reports/MAE4_ROOT_CAUSE.md`。

- 延迟（CPU，100 次，P50/P95）：FP32 10.08 / 44.71 ms（门限 150/500 PASS）；INT8 65.71 / 113.85 ms（小模型上动态量化不收益，primary=fp32）。
- 逐维 MAE 与欠拟合归因：见 `reports/ERROR_ANALYSIS.md`（序号口径，仅供参考）。
- 仿射校准对照：校准后 mae4 val 9.98 / test 8.47（同为序号口径）—— 排除线性尺度可修复假设。

## 局限

1. **三项精度指标全部未达标**（契约口径）：pairwise val 0.5497 / test 0.4622（test 低于随机）、Pearson val 0.1551 / test 0.0062、mae4 val 14.2705 / test 14.7202。当前模型既不可当绝对分值，也不可当排序依据。
2. **历史指标存在泄漏**：S5–S8 期间引用的 pairwise 0.91 / Pearson 0.956 系评测 split 与训练 split 不同源所致，已作废；相关 QA 报告已追加修订节。
3. 训练数据为 200 张合成图（已扩至 2000，见 `reports/DATA_CARD.md`），与真实摄影/艺术图分布存在域差；跨域泛化未验证。
4. 输出动态范围塌缩（pred std < label std）：低分与高分两端区分能力弱（见 ERROR_ANALYSIS §2/§4）。
5. INT8 动态量化在本模型上推理更慢且精度未单独复测，生产建议 FP32。
6. 输入固定 224×224，非正方形图经 BILINEAR 压缩，长宽比信息丢失。
7. ranking 头不进 ONNX 图，服务端不做 pairwise 推理。

## 复现

- 环境：Python 3.13 / onnxruntime 1.28.0 / onnx 1.23.2（完整清单 `reports/env_record.json`）。
- 一键：`make reproduce`（pytest + 契约键自检）；评估复算：`python src/aesthetic_prism/bench/metric_recheck.py`（写 `reports/metric_recheck.json`）。
- 图表复现：`AP_ROOT=<项目根> python src/aesthetic_prism/bench/gen_figs.py` → `reports/figs/*.png`。
- 错误分析复现：`AP_ROOT=<项目根> python src/aesthetic_prism/bench/error_analysis.py` → `reports/error_analysis_data.json`。
- 量化/延迟：`python src/aesthetic_prism/bench/quantize_int8.py` / `bench_latency.py`（CJK 路径经 ASCII 临时目录中转）。
