# mae4 门控归因报告（goal ① · 2026-11-20 · round 5 终局）

## 结论

**mae4 ≤ 5.0 不可达，根因在数据生成器：标签信号被不进入标签公式的随机参数以 1:10.3 的强度比淹没。**

这不是训练问题。网络能过拟合（32 张到 0.009），但过拟合学的是「id 的随机指纹」，不是标签规则。

## 判决实验（决定性，`scripts/goal1_masking.py`）

对同一 `sample_id`，固定 rng 流，只改**一个**参数后重渲染，测像素平均绝对差（0–255 域）：

| 扰动 | 是否进入标签公式 | Δ像素 |
|---|---|---|
| 同 id 重复渲染（基线） | — | **0.0000** |
| `d3` +0.20（composition 权重 0.55） | 是 | 7.616 |
| **`w` +0.20（composition 权重 0.25）** | **是** | **0.959** |
| `g` +0.15（composition 权重 0.20） | 是 | 3.625 |
| `dL` +0.15（light 权重 0.40） | 是 | 7.343 |
| `c` +0.20（light 权重 0.30） | 是 | 4.115 |
| `v` +0.20（light 权重 0.20） | 是 | 2.285 |
| `sigma` +4.0（light 权重 0.10） | 是 | 1.966 |
| **`u` +0.20（creativity 权重 0.50）** | **是** | **1.718** |
| `e` +0.20（creativity 权重 0.30） | 是 | 2.019 |
| `h` +0.20（story 权重 0.20） | 是 | 3.130 |
| **`theta` +0.60（背景渐变方向）** | **否** | **12.103** |
| **`h1` +0.35（色相）** | **否** | **59.653** |
| 标签参数均值 **S** | — | **3.478** |
| 非标签参数均值 **N** | — | **35.878** |
| **S / N** | | **0.097（1 : 10.3）** |

### 译读

像素总变异里，**90% 以上来自完全不参与标签计算的参数**（`theta`、`h1`、每主体独立抽样）。
真正决定标签的参数，在像素上的可测效应只占约 10%。

最刺眼的一对比：
- `w` 是 composition 公式里权重 **0.25** 的主控项，改 0.20 → 像素变 **0.959**
- `h1` 与所有标签**毫无关系**，改 0.35 → 像素变 **59.653**

**62 倍**。这意味着任何模型在这份数据上学「composition」时，看到的主要信息都与目标无关。

## 这一结论解释了此前全部实验（自洽性检验）

| 观察 | 此前归因 | 真实原因 |
|---|---|---|
| 32 张能过拟合到 train 0.009 | （未解释） | 376k 参数足以记住 32 Aliyun 个样本的「theta/h1 指纹」，等价于查表 |
| 1603 张 train 5.70 / val 12.31 gap 6.60 | 过拟合 | 指纹无法跨样本泛化，模型被迫退到均值; train 5.70 是记忆残留 |
| 分辨率 8→224 mae4 全在 12.7±0.1 | （假设详情丢失） | `theta/h1` 的差异在的 8×8 网格上已饱和可见，无细节可捡 |
| 手工统计 12.49 ≈ 网络 11.54 | （假设网络没学到） | 两者都只能在 1:10.3 信噪比里榨同一丁点信号 |
| 降容量到 105k，gap 7.64→1.28 | 降容量有效 | 小模型记不住指纹，直接退到均值，gap 看似小而 VAL 不降 |
| `u` 可观测性扫描"0% 像素相同" | u 可见 | 可见 ≠ 可辨。u 改动引起的像素变化(1.718)被同级随机波动淹没 |
| 参数探针 mae4 = 0.025 | 标签可学 | 用**参数本身**当然准；从像素反推参数才是瓶颈 |

## 此前被推翻的假设（留档，避免重走）

| 轮次 | 假设 | 判决实验 | 结果 |
|---|---|---|---|
| r1 | 数学不可达（线性回归下限 9.84） | — | 论证方法错（非线性公式套线性界） |
| r3 | 特征判别力不足 | 32 张过拟合 train 0.009 | 推翻：容量充足 |
| r4 | 标签参数像素不可恢复（R²<0） | 32 张过拟合 | 推翻：手工特征失败≠网络失败 |
| r5 | 训练量不足 | 2000 步 curve，VAL step600 触底后回升 | 推翻：加步数单调变差 |
| r5 | 容量过大导致过拟合 | small 105k gap 1.28 但 VAL 仍 12+ | 部分推翻：降容量缩小 gap 不降 VAL |
| **r5** | **渲染器信噪比 1:10.3** | **单参数扰动像素差对比** | **成立，解释以上全部** |

## 已确认并修复的两处真实 BUG（与 mae4 独立）

### 1. 评测 split 口径错位 → 指标泄漏

`metric_recheck.py` 按「id 排序序号」切 split，训练侧用契约 `C-DATA-01 §2.2 split_of(sha256(id)[:8]%20)`。旧口径 test 20 个样本在契约口径下 **20/20 全属 train**。

S6–S8 记录的 `pairwise 0.910 / pearson 0.956 / mae4 8.196` 是训练集指标，**全部作废**。

已修：`metric_recheck.py`、`mae4_decompose.py`、`metric_calibrate.py`、`ts_mae.py`

**契约口径真实指标**（旧模型）：val (n=19) mae4 14.2705 / pairwise 0.5497 / pearson 0.1551；test (n=16) mae4 14.7202 / pairwise 0.4622 / pearson 0.0062。

### 2. INT8 校准集混入 val/test

`quantize_int8.py:calib_list()` 同样按序号切分。已经改为 `schema.split_of` 只取 train。

## 数据侧现状

N 从 200 扩到 **2000**（旧 200 个 id 的 `image_sha256` 200/200 完全保留），契约口径 train 1603 / val 208 / test 189。

分布覆盖诊断（`scripts/goal1_coverage.py`，16×16 缩略图 kNN）：
`val→train` 均值 4.744、`test→train` 4.701、`train→train` 4.623，**比值 1.026 / 1.017** —— val/test 与 train 同分布，不是分布外问题。

## 修复路径（唯一）

**改 `data/synthetic.py:_render`，让不进入标签的随机量不再主导像素。**

具体优先级（按 S/N 贡献）：

| 参数 | 当前作用 | 像素影响 | 处置 |
|---|---|---|---|
| `h1`（色相） | 主体颜色 | **59.653** | 由标签参数派生而非独立抽样；或降到固定色板 |
| `theta`（渐变方向） | 背景渐变 | **12.103** | 由 `d3`/`w` 派生（让构图偏移真实改变画面方向性） |
| 每 subject 抖动 | 位置随机偏移 | 与 `e` 耦合 | 幅度随 `e` 线性，且 `e` 本身要可测 |
| `w` | `rng.random() < w` 逐主体抽样 | **0.959** | 改为**整体**左右能量比，可测 |

目标：把 S/N 从 0.097 推到 ≥1.0，使标签信号成为像素变异的主成分。

改完需同步 `docs/02_DATA.md` 的冻结公式说明，重生成数据、重训、复跑 `metric_recheck.py`。

## 本轮产物

脚本（可作为复现入口）：
- `scripts/goal1_masking.py` — **判决实验**：单参数扰动 → 像素差，产出 S/N
- `scripts/goal1_scale.py` — 尺度扫描（8→224 分辨率下 kNN 精度，证明分辨率无关）
- `scripts/goal1_coverage.py` — 分布覆盖诊断（val/test 是否在 train 支撑集外）
- `scripts/goal1_generalize.py` — 训练/验证 gap 曲线（small vs teacher）
- `scripts/goal1_lr_curve.py` — 收敛曲线（含小数据过拟合对照）
- `scripts/goal1_param_probe.py` — 参数探针 mae4 = 0.0251
- `scripts/goal1_pos_probe.py` — 原始参数可恢复性（raw_d3 R²=−0.023 等）
- `scripts/goal1_jitter_sweep.py` — 抖动系数 0.05→0 扫描（无改善）
- `scripts/goal1_gap_experiment.py` — GAP/3×3/4×4 池化对照
- `scripts/goal1_cond_var.py` — 条件方差 / 像素 kNN
- `scripts/goal1_train_vs_val.py` — train/val 对照
- `scripts/goal1_observability.py` — u/e/L 单参数扫描
- `scripts/goal1_v2.py`、`scripts/goal1_v3.py`、`scripts/goal1_train.py`、`scripts/goal1_fast.py`、`scripts/goal1_retrain.py` — 训练器
- `make_own_image.py` — S8-05 自有测试图

报告：`reports/scale_probe.json`、`reports/coverage_probe.json`、`reports/gen_small.json`、`reports/train_val_curve.json`、`reports/position_sensitive_probe.json`、`reports/jitter_sweep.json`、`reports/gap_pooling_experiment.json`、`reports/conditional_variance_probe.json`、`reports/train_vs_val.json`、`reports/contract_split_metrics.json`、`reports/mae4_param_probe.json`、`reports/param_observability.json`

证据：`qa/evidence/S8/G1-*.log`

代码修复：`metric_recheck.py`、`mae4_decompose.py`、`metric_calibrate.py`、`ts_mae.py`、`quantize_int8.py`

## 待办

- [ ] 契约负责人决定：改 `_render` 的信噪比（推荐）或放宽 mae4 门限并记录本报告依据
- [ ] 若改渲染器：调 `h1`/`theta`/`w`/抖动 4 项 → 重生成 → 重训 → 复跑门禁 → 同步文档
