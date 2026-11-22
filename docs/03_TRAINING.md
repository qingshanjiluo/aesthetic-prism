# 03 训练方案（TRAINING）— HAP-Net 三阶段训练 / 蒸馏 / 复现

| 项 | 值 |
|---|---|
| 文档 ID | D-TRAIN-03 |
| 归属 | MODEL 起草（工单 W-0-04），lead 批准；段3 训练与段6 蒸馏评测的唯一执行依据 |
| 状态 | 草案（lead 批准后冻结，回改须 lead 批准） |
| 引用契约 | C-DATA-01（`split_of` 与五键标签，docs/contracts/dataset_DatasetSample.md）、C-EXPORT-01（ONNX IO/opset 17/ranking 头不进图，docs/contracts/onnx_io_names.md）、C-BRANCH-01（四分支/门控/双头张量形状，落地后补充引用） |
| 关联门禁 | 08_ACCEPTANCE：S3-02/03/04/05、S4-02、S6-01~04、S6-06；00_PRD：AC2/AC3/AC4；裁决 G（指标统一线，已并入 §7.5） |

## 1. 输入（数据来源）与输出（产物）

### 1.1 输入

- 数据源：DATA 产出的 DatasetSample JSONL（C-DATA-01 §3，UTF-8、LF）。`labels` 为 `null` 的样本**不得**进入任何训练或评测阶段。
- 划分：`split_of(sample_id)` 确定性推导（C-DATA-01 §2.2，80% train / 10% val / 10% test）。训练只用 `train`，调参与早停只用 `val`，最终报告只在 `test`；任何 val/test 样本混入训练集判 FAIL。
- 输入张量：`images (N,3,224,224)` float32，ImageNet 归一化 `x=(px/255-mean)/std`，`mean=(0.485,0.456,0.406)`，`std=(0.229,0.224,0.225)`，值域 `[-2.1179, 2.6400]`（C-EXPORT-01 §3.1）。
- 配对数据（阶段1）：由指定 split 内 `labels.total` **不同**的样本组成无序对 `(i,j)`；标签并列的对剔除，不进分母。确定性采样：按 `sample_id` 升序枚举全部无序对后 Fisher–Yates 打乱（`seed` 固定），每 epoch 上限 `max_pairs_per_epoch=20000`。

### 1.2 输出（产物清单）

| 产物 | 路径 | 说明 |
|---|---|---|
| 阶段 checkpoint | `checkpoints/stage{1,2,3}_step{step:06d}.pt`、`checkpoints/latest.pt`、`checkpoints/best.pt` | §8 语义 |
| 冒烟 loss 记录 | `qa/evidence/S3/loss.json` | JSON 数组，每步一条，≥20 条（S3-03） |
| 训练指标 | `reports/train_metrics.json` | 每阶段 val 指标 + 阈值判定 |
| 最终评测 | `reports/metrics.json` | 含 `pairwise_accuracy`、`pearson`、`n_test`（S6-03/04；终验线 0.68/0.70 val=test 同线复算，S6-06） |
| 学生工件 | `artifacts/student_int8.pt`、`artifacts/student.onnx`（<10M 参数，S6-01） | 导出协作对齐 C-EXPORT-01 |

### 1.3 错误语义（训练侧）

| # | 触发条件 | 行为 | 对齐 |
|---|---|---|---|
| T1 | 读到非法样本 | 让 `DatasetValidationError` 原样上抛，**不得吞异常继续训练**；门禁判 FAIL | C-DATA-01 §4 通用规则 |
| T2 | split 泄漏（val/test 样本出现在训练对） | 启动期自检直接 `SystemExit`，信息含样本 id | 本文 §2 |
| T3 | loss 非有限（NaN/Inf） | 记录 step 后中止，不写 `latest.pt`，退出码非 0 | 本文 §4/§5 判据 |
| T4 | `--resume-from` 的 checkpoint 键集合不匹配 | `load_state_dict(strict=True)` 抛错上抛，fail fast | S3-04 |
| T5 | 导出时模型非 eval / 含 ranking 头残留 | 按 C-EXPORT-01 E1/E3 抛错 | C-EXPORT-01 §4 |

## 2. 双头与五键（裁决 A / B）

- 双头 dict 键与 API 响应键、ONNX 输出名**逐字同名**：`total`、`composition`、`light`、`creativity`、`story`（顺序固定为该五元组）。
- ranking 头：标量 `ranking_logit r = 100·tanh(z_r)`（∈[-100,100]，与 0–100 分数量纲一致），训练态参与梯度（S3-02），**eval 态不进 ONNX 图**（裁决 B）。
- score 头四维映射：`ŝ_k = 100·σ(z_k)`，k ∈ {composition, light, creativity, story}；图内完成，保证恒 ∈[0,100]（S3-05）。
- 门控与总分：`w = softmax(gate_logits, dim=1) ∈ (N,4)`（行和=1，AC2）；`ŝ_total = clip(Σᵢ wᵢ·ŝᵢ, 0, 100)`；1 位小数舍入归服务层（C-EXPORT-01 §1）。

## 3. 三阶段总览

| 阶段 | 交付段 | 目标 | 损失核心 | 进入条件 | 切换（完成）判据 |
|---|---|---|---|---|---|
| 阶段1 | 段3 | 排序预训练：ranking 头学会成对偏好（含 §9 20-step 冒烟，S3-03 即其门禁样本） | `L_BT`（§4.1） | §4.3 进入 | §4.3 切换 |
| 阶段2 | 段3 末→段4 | score 头回归 + 双头联合微调（全量训练至收敛出 checkpoint） | `L_reg` / `L_joint`（§5.1） | §5.3 进入 | §5.3 切换 |
| 阶段3 | 段6 | 教师→学生蒸馏 + 通道剪枝 + INT8 | `L_distill`（§6.1） | §6.3 进入 | §6.3 切换（含 <10M） |

阶段衔接：阶段1 产出 `best.pt`（按 val pairwise accuracy 取最大）→ 阶段2 以其为初始化继续训练 → 阶段2 产出教师（按 val 四子分 MAE 取最小）→ 阶段3 蒸馏剪枝得学生。三阶段全部在 CPU（torch CPU）上可复现，`seed` 全局一致。

## 4. 阶段1：Bradley-Terry 排序预训练

### 4.1 损失公式

对 batch 内无序对集合 `B`（`y_ij = 1` 当 `y_i > y_j`，否则 0；`y = labels.total`）：

```text
P(i ≻ j) = σ( (r_i − r_j) / τ )            σ 为 logistic sigmoid
L_BT = −(1/|B|) · Σ_{(i,j)∈B} [ y_ij · ln P(i≻j) + (1−y_ij) · ln(1−P(i≻j)) ]
```

- 温度 **τ = 10.0**：`r` 量纲为 0–100 分，τ=10 使 10 分实用差对应 odds ≈ e¹，梯度饱和可控；τ 固定不可学（可 `--tau` 覆盖，改值须回改本文档）。
- 本阶段只更新 backbone + 融合门控 + ranking 头；score 头保持初始化不冻结梯度但 `L_BT` 对其无贡献。

### 4.2 超参表

| 超参 | 值 | 说明 |
|---|---|---|
| steps | 2000 | 固定步数 + 判据早停取 best |
| optimizer | AdamW（β=(0.9,0.999)） | backbone wd=0.01，heads wd=0 |
| lr | 1e-4 | 线性 warmup 100 步 |
| batch（对数） | 64 | 每步 64 对 |
| τ | 10.0 | §4.1 |
| max_pairs_per_epoch | 20000 | §1.1 |
| eval_interval | 200 步 | val 上算 PAcc_rank |
| seed | 42 | 全阶段固定 |

### 4.3 进入与切换判据

- **进入**：20-step 冒烟训练通过（§9，S3-03）；train split 有效样本 ≥64 且可组成 ≥100 个不并列对。
- **切换（阶段1 完成，训练过程判据，非验收线）**：满足其一——① val `PAcc_rank ≥ 0.65`；② 达 2000 步上限取 val `PAcc_rank` 最大的 checkpoint。硬约束：全程无 NaN（T3），且 val 上无并列对时回退以全部可比对计算并在 `train_metrics.json` 标注 `pairwise_val_ties=true`。0.65 是爬坡期过程判据（低于终验线 0.68 属正常设计，裁决 G 确认保留，不称作"验收"）。

## 5. 阶段2：score 头回归 + 双头联合微调

### 5.1 损失公式

回归主损失（0–100 分空间直接回归，均方误差）：

```text
L_reg = (ŝ_total − y_total)² + (1/4) · Σ_{k∈{composition,light,creativity,story}} (ŝ_k − y_k)²
        ŝ_k = 100·σ(z_k)； ŝ_total = clip(Σᵢ wᵢ·ŝᵢ, 0, 100)   （§2，四维 0–100 映射即在此完成）
```

末段双头联合微调（对应 00_PRD M3「联合微调」，并入本阶段收尾）：

```text
L_joint = α · L_BT + (1 − α) · L_reg          α = 0.3（τ 沿用 10.0）
```

### 5.2 超参表

| 超参 | 值 | 说明 |
|---|---|---|
| steps | 5000 | `joint_from=4500` 起用 `L_joint` |
| optimizer | AdamW | backbone wd=0.01 |
| lr | 3e-4 | cosine 衰减至 3e-5 |
| batch | 32 | 图像批 |
| α | 0.3 | 仅 `step ≥ joint_from` 生效 |
| eval_interval | 500 步 | val 四子分 MAE + PAcc |
| seed | 42 | 与阶段1 一致 |

### 5.3 进入与切换判据

- **进入**：阶段1 切换判据已满足，`best.pt` 存在并 `strict=True` 载入。
- **切换（阶段2 完成，教师定版）**：在 **val** 上同时满足——
  1. 四子分 MAE ≤ **5.0**（00_PRD AC3/G3，量表 0–100）；
  2. pairwise accuracy ≥ **0.68**（00_PRD AC3；终验线同值，val 与 test 同线，裁决 G）；
  3. 前向输出五键恒 ∈[0,100]（S3-05 语义，随机 100 批抽测）。
  三者达不齐时不得进入阶段3；取满足 1+2 的 MAE 最小 checkpoint 作教师。

## 6. 阶段3：教师→学生蒸馏 + 通道剪枝 + INT8

### 6.1 损失公式（蒸馏目标函数）

```text
L_distill = λ_gt · L_reg(ŝ_student, y)
          + λ_kd · T² · KL( softmax(z_t / T) ‖ softmax(z_s / T) )     # 四分支 logits 蒸馏
          + λ_bt · L_BT(r_student)                                    # 保持排序能力

λ_gt = 1.0   λ_kd = 1.0   λ_bt = 0.2   T = 4.0   （温度 T 与阶段1 的 τ 不同，勿混用）
```

- **剪枝**：以阶段2 教师权重为底，按通道 `|w|₁` 均值逐层排序，剪枝率 **ρ = 0.40**（保 60% 通道）；每层保底保留 25%，分类/回归末端层不剪。先验预算：`params_student ≈ (1−ρ)² · P_teacher`，教师 ≤25M → ≈9.0M < 10M；**实测 ≥10,000,000 时按 ρ += 0.05 递增重剪（上限 0.60），直到 <10M（S6-01 硬门禁）**。
- **INT8**：FX graph 静态量化，权重量化逐通道对称 int8，激活 8 位；校准集 = 512 张（按 `sample_id` 升序优先取 test、不足回退 val/train 确定性补齐）。量化无梯度，属后处理；判据见 §6.3。

### 6.2 超参表

| 超参 | 值 | 说明 |
|---|---|---|
| steps | 3000 | 剪枝后恢复训练 |
| optimizer | AdamW | 同 §5 |
| lr | 1e-4 | cosine 至 1e-5 |
| batch | 32 | |
| ρ / T / λ | 0.40 / 4.0 / (1.0, 1.0, 0.2) | §6.1 |
| calib | 512 张 | INT8 校准 |
| eval_interval | 250 步 | val MAE + PAcc |
| seed | 42 | |

### 6.3 进入与切换判据

- **进入**：阶段2 切换判据满足；教师 checkpoint 与 eval 态前向可用；校准集可凑满 512 张。
- **切换（阶段3 完成）**：在 **test** 上同时满足——
  1. 学生参数量 < **10,000,000**（S6-01）且 INT8 权重文件 <10 MB（00_PRD AC4）；
  2. 学生四子分 MAE ≤ 教师 + **0.5**（00_PRD AC4/M4，衰减 ≤10% 口径下的子分差判据）；
  3. 量化前后学生在 test 上 `total` MAE 差 ≤ 0.5；
  4. 导出 `artifacts/student.onnx` 通过 C-EXPORT-01 §6 的 IO 核对（输入 `images`、五输出 `(N,1)`、opset 17）。

## 7. 指标定义（精确定义式 + 测试集样本量要求）

记 test 集为 `D_test = {(y_i, ŷ_i)}`，`y = labels.total`，`ŷ` = 模型 `total` 输出（未做 1 位小数舍入），`n = |D_test|`。

### 7.1 pairwise accuracy（成对一致率）

```text
P = { (i,j) | i < j, y_i ≠ y_j }          # 标签并列对剔除，不进分母
PAcc = (1/|P|) · Σ_{(i,j)∈P} [ 1[sign(ŷ_i−ŷ_j) = sign(y_i−y_j)] + 0.5 · 1[ŷ_i = ŷ_j] ]
```

- 预测并列计 0.5；标签并列不计（与 §1.1 配对规则一致）。
- 阶段1 的 `PAcc_rank` 同式，仅以 `r` 替代 `ŷ`。

### 7.2 Pearson 线性相关系数

```text
Pearson = Σᵢ (ŷᵢ−mean(ŷ))·(yᵢ−mean(y)) / sqrt( Σᵢ(ŷᵢ−mean(ŷ))² · Σᵢ(yᵢ−mean(y))² )
```

在 test 全集的 `total` 上计算；`n < 20` 时相关系数不可信——**判 FAIL、不出报告**（S6-03 视为未达成）。

### 7.3 MAE（四子分，00_PRD G3/AC3 判据）

```text
MAE_k = (1/n) · Σᵢ |ŝ_k(i) − y_k(i)|,  k ∈ {composition, light, creativity, story}
报告值 = 四个 MAE_k 的均值（并逐维列出）
```

### 7.4 测试集样本量要求

| 条件 | 处理 |
|---|---|
| `n ≥ 50` | 正常判定，报告无需标注 |
| `20 ≤ n < 50` | **阈值判定照常执行（不放宽）**，`reports/metrics.json` 必须记录 `n_test` 供复核，报告标注「样本量偏小」 |
| `n < 20` | 判 FAIL，不产出达标结论；须扩充数据（DATA 职责）后重跑 |

### 7.5 指标阈值总表（来源逐条标注，禁止静默改数）

| 指标 | 评估集 | 阈值 | 来源 |
|---|---|---|---|
| PAcc_rank | val | ≥0.65 | 本文 §4.3 **训练过程判据（爬坡用，非验收）**，裁决 G 裁定保留 |
| pairwise accuracy（终验线） | **val 与 test 同线** | ≥0.68 | 00_PRD AC3 + 08_ACCEPTANCE S6-03（裁决 G 统一；CW-F 已令 QA 同步 0.68） |
| 四维子分 MAE（终验线） | **val 与 test 同线** | ≤5.0 | 00_PRD AC3 / G3（裁决 G 统一） |
| Pearson 线性相关系数（终验线） | **val 与 test 同线** | ≥0.70 | 08_ACCEPTANCE S6-03（裁决 G 统一；已批准补入 00_PRD AC3，CW-S0-02） |
| 学生参数量 | — | <10,000,000 | 08_ACCEPTANCE S6-01 / 00_PRD G5 |
| 学生 vs 教师四子分 MAE 差 | test | ≤ +0.5 | 00_PRD AC4 / M4 |

> **裁决 G 结论（即刻生效，原差异申报已结案）**：终验线统一为 pairwise accuracy **0.68**、Pearson **0.70**、四维 MAE **≤5.0**，**val 与 test 同线，不存在 val/test 双线**，原「0.70 为 test 最终线」表述已删除。阶段1 的 0.65 是训练过程爬坡判据，不叫验收。来源：00_PRD AC3 + 08_ACCEPTANCE S6-03/S6-06（QA 同步工单 CW-F）。

## 8. checkpoint 保存与恢复语义（对齐 S3-04）

### 8.1 Bundle 结构（`torch.save` 单 dict）

```python
{
  "schema_version": 1,
  "stage": 1 | 2 | 3,          # 阶段号
  "step": int,
  "model": state_dict,          # 含 ranking 头与 score 头；float32，存盘前 detach().cpu()
  "optimizer": state_dict,
  "rng": {"python": ..., "numpy": ..., "torch": ..., "torch_cuda": None},
  "config": {...},              # 本文档全部超参值（可复现的单一事实源）
  "val_metrics": {...},         # 保存时点的 val 指标
}
```

### 8.2 保存语义

- 原子写：先写 `*.pt.tmp` 再 `os.replace` 为正式名；崩溃不得留半截文件。
- 每 `save_interval=200` 步写 `latest.pt`；阶段结束与每次 val 刷新最优时写 `stage{N}_step*.pt` 与 `best.pt`。
- `best` 判据：阶段1 = val PAcc 最大；阶段2 = 满足 §5.3 的 val MAE 最小；阶段3 = 满足 §6.3 的 test 之前的 val `L_distill` 最小（test 只在定版后跑一次）。
- 保留策略：`latest.pt` + `best.pt` + 每阶段最后一个 `stage{N}_step*.pt`，其余按 mtime 保留最近 5 个、滚动清理。

### 8.3 恢复语义（S3-04 硬门禁）

- `load_state_dict(strict=True)`：save→load 后 **state_dict 键集合全等、逐参数数值全等（atol=0）**；任何键缺失/多出/数值差 >0 即测试 FAIL。
- `--resume-from latest.pt`：恢复 `model + optimizer + 三路 RNG`，step 从 bundle 续算；阶段号/超参以 bundle `config` 为准，与命令行不一致时报错退出（防错配复现）。
- 三阶段互不交叉恢复：阶段 N 的 bundle 只能被阶段 N 的 `--resume` 接受；跨阶段只能以「载入 model、重建 optimizer」方式初始化（`--init-from`）。

## 9. 小数据 20-step 冒烟训练配方（对齐 S3-03）

- **目的**：数据读入 → 前向 → 反向 → optimizer.step 全链路贯通，且 loss 呈下降趋势。
- **配方**：train split 内按 `sample_id` 升序取前 8 个有效样本（确定性，不随机）；`batch_size=4`；损失用阶段2 的 `L_reg`（同时覆盖双头与门控反传）；optimizer = Adam `lr=1e-3`（不调度）；`steps=20`；**不加载任何 checkpoint**、`model.train()`。
- **记录**：每步把**总 loss 标量**追加为 JSON 数组写入 `--loss-log`，数组长度 ≥20。
- **判据（S3-03 原文）**：`len(L) >= 20` 且 `mean(L[-5:]) < mean(L[:5])`（后 5 步均值 < 前 5 步均值）。任一不满足判 FAIL，先查数据与 lr，不改判据。
- **命令（与 S3-03 门禁同形，可直接跑）**：

```bash
sh -c "python -m src.train --steps 20 --loss-log qa/evidence/S3/loss.json --seed 42"
```

- 冒烟通过后立即执行 §10 阶段1；冒烟通过本身即 S3-03 证据，S3-02（前向反向形状）与 S3-04（checkpoint 往返）由对应 pytest 门禁兜底。

## 10. 复现命令（Git sh 直接执行；占位参数版，裁决 D）

工作目录：项目根 `aesthetic-prism/`。全部命令为 `sh -c "…"` 形态，参数即 §4–§6 超参表的默认值（命令行缺省时以本文档为准）。

```bash
# 阶段1：Bradley-Terry 排序预训练
sh -c "python -m src.train --stage 1 --steps 2000 --lr 1e-4 --batch-size 64 --tau 10.0 --seed 42 --out checkpoints"

# 阶段2：score 头回归（末 500 步双头联合微调）
sh -c "python -m src.train --stage 2 --steps 5000 --joint-from 4500 --alpha 0.3 --lr 3e-4 --batch-size 32 --seed 42 --out checkpoints"

# 阶段3：蒸馏 + 通道剪枝 + INT8
sh -c "python -m src.distill --teacher checkpoints/best.pt --steps 3000 --lr 1e-4 --batch-size 32 --prune-ratio 0.4 --kd-temperature 4.0 --lambda-kd 1.0 --lambda-bt 0.2 --int8 --calib 512 --seed 42 --out artifacts"

# 最终评测（test 集，产出 reports/metrics.json：pairwise_accuracy / pearson / n_test；终验线 0.68/0.70 val=test 同线，裁决 G）
sh -c "python -m src.eval --split test --ckpt artifacts/student_int8.pt --out reports/metrics.json"

# 恢复训练（从 latest.pt 续训，验证 §8.3 语义）
sh -c "python -m src.train --stage 2 --resume checkpoints/latest.pt --steps 5000 --loss-log reports/resume_loss.json"

# ONNX 导出（对齐 C-EXPORT-01：opset 17、ranking 头不进图；MODEL 段4 实现）
sh -c "python -m src.export.onnx --ckpt checkpoints/best.pt --out artifacts/model.onnx --opset 17"

# 冒烟 20-step（S3-03 门禁原文命令）
sh -c "python -m src.train --steps 20 --loss-log qa/evidence/S3/loss.json --seed 42"
```

复现约定：同 `seed`（42）+ 同数据（JSONL 由 `image_sha256` 锁定）+ 同超参表 ⇒ 同 loss 轨迹（CPU 线程数固定为 4 抑制浮点非确定性）；`reports/train_metrics.json` 写入 git SHA 与以上全部超参。各命令产出对应交付段见 §3「交付段」列（裁决表 E 映射）。

## 11. 与 00_PRD / 08_ACCEPTANCE 的对齐说明（三项申报已由裁决 G / 裁决 E / 裁决 F 结案）

1. **阶段↔段号映射（裁决表 E，已改）**：本文三阶段**算法编号不动**，新增 §3「交付段」列映射交付段——阶段1（BT 首跑 + 20-step 冒烟，S3-03 即其门禁样本）→ **段3**；阶段2（score 回归 + 联合微调全量训练至收敛出 checkpoint）→ **段3 末→段4**（03_TRAINING 是段3 依据文档，训练至收敛属段4）；阶段3（蒸馏 + 剪枝 + INT8）→ **段6**（旧 PRD M3/M4 段义已废）。
2. **阈值结案（裁决 G）**：终验线统一 pairwise accuracy **0.68**、Pearson **0.70**、MAE **≤5.0**，**val 与 test 同线**（来源 00_PRD AC3 + 08_ACCEPTANCE S6-03/S6-06，CW-F 已令 QA 同步 0.68）；原「0.70 test 最终线」双线表述已删除，`grep '0\.70'` 复核仅 Pearson 语境命中。0.65 仅为阶段1 训练过程判据，不称验收。
3. **Pearson 补 PRD（裁决 F，已批准）**：Pearson≥0.70 补入 00_PRD AC3 **已获批准**，由 ARCH 经 CW-S0-02 执行，本文无需改 PRD。

## 验收标准（可执行检查）

```bash
# 1) 文件存在且结构齐全：三阶段小节 + 损失公式 + 超参表 + 切换判据 + 指标 + checkpoint + 冒烟
sh -c "test -f docs/03_TRAINING.md && grep -q '## 4. 阶段1' docs/03_TRAINING.md && grep -q '## 5. 阶段2' docs/03_TRAINING.md && grep -q '## 6. 阶段3' docs/03_TRAINING.md && test $(grep -c '损失公式' docs/03_TRAINING.md) -ge 3 && test $(grep -c '超参表' docs/03_TRAINING.md) -ge 3 && test $(grep -c '切换' docs/03_TRAINING.md) -ge 6"

# 2) 裁决 A 五键逐字在位（word 级匹配）
sh -c "for k in total composition light creativity story; do grep -qw \"$k\" docs/03_TRAINING.md || exit 1; done"

# 3) 旧键零残留（三类旧键全不出现；模式内方括号转义以避免检查命令自身命中）
sh -c "! grep -qiE 'colou?r|ligh[t]ing|detai[l]' docs/03_TRAINING.md"

# 4) 复现与验收命令均为 sh -c 可执行形态（≥7 条复现 + 本节 ≥3 条）
sh -c "test $(grep -c 'sh -c \"' docs/03_TRAINING.md) -ge 10"

# 5) 门禁对齐：S3-03 冒烟命令原文、S3-04 checkpoint 语义、S6-01 学生参数上限字面在位
sh -c "grep -q -- '--steps 20 --loss-log qa/evidence/S3/loss.json' docs/03_TRAINING.md && grep -q '10,000,000' docs/03_TRAINING.md && grep -q 'atol=0' docs/03_TRAINING.md"

# 6) 裁决 G 复核：全文 '0.70' 只出现在 Pearson 语境（pairwise 终验线已统一 0.68，无 val/test 双线）
sh -c "grep -n '0\\.70' docs/03_TRAINING.md | grep -vi 'pearson' && exit 1 || exit 0"

# 7) 裁决 E 复核：§3 表含「交付段」列且三阶段映射 3 / 3-4 / 6 在位
sh -c "grep -q '| 阶段 | 交付段 |' docs/03_TRAINING.md && grep -q '| 阶段1 | 段3 |' docs/03_TRAINING.md && grep -q '| 阶段2 | 段3 末→段4 |' docs/03_TRAINING.md && grep -q '| 阶段3 | 段6 |' docs/03_TRAINING.md"
```
