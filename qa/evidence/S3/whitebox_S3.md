# 段3 白盒审查 whitebox_S3.md（QA 独立审查方 · 2026-11-11 08:40 CST）

读面（11 文件）：model/{model,heads,branches,fusion,primitives,params,hapnet,__init__}.py、train/{cli,__init__}.py、src/train.py、tests/test_model.py。
对照契约：C-BRANCH-01（§2/§3/§4）、03_TRAINING（§1.1 划分 / §4.1-4.3 / §5.1-5.3 / §7-§9）、00_PRD G5。

## 3 个具体问题（协议 ≥1 达标）

### S3-P1 · L_reg 四维子项权重实现比 03 §5.1 冻结公式**稀释 4 倍**（最重）

- **契约字面**（03_TRAINING §5.1，冻结）：`L_reg = (ŝ_total − y_total)² + (1/4)·Σ_{k∈4维}(ŝ_k − y_k)²`——per-sample 语义，四维子项 = (1/4)Σ_k e_k²。
- **实现**（cli.py L131）：`(out["total"]-totals).pow(2).mean() + 0.25*(pred_sub-subs).pow(2).mean()`。
- **数值推导**：`(pred_sub-subs)` 形状 (B,4)，`.mean()` = ΣΣ/(4B) → 实现 sub 项 = 0.25·ΣΣ/(4B) = **ΣΣ/(16B)**；契约 batch 化 = (1/B)Σ_i (1/4)Σ_k e² = **ΣΣ/(4B)**。**实现 = 契约 × 1/4**（total 项无误，仅 sub 项差 4 倍）。
- **后果**：score 头四维回归梯度被稀释 4×→ 学习速率实质变慢 → 直击段4/段6 门禁 **S6-06 四维 MAE≤5.0** 与阶段2 切换判据（§5.3 条件 1）达标难度被实现放大；总分项权重相对虚高 4 倍，门控-子分联合解偏移。
- **归 MODEL**；验收点：S6-06（段6 MAE）+ 段4 训练收敛复跑（修复后重训 loss 曲线对比）。

### S3-P2 · val split 从未加载——「val 指标」实为 train 指标（best/切换判据虚标）

- **契约字面**（03 §1.1，冻结）：「训练只用 `train`，调参与早停只用 `val`，最终报告只在 `test`；任何 val/test 样本混入训练集判 FAIL」。
- **实现**：cli.py L655 `ds = _load_real(source_path, split="train")` 是**全文件唯一数据加载点**；L517 `_maybe_eval_and_save` → `metrics = evaluate(model, ds)` 用**同一 train ds**；`_PairCursor`/`_IndexCursor` 也用它。→ `evaluate()` 输出的 `pairwise_accuracy/mae4`（best.pt 选取键、日志里的 "[stageN] eval step"）**全部是训练集指标**，`val` 与 `test` 在训练路径上从未存在。
- **后果**：①§4.3/§5.3 阶段切换判据（val PAcc≥0.68 / val MAE≤5.0）被 train 指标冒名顶替 → 教师"定版"信号虚高；②06_RISK R2（过拟合）的缓解措施①「split_of 确定性切分防调参改划分」被实现绕过——分了却不用；③S3-03 冒烟不受影响（无 val 依赖），但段4「全量训练至收敛出 checkpoint」无真 val 证据。
- **归 MODEL**；验收点：段4 开审时新增 val 分离断言（best.pt 生成路径必须 `split="val"` 且 `n_val≥1`）+ 修复后 stage1/2 复跑日志含 `split=val` 标记。

### S3-P3 · 阶段完成（切换/定版）判据未实现——run_stage 无 03 §4.3/§5.3 语义

- 03 §4.3/§5.3 规定**阶段完成判据**（① val PAcc≥0.65/0.68 ② 达步数上限取最优 ③ §5.3 三条件同时满足才「进入阶段3」「取满足 1+2 的 MAE 最小 checkpoint 作教师」）；实现 `run_stage`（cli L416-594）只做固定步数循环 + `_improved` 单键 best 追踪，**无任何达标判断/阶段完成信号/教师定版产物**（`best.pt` 无 "meets_criteria" 标记，阶段2 结束不校验 §5.3 三条件）。→ 段6 蒸馏的「进入条件」（§6.3「阶段2 切换判据满足」）无机器可读依据，靠人看日志。
- **归 MODEL**（段4 阶段2 定版时一并补）；验收点：段4/段6 开审核 `train_metrics.json` 含判据字段。

## 次要观察（不判问题，记录）

1. fusion.py L44 错误消息报 `row_sums[0]`（第一行）而非 worst 对应行（L41 worst 全行 max）→ 诊断误导，实现 bug 轻微。
2. `_optimizer`（L154-156）把 gate 归 heads（wd=0）；03 §4.2「backbone wd=0.01 heads wd=0」未定义门控归属，且 §4.1「本阶段只更新 backbone+融合门控+ranking 头」把门控与 backbone 并列 → 归属歧义，wd 影响 L2 正则面。
3. `pairwise_accuracy`（L171-188）O(n²) 纯 Python 双循环；n=200 test → 2 万次可接受，n=5000 → 1250 万次评估卡顿（段6 时间预算未覆盖此段）。
4. `_gather_pairs`（L99-110）每步 stage1 64 对全量重解码 128 图无缓存 → 训练 IO 瓶颈（段6 P50/P95 只测推理，训练步时不入 S6-02）。

## 排除项（读码核过，无缺陷）

- **输入验证 E1-E5/E11**：`_validate_images`（model L68-93）rank/通道/空间/batch/dtype/NaN 六查**全部在 compute graph 前**（L150 forward 首行），NaN 定位到具体下标——合 C-BRANCH §4 通用规则「进图前或产出校验时抛」✓。
- **输出校验 E7/E8/E9**：门控行和 `validate_gate_row_sum`（double 精度 atol 1e-4）+ `_check_range` sub/total + 键序 `tuple(out.keys())==expected`（model L161/185/187）✓；`DICT_KEYS_TRAIN`/`SCORE_KEYS` 字面与契约逐字一致。
- **ScoreOnlyWrapper E10**：`model.training` 检查在剥键前（heads L125），test_model L193-199 真断言 ✓；重建 dict 按 SCORE_KEYS 序（L132）→ ONNX 序合 C-EXPORT §3.2 ✓。
- **hapnet.py 双路径 shim**：同签名 re-export（class/keys 同对象），契约钉路径与工单 model.py 两头都满足，非重复逻辑 ✓（第 2 次 S3-01 式命名漂移的自防，比 RW-S2-01 时的处理干净）。
- **stage3 stub exit 2**（cli L638-641）：显式拒绝假跑、非零退出、消息自证段6 范围——合 W-3-01「不伪造」✓。
- **T3 非有限 loss**：`_record` 先记录后中止，main L669 `not math.isfinite(sum(losses))` → return 3、不写 latest.pt（return 在 stage-end 写盘前）✓。
- **checkpoint 原子写**：`*.tmp` + `os.replace`（L251-256）；bundle 八字段与 03 §8.1 逐字一致（test_model L124-125 断言）；`_restore_rng` 三路恢复（L265-268）✓；`_load_bundle(weights_only=False)`——checkpoint 来自本仓训练产物，风险面可接受。
- **resume 语义**：stage 不匹配/ lr 不匹配 SystemExit（L434-437）合 §8.3「与命令行不一致报错退出」✓。
- **进入判据**：stage1 `n<64`/`pool<100` SystemExit（L443-449）、stage2 缺 best.pt SystemExit（L454-462）合 §4.3/§5.3 ✓；`--fixture` 显式 opt-in 防脏数据混入默认路径 ✓。
- **S3-03 冒烟配方**：8 样本序、bs4、Adam 1e-3、train 态、无 checkpoint、loss 数组直写 JSON（L372-413）与 §9 逐项一致；黑盒实测 head5 222.82→tail5 51.53 ✓。
- **ranking_logit = 100·tanh**（heads L110）与 03 §2「r∈[-100,100] 与分数量纲一致」一致，BT loss softplus 形式（L116-123）与 §4.1 等价（log(1+e^{-sign·Δr/τ}) = -log σ(...)）✓。
- **超参常量**：TAU/ALPHA/JOINT_FROM/warmup/eval_interval/LR 表（L38-50）与 03 §4.2/5.2/6.2 逐字一致；`run_stage` 无 stage3 入口（main 拦截）✓。
- **test_model 5 测试真断言**：形状 (B,4) 批量视图、四分支 grad non-None+finite、bit-exact roundtrip（torch.equal atol=0）、100 批范围、E1-E6/E11 消息逐字——非摆设，与 blackbox 实跑 1 passed×4 互证。

## 结论

**具体问题 3 项（S3-P1 权重 4× 偏差最重→S6-06；S3-P2 val 未分离→段4 前置；S3-P3 阶段判据缺失→段4）+ 次要观察 4 + 排除 11**；人工复核 0 项。
协议达标：≥1 具体问题 ✓。
